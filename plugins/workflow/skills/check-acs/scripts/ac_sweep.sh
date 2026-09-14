#!/usr/bin/env bash
# usage: ac_sweep.sh <run-dir> [AC ...]     env: N=3 P=1 STYLE=explain DIFF=payload
#
# Idempotent: a cell that already holds a result is skipped, so re-running after an API cap
# resumes rather than restarting. Screen wide and shallow first (N=3 over every criterion),
# then deepen only where the verdict came back split or negative — that is where the signal is,
# and it is where the money is worth spending.
#
# P defaults to 1 because the N repeats of one criterion must not RACE for the prompt cache.
# Measured, not assumed (~226K-token payload, one model): a cell costs ~$4.9 cold and ~$0.65 when
# it reuses a warm cache — 7.6x. But the reuse is narrower than the prompt layout suggests. The
# cache key covers the WHOLE prompt, the criterion in section (3) included, so it is only the 2nd
# and 3rd run of the SAME criterion that hit; the first call of every new criterion pays full price
# however the sweep is scheduled. Observed in one sequential run: AC7#1 $4.94 -> AC7#2 $0.65, then
# the next criterion's first call $4.97 cold again, and the same shape for every AC after it.
#
# So the saving is (N-1)/N of the calls, which is why the loop below emits all N of one criterion
# consecutively — keep that order. At N=3 sequential averages ~$2.1/cell against ~$4.9 at P=6
# (2.4x); at N=10 it is ~$1.1 (4.6x). Concurrent calls all start before any has finished writing,
# so at P=6 every call is cold. Calls take ~45-60s and the cache survives the gap between them.
# Caching does not weaken the sweep: each verdict is still sampled fresh in a context that cannot
# see the other runs, which is what makes a SPLIT meaningful. Raise P only to buy speed knowingly.
# -e is deliberately NOT set: one capped or refused call must not abort a sweep of several
# hundred, and a partial sweep is still useful — the tally reports which cells are missing and
# re-running fills only those. The sweep's own exit status is computed at the end instead, so a
# caller still learns that it did not complete.
set -uo pipefail
B="$(cd "$(dirname "$0")" && pwd)"
RUN=$1; shift
N=${N:-3}; P=${P:-1}; STYLE=${STYLE:-explain}; DIFF=${DIFF:-payload}
ACS=("$@"); [ ${#ACS[@]} -eq 0 ] && ACS=($(ls "$RUN/acs" | sed 's/\.md$//'))
for ac in "${ACS[@]}"; do for n in $(seq 1 "$N"); do echo "$RUN $ac $n $STYLE $DIFF"; done; done \
  | xargs -P "$P" -n 5 "$B/ac_judge.sh"
echo "SWEEP-DONE $(date +%H:%M:%S)"
"$B/ac_tally.py" "$RUN" --diff "$DIFF" --style "$STYLE"

# Exit non-zero when cells are still empty, so a caller (or CI) is not told a capped sweep
# succeeded. Re-running is safe and cheap: completed cells are skipped.
missing=0
for ac in "${ACS[@]}"; do
  for n in $(seq 1 "$N"); do
    [ -s "$RUN/results/$DIFF/$ac/$STYLE/$n.json" ] || missing=$((missing + 1))
  done
done
if [ "$missing" -gt 0 ]; then
  echo "INCOMPLETE: $missing of $(( ${#ACS[@]} * N )) cells have no verdict. Re-run to fill them." >&2
  exit 1
fi
