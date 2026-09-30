#!/usr/bin/env bash
# tests/delta-conversation.sh — a question asked on a delta page gets its answer ON THAT PAGE.
#
# Observed on a real report (plugin 1.28.0): the reader commented on "since you last read this",
# Claude answered with `feedback.py answer` and re-rendered, `comments` listed every thread as
# answered and index.html showed the answers — and every delta page showed the same threads with
# no reply. The code-scoped delta page is rendered by a sub-process over <report>/deltas/<seq>/,
# and the loop copied feedback.jsonl into that folder but not answers.jsonl, which the Conversation
# section reads. The copy list was a second source of truth and it missed the second file.
#
# The fix reads the thread files from the PARENT report folder (`--threads-dir`), so there is no
# copy to forget. Run by tests/run.sh; runnable alone. Red without the fix: with `--threads-dir`
# not passed, delta-001.html carries the question and not ANSWER-MARKER (probed at authoring).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$HERE/../skills/changes/scripts"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export DESCRIBE_CHANGES_HOME="$T/home"
fail() { echo "FAIL: $*" >&2; exit 1; }
[ -n "$T" ] && [ -d "$T" ] || { echo "FATAL: no scratch dir" >&2; exit 1; }
[ -z "$(ls -A "$T")" ] || { echo "FATAL: scratch dir '$T' is not empty" >&2; exit 1; }
cd "$T" || { echo "FATAL: cannot enter scratch dir" >&2; exit 1; }
git rev-parse --show-toplevel >/dev/null 2>&1 && { echo "FATAL: '$T' is inside an existing git repo" >&2; exit 1; }
git init -q -b main . && git config user.email t@t && git config user.name t
printf '.describe-changes/\nhome/\n' > .gitignore
mkdir -p src
printf 'export function total(n: number[]) {\n  return n.reduce((a, b) => a + b, 0);\n}\n' > src/sum.ts
git add -A && git commit -qm init

# First reading: one staged change, a minimal report, one render → snapshot 001.
printf 'export function total(n: number[]) {\n  return n.reduce((a, b) => a + b, 0) || 0;\n}\n' > src/sum.ts
git add -A
OUT="$(bash "$S/collect-diff.sh" --staged | tail -1 | sed 's/^OUT=//')"
cat > "$OUT/report.json" <<'J'
{ "title": "Sum tolerates an empty list", "intent": "make total() return 0 for []",
  "summary": "The total of an empty list is now zero instead of undefined; nothing else moves.",
  "phases": [ {"id":"p1","title":"The guard","narrative":"One fallback on the reduce.","files":["src/sum.ts"]} ],
  "graph": {"nodes": [], "edges": []},
  "findings": [ {"id":"L1","severity":"low","title":"`total` now answers 0 for an empty list",
                 "verify":"Is 0 the right answer for an empty list, or should it stay undefined?",
                 "why_human":"A contract question the code cannot settle.","file":"src/sum.ts","lines":"2"} ],
  "folded": [] }
J
python3 "$S/check-report.py" "$OUT/report.json" >/dev/null || fail "the fixture report is not valid"
python3 "$S/render-report.py" --dir "$OUT" >/dev/null
python3 "$S/snapshots.py" list --dir "$OUT" | grep -q "001-" || fail "no first snapshot"

# The code moves on, so the next render can build a code-scoped delta page.
printf 'export function total(n: number[]) {\n  return n.reduce((a, b) => a + b, 0) || 0;\n}\nexport function count(n: number[]) {\n  return n.length;\n}\n' > src/sum.ts
git add -A
bash "$S/collect-diff.sh" --staged --out "$OUT" >/dev/null

# The reader asks on the page (serve.py appends exactly this shape to the PARENT's feedback.jsonl —
# a delta page posts to the same relative `feedback` endpoint), and Claude answers.
printf '%s\n' '{"ts":"2026-01-01T00:00:00Z","type":"comment","id":"cdelta1","text":"WHY-DOES-COUNT-EXIST","anchor":{"text":"count","context":"…count…","section":"findings","finding":null},"report_id":"x"}' >> "$OUT/feedback.jsonl"
python3 "$S/feedback.py" answer --dir "$OUT" --id cdelta1 --improvement "say why count() was added" --text "ANSWER-MARKER: it feeds the empty-list guard." | grep -q "answered cdelta1" || fail "answer"
python3 "$S/render-report.py" --dir "$OUT" >/dev/null
[ -f "$OUT/delta.html" ] && [ -f "$OUT/delta-001.html" ] || fail "no delta page was written"
[ -f "$OUT/deltas/001/diff-model.json" ] || fail "the delta page is not code-scoped — this suite needs the sub-render path"

# The whole point: the question AND its answer, on every page the reader may be looking at.
for page in index.html delta.html delta-001.html; do
  grep -q 'WHY-DOES-COUNT-EXIST' "$OUT/$page" || fail "$page does not show the question (positive control)"
  grep -q 'ANSWER-MARKER' "$OUT/$page" || fail "$page shows the question but not its answer"
  grep -q 'id="t-cdelta1"' "$OUT/$page" || fail "$page has no thread for the comment"
done
# …and the thread reads ANSWERED there, not open: the page and `comments` must agree.
grep -q 'Open — not answered yet' "$OUT/delta-001.html" && fail "delta-001.html marks an answered thread as open"
python3 "$S/feedback.py" comments --dir "$OUT" --open | grep -q 'no open comments' || fail "comments still lists the thread as open"
# No copy of the thread files lives beside the sub-render any more: the parent folder is the one source.
[ ! -e "$OUT/deltas/001/answers.jsonl" ] || fail "answers.jsonl was copied into the delta folder — a second source of truth"
[ ! -e "$OUT/deltas/001/feedback.jsonl" ] || fail "feedback.jsonl was copied into the delta folder — a second source of truth"

# The FALLBACK page — used when no code range can be built (a snapshot older than tree refs) — must
# carry the same conversation. It rendered no Conversation section at all before this fix, so a
# question asked there was answered on index.html only. Forced by blanking the snapshot's tree ref.
python3 - "$OUT" <<'PY'
import glob, json, os, sys
d = sys.argv[1]
snaps = sorted(glob.glob(os.path.join(d, "snapshots", "001-*", "snapshot.json")))
assert snaps, "no first snapshot"
info = json.load(open(snaps[0])); info["tree_sha"] = None
json.dump(info, open(snaps[0], "w"), indent=2)
PY
python3 "$S/render-report.py" --dir "$OUT" >/dev/null
grep -q 'id="folded"' "$OUT/delta-001.html" && fail "the fallback page was not exercised — delta-001.html is still the code-scoped page"
grep -q 'id="conversation"' "$OUT/delta-001.html" || fail "the fallback delta page renders no Conversation"
grep -q 'WHY-DOES-COUNT-EXIST' "$OUT/delta-001.html" || fail "the fallback delta page does not show the question"
grep -q 'ANSWER-MARKER' "$OUT/delta-001.html" || fail "the fallback delta page shows the question but not its answer"
echo "delta conversation OK"
