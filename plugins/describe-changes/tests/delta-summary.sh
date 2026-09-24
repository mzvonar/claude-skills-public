#!/usr/bin/env bash
# tests/delta-summary.sh — a delta page's summary says WHAT was done before how much.
#
# The counts were always there; the subjects were not, and a returning reader opens a delta asking
# what happened rather than how big it was. These rows pin the prose rules that make the sentence
# readable (merges dropped, conventional-commit prefixes stripped, a cap with the remainder counted)
# and the fallback when there is no commit to quote. Run by tests/run.sh; runnable alone.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$HERE/../skills/describe-changes/scripts"
fail() { echo "FAIL: $*" >&2; exit 1; }

S="$S" python3 - <<'PY' || fail "commit_subjects"
import os, sys
sys.path.insert(0, os.environ["S"])
from snapshots import commit_subjects

# A `git log --oneline` row is "<sha> <subject>"; that is the only shape this ever sees.
def row(subject): return "abc1234 " + subject

subjects, more = commit_subjects([
    row("feat(pd-t09): build the filter chips from the dictionary"),
    row("Merge remote-tracking branch 'origin/main' into topic"),
    row("fix: count conditions, not the fields carrying them"),
])
assert subjects == [
    "Build the filter chips from the dictionary",
    "Count conditions, not the fields carrying them",
], subjects
assert more == 0, more
print("scope stripped, merge dropped, sentence-cased  OK")

# The cap reports what it hid. A page showing four of eleven and implying four is the failure here;
# the count is what makes the truncation honest.
subjects, more = commit_subjects([row(f"fix: thing {n}") for n in range(11)])
assert len(subjects) == 4, subjects
assert more == 7, more
print("cap counts the remainder                      OK")

# A breaking change keeps a marker; nothing else earns a word, and the scope goes either way.
for line in ("feat!: drop the v0 endpoint", "feat(api)!: drop the v0 endpoint"):
    subjects, _ = commit_subjects([row(line)])
    assert subjects == ["Breaking: drop the v0 endpoint"], (line, subjects)
print("breaking marker survives, scope does not      OK")

# Merges only, and no commits at all: both yield nothing to quote rather than an empty sentence.
assert commit_subjects([row("Merge branch 'main'"), row("Merge pull request #3")]) == ([], 0)
assert commit_subjects([]) == ([], 0)
print("nothing to quote yields nothing               OK")

# A subject with no conventional prefix is left alone but for its first letter.
subjects, _ = commit_subjects([row("tidy the gallery stories")])
assert subjects == ["Tidy the gallery stories"], subjects
print("un-prefixed subject survives intact           OK")

# The type word is dropped, NOT kept as a label — `docs:` and `test:` read as noise in a sentence
# whose whole job is to be read quickly.
subjects, _ = commit_subjects([row("docs(dw-1): file the finding")])
assert subjects == ["File the finding"], subjects
print("type word dropped from the prose              OK")
PY

echo "DELTA SUMMARY TESTS PASSED"
