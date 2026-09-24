#!/usr/bin/env bash
# tests/line-comment-view.sh — a line that already carries a comment can SHOW it.
#
# The gutter mark (has-c) tells the reader a comment is on this line, which invites exactly one
# question: what did I say? Before this the popup answered it with a blank box, so reading your own
# note meant leaving the diff for Conversation and finding it by eye.
#
# SCOPE, stated because it matters: this is a WIRING test, not a behaviour test. The suite is
# bash + python3 stdlib + git by design, so it cannot open a browser and click a gutter. What it
# guards is that the four pieces the behaviour rests on are still connected — the container, the
# populate call, the store that holds the threads, and the clear on the prose path. The behaviour
# itself was driven in headless Chromium when it landed (seed a thread + reply, click the gutter,
# assert both render in the popup) and that check was confirmed RED against the previous template.
# Run by tests/run.sh; runnable alone.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$HERE/../skills/describe-changes/scripts"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export DESCRIBE_CHANGES_HOME="$T/home"
fail() { echo "FAIL: $*" >&2; exit 1; }
[ -n "$T" ] && [ -d "$T" ] || { echo "FATAL: no scratch dir" >&2; exit 1; }

cd "$T"
git init -q -b main . ; git config user.email t@t; git config user.name t
printf '.describe-changes/\nhome/\n' > .gitignore

mkdir -p src
cat > src/real.ts <<'F'
export const add = (a: number, b: number): number => a + b;
F
git add -A && git commit -qm "base"
cat > src/real.ts <<'F'
export const add = (a: number, b: number): number => a + b;
export const div = (a: number, b: number): number => a / b;
F

OUT=$(bash "$S/collect-diff.sh" | tail -1 | sed 's/^OUT=//')
[ -n "$OUT" ] || fail "collect produced no OUT"

OUT="$OUT" python3 - <<'PY'
import json, os
d = os.environ["OUT"]
json.dump({
    "title": "t", "intent": "t", "summary": "A helper was added to the math module.",
    "phases": [{"id": "p1", "title": "p", "narrative": "n", "files": ["src/real.ts"]}],
    "graph": {"nodes": [], "edges": []}, "findings": [], "folded": [], "unreviewed_notes": {},
}, open(os.path.join(d, "report.json"), "w"))
PY

python3 "$S/render-report.py" --dir "$OUT" >/dev/null || fail "render"

OUT="$OUT" python3 - <<'PY' || fail "the per-line comment view is not wired"
import os, re
page = open(os.path.join(os.environ["OUT"], "index.html"), encoding="utf-8").read()

# 1. The container exists, inside the ask popup and before the new-comment box — a preview that
#    renders under the textarea is one a phone reader scrolls past without seeing.
m = re.search(r'<div class="ask-pop" id="ask-pop">(.*?)</div>\s*<div class="footer"', page, re.S)
assert m, "the ask popup is not in the page in the shape this test reads"
pop = m.group(1)
assert 'id="ask-prev"' in pop, "no #ask-prev container in the ask popup"
assert pop.index('id="ask-prev"') < pop.index('id="ask-text"'), \
    "#ask-prev must come BEFORE the new-comment textarea"
print("the popup has a preview slot, above the new-comment box  OK")

# 2. Opening a line populates it. Without this call the container is dead markup.
assert re.search(r"const openLineAsk\s*=.*?showPrev\(lineKey\(sel\)\)", page, re.S), \
    "openLineAsk does not populate the preview"
print("tapping a line populates it from that line's key         OK")

# 3. The store holds the THREADS, not just the fact of them. A Set of keys can light the gutter
#    and can never answer "what did I say" — that regression would be invisible to check 1 and 2.
assert "const COMMENTED = new Map()" in page, \
    "COMMENTED is not a Map — a Set cannot carry the threads the preview reads"
assert re.search(r"COMMENTED\.get\(k\)\.push\(e\)", page), "threads are not stored against the line"
assert re.search(r"showPrev\s*=\s*key\s*=>", page) and "COMMENTED.get(key)" in page, \
    "showPrev does not read the threads out of the store"
print("the store carries the threads, and the preview reads it  OK")

# 4. The popup is SHARED with prose selections, so the line path must clear it — otherwise a
#    sentence inherits the last line's thread and the page attributes it to text it was never on.
assert re.search(r"askBtn\.onclick\s*=.*?showPrev\(null\)", page, re.S), \
    "the prose path does not clear the preview"
print("a prose selection clears it, so no thread is misplaced    OK")

# 5. Reader-written text reaches the DOM as text, never markup.
seg = page[page.index("const showPrev"):page.index("const openLineAsk")]
assert ".innerHTML" not in seg, "showPrev builds markup from reader-written text"
print("reader text is set as text, not markup                    OK")

# 6. Closing the file sheet takes the popup with it. The popup is anchored to ONE LINE of the
#    diff the sheet is showing, so a popup that outlives its sheet sits over the report offering
#    a comment box for code that is no longer on screen. All three close paths — the ✕, the
#    backdrop, Escape — route through closeSheet, which is why asserting on it covers them; if a
#    later change gives one its own path, this row stops covering that path and the browser check
#    in the header is what would catch it.
m = re.search(r"const closeSheet = \(\) => \{(.*?)\n  \};", page, re.S)
assert m, "closeSheet is not in the shape this test reads"
body = m.group(1)
assert "ask-pop" in body, "closing the sheet leaves the comment popup open over the report"
assert "ask-btn" in body, "closing the sheet leaves the floating ask button behind"
for path in ("#sheet-x').onclick = closeSheet", "sheetBg.onclick = closeSheet"):
    assert path in page, f"a sheet close path no longer routes through closeSheet: {path}"
assert re.search(r"ev\.key === 'Escape'.*?closeSheet\(\)", page, re.S), \
    "Escape no longer routes through closeSheet"
print("closing the sheet closes the popup anchored inside it     OK")
PY

echo "LINE COMMENT VIEW TESTS PASSED"
