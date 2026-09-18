#!/usr/bin/env bash
# tests/highlight.sh — the render-time syntax lexer (skills/describe-changes/scripts/highlight.py).
#
# The property that matters most is the ROUND TRIP: stripping the emitted tags must reproduce the
# input byte for byte. The page's `codeOf()` rebuilds a quoted selection from the DOM text, so the
# moment highlighting drops or reorders a character, a comment thread quotes something the file does
# not contain — silently, and only for the languages the lexer models.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
S="$HERE/../skills/describe-changes/scripts"

S="$S" python3 - <<'PY'
import os, sys, re, html
sys.path.insert(0, os.environ["S"])
from highlight import language_for, scan, OPEN_NONE

fails = []
def check(name, got, want):
    if got != want:
        fails.append("%s\n   got:  %r\n   want: %r" % (name, got, want))

SAMPLES = {
 "a.ts": ['const x = "hi";', 'const re = /^[A-Za-z0-9_-]+$/u;', 'const half = w / 2;', '// note', 'let n = 42;', 'if (a && b) { foo(1) }',
          'const s = `tpl ${x}`;', 'type T = { a: string }', "x = 'it\\'s'", '  ', '',
          'a.b.c(1,2)', '/* block */ const y = 1;', 'class Foo extends Bar {}',
          'const re = /ab+/g;', 'export default async function run() {}'],
 "b.py": ['def f(x):', '    return {"a": 1}', '# comment', 's = """doc', 'still doc"""',
          'if x is None: pass', 'xs = [i for i in range(10)]'],
 "c.kt": ['fun f(): String {', '    val x = "s"', '}', '// c', 'data class P(val id: Long)'],
 "d.sql":['SELECT * FROM t WHERE a = 1;', 'select id from x -- note', "insert into t values ('a')"],
 "e.yaml":['key: value', '# c', '- item: true', 'n: 12', 'nested:\n'.rstrip()],
 "f.json":['{"a": 1, "b": null}', '  "deep": {"x": [1,2]}'],
 "g.sh": ['echo "$x" # c', 'if [ -f x ]; then', 'export A=1'],
 "h.md": ['# heading', '**bold** and `code`'],        # unmodelled -> plain
 "i.html":['<div class="x">hi</div>'],                # unmodelled -> plain
 "j.go": ['func main() { fmt.Println("x") }'],
 "k.rs": ['fn main() { let x: u32 = 1; }'],
 "l.css":['.a { color: #fff; /* c */ }'],
 "m.toml":['[tool]', 'x = 1'],
 "n.prisma":['model User {', '  id String @id', '}'],
}
strip = re.compile(r"<[^>]+>")

# 1. ROUND TRIP — the load-bearing property.
for path, lines in SAMPLES.items():
    lang = language_for(path); st = OPEN_NONE
    for ln in lines:
        out, st = scan(ln, lang, st)
        check("roundtrip %s %r" % (path, ln), html.unescape(strip.sub("", out)), ln)

# 2. An unmodelled language emits NO spans — the graceful path.
for path in ("h.md", "i.html", "x.xml", "y.bin", "noext", ""):
    out, _ = scan('const x = "s"; // c', language_for(path), OPEN_NONE)
    check("no spans for %r" % path, "<span" in out, False)

# 3. POSITIVE CONTROL for #2: a modelled language does emit them. Without this row, an over-eager
#    predicate that returned None for everything would pass #2 on every input.
for path in SAMPLES:
    if language_for(path) is None:
        continue
    out, _ = scan('x = "s"', language_for(path), OPEN_NONE)
    check("spans for %s" % path, "<span" in out, True)

# 4. Block comments and multi-line strings carry state ACROSS lines and close.
st = OPEN_NONE
_,  st = scan("/* start", "ts", st);              check("block opens", st, ("block", "*/"))
o2, st = scan("still comment", "ts", st);         check("block holds", st, ("block", "*/"))
check("held line is all comment", o2, '<span class="hl-c">still comment</span>')
o3, st = scan("end */ const x = 1;", "ts", st);   check("block closes", st, OPEN_NONE)
check("code after close is lexed", 'hl-k">const' in o3, True)
st = OPEN_NONE
_, st = scan("const a = `one", "ts", st);         check("template opens", st, ("str", "`"))
_, st = scan("two`;", "ts", st);                  check("template closes", st, OPEN_NONE)
st = OPEN_NONE
_, st = scan('s = """a', "py", st);               check("py triple opens", st, ("str", '"""'))
_, st = scan('b"""', "py", st);                   check("py triple closes", st, OPEN_NONE)

# 5. A backslash-escaped quote does not end the string early.
out, st = scan(r"x = 'it\'s' + y", "ts", OPEN_NONE)
check("escape leaves no open state", st, OPEN_NONE)
check("escaped quote is one string", out.count('class="hl-s"'), 1)

# 6. Source text is HTML-escaped — a diff may contain markup.
out, _ = scan('const s = "<script>alert(1)</script>";', "ts", OPEN_NONE)
check("no raw tag", "<script>" in out, False)
check("entity present", "&lt;script&gt;" in out, True)
check("ampersand escaped", "&amp;&amp;" in scan("a && b", "ts", OPEN_NONE)[0], True)

# 7. SQL keywords match case-insensitively; C-family ones do not.
check("sql lower", 'hl-k">select' in scan("select 1", "sql", OPEN_NONE)[0], True)
check("sql upper", 'hl-k">SELECT' in scan("SELECT 1", "sql", OPEN_NONE)[0], True)
check("ts case-sensitive", 'hl-k">CONST' in scan("CONST x", "ts", OPEN_NONE)[0], False)

# 8. A digit inside an identifier is not a number.
check("ident with digit", scan("a1 = 1", "ts", OPEN_NONE)[0].count('class="hl-n"'), 1)

# 9. Regex literals are ONE token. Without this the character class is lexed as code and
#    `/^[A-Za-z0-9_-]+$/u` paints `Za` as a type and `9_` as a number — the defect that prompted it.
out, _ = scan("const SEGMENT = /^[A-Za-z0-9_-]+$/u;", "ts", OPEN_NONE)
check("regex is one string token", out.count('class="hl-s"'), 1)
check("no type inside regex", 'hl-y">Za' in out, False)
check("no number inside regex", 'hl-n">9_' in out, False)
check("keyword outside regex still lexed", 'hl-k">const' in out, True)
# A `/` inside the class does not end it, and flags are part of the token.
out, _ = scan(r"const re = /a[/]b/gi;", "ts", OPEN_NONE)
check("slash in class does not end regex", out.count('class="hl-s"'), 1)
# DIVISION must NOT become a string — the heuristic's own failure mode.
for src in ("const r = a / b;", "x = (n + 1) / 2;", "const avg = total / count;"):
    out, _ = scan(src, "ts", OPEN_NONE)
    check("division not a string: %r" % src, 'class="hl-s"' in out, False)
# `return /re/` is a regex despite following a word.
check("regex after return", scan("return /x+/.test(s);", "ts", OPEN_NONE)[0].count('class="hl-s"'), 1)
# Languages without regex literals never take that branch.
check("kotlin division untouched", 'class="hl-s"' in scan("val r = a / b", "kt", OPEN_NONE)[0], False)
# An unterminated `/` falls through to code rather than painting the rest of the line.
out, _ = scan("const half = width / 2 + pad;", "ts", OPEN_NONE)
check("unterminated slash falls through", 'class="hl-s"' in out, False)

# 10. Empty and whitespace-only lines survive untouched.
for ln in ("", "   ", "\t"):
    out, _ = scan(ln, "ts", OPEN_NONE)
    check("blank %r" % ln, html.unescape(strip.sub("", out)), ln)

print("FAIL %d\n%s" % (len(fails), "\n".join(fails)) if fails else "highlight lexer OK")
sys.exit(1 if fails else 0)
PY
