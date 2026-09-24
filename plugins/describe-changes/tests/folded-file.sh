#!/usr/bin/env bash
# tests/folded-file.sh — a file whose every hunk was folded still opens to its diff.
#
# The fold is a claim about ATTENTION: not worth yours by default. A reader who opens the file
# anyway is checking that claim, and answering them with a sentence saying "folded as noise" and no
# code asks them to take it on trust at the one moment they declined to. So the sheet shows the
# folded hunks under a banner naming what they are. Run by tests/run.sh; runnable alone.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$HERE/../skills/describe-changes/scripts"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export DESCRIBE_CHANGES_HOME="$T/home"
fail() { echo "FAIL: $*" >&2; exit 1; }
[ -n "$T" ] && [ -d "$T" ] || { echo "FATAL: no scratch dir" >&2; exit 1; }

cd "$T"
git init -q -b main . ; git config user.email t@t; git config user.name t
printf '.describe-changes/\nhome/\n' > .gitignore

# Two files: one that will carry a real change, one that will only ever get a comment. The real one
# is needed because a report with NO substantive file is a different (and already tested) path.
mkdir -p src
cat > src/real.ts <<'F'
export const add = (a: number, b: number): number => a + b;
F
cat > src/commented.ts <<'F'
export const NAME = "registry";
export const PORT = 4330;
F
git add -A && git commit -qm "base"

cat > src/real.ts <<'F'
export const add = (a: number, b: number): number => a + b;
export const mul = (a: number, b: number): number => a * b;
F
cat > src/commented.ts <<'F'
// The deployment's own name, not the product's — it reaches the operator in the tab title.
export const NAME = "registry";
export const PORT = 4330;
F
# Left UNCOMMITTED on purpose: the working tree is what a report covers by default, and it is
# the shortest fixture that gives the two files a diff to classify.
OUT=$(bash "$S/collect-diff.sh" | tail -1 | sed 's/^OUT=//')
[ -n "$OUT" ] || fail "collect produced no OUT"

OUT="$OUT" python3 - <<'PY' || fail "the commented file is not classified as folded"
import json, os
m = json.load(open(os.path.join(os.environ["OUT"], "diff-model.json")))
f = next(f for f in m["files"] if f["path"].endswith("commented.ts"))
assert f["substantive_hunks"] == 0, f"expected a folded-only file, got {f['substantive_hunks']} substantive hunks"
assert f["hunks"], "the file has no hunks at all — fixture is wrong"
print("fixture: commented.ts folds to nothing substantive  OK")
PY

# The minimum report the renderer accepts, naming only the file that really changed.
OUT="$OUT" python3 - <<'PY'
import json, os
d = os.environ["OUT"]
json.dump({
    "title": "t", "intent": "t", "summary": "A file changed and another only gained a comment.",
    "phases": [{"id": "p1", "title": "p", "narrative": "n", "files": ["src/real.ts"]}],
    "graph": {"nodes": [], "edges": []}, "findings": [], "folded": [], "unreviewed_notes": {},
}, open(os.path.join(d, "report.json"), "w"))
PY

python3 "$S/render-report.py" --dir "$OUT" >/dev/null || fail "render"

OUT="$OUT" python3 - <<'PY' || fail "folded file does not open to its diff"
import json, os, re
page = open(os.path.join(os.environ["OUT"], "index.html"), encoding="utf-8").read()
m = re.search(r"FILE_STORE\s*=\s*(\{.*?\});\n", page, re.S) or re.search(
    r'id="file-store"[^>]*>(\{.*?\})</script>', page, re.S)
assert m, "no file store in the rendered page"
store = json.loads(m.group(1))

entry = next(v for k, v in store.items() if k.endswith("commented.ts"))["html"]
assert "foldnote" in entry, "no banner on a folded-only file"
assert entry.lstrip().startswith('<div class="foldnote"'), "the banner must come FIRST, before the code"
assert "comment-only" in entry, "the banner does not name what the fold was"
# The point of the change: the code is there, not just the sentence.
assert 'class="diff"' in entry, "the folded file still has no diff — the fix is not doing anything"
assert "the operator in the tab title" in entry, "the folded hunk's own lines are missing"
print("folded file: banner first, then the real diff            OK")

# …but COLLAPSED behind a disclosure. A banner saying "not worth your attention" answered with a
# screen of that content buries its own sentence, which is what made the notice unreadable.
assert '<details class="foldcode">' in entry, "the folded code is not behind a disclosure"
assert entry.index("foldnote") < entry.index("foldcode"), "the banner must precede the disclosure"
assert entry.index("foldcode") < entry.index('class="diff"'), "the diff must sit INSIDE the disclosure"
assert "<summary>Expand code" in entry, "the disclosure has no Expand code control"
assert entry.rstrip().endswith("</details>"), "the disclosure is not closed around the code"
# The control says how much is behind it, so the click is an informed one.
import re as _re
m2 = _re.search(r"<summary>Expand code · (\d+) changed line", entry)
assert m2, "the Expand control does not say how much code it hides"
assert int(m2.group(1)) >= 1, "the changed-line count reads zero on a file that changed"
print("its code is collapsed behind Expand, with a line count   OK")

# A file with real changes keeps its plain sheet — no banner, because nothing was withheld.
real = next(v for k, v in store.items() if k.endswith("real.ts"))["html"]
assert "foldnote" not in real, "a substantive file must not carry the fold banner"
assert 'class="diff"' in real, "the substantive file lost its diff"
print("substantive file: unchanged, no banner                   OK")

# THE OTHER WAY IN. A fold card's own file buttons open the folded HUNKS (openHunks), not the
# file store above, and that path is built client-side — so it carried no banner at all while
# this file's path had one. A notice on one path and not the other reads, to whoever took the
# other one, as no notice; that is exactly how it was reported. Both paths now say the same thing.
assert 'data-open-kind="' in page, "the fold card does not pass its kind into the hunk view"
m3 = re.search(r"const openHunks = \(ids, label, kind\) => \{(.*?)\n  \};", page, re.S)
assert m3, "openHunks does not take the fold kind"
oh = m3.group(1)
assert "foldnote" in oh, "the hunk view renders no fold banner"
assert 'details class="foldcode"' in oh, "the hunk view does not collapse its code"
assert "esc(kind)" in oh, "the fold kind reaches the DOM unescaped"
assert "dataset.openKind" in page, "the click handler does not forward the fold kind"
print("the fold-card hunk view carries the same banner          OK")
PY

echo "FOLDED FILE TESTS PASSED"
