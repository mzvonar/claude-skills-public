#!/usr/bin/env bash
# usage: ac_sweep.sh <run-dir> [AC ...]     env: N=3 P=6 STYLE=explain DIFF=payload
#
# Idempotent: a cell that already holds a result is skipped, so re-running after an API cap
# resumes rather than restarting. Screen wide and shallow first (N=3 over every criterion),
# then deepen only where the verdict came back split or negative — that is where the signal is,
# and it is where the money is worth spending.
# -e is deliberately NOT set: one capped or refused call must not abort a sweep of several
# hundred, and a partial sweep is still useful — the tally reports which cells are missing and
# re-running fills only those. The sweep's own exit status is computed at the end instead, so a
# caller still learns that it did not complete.
set -uo pipefail
B="$(cd "$(dirname "$0")" && pwd)"
RUN=$1; shift
N=${N:-3}; P=${P:-6}; STYLE=${STYLE:-explain}; DIFF=${DIFF:-payload}
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
