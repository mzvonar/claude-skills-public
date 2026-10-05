#!/usr/bin/env python3
"""mdlite.py — a small, safe Markdown → HTML renderer for the plan page's "As written" cards.

A plan's acceptance criteria and open questions are Markdown, and the reader approves and answers
THOSE words — so the page shows them rendered (paragraphs, lists, tables, code, emphasis), never as raw
syntax and never retyped. Stdlib only and deliberately small: a plan's everyday Markdown is the goal,
not every corner of CommonMark. Everything is escaped first and only the tags below are produced, so a
plan cannot put markup into the page; a link opens only when it is http(s).

    md_to_html(text, code_link=None) -> str     block-level: paragraphs, lists, tables, code, quotes
    inline(text, code_link=None) -> str         one line: code, links, emphasis

`code_link(code_text)` may return HTML for an inline code span — the renderer turns a repository path
into a button that opens the file as it is today — or None to keep it as code.
"""
import html, re

E = lambda s: html.escape(s, quote=True)
FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([\w+.-]*)\s*$")
HEAD_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
RULE_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
LIST_RE = re.compile(r"^(?P<ind> *)(?P<mark>[-*+]|\d{1,9}[.)])(?: +(?P<rest>.*)|$)")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
QUOTE_RE = re.compile(r"^\s{0,3}>\s?(.*)$")
PH = ""   # placeholder delimiter: a private-use character no plan's text carries

def _indent(line):
    return len(line) - len(line.lstrip(" "))

def _emphasis(s):
    s = re.sub(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1", r"<strong>\2</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"(?<![\w_])_(?=[^\s_])(.+?)(?<=[^\s_])_(?![\w_])", r"<em>\1</em>", s)
    return re.sub(r"~~(?=\S)(.+?)(?<=\S)~~", r"<del>\1</del>", s)

def _url(url):
    return f'<a href="{E(url)}" target="_blank" rel="noopener noreferrer">{E(url)}</a>'

def inline(text, code_link=None):
    """One line of Markdown. Code spans, links and URLs are cut out first into placeholders, the rest
    is escaped, emphasis is applied to the escaped text, and the placeholders go back in."""
    slots = []
    def keep(h):
        slots.append(h)
        return f"{PH}{len(slots) - 1}{PH}"
    # Code spans FIRST, so nothing inside one is read as Markdown. A plan writes a literal backtick inside
    # a single-backtick span as \` (`**Pinned tag:** \`0.6.0\``); that is the author's intent, so honour it.
    def code(m):
        c = m.group(2)
        if len(m.group(1)) == 1:
            c = c.replace("\\`", "`")
        if c.startswith(" ") and c.endswith(" ") and c.strip():
            c = c[1:-1]
        h = code_link(c) if code_link else None
        return keep(h if h else f"<code>{E(c)}</code>")
    text = re.sub(r"(`+)((?:\\`|(?!\1).)+?)\1(?!`)", code, text)
    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|>~])", lambda m: keep(E(m.group(1))), text)
    def link(m):
        # The label may already hold placeholders (a code span inside it): escape and emphasise it in
        # place, and let the restore loop below resolve them.
        label, url = _emphasis(E(m.group(1))), m.group(2)
        if re.match(r"https?://", url, re.I):
            return keep(f'<a href="{E(url)}" target="_blank" rel="noopener noreferrer">{label}</a>')
        return keep(f'<span class="md-ref" title="{E(url)}">{label}</span>')
    text = re.sub(r"\[([^\]\n]+)\]\(\s*<?((?:[^()\s<>]|\([^()\s]*\))+)>?(?:\s+\"[^\"]*\")?\s*\)", link, text)
    text = re.sub(r"<(https?://[^>\s]+)>", lambda m: keep(_url(m.group(1))), text)
    text = re.sub(r"(?<![\w/\"'=])(https?://[^\s<>()\[\]]*[^\s<>()\[\].,;:!?'\"`*_])", lambda m: keep(_url(m.group(1))), text)
    s = _emphasis(E(text))
    # A slot can hold another slot (a link label with code in it): restore until none is left.
    for _ in range(4):
        if PH not in s:
            break
        s = re.sub(PH + r"(\d+)" + PH, lambda m: slots[int(m.group(1))], s)
    return s.replace(PH, "")

def _cells(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", line)]

def _table(head, rows, cl):
    th = "".join(f"<th>{inline(c, cl)}</th>" for c in _cells(head))
    trs = "".join("<tr>" + "".join(f"<td>{inline(c, cl)}</td>" for c in _cells(r)) + "</tr>" for r in rows)
    return f'<div class="md-table"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'

def _starts_block(line):
    lm = LIST_RE.match(line)
    return bool(FENCE_RE.match(line) or HEAD_RE.match(line) or RULE_RE.match(line) or QUOTE_RE.match(line)
                or (lm and lm.group("rest")))

def _blocks(lines, cl):
    out, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1; continue
        m = FENCE_RE.match(line)
        if m:
            fence, ind, body, j = m.group(2), len(m.group(1)), [], i + 1
            close = re.compile(r"^\s*" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$")
            while j < n and not close.match(lines[j]):
                body.append(lines[j][ind:] if lines[j][:ind].strip() == "" else lines[j]); j += 1
            out.append(f"<pre><code>{E(chr(10).join(body))}</code></pre>"); i = j + 1; continue
        h = HEAD_RE.match(line)
        if h:
            out.append(f'<p class="md-h">{inline(h.group(2), cl)}</p>'); i += 1; continue
        if RULE_RE.match(line):
            out.append("<hr>"); i += 1; continue
        if "|" in line and i + 1 < n and "|" in lines[i + 1] and TABLE_SEP_RE.match(lines[i + 1]):
            j, rows = i + 2, []
            while j < n and lines[j].strip() and "|" in lines[j]:
                rows.append(lines[j]); j += 1
            out.append(_table(line, rows, cl)); i = j; continue
        if QUOTE_RE.match(line):
            j, inner = i, []
            while j < n and lines[j].strip() and QUOTE_RE.match(lines[j]):
                inner.append(QUOTE_RE.match(lines[j]).group(1)); j += 1
            out.append(f"<blockquote>{_blocks(inner, cl)}</blockquote>"); i = j; continue
        lm = LIST_RE.match(line)
        if lm and lm.group("rest") is not None:
            base, ordered = _indent(line), lm.group("mark")[0].isdigit()
            items, cut, j = [], 0, i
            while j < n:
                l = lines[j]
                m2 = LIST_RE.match(l)
                if m2 and m2.group("rest") is not None and _indent(l) == base:
                    if m2.group("mark")[0].isdigit() != ordered:
                        break
                    cut = base + len(m2.group("mark")) + 1
                    items.append([m2.group("rest")]); j += 1; continue
                if not l.strip():
                    k = j + 1
                    while k < n and not lines[k].strip():
                        k += 1
                    nxt = LIST_RE.match(lines[k]) if k < n else None
                    if k < n and (_indent(lines[k]) > base or (nxt and nxt.group("rest") is not None and _indent(lines[k]) == base)):
                        items[-1].append(""); j += 1; continue
                    break
                if _indent(l) > base:
                    items[-1].append(l[cut:] if l[:cut].strip() == "" else l.strip()); j += 1; continue
                # A line flush with the marker right after the item's text continues its paragraph.
                if items[-1][-1].strip() and not _starts_block(l):
                    items[-1].append(l.strip()); j += 1; continue
                break
            tag = "ol" if ordered else "ul"
            first = int(lm.group("mark")[:-1]) if ordered else 1
            lis = []
            for it in items:
                inner = _blocks(it, cl)
                # A tight item is one paragraph: drop its <p> so the list is not double-spaced.
                if inner.startswith("<p>") and inner.endswith("</p>") and inner.count("<p>") == 1:
                    inner = inner[3:-4]
                lis.append(f"<li>{inner}</li>")
            out.append(f'<{tag}{f" start={chr(34)}{first}{chr(34)}" if ordered and first != 1 else ""}>{"".join(lis)}</{tag}>')
            i = j; continue
        j, para = i, []
        while j < n and lines[j].strip() and not (j > i and _starts_block(lines[j])):
            para.append(lines[j].strip()); j += 1
        out.append(f"<p>{inline(' '.join(para), cl)}</p>"); i = j
    return "".join(out)

def md_to_html(text, code_link=None):
    """A block of Markdown as HTML: every character escaped, only known tags produced."""
    return _blocks((text or "").expandtabs(4).split("\n"), code_link)
