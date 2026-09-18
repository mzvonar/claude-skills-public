#!/usr/bin/env python3
"""Syntax highlighting for the code shown in the report — at RENDER time, stdlib only.

Why not a CDN highlighter. The page loads exactly one remote thing (mermaid) and degrades to a text
list without it. A second network dependency would put the readability of every diff behind a
request that a phone on a train, a locked-down corporate network or an air-gapped review box may not
complete. Highlighting here means the spans are in the HTML: there is nothing to fail when the page
is opened, and `file://` works as well as the server does.

What this is NOT. It is a lexer, not a parser: comments, strings, numbers, keywords, and two cheap
identifier shapes. It does not resolve types, and it will colour a keyword used as a property name.
That is the right trade for a diff, where the reader wants the shape of the line at a glance and has
the real file for anything more.

The honest limitation, stated because it is invisible: a hunk starts mid-file, so a block comment or
template literal that OPENED before the hunk is not known to be open. State is carried line to line
WITHIN a hunk (`scan` takes and returns it), which fixes the common multi-line case; across the hunk
boundary the first lines of an already-open block are highlighted as code. Nothing can fix that
without the whole file, and reading the whole file to colour six lines is not worth it.
"""

from html import escape as _esc

__all__ = ["language_for", "scan", "OPEN_NONE"]

# ── state carried between lines of one hunk ────────────────────────────────────────────────────
OPEN_NONE = None  # not inside anything
# otherwise: ("block", close_delim) | ("str", quote, allows_newline)


class _Spec:
    __slots__ = ("line", "block", "quotes", "raw3", "keywords", "types", "case_kw", "regex")

    def __init__(self, line=(), block=(), quotes="'\"", raw3=(), keywords=(), types=(), case_kw=True,
                 regex=False):
        self.line = tuple(line)          # line-comment starters
        self.block = tuple(block)        # (open, close) pairs
        self.quotes = quotes             # single-line string delimiters
        self.raw3 = tuple(raw3)          # delimiters that may span lines (''' """ `)
        self.keywords = frozenset(keywords)
        self.types = frozenset(types)
        self.case_kw = case_kw           # False → match keywords case-insensitively (SQL)
        self.regex = regex               # language has /…/ literals (JS family only)


# After one of these, a `/` opens a REGEX; after anything else it is division. This is the standard
# heuristic and it is not perfect — no lexer can settle `a /b/ c` without parsing — but the failure
# it prevents is loud and common (`/^[A-Za-z0-9_-]+$/` lexed as code, colouring `Za` as a type and
# `9_` as a number) while the failure it introduces is a divisor tinted like a string.
_RE_OK_AFTER = set("(,=:[!&|?{};+-*%~^<>") | {""}
_RE_OK_WORDS = frozenset("return typeof instanceof in of case delete void new do else yield await".split())


_C_STR = "'\"`"

_JS_KW = """await async break case catch class const continue debugger default delete do else enum export
extends false finally for from function get if implements import in instanceof interface let new null of
package private protected public readonly return satisfies set static super switch this throw true try
type typeof undefined var void while with yield as declare abstract infer keyof namespace override""".split()

_PY_KW = """and as assert async await break class continue def del elif else except False finally for from
global if import in is lambda None nonlocal not or pass raise return True try while with yield match case""".split()

_KT_KW = """abstract actual annotation as break by catch class companion const constructor continue crossinline
data delegate do dynamic else enum expect external false field file final finally for fun get if import in
infix init inline inner interface internal is it lateinit noinline null object open operator out override
package param private property protected public receiver reified return sealed set setparam super suspend
tailrec this throw true try typealias val var vararg when where while""".split()

_GO_KW = """break case chan const continue default defer else fallthrough for func go goto if import interface
map package range return select struct switch type var nil true false""".split()

_RS_KW = """as async await break const continue crate dyn else enum extern false fn for if impl in let loop
match mod move mut pub ref return self Self static struct super trait true type unsafe use where while""".split()

_SQL_KW = """add all alter and any as asc begin between by cascade case cast check column commit constraint
create cross default delete desc distinct drop else end exists foreign from full group having if in index
inner insert intersect into is join key left like limit not null offset on or order outer primary references
rename replace return returning right rollback select set table then to union unique update using values
view when where with""".split()

_SH_KW = """case do done elif else esac fi for function if in local return select then time until while
export readonly declare eval exec exit set shift source trap unset""".split()

_TYPES = """string number boolean object symbol bigint unknown never any void Array Promise Record Map Set
Date RegExp Error Int Long Float Double Boolean String List Map Set Unit Any Nothing""".split()

_SPECS = {
    "ts": _Spec(("//",), (("/*", "*/"),), _C_STR, ("`",), _JS_KW, _TYPES, regex=True),
    "py": _Spec(("#",), (), "'\"", ('"""', "'''"), _PY_KW, _TYPES),
    "kt": _Spec(("//",), (("/*", "*/"),), "'\"", ('"""',), _KT_KW, _TYPES),
    "java": _Spec(("//",), (("/*", "*/"),), "'\"", (), _KT_KW, _TYPES),
    "go": _Spec(("//",), (("/*", "*/"),), _C_STR, ("`",), _GO_KW, _TYPES),
    "rs": _Spec(("//",), (("/*", "*/"),), "'\"", (), _RS_KW, _TYPES),
    "sql": _Spec(("--",), (("/*", "*/"),), "'\"", (), _SQL_KW, (), case_kw=False),
    "sh": _Spec(("#",), (), "'\"", (), _SH_KW, ()),
    "css": _Spec((), (("/*", "*/"),), "'\"", (), (), ()),
    "json": _Spec((), (), '"', (), ("true", "false", "null"), ()),
    "yaml": _Spec(("#",), (), "'\"", (), ("true", "false", "null", "yes", "no", "on", "off"), ()),
    "toml": _Spec(("#",), (), "'\"", ('"""', "'''"), ("true", "false"), ()),
    "prisma": _Spec(("//",), (), '"', (), ("model", "enum", "datasource", "generator", "type", "true", "false", "null"), _TYPES),
}

_BY_EXT = {
    "ts": "ts", "tsx": "ts", "js": "ts", "jsx": "ts", "mjs": "ts", "cjs": "ts", "mts": "ts", "cts": "ts",
    "py": "py", "pyi": "py",
    "kt": "kt", "kts": "kt", "java": "java", "go": "go", "rs": "rs",
    "sql": "sql",
    "sh": "sh", "bash": "sh", "zsh": "sh",
    "css": "css", "scss": "css", "less": "css",
    "json": "json", "jsonc": "json",
    "yaml": "yaml", "yml": "yaml",
    "toml": "toml",
    "prisma": "prisma",
}

# Extensionless files worth recognising by name alone.
_BY_NAME = {
    "dockerfile": "sh", "makefile": "sh", ".env": "sh", ".gitignore": "sh",
    ".bashrc": "sh", ".zshrc": "sh", ".profile": "sh",
}


def language_for(path):
    """The language key for a path, or None when we do not model it.

    None is the graceful path and it is deliberately common: Markdown, HTML and XML are tag- or
    prose-shaped and a keyword lexer makes them worse, not better, so they are left plain.
    """
    if not path:
        return None
    name = path.rsplit("/", 1)[-1].lower()
    if name in _BY_NAME:
        return _BY_NAME[name]
    if "." not in name:
        return None
    return _BY_EXT.get(name.rsplit(".", 1)[-1])


def _is_word(ch):
    return ch.isalnum() or ch in "_$"


def _emit(out, cls, text):
    if not text:
        return
    if cls:
        out.append('<span class="hl-%s">%s</span>' % (cls, _esc(text, quote=False)))
    else:
        out.append(_esc(text, quote=False))


def scan(text, lang, state=OPEN_NONE):
    """Highlight one line. Returns (html, next_state).

    `state` carries an unterminated block comment or multi-line string from the previous line of the
    SAME hunk. Pass OPEN_NONE for the first line of a hunk.

    With no spec for `lang` the text comes back escaped and unwrapped — same bytes the renderer used
    before highlighting existed, which is what makes this safe to add everywhere.
    """
    spec = _SPECS.get(lang or "")
    if spec is None:
        return _esc(text, quote=False), OPEN_NONE

    out, i, n = [], 0, len(text)
    buf = []  # plain run waiting to be flushed
    prev = ""  # last significant char emitted, for the regex-vs-division call

    def flush():
        if buf:
            _emit(out, None, "".join(buf))
            buf.clear()

    def prev_word():
        """The identifier immediately before position `i`, for `return /re/` and friends."""
        j = i
        while j and text[j - 1].isspace():
            j -= 1
        k = j
        while k and _is_word(text[k - 1]):
            k -= 1
        return text[k:j]

    # ── continue whatever the previous line left open ──────────────────────────────────────────
    if state is not None:
        kind, delim = state[0], state[1]
        end = text.find(delim)
        cls = "c" if kind == "block" else "s"
        if end == -1:
            _emit(out, cls, text)
            return "".join(out), state
        _emit(out, cls, text[: end + len(delim)])
        i = end + len(delim)

    while i < n:
        ch = text[i]

        # line comment
        hit = next((m for m in spec.line if text.startswith(m, i)), None)
        if hit:
            flush()
            _emit(out, "c", text[i:])
            return "".join(out), OPEN_NONE

        # block comment
        blk = next((p for p in spec.block if text.startswith(p[0], i)), None)
        if blk:
            flush()
            end = text.find(blk[1], i + len(blk[0]))
            if end == -1:
                _emit(out, "c", text[i:])
                return "".join(out), ("block", blk[1])
            _emit(out, "c", text[i : end + len(blk[1])])
            i = end + len(blk[1])
            prev = "/"
            continue

        # regex literal — one token, so its character classes are not lexed as code
        if spec.regex and ch == "/" and (prev in _RE_OK_AFTER or prev_word() in _RE_OK_WORDS):
            j, closed = i + 1, False
            in_class = False
            while j < n:
                c = text[j]
                if c == "\\":
                    j += 2
                    continue
                if c == "[":
                    in_class = True
                elif c == "]":
                    in_class = False
                elif c == "/" and not in_class:
                    j += 1
                    closed = True
                    break
                j += 1
            if closed:
                while j < n and text[j].isalpha():  # flags
                    j += 1
                flush()
                _emit(out, "s", text[i:j])
                prev = "/"
                i = j
                continue
            # Unterminated on this line: almost certainly division after all, so fall through and
            # lex the rest as code rather than painting the remainder of the line as a string.

        # multi-line string (''' """ `)
        raw = next((d for d in spec.raw3 if text.startswith(d, i)), None)
        if raw:
            flush()
            end = text.find(raw, i + len(raw))
            if end == -1:
                _emit(out, "s", text[i:])
                return "".join(out), ("str", raw)
            _emit(out, "s", text[i : end + len(raw)])
            i = end + len(raw)
            prev = raw[-1]
            continue

        # single-line string, honouring backslash escapes
        if ch in spec.quotes:
            flush()
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == ch:
                    j += 1
                    break
                j += 1
            _emit(out, "s", text[i:j])
            i = j
            prev = ch
            continue

        # number
        if ch.isdigit() or (ch == "." and i + 1 < n and text[i + 1].isdigit() and not (i and _is_word(text[i - 1]))):
            if not (i and _is_word(text[i - 1])):
                flush()
                j = i
                while j < n and (text[j].isalnum() or text[j] in "._"):
                    j += 1
                _emit(out, "n", text[i:j])
                i = j
                prev = text[j - 1]
                continue

        # word: keyword, type-ish, call-ish, or plain
        if _is_word(ch) and not ch.isdigit():
            j = i
            while j < n and _is_word(text[j]):
                j += 1
            word = text[i:j]
            probe = word if spec.case_kw else word.lower()
            if probe in spec.keywords:
                flush()
                _emit(out, "k", word)
            elif word in spec.types or (word[:1].isupper() and len(word) > 1 and not word.isupper()):
                flush()
                _emit(out, "y", word)
            elif text[j : j + 1] == "(":
                flush()
                _emit(out, "fn", word)
            else:
                buf.append(word)
            i = j
            prev = word[-1]
            continue

        buf.append(ch)
        if not ch.isspace():
            prev = ch
        i += 1

    flush()
    return "".join(out), OPEN_NONE
