#!/usr/bin/env python3
"""render-plan.py — a plan's report.json + meta.json + citations.json → self-contained mobile-first index.html.

Usage: render-plan.py --dir <out-dir> [--out <index.html>]

The page is the changes skill's shell (`../changes/assets/template.html`: CSS, the sheet, the
comment system, the map canvas, the feedback footer) with this skill's own styles injected and a
plan's sections in the body. The LLM never writes HTML: it writes report.json (reference/plan-schema.md);
this script quotes the code as it is today by line number, lays out the cards and the sketches, and
replays the reader's notes and threads. Deterministic: same inputs → same HTML.

Every file reference on the page opens the file AS IT IS TODAY — a plan has no diff to open into —
and a planned file that does not exist yet renders as an inert `+` chip.
"""
import argparse, hashlib, html, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHANGES = os.path.normpath(os.path.join(HERE, "..", "..", "changes", "scripts"))
sys.path.insert(0, CHANGES)
from views import mermaid, map_list, render_view                       # noqa: E402  (shared with /describe:changes)
from highlight import language_for, scan, OPEN_NONE                   # noqa: E402
from report_keys import (check_key, finding_key, thread_turns, thread_is_open,   # noqa: E402
                         note_group_key, note_thread_id, check_group_key, check_thread_id,
                         item_group_key, item_thread_id)
sys.path.insert(0, HERE)
from mdlite import md_to_html, inline as md_inline                    # noqa: E402  (the "As written" cards)

E = html.escape
SEV_ORDER = {"critical": 0, "medium": 1, "low": 2}
SEV_WORD = {"critical": "settle first", "medium": "weigh", "low": "note"}
TOUCH_ST = {"new": "added", "changed": "modified", "removed": "deleted", "unchanged": ""}
SKETCH_ST = {"new": "added", "changed": "modified", "removed": "deleted"}
CHECKED_LABEL = {"measured": "measured", "read": "read", "assumed": "assumed"}
SOURCE_LINES = 40         # shown for a path cited without a range, or as context around a cited one
SOURCE_MAX_LINES = 160    # the cap for a cited range plus its context
SOURCE_MAX_BYTES = 2_000_000
LEGEND = ('<div class="legend"><span><i style="background:#1f5a3a"></i>will be new</span>'
          '<span><i style="background:#6b4a12"></i>will change</span><span><i style="background:#6b1f1f"></i>goes</span>'
          '<span><i style="background:#1f3f6b"></i>moves</span><span>⟨/⟩ tap a file to see it as it is today</span></div>')

ROOT = ""          # the repo the plan is about (meta.root)
STORE = {}         # path → {"status", "html"} — the file as it is today, for every existing path the page names
STATUS = {}        # path → added | modified | deleted, from the plan's touches and sketches
CITED = {}         # path → (first, last) — the first line range the plan cites, for the store view

# ---- reading the tree ---------------------------------------------------------------------------
def read_lines(path):
    """The file's lines, or None: absolute paths, paths climbing out of the root, binaries and
    oversized files are refused — a path on the page is reader-facing, never a way to read the disk."""
    if not ROOT or not path or os.path.isabs(path):
        return None
    root = os.path.realpath(ROOT)
    full = os.path.realpath(os.path.join(root, path))
    if not full.startswith(root + os.sep) or not os.path.isfile(full) or os.path.getsize(full) > SOURCE_MAX_BYTES:
        return None
    data = open(full, "rb").read()
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", "replace").splitlines()

def code_rows(lines, path, start, cls, data_f=None, lang=None, cited=(), side="new"):
    """Numbered code lines with the shared comment gutter. `data_f` is what a comment on the line
    will be anchored to — the real path for today's code, `sketch:<id>` for planned lines."""
    lang = lang or language_for(path)
    state, rows = OPEN_NONE, []
    key = data_f or path
    for i, text in enumerate(lines):
        n = start + i
        code, state = scan(text, lang, state)
        c = cls + (" cited" if n in cited else "")
        rows.append(f'<div class="l {c}" data-f="{E(key)}" data-n="{n}" data-side="{side}">'
                    f'<span class="ln" role="button" tabindex="0" title="Comment on {E(key)}:{n}">{n}</span> {code}</div>')
    return "".join(rows)

def source_view(path, first=None, last=None):
    lines = read_lines(path)
    if not lines:
        return None
    if first is None or first > len(lines):
        start, end, first, last = 1, min(len(lines), SOURCE_LINES), None, None
    else:
        start = max(1, first - 4)
        end = min(len(lines), max(last + 4, start + SOURCE_LINES - 1), start + SOURCE_MAX_LINES - 1)
    cited = set(range(first, last + 1)) if first else ()
    rows = code_rows(lines[start - 1:end], path, start, "c", cited=cited)
    note = (f"<b>As it is today.</b> Lines {start}–{end}"
            + (f"; the plan cites {first}–{last}, marked." if first else " — the plan names the file, not a line.")
            + " Nothing here has been changed yet.")
    return (f'<div class="srcnote">{note}</div>'
            f'<div class="diff" data-file="{E(path)}"><div class="hh">{E(path)} lines {start}–{end}'
            f'<span class="hint">💬 tap a line number to comment</span></div><pre>{rows}</pre></div>')

# ---- file references ---------------------------------------------------------------------------
def st_attr(path):
    st = STATUS.get(path)
    return f' data-st="{st}"' if st else ""

def fpath(path, label=None):
    """A full path, clickable to the file as it is today; inert, with a + glyph, for a file the plan will create."""
    if path in STORE:
        return f'<button class="fpath" data-open="{E(path)}"{st_attr(path)} title="Show {E(path)} as it is today">{E(label or path)}</button>'
    st = STATUS.get(path) or "added"
    return f'<span class="fplan" data-st="{E(st)}" title="{E(path)} — planned, not in the tree yet">{E(label or path)}</span>'

def fchip(node):
    f = node.get("file") if isinstance(node, dict) else None
    if not f:
        return ""
    if f in STORE:
        return f'<button class="fchip" data-open="{E(f)}"{st_attr(f)} title="{E(f)} — as it is today">⟨/⟩ {E(os.path.basename(f))}</button>'
    return f'<span class="fplan" data-st="{E(STATUS.get(f) or "added")}" title="{E(f)} — planned, not in the tree yet">{E(os.path.basename(f))}</span>'

# ---- cards -----------------------------------------------------------------------------------------
def plain_block(text):
    return f'<div class="cp-plain">{E(text)}</div>' if text else ""

def steer_card(f, note=None):
    sev = f["severity"]; tags = f.get("tags") or []
    loc = f["file"] + (f':{f["lines"]}' if f.get("lines") else "")
    unit = f' · {E(f["unit"])}' if f.get("unit") else ""
    tags_html = ('<div class="tags">' + "".join(f'<span class="tag">{E(t)}</span>' for t in tags) + "</div>") if tags else ""
    cost = f'<div class="cost"><b>What changing it costs</b>{E(f["cost"])}</div>' if f.get("cost") else ""
    return f'''<div class="card sev-{sev}" data-id="{E(f["id"])}" data-key="{E(finding_key(f))}" data-sev="{sev}" data-tags="{E(" ".join(tags))}">
  <div class="card-h"><span class="tw">▶</span><span class="pill {sev}">{E(f["id"])}</span>
    <div class="title">{E(f["title"])}<span class="steer-word">{SEV_WORD[sev]}</span><small>{E(loc)}{unit}</small></div></div>
  <div class="card-b">
    {plain_block(f.get("plain"))}
    <div class="verify"><b>The question</b>{E(f["question"])}</div>
    <div class="cur-alt"><div class="cur"><b>The plan says</b>{E(f["current"])}</div><div class="alt"><b>The alternative</b>{E(f["alternative"])}</div></div>
    {cost}
    <div class="kv detail"><b>Why a person decides</b>{E(f["why_human"])}</div>
    {tags_html}
    <div class="floc">{fpath(f["file"], loc)}<span class="loc cp" data-loc="{E(loc)}" title="Copy {E(loc)}">⧉</span></div>
    <div class="fb"><button data-t="more">▲ Settle first</button><button data-t="less">▼ Fine as is</button><button data-t="noise" class="danger">✕ Not a decision</button><button data-t="checked">✓ Keep as planned</button></div>
    <div class="fb"><textarea placeholder="Your steer — what should change, or why the plan's answer stands…">{E(note or "")}</textarea></div>
  </div></div>'''

def unit_card(u, i, open_=False):
    acs = []
    for ac in u.get("acs") or []:
        acid = f'<span class="acid">{E(ac["id"])}</span>' if ac.get("id") else ""
        if ac.get("plain"):
            acs.append(f'<li>{acid}<details><summary>{E(ac["text"])}</summary><div class="acp">{E(ac["plain"])}</div></details></li>')
        else:
            acs.append(f'<li>{acid}{E(ac["text"])}</li>')
    touches = "".join(fpath(t["file"]) + (f' <span class="dim">{E(t["note"])}</span>' if t.get("note") else "")
                      for t in u.get("touches") or [])
    meta = []
    if u.get("size"): meta.append(f'<span class="size">{E(u["size"])}</span>')
    if u.get("depends_on"): meta.append(f'<span><b>after</b> {E(", ".join(u["depends_on"]))}</span>')
    if u.get("reviewers"): meta.append(f'<span><b>review</b> {E(u["reviewers"])}</span>')
    if u.get("outside"): meta.append(f'<span><b>needs from outside</b> {E("; ".join(u["outside"]))}</span>')
    return (f'<div class="card{" open" if open_ else ""}" data-id="{E(u["id"])}"><div class="card-h"><span class="tw">▶</span><span class="pill phase">{i}</span>'
            f'<div class="title">{E(u["id"])} · {E(u["title"])}</div></div>'
            f'<div class="card-b">{plain_block(u.get("plain"))}'
            + (f'<div class="kv detail"><b>How</b>{E(u["detail"])}</div>' if u.get("detail") else "")
            + (f'<div class="kv"><b>Acceptance criteria, as written</b><ol class="acs">{"".join(acs)}</ol></div>' if acs else "")
            + (f'<div class="kv"><b>Touches</b><div class="files" data-fgroup="{E(u["id"])}">{touches}</div></div>' if touches else "")
            + (f'<div class="umeta">{"".join(meta)}</div>' if meta else "")
            + "</div></div>")

def sketch_card(k):
    path, st, kid = k["file"], k["status"], k["id"]
    lang = language_for(path)
    parts = []
    before = k.get("before") or {}
    if st in ("changed", "removed") and before:
        if before.get("lines"):
            a, _, b = str(before["lines"]).partition("-")
            a, b = int(a), int(b or a)
            lines = read_lines(path)
            rows = code_rows(lines[a - 1:b], path, a, "d" if st == "removed" else "c") if lines else ""
            head = f"{path} lines {a}–{b}"
        else:
            rows = code_rows((before.get("text") or "").splitlines(), path, 1, "c", data_f=f"sketch:{kid}:today", lang=lang)
            head = path
        parts.append(f'<div class="diff" data-file="{E(path)}"><div class="hh">{E(head)}<span class="tag-today">{"goes" if st == "removed" else "today"}</span>'
                     f'<span class="hint">💬 tap a line number to comment</span></div><pre>{rows}</pre></div>')
    if st in ("changed", "new") and (k.get("after") or "").strip():
        rows = code_rows(k["after"].splitlines(), path, 1, "a", data_f=f"sketch:{kid}", lang=lang)
        parts.append(f'<div class="diff planned" data-file="sketch:{E(kid)}"><div class="hh">{E(path)}<span class="tag-sk">sketch · planned</span>'
                     f'<span class="hint">💬 tap a line number to comment</span></div><pre>{rows}</pre></div>')
    unit = f' · {E(k["unit"])}' if k.get("unit") else ""
    return (f'<div class="card open sk" data-id="{E(kid)}"><div class="card-h"><span class="tw">▶</span><span class="pill phase">{E(kid)}</span>'
            f'<div class="title">{E(k["title"])}<span class="sk-lang">{E(k.get("language") or lang or "")}</span>'
            f'<small>{fpath(path)}{unit} · {E(st)}</small></div></div>'
            f'<div class="card-b">{plain_block(k.get("plain"))}{"".join(parts)}'
            + (f'<div class="sk-note">{E(k["note"])}</div>' if k.get("note") else "") + "</div></div>")

VERBATIM_GROUPS = (("acceptance", "Acceptance criteria", "as-written-acceptance", "criterion", "criteria"),
                   ("questions", "Open questions", "as-written-questions", "question", "questions"))

def code_link(code):
    """An inline code span that names a repository path (`dev/compose.yaml`, `…:12-20`) opens the file as it
    is today, or shows the planned-file chip; any other code span stays code."""
    m = re.match(r"^([\w@.\-]+(?:/[\w@.\-]+)+)(?::\d+(?:-\d+)?)?$", code)
    return fpath(m.group(1), code) if m and (m.group(1) in STORE or m.group(1) in STATUS) else None

def item_loc(v, it):
    if it.get("start"):
        return f'{v["file"]}:{it["start"]}' + (f'-{it["end"]}' if it.get("end") and it["end"] != it["start"] else "")
    return v.get("file") or v.get("source") or ""

def item_card(v, it, note=None):
    """One acceptance criterion or open question: the plan's id and title, its text rendered from the plan's
    Markdown, where it sits in the plan, and a comment box of its own. The comment goes back as an
    `item_note` keyed by the item's content key (report_keys.item_key), so a re-numbered plan does not
    move it onto another item."""
    kind, loc = v["kind"], item_loc(v, it)
    noun = "criterion" if kind == "acceptance" else "question"
    body = md_to_html(it.get("text") or "", code_link)
    short = os.path.basename(loc.split(":", 1)[0]) + (":" + loc.split(":", 1)[1] if ":" in loc else "")
    return (f'<div class="card it it-{kind}{" noted" if note else ""}" data-id="{E(it["id"])}" data-item="{E(it["id"])}" data-key="{E(it["key"])}">'
            f'<div class="card-h"><span class="tw">▶</span><span class="pill it-id">{E(it["label"])}</span>'
            f'<div class="title">{md_inline(it["title"], code_link)}<span class="it-noted" title="You commented on this {noun}">commented</span>'
            f'<small>{E(short)}</small></div></div>'
            f'<div class="card-b">'
            + (f'<div class="md">{body}</div>' if body else "")
            + f'<div class="floc"><span class="it-loc">{E(loc)}</span><span class="loc cp" data-loc="{E(loc)}" title="Copy {E(loc)}">⧉</span></div>'
            + f'<div class="it-fb"><textarea placeholder="Your comment on {E(it["label"])}: what should change, or a question…">{E(note or "")}</textarea></div>'
            + '</div></div>')

def verbatim_band(sections, notes):
    """The plan's own acceptance criteria and open questions (structure.json → verbatim): a list of cards,
    one per criterion or question, each with a comment box of its own.

    The reader approves and answers THESE words, so a card shows the plan's own text, rendered from its
    Markdown — never a paraphrase, never raw syntax. The collector split each section into its items by
    the section's own shape and kept every item's lines, so a card says where it sits in the plan. A
    section without items (a structure.json from before the split) renders whole, still the plan's words.
    """
    if not sections:
        return []
    count = {k: sum(len(v.get("items") or []) for v in sections if v["kind"] == k) for k, *_ in VERBATIM_GROUPS}
    what = " and ".join(x for x in [
        (f'{count["acceptance"]} acceptance criteri{"on" if count["acceptance"] == 1 else "a"}' if count["acceptance"] else ""),
        (f'{count["questions"]} open question{"" if count["questions"] == 1 else "s"}' if count["questions"] else "")] if x)
    lede = (f"The plan's {what}, in its own words. Tap one to read it in full and leave a comment." if what
            else "The plan's own acceptance criteria and open questions, in its own words.")
    out = ['<section id="as-written" class="detail as-written"><h2 class="sec-t part part-v" data-collapsed="0">'
           '<span class="lhs"><span class="tw">▼</span>As written in the plan</span>'
           f'<span class="cnt">{E(lede)} Tap here to fold.</span></h2><div class="detail-b">']
    for kind, name, sid, one, many in VERBATIM_GROUPS:
        group = [v for v in sections if v.get("kind") == kind]
        if not group:
            continue
        n = sum(len(v.get("items") or []) for v in group)
        files = sorted({os.path.basename(v.get("file") or v.get("source") or "") for v in group} - {""})
        cnt = (f'{n} {one if n == 1 else many} · ' if n else "") + "from " + ", ".join(files)
        out.append(f'<section id="{sid}"><h2>{E(name)} <span class="cnt">{E(cnt)}</span></h2>')
        for v in group:
            out.append('<div class="it-sec">')
            if len(group) > 1 and v.get("context"):
                out.append(f'<div class="it-ctx">{md_inline(v["context"], code_link)}</div>')
            if v.get("intro"):
                out.append(f'<div class="it-intro md">{md_to_html(v["intro"], code_link)}</div>')
            items = v.get("items")
            if items is None:
                text = "\n".join((v.get("text") or "").split("\n")[1:])
                out.append(f'<div class="card open"><div class="card-b"><div class="md">{md_to_html(text, code_link)}</div></div></div>')
            intros = {g["title"]: g.get("intro") for g in v.get("groups") or []}
            current, cards = object(), []
            def flush():
                if cards:
                    out.append(f'<div class="it-list" data-fgroup="{E(name)}">' + "".join(cards) + '</div>'); cards.clear()
            for it in items or []:
                if it.get("group") != current:
                    flush(); current = it.get("group")
                    if current:
                        out.append(f'<h3 class="it-group">{md_inline(current, code_link)}</h3>')
                        if intros.get(current):
                            out.append(f'<div class="it-intro md">{md_to_html(intros[current], code_link)}</div>')
                cards.append(item_card(v, it, notes.get(it.get("key"))))
            flush()
            out.append('</div>')
        out.append('</section>')
    out.append('</div></section><!-- /as-written -->')
    return out

def try_card(c):
    steps = "".join(f"<li>{E(s)}</li>" for s in c.get("steps", []))
    where = f'<div class="ck-where">{E(c["where"])}</div>' if c.get("where") else ""
    setup = f'<div class="kv"><b>First</b>{E(c["setup"])}</div>' if c.get("setup") else ""
    expect = f'<div class="verify"><b>You should see</b>{E(c["expect"])}</div>' if c.get("expect") else ""
    unit = f'<small>after {E(c["unit"])}</small>' if c.get("unit") else ""
    return (f'<div class="card" data-id="{E(c["id"])}" data-key="{E(check_key(c))}"><div class="card-h"><span class="tw">▶</span>'
            f'<span class="pill check">{E(c["id"])}</span><div class="title">{E(c["feature"])}{unit}</div></div>'
            f'<div class="card-b">{where}{setup}<ol class="ck-steps">{steps}</ol>{expect}</div></div>')

def grounding_section(cit, note=""):
    """The plan checked against the tree: every path and identifier it names, found or not.

    Mechanical rows plus ONE line of judgement (`report.grounding_note`): the rows say what is
    missing, the analyst says why — a typo, another repository, or a thing the plan creates — so a
    reader does not have to work that out from a list of red paths.
    """
    if not cit:
        return ""
    s = cit.get("summary") or {}
    # Stacked rows, not a table: on a phone a four-column table with breakable cells is squeezed to
    # one character per line. Each entry is its subject on one line and the verdict line under it.
    def row(subject, verdict_cls, verdict, meta_bits=()):
        meta = "".join(f'<span class="gr-b">{m}</span>' for m in meta_bits if m)
        return f'<div class="gr-row"><div class="gr-p">{subject}</div><div class="gr-m">{meta}<span class="gr-v {verdict_cls}">{verdict}</span></div></div>'
    rows = []
    for p in cit.get("paths") or []:
        real = p.get("resolved_to") or p["path"]
        if p.get("exists"):
            if p.get("out_of_range"):
                cls, verdict = "warn", "found · a cited range is past the end (" + ", ".join(f'{a}-{b}' for a, b in p["out_of_range"]) + f", the file has {p.get('lines')} lines)"
            elif p.get("resolved"):
                cls, verdict = "ok", f"found as {E(real)} — cited relative to its row"
            else:
                cls, verdict = "ok", "found"
        elif p.get("candidates"):
            cls, verdict = "warn", "ambiguous — " + E(", ".join(p["candidates"]))
        else:
            cls, verdict = "miss", "not in the tree — a typo, a file in another repository, or one the plan creates"
        ranges = ", ".join(f"{a}-{b}" if a != b else str(a) for a, b in (p.get("ranges") or []))
        rows.append(row(fpath(real, p["path"]) if p.get("exists") else E(p["path"]), cls, verdict,
                        [f'lines {E(ranges)}' if ranges else "", f'{p.get("mentions", 1)}×']))
    for b in cit.get("bare_files") or []:
        if b.get("resolved"):
            rows.append(row(E(b["name"]), "ok", f'found: {fpath(b["resolved"])}', [f'{b.get("mentions", 1)}×']))
        elif b.get("candidates"):
            rows.append(row(E(b["name"]), "warn", f'ambiguous — {len(b["candidates"])} files: ' + E(", ".join(b["candidates"])), [f'{b.get("mentions", 1)}×']))
        else:
            rows.append(row(E(b["name"]), "miss", "no such file", [f'{b.get("mentions", 1)}×']))
    syms = cit.get("symbols") or []
    missing_syms = [x for x in syms if not x.get("files")]
    found_syms = [x for x in syms if x.get("files")]
    sym_rows = "".join(row(f'<code>{E(x["symbol"])}</code>',
                           "ok" if x.get("files") else "miss",
                           (f'in {x["files"]} file{"s" if x["files"] != 1 else ""}: ' + E(", ".join(x.get("sample") or []))
                            + (" …" if x["files"] > len(x.get("sample") or []) else "")) if x.get("files") else "nowhere in the tree",
                           [f'{x.get("mentions", 1)}×'])
                       for x in missing_syms + found_syms[:40])
    more = f'<div class="empty">… and {len(found_syms) - 40} more symbols that are in the tree</div>' if len(found_syms) > 40 else ""
    collapsed = "1" if not missing_syms and not any(not p.get("exists") for p in cit.get("paths") or []) else "0"
    head = f'{s.get("paths_found", 0)}/{s.get("paths", 0)} paths · {s.get("symbols_found", 0)}/{s.get("symbols", 0)} symbols'
    return (f'<section id="grounding"><h2 class="sec-t" data-collapsed="{collapsed}"><span class="lhs"><span class="tw">▼</span>Grounding</span>'
            f'<span class="cnt">{E(head)}</span></h2><div class="card open"><div class="card-b">'
            + (f'<div class="verify"><b>What the check found</b>{E(note)}</div>' if note else "")
            + '<div class="gr-sum">The plan names files and code identifiers; each one was looked up in the repository as it is today. '
              'Green exists. Red is one of three things — a typo in the plan, a file in another repository, or a thing the plan will create. '
              'Skim for red; when everything is green this section arrives collapsed.</div>'
            f'<div class="gr"><div class="gr-h">paths</div>{"".join(rows)}</div>'
            + (f'<div class="gr" style="margin-top:.8rem"><div class="gr-h">symbols — the ones not found first</div>{sym_rows}</div>{more}' if syms else "")
            + '</div></div></section>')

# ---- main ------------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True); ap.add_argument("--out")
    ap.add_argument("--template", default=os.path.join(HERE, "..", "..", "changes", "assets", "template.html"))
    ap.add_argument("--css", default=os.path.join(HERE, "..", "assets", "plan.css"))
    a = ap.parse_args()
    d = a.dir
    report = json.load(open(os.path.join(d, "report.json"), encoding="utf-8"))
    meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8")) if os.path.exists(os.path.join(d, "meta.json")) else {}
    cit = json.load(open(os.path.join(d, "citations.json"), encoding="utf-8")) if os.path.exists(os.path.join(d, "citations.json")) else {}
    structure = json.load(open(os.path.join(d, "structure.json"), encoding="utf-8")) if os.path.exists(os.path.join(d, "structure.json")) else {}
    verbatim = [v for v in (structure.get("verbatim") or []) if isinstance(v, dict) and v.get("text")]
    tpl = open(a.template, encoding="utf-8").read()
    css = open(a.css, encoding="utf-8").read()

    global ROOT
    ROOT = meta.get("root") or ""
    findings = sorted(report["findings"], key=lambda f: (SEV_ORDER[f["severity"]], int(re.sub(r"\D", "", f["id"]) or 0)))
    units = report["units"]; sketches = report.get("sketches") or []

    # Which files the plan will create / change / remove, for the glyph every reference carries.
    for u in units:
        for t in u.get("touches") or []:
            st = TOUCH_ST.get(t.get("status", "changed"), "")
            if st: STATUS[t["file"]] = st
    for k in sketches:
        st = SKETCH_ST.get(k.get("status", "changed"), "")
        if st: STATUS.setdefault(k["file"], st)
    # Which lines the plan cites, so the store shows them marked.
    for p in cit.get("paths") or []:
        if p.get("ranges"): CITED[p.get("resolved_to") or p["path"]] = tuple(p["ranges"][0])
    for f in findings:
        if f.get("lines") and f["file"] not in CITED:
            a1, _, b1 = str(f["lines"]).partition("-"); CITED[f["file"]] = (int(a1), int(b1 or a1))
    # The store: every existing path the page names, as it is today.
    named = {f["file"] for f in findings}
    named |= {t["file"] for u in units for t in (u.get("touches") or [])}
    named |= {k["file"] for k in sketches}
    named |= {p.get("resolved_to") or p["path"] for p in (cit.get("paths") or []) if p.get("exists")}
    named |= {b["resolved"] for b in (cit.get("bare_files") or []) if b.get("resolved")}
    named |= {n["file"] for n in report["graph"].get("nodes", []) if n.get("file")}
    def walk_views(o):
        if isinstance(o, dict):
            if isinstance(o.get("file"), str): named.add(o["file"])
            for x in (o.get("files") or []):
                if isinstance(x, str): named.add(x)
            for v in o.values(): walk_views(v)
        elif isinstance(o, list):
            for v in o: walk_views(v)
    walk_views(report.get("views") or [])
    for path in sorted(named):
        rng = CITED.get(path)
        view = source_view(path, *(rng or (None, None)))
        if view:
            st = STATUS.get(path)
            STORE[path] = {"status": ("will change" if st == "modified" else "goes" if st == "deleted" else "as it is today"), "html": view}

    # Reader input replayed from the report dir (serve.py appends to feedback.jsonl).
    def read_jsonl(name):
        fp = os.path.join(d, name); out = []
        if os.path.exists(fp):
            for l in open(fp, encoding="utf-8"):
                try: out.append(json.loads(l))
                except Exception: pass
        return out
    fb_events = read_jsonl("feedback.jsonl")
    answers_all = [x for x in read_jsonl("answers.jsonl") if x.get("id")]
    keyed = {finding_key(f): f for f in findings}
    card_notes, orphan_notes = {}, {}
    for e in fb_events:
        if e.get("type") != "note" or not e.get("text"): continue
        key = e.get("finding_key")
        if key and key in keyed: card_notes[key] = e
        elif e.get("finding"): orphan_notes[note_group_key(e)] = e
    # Comments on the plan's own acceptance criteria and open questions: the latest per item wins, and
    # one whose item is no longer in the plan stays in the conversation, labelled as such.
    live_items = {it["key"]: (v, it) for v in verbatim for it in (v.get("items") or []) if it.get("key")}
    item_notes = {}
    for e in fb_events:
        if e.get("type") == "item_note" and e.get("text"):
            item_notes[item_group_key(e)] = e
    item_note_text = {k: e["text"] for k, e in item_notes.items() if k in live_items}

    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEV_ORDER}
    slug = meta.get("slug") or os.path.basename(os.path.abspath(d))
    report_id = report.get("report_id") or hashlib.md5((meta.get("repo", "") + "|plan:" + slug).encode()).hexdigest()[:10]
    title = report["title"]
    tags = sorted({t for f in findings for t in f.get("tags", [])})
    gs = (cit.get("summary") or {})
    b = []

    # ---- header ------------------------------------------------------------------------------------
    sub = f'{E(meta.get("repo", ""))} · plan · {E(slug)}' + (f' · at <code>{E(meta["head"])}</code>' if meta.get("head") else "")
    b.append(f'<header class="top"><h1>{E(title)}</h1><div class="sub">{sub}</div>')
    b.append('<div class="chips">'
             + (f'<span class="chip crit"><i class="dot"></i>{counts["critical"]} to settle first</span>' if counts["critical"] else "")
             + (f'<span class="chip med"><i class="dot"></i>{counts["medium"]} to weigh</span>' if counts["medium"] else "")
             + (f'<span class="chip low"><i class="dot"></i>{counts["low"]} to note</span>' if counts["low"] else "")
             + f'<span class="chip"><b>{len(units)}</b> unit{"s" if len(units) != 1 else ""}</span>'
             + f'<span class="chip"><b>{len(sketches)}</b> sketch{"es" if len(sketches) != 1 else ""}</span>'
             + (f'<span class="chip"><b>{gs.get("paths_found", 0)}</b>/{gs.get("paths", 0)} cited paths found</span>' if gs else "")
             + '</div>')
    toc = ['<a href="#summary">Plain words</a>']
    if report.get("views"): toc.append('<a href="#view-1">Pictures</a>')
    if report["graph"].get("nodes"): toc.append('<a href="#map">Map</a>')
    toc.append('<a href="#findings">Steering</a>')
    if verbatim: toc.append('<a href="#as-written">As written</a>')
    if report.get("decisions"): toc.append('<a href="#decisions">Decided</a>')
    toc.append('<a href="#units">Build</a>')
    if sketches: toc.append('<a href="#sketches">Sketches</a>')
    if report.get("invariants"): toc.append('<a href="#same">Stays the same</a>')
    if report.get("assumptions"): toc.append('<a href="#assumptions">Assumptions</a>')
    if report.get("how_to_check"): toc.append('<a href="#check">Try it</a>')
    if report.get("people"): toc.append('<a href="#people">People</a>')
    if cit: toc.append('<a href="#grounding">Grounding</a>')
    if report.get("glossary"): toc.append('<a href="#glossary">Glossary</a>')
    toc.append('<a href="#conversation">Conversation</a>')
    b.append('<div class="toc">' + "".join(toc) + '</div></header>')
    b.append('<div class="howto" id="howto"><span><b>Steer anywhere:</b> select any text and tap <b>Ask about this</b> · tap a '
             '<b>line number</b> beside any line of code, a sketch included · press a verdict or write a note on a steering point · '
             + ('comment on any of the plan\'s acceptance criteria or open questions · ' if verbatim else '')
             + 'or <b>reply</b> to a thread in Conversation. It all comes back to Claude, who drafts the changes to the plan.'
             '</span><button id="howto-x" title="Dismiss">✕</button></div>')
    # Two levels, each fronted by a BAND the small section headings cannot be mistaken for: the
    # 5-minute version (plain words, pictures, steering points), then the detail (its band is below).
    follows = ("The plan's own acceptance criteria and open questions follow, one card each with a comment box, then the detail."
               if verbatim else "The detail follows, one level down.")
    b.append('<div class="part part-1"><span class="part-t">The 5-minute version</span>'
             f'<span class="part-c">plain words · pictures · steering points — enough to judge the direction. {follows}</span></div>')

    # ---- plain words ---------------------------------------------------------------------------------
    scope = report.get("scope") or {}
    scope_html = ""
    if scope.get("in") or scope.get("out"):
        scope_html = ('<div class="scope">'
                      + (f'<div><b>In</b><ul>{"".join(f"<li>{E(x)}</li>" for x in scope.get("in") or [])}</ul></div>' if scope.get("in") else "")
                      + (f'<div><b>Not in this plan</b><ul>{"".join(f"<li>{E(x)}</li>" for x in scope.get("out") or [])}</ul></div>' if scope.get("out") else "")
                      + '</div>')
    b.append('<section id="summary" class="q"><h2>In plain words</h2><div class="card open"><div class="card-b" style="border:0;padding-top:1rem">'
             + (f'<div class="lede"><b>What this plan is for</b>{E(report["intent"])}</div>' if report.get("intent") else "")
             + f'<div class="pw"><b class="pwl">In plain words</b>{E(report["plain"])}</div>'
             + f'<div class="narr">{E(report["summary"])}</div>' + scope_html + '</div></div></section>')

    # ---- pictures before prose -------------------------------------------------------------------
    for i, v in enumerate(report.get("views") or [], 1):
        body = render_view(v, fchip)
        if not body: continue
        b.append(f'<section id="view-{i}" class="view q"><h2>{E(v.get("title") or v["kind"])} <span class="cnt">{E(v["kind"])} · will be</span></h2>'
                 + (f'<div class="narr" style="margin-bottom:.6rem">{E(v["narrative"])}</div>' if v.get("narrative") else "")
                 + LEGEND + f'<div data-fgroup="{E(v.get("title") or v["kind"])}">{body}</div></section>')
    mm = mermaid(report["graph"]) if report["graph"].get("nodes") else ""
    if mm:
        b.append('<section id="map" class="q"><h2>Map — what goes where</h2>'
                 '<div class="legend"><span><i style="background:#1f5a3a"></i>will be new</span><span><i style="background:#6b4a12"></i>will change</span>'
                 '<span><i style="background:#6b1f1f"></i>goes</span><span><i style="background:#2d3748"></i>stays</span><span>→ calls · ⇒ data flows · ⇢ imports/moves</span></div>'
                 '<div class="map static" id="map-canvas" tabindex="0" aria-label="Plan map. Drag to pan, scroll or pinch to zoom, or press the List button for the same graph as text.">'
                 f'<pre class="mermaid">{E(mm)}</pre></div>'
                 '<div class="map-tools hidden"><span class="map-hint">drag to pan · scroll or pinch to zoom</span>'
                 '<span class="map-pct" id="map-pct" aria-live="polite">100%</span>'
                 '<button class="btn" id="map-out" aria-label="Zoom out">−</button><button class="btn" id="map-in" aria-label="Zoom in">+</button>'
                 '<button class="btn" id="map-fit">Fit</button><button class="btn" id="map-read" aria-label="Zoom to a readable text size">Read</button>'
                 '<button class="btn" id="map-list" aria-expanded="false">List</button></div>'
                 f'<div class="map-list" id="map-fallback">{map_list(report["graph"])}</div>'
                 + (f'<div class="narr" style="margin-top:.6rem">{E(report["graph"]["narrative"])}</div>' if report["graph"].get("narrative") else "")
                 + '</section>')

    # ---- steering points -----------------------------------------------------------------------------
    b.append('<section id="findings" class="q"><h2>Steering points <span class="cnt">settle first, then weigh, then note</span></h2>')
    b.append('<div class="filter"><button class="on" data-f="all">All</button><button data-f="critical">Settle first</button><button data-f="medium">Weigh</button><button data-f="low">Note</button>'
             + "".join(f'<button data-f="{E(t)}">{E(t)}</button>' for t in tags) + "</div>")
    if findings:
        b.append('<div data-fgroup="Steering points">')
        b.extend(steer_card(f, (card_notes.get(finding_key(f)) or {}).get("text")) for f in findings)
        b.append("</div>")
    else:
        b.append('<div class="empty">Nothing to steer: every decision in this plan carries a dated ruling. That is a claim about the plan, not a guarantee — the units and sketches below are where to look.</div>')
    b.append("</section>")

    # ---- the plan's own words: its acceptance criteria and open questions, as written --------------
    # Its own band and its own fold, between the 5-minute version and the detail: this is the text the
    # reader approves and answers, so it sits above the analysis of how it will be built.
    b.extend(verbatim_band(verbatim, item_note_text))

    # ---- the detail: everything after the 5-minute version, behind ONE fold ----------------------
    # The page's first part IS the 5-minute version (plain words, pictures, steering points); there is
    # no mode to switch. The rest sits in one section whose band is also its fold (the shell's section
    # collapse): open at render time, one tap shuts it, the choice remembered per repo like every other
    # fold. The band is filled in below, once the sections it fronts have been rendered and counted.
    detail_at = len(b)
    b.append("")
    decisions = report.get("decisions") or []
    if decisions:
        rows = "".join(f'<li>{("<span class=when>" + E(dc["when"]) + "</span>") if dc.get("when") else ""}{E(dc["text"])}'
                       + (f'<span class="by">— {E(dc["by"])}</span>' if dc.get("by") else "")
                       + (f'<span class="by">({E(dc["source"])})</span>' if dc.get("source") else "") + '</li>' for dc in decisions)
        b.append(f'<section id="decisions"><h2 class="sec-t" data-collapsed="{"1" if len(decisions) > 8 else "0"}"><span class="lhs"><span class="tw">▼</span>Decided already</span>'
                 f'<span class="cnt">{len(decisions)} dated ruling{"s" if len(decisions) != 1 else ""} — not up for steering unless a new fact reopens one</span></h2>'
                 f'<div class="card open"><div class="card-b"><ul class="dec">{rows}</ul></div></div></section>')

    # ---- how it will be built ------------------------------------------------------------------------
    b.append(f'<section id="units"><h2 class="sec-t" data-collapsed="0"><span class="lhs"><span class="tw">▼</span>How it will be built</span><span class="cnt">{len(units)} unit{"s" if len(units) != 1 else ""}, in the plan\'s order</span></h2>')
    b.extend(unit_card(u, i, open_=(i == 1)) for i, u in enumerate(units, 1))
    b.append("</section>")

    if sketches:
        b.append(f'<section id="sketches"><h2 class="sec-t" data-collapsed="0"><span class="lhs"><span class="tw">▼</span>Sketches</span>'
                 f'<span class="cnt">{len(sketches)} — the shapes as they are today, then as planned; shapes and signatures, never bodies</span></h2>')
        b.extend(sketch_card(k) for k in sketches)
        b.append("</section>")

    if report.get("invariants"):
        b.append('<section id="same"><h2>What stays the same</h2><div class="card open"><div class="card-b"><ul class="plain-list">'
                 + "".join(f"<li>{E(x)}</li>" for x in report["invariants"]) + "</ul></div></div></section>")
    if report.get("assumptions"):
        b.append('<section id="assumptions"><h2>Assumptions <span class="cnt">and how each was checked</span></h2><div class="card open"><div class="card-b"><ul class="plain-list">'
                 + "".join(f'<li><span class="chk chk-{E(x["checked_by"])}">{E(CHECKED_LABEL.get(x["checked_by"], x["checked_by"]))}</span>{E(x["text"])}'
                           + (f'<span class="note">{E(x["note"])}</span>' if x.get("note") else "") + "</li>" for x in report["assumptions"])
                 + "</ul></div></div></section>")
    checks = report.get("how_to_check") or []
    if checks:
        b.append(f'<section id="check"><h2>How you\'ll try it <span class="cnt">{len(checks)} — once the unit lands</span></h2>')
        b.extend(try_card(c) for c in checks)
        b.append("</section>")
    if report.get("people"):
        b.append('<section id="people"><h2>Who else is involved</h2><div class="card open"><div class="card-b"><ul class="plain-list people">'
                 + "".join(f'<li><b>{E(p["who"])}</b> — {E(p.get("role", ""))}' + (f'<span class="for">for {E(p["needed_for"])}</span>' if p.get("needed_for") else "") + "</li>"
                           for p in report["people"]) + "</ul></div></div></section>")
    b.append(grounding_section(cit, report.get("grounding_note") or ""))
    if report.get("glossary"):
        b.append(f'<section id="glossary"><h2 class="sec-t" data-collapsed="1"><span class="lhs"><span class="tw">▼</span>Glossary</span><span class="cnt">{len(report["glossary"])} terms</span></h2>'
                 '<div class="card open"><div class="card-b"><dl class="gloss">'
                 + "".join(f'<dt>{E(g["term"])}</dt><dd>{E(g["plain"])}</dd>' for g in report["glossary"]) + "</dl></div></div></section>")
    DETAIL_NAMES = {"decisions": "decided already", "units": "how it will be built", "sketches": "sketches", "same": "what stays the same",
                    "assumptions": "assumptions", "check": "how you'll try it", "people": "who else is involved", "grounding": "grounding",
                    "glossary": "glossary"}
    detail_secs = [m.group(1) for s in b[detail_at + 1:] for m in [re.match(r'<section id="([^"]+)"', s)] if m]
    names = ", ".join(DETAIL_NAMES.get(i, i) for i in detail_secs)
    b[detail_at] = ('<section id="detail" class="detail"><h2 class="sec-t part part-2" data-collapsed="0"><span class="lhs"><span class="tw">▼</span>The detail</span>'
                    f'<span class="cnt">everything under the 5-minute version, one level down — {len(detail_secs)} sections: {E(names)}. Tap to fold.</span></h2><div class="detail-b">')
    b.append('</div></section><!-- /detail -->')

    # ---- conversation: comments + answers + notes, same threads the CLI sees ------------------------
    comments = [e for e in fb_events if e.get("type") == "comment" and e.get("id")]
    seen_c, threads = set(), []
    for c in comments:
        if c["id"] in seen_c: continue
        seen_c.add(c["id"]); threads.append(c)
    threads += [{"id": note_thread_id(e), "text": e["text"], "kind": "note",
                 "anchor": {"text": "steer on this point", "section": "steering", "finding": keyed[key]["id"]}}
                for key, e in card_notes.items()]
    threads += [{"id": note_thread_id(e), "text": e["text"], "kind": "note",
                 "anchor": {"text": "note on a steering point that is no longer on the page", "section": "steering (earlier version)", "finding": e.get("finding")}}
                for e in orphan_notes.values()]
    for k, e in item_notes.items():
        if k in live_items:
            v, it = live_items[k]
            noun = "acceptance criterion" if v["kind"] == "acceptance" else "open question"
            an = {"text": f'{it["label"]} · {it["title"]}', "section": f"as written · {noun}", "finding": it["label"]}
            if it.get("start"):
                an.update(file=v["file"], line=it["start"])
        else:
            an = {"text": "comment on an item that is no longer in the plan", "section": "as written (earlier version)", "finding": e.get("item")}
        threads.append({"id": item_thread_id(e), "text": e["text"], "kind": "item_note", "anchor": an})
    ctx_checks = {c["id"]: c for c in checks if c.get("id")}
    ctx_by_key = {check_key(c): c for c in checks}
    check_note_ev = {}
    for e in fb_events:
        if e.get("type") == "check_note" and e.get("text") and e.get("check"):
            check_note_ev[check_group_key(e)] = e
    for e in check_note_ev.values():
        ck = e.get("check_key"); cid = e["check"]
        m = (ctx_by_key.get(ck) if ck else None) or (ctx_checks.get(cid) if not ck else None) or {}
        threads.append({"id": check_thread_id(e), "text": e["text"], "kind": "check_note",
                        "anchor": {"text": m.get("feature") or cid, "section": "try it", "finding": e.get("finding")}})
    def answer_html(t):
        paras = [p for p in re.split(r"\n\s*\n", t.strip()) if p.strip()]
        def inl(x): return re.sub(r"`([^`]+)`", lambda m: "<code>" + E(m.group(1)) + "</code>", E(x)).replace("\n", "<br>")
        return "".join(f"<p>{inl(p)}</p>" for p in paras)
    turns_of = {c["id"]: thread_turns(c["id"], fb_events, answers_all) for c in threads}
    open_threads = sum(1 for c in threads if thread_is_open(turns_of[c["id"]]))
    # NEVER collapsed by default. The changes page shuts a long, fully-answered conversation because
    # two sections follow it; here it is the last section, and an answered thread is exactly what the
    # reader comes back to read — shut, it looked like the answers were not there.
    answered = len(threads) - open_threads
    cnt = " · ".join(x for x in [f'{open_threads} open' if open_threads else "", f'{answered} answered' if answered else ""] if x) or "none yet"
    b.append(f'<section id="conversation"><h2 class="sec-t" data-collapsed="0"><span class="lhs"><span class="tw">▼</span>Conversation</span><span class="cnt">{cnt} — your questions, notes and the answers</span></h2><div id="threads">')
    for c in reversed(threads):
        turns = turns_of[c["id"]]; an = c.get("anchor") or {}
        loc = (an["file"] + (f':{an["line"]}' if an.get("line") else "")) if an.get("file") else ""
        where = f'<span class="loc" data-loc="{E(loc)}">⧉ {E(loc)}</span> ' if loc else ""
        b.append('<div class="thread" id="t-' + E(c["id"]) + '"><div class="anchor">' + where + '“' + E(an.get("text", "")) + '” <small>· ' + E(an.get("section", ""))
                 + ((" · " + E(an["finding"])) if an.get("finding") else "") + '</small></div>'
                 + '<div class="ctext">' + E(c.get("text", "")) + '</div><div class="turns">'
                 + "".join(('<div class="ans"><b>Claude</b>' + answer_html(t["text"]) + '</div>') if t["role"] == "claude"
                           else ('<div class="rply" data-rid="r-' + E(t.get("rid") or "") + '"><b>You</b><p>' + E(t["text"]).replace("\n", "<br>") + '</p></div>')
                           for t in turns)
                 + '</div>' + ('<div class="st open">Open — not answered yet</div>' if thread_is_open(turns) else '')
                 + '<div class="rbox"><textarea class="rin" rows="1" placeholder="Reply to this thread…"></textarea>'
                 + '<button class="rsend" data-thread="' + E(c["id"]) + '">Reply</button></div></div>')
    b.append('</div>' + ('<div class="empty" id="threads-empty">No comments yet. Select a word or sentence anywhere above and tap <b>Ask about this</b>, or tap the line number beside any line of code.</div>' if not threads else '') + '</section>')

    # ---- stores, sheet, data -------------------------------------------------------------------------
    b.append('<script type="application/json" id="file-store">' + json.dumps(STORE).replace("</", "<\\/") + '</script>')
    b.append('<script type="application/json" id="hunk-store">{}</script>')
    b.append('<div class="sheet-bg" id="sheet-bg"></div><div class="sheet" id="sheet"><div class="sheet-h">'
             '<span class="sheet-t" id="sheet-t"></span>'
             '<span class="sheet-nav" id="sheet-nav" hidden><button class="btn" id="sheet-prev" aria-label="Previous file in this group">‹</button><span class="sheet-pos" id="sheet-pos"></span><button class="btn" id="sheet-next" aria-label="Next file in this group">›</button></span>'
             '<button class="btn" id="sheet-x">✕</button></div><div class="sheet-b" id="sheet-b"></div></div>')
    # A link into a fold — the TOC, a hash in the URL, anything on the page — unfolds it first, so a
    # shut fold never swallows a jump. The folds are the detail and, when the plan has them, its own
    # words ("as written"). Deferred to DOMContentLoaded: the shell's script, which defines
    # `dcOpenSection`, runs after this body. Capture phase, so the unfold precedes the browser's own scroll.
    b.append("<script>document.addEventListener('DOMContentLoaded',function(){if(!window.dcOpenSection)return;"
             "var F=['as-written','detail'].map(function(i){return document.getElementById(i);}).filter(Boolean);if(!F.length)return;"
             "var open=function(h,scroll){if(!h||h.length<2||h.charAt(0)!=='#')return;var t=document.getElementById(h.slice(1));if(!t)return;"
             "F.forEach(function(D){if(t!==D&&D.contains(t)){window.dcOpenSection(D.id);if(scroll)t.scrollIntoView();}});};"
             "open(location.hash,true);window.addEventListener('hashchange',function(){open(location.hash,false);});"
             "document.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('a[href^=\"#\"]');if(a)open(a.getAttribute('href'),false);},true);});</script>")
    prior = [{k: v for k, v in e.items() if k in ("ts", "type", "finding", "finding_key", "file", "check", "check_key", "item", "item_key", "text", "undo", "id", "anchor", "thread", "rid")}
             for e in fb_events][-800:]
    data = {"report_id": report_id, "repo": meta.get("repo", ""), "range_label": f"plan · {slug}", "prior": prior,
            "findings": [{"id": f["id"], "severity": f["severity"], "tags": f.get("tags", [])} for f in findings]}
    page = tpl.replace("</style>", css + "\n</style>", 1)
    out = page.replace("__TITLE__", E(title)).replace("__BODY__", "\n".join(b)).replace("__DATA__", json.dumps(data).replace("</", "<\\/"))
    out_path = a.out or os.path.join(d, "index.html")
    open(out_path, "w", encoding="utf-8").write(out)
    print(f"rendered {out_path} ({len(out)//1024} KB): {counts['critical']} settle-first / {counts['medium']} weigh / {counts['low']} note, "
          f"{len(units)} units, {len(sketches)} sketches, {len(STORE)} files openable")

if __name__ == "__main__":
    main()
