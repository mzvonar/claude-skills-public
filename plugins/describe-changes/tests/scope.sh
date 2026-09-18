#!/usr/bin/env bash
# tests/scope.sh — WHAT a report covers. Three rules, each of which has failed in the wild:
#   1. the working tree is in scope by default;
#   2. leaving it out is an explicit act, never a side effect of naming a range;
#   3. a stale LOCAL default branch never decides the base.
# The failure they prevent is a report whose findings describe code the diff beside them does not
# show — unfalsifiable against the disk, which is the one check its reader can run.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$HERE/../skills/describe-changes/scripts"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
meta() { python3 -c "import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$1" "$2"; }
nfiles() { python3 -c "import json,sys;print(len(json.load(open(sys.argv[1]))[sys.argv[2]]))" "$1" "$2"; }

[ -n "$T" ] && [ -z "$(ls -A "$T")" ] || fail "scratch dir unusable"
cd "$T"

# A bare "remote" plus a clone, so origin/main is real and local main can be made stale.
git init -q --bare -b main remote.git
git clone -q remote.git work 2>/dev/null
cd work
git config user.email t@t; git config user.name t
git symbolic-ref HEAD refs/heads/main
echo "base" > a.txt; git add .; git commit -qm "base"; git push -q -u origin main

# main moves on the REMOTE (someone else's merges) while our local main stays behind.
git clone -q "$T/remote.git" "$T/other"
( cd "$T/other" && git config user.email o@o && git config user.name o
  for i in 1 2 3; do echo "upstream $i" > "up$i.txt"; git add .; git commit -qm "upstream $i"; done
  git push -q origin main )
git fetch -q origin
LOCAL_MAIN="$(git rev-parse main)"; REMOTE_MAIN="$(git rev-parse origin/main)"
[ "$LOCAL_MAIN" != "$REMOTE_MAIN" ] || fail "fixture: local main should be stale"

# Our feature branch is cut from the CURRENT remote, which is the real shape: you branch from an
# up-to-date origin/main while the local `main` you never check out rots behind it. Cutting from the
# stale local branch instead would make both merge-bases identical — origin/main being a descendant
# — and the test would pass against the very bug it exists to catch. (It did, until a mutation probe
# showed the row staying green with the fix removed.)
git switch -qc feat origin/main
echo "mine" > mine.txt; git add .; git commit -qm "my commit"

# ── 3. the stale local main must NOT decide the base ───────────────────────────────────────────
bash "$S/collect-diff.sh" --out "$T/o1" >/dev/null 2>&1 || fail "default run failed"
[ "$(meta "$T/o1/meta.json" mode)" = branch ] || fail "expected branch mode"
BASE_SHA="$(meta "$T/o1/meta.json" base_sha)"
[ "$BASE_SHA" = "$(git merge-base origin/main HEAD)" ] || fail "base_sha not taken from origin/main"
# The three upstream files are NOT ours and must not appear.
grep -q "up1.txt" "$T/o1/raw.diff" && fail "upstream commits leaked into the report"
grep -q "mine.txt" "$T/o1/raw.diff" || fail "our own commit missing"
echo "base comes from origin/, not stale local  OK"

# ── 1. the working tree is in scope by default ─────────────────────────────────────────────────
echo "dirty edit" >> mine.txt          # unstaged
echo "brand new" > untracked.txt       # untracked
bash "$S/collect-diff.sh" --out "$T/o2" >/dev/null 2>&1 || fail "default run with dirty tree failed"
grep -q "dirty edit" "$T/o2/raw.diff"  || fail "unstaged change not in the default scope"
grep -q "untracked.txt" "$T/o2/raw.diff" || fail "untracked file not in the default scope"
[ "$(nfiles "$T/o2/meta.json" uncommitted_files)" -ge 2 ] || fail "uncommitted_files not recorded"
[ "$(nfiles "$T/o2/meta.json" excluded_uncommitted)" = 0 ] || fail "nothing should be excluded by default"
echo "working tree in scope by default          OK"

# ── 2. naming a range while dirty REFUSES, and says how ────────────────────────────────────────
set +e
OUTPUT="$(bash "$S/collect-diff.sh" --out "$T/o3" origin/main...HEAD 2>&1)"; RC=$?
set -e
[ "$RC" = 4 ] || fail "explicit range with a dirty tree should exit 4, got $RC"
case "$OUTPUT" in *--committed-only*) ;; *) fail "refusal does not name --committed-only" ;; esac
case "$OUTPUT" in *--base*) ;;           *) fail "refusal does not name the --base alternative" ;; esac
[ -f "$T/o3/meta.json" ] && fail "refused run still wrote a report"
echo "explicit range + dirty tree refuses       OK"

# …and passing the flag makes it work, recording what it left out.
bash "$S/collect-diff.sh" --out "$T/o4" --committed-only origin/main...HEAD >/dev/null 2>&1 \
  || fail "--committed-only with an explicit range failed"
grep -q "dirty edit" "$T/o4/raw.diff" && fail "--committed-only still included the working tree"
[ "$(nfiles "$T/o4/meta.json" excluded_uncommitted)" -ge 2 ] \
  || fail "excluded files not recorded — the reader cannot tell anything is missing"
[ "$(nfiles "$T/o4/meta.json" uncommitted_files)" = 0 ] || fail "excluded files listed as included"
echo "opting out is explicit and recorded       OK"

# ── the refusal targets COMMIT-ish args only. `--staged` describes the index on purpose and an
#    unstaged remainder is its normal state; a path filter still diffs the tree. Both must pass
#    while dirty, or the rule fires on correct usage.
echo "staged content" > staged.txt; git add staged.txt      # something IS staged…
echo "more unstaged" >> mine.txt                            # …and something is NOT
set +e; bash "$S/collect-diff.sh" --out "$T/s1" --staged >/dev/null 2>&1; RC=$?; set -e
[ "$RC" = 4 ] && fail "--staged refused while dirty — the rule fires on correct usage"
[ "$RC" = 0 ] || fail "--staged failed for another reason (rc=$RC)"
set +e; bash "$S/collect-diff.sh" --out "$T/s2" -- mine.txt >/dev/null 2>&1; RC=$?; set -e
[ "$RC" = 4 ] && fail "a path-only filter was refused while dirty"
[ "$RC" = 0 ] || fail "path filter failed for another reason (rc=$RC)"
echo "--staged / path filters not refused       OK"

# ── a clean tree still accepts a range with no flag (the refusal is about LOSS, not about ranges)
git add -A; git commit -qm "commit the rest"
bash "$S/collect-diff.sh" --out "$T/o5" origin/main...HEAD >/dev/null 2>&1 \
  || fail "explicit range on a clean tree should be allowed"
[ "$(meta "$T/o5/meta.json" mode)" = explicit ] || fail "expected explicit mode"
echo "clean tree + range still allowed          OK"

echo "SCOPE TESTS PASSED"
