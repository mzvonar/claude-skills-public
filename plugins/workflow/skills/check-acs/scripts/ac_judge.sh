#!/usr/bin/env bash
# One judge call. usage: ac_judge.sh <run-dir> <AC> <n> [style] [diff-basename]
#
# The flag set matters. --no-session-persistence --setting-sources "" --strict-mcp-config
# --tools "" gives a genuinely fresh, tool-free context; the call also runs from a scratch
# directory so no CLAUDE.md from the project is discovered and silently steers the verdict.
# (--bare looks like the right flag but skips keychain reads, so every call fails "Not logged in".)
#
# Prompt order is deliberate: spec and diff first and byte-identical across every call of a run,
# the criterion and the answer format last. That way the expensive prefix is cached — on a
# 60K-token payload the first call cost ~$1.45 and every later one ~$0.29 (measured on one corpus,
# one model — your prices will differ).
set -u
RUN=$1; AC=$2; N=$3; STYLE=${4:-explain}; DIFF=${5:-payload}
# Model precedence: AC_MODEL env > `check-acs.model` in .claude/claude-skills.json > claude-fable-5.
B="$(cd "$(dirname "$0")" && pwd)"
MODEL="${AC_MODEL:-$(python3 "$B/ac_config.py" model)}"; MODEL="${MODEL:-claude-fable-5}"
SCRATCH="${AC_SCRATCH:-${TMPDIR:-/tmp}/ac-audit-judge-cwd}"; mkdir -p "$SCRATCH"
OUT="$RUN/results/$DIFF/$AC/$STYLE"; mkdir -p "$OUT"

# A cell counts as done only when it holds a real verdict. An API cap or a refusal still returns
# a well-formed JSON envelope with no verdict in it, so "the file exists" is not the same as
# "the work is done" — treating it as done is how a capped sweep silently reports itself complete
# and can never be resumed.
has_verdict() {
  python3 - "$1" <<'PY' 2>/dev/null
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
v = (d.get('structured_output') or {}).get('verdict')
if v is None and d.get('result'):
    try: v = json.loads(d['result']).get('verdict')
    except Exception: v = None
sys.exit(0 if v in ('satisfied', 'not_satisfied') else 1)
PY
}
if [ -s "$OUT/$N.json" ] && has_verdict "$OUT/$N.json"; then exit 0; fi
rm -f "$OUT/$N.json"
SCHEMA='{"type":"object","properties":{"explanation":{"type":"string"},"verdict":{"type":"string","enum":["satisfied","not_satisfied"]},"fix":{"type":"string"}},"required":["verdict"]}'
{
  printf 'You are reviewing whether an implementation satisfies ONE acceptance criterion of a specification.\n\nBelow are: (1) the specification with all of its criteria, for context; (2) the complete diff of the implementation; (3) the ONE criterion you must judge; (4) how to answer.\n\nJudge only the criterion in section (3). Everything the specification describes as already existing can be assumed to exist as described.\n'
  [ -f "$RUN/context.md" ] && { printf '\n\n===== (0) ADDITIONAL CONTEXT =====\n\n'; cat "$RUN/context.md"; }
  printf '\n\n===== (1) SPECIFICATION =====\n\n'; cat "$RUN/spec.md"
  printf '\n\n===== (2) IMPLEMENTATION DIFF =====\n\n```diff\n'; cat "$RUN/$DIFF.diff"; printf '\n```\n'
  printf '\n\n===== (3) CRITERION UNDER REVIEW =====\n\n'; cat "$RUN/acs/$AC.md"
  printf '\n\n===== (4) HOW TO ANSWER =====\n\n'
  case "$STYLE" in
    direct) printf 'Answer with the verdict only. Do not explain.\n' ;;
    explain_fix) printf 'First explain your reasoning, citing the specific parts of the criterion and of the diff that decide it. Then give the verdict. If it is not satisfied, describe the concrete change that would satisfy it.\n' ;;
    *) printf 'First explain your reasoning, citing the specific parts of the criterion and of the diff that decide it. Then give the verdict.\n' ;;
  esac
} | (cd "$SCRATCH" && claude -p --no-session-persistence --setting-sources "" --strict-mcp-config \
      --tools "" --model "$MODEL" --output-format json --json-schema "$SCHEMA") \
    > "$OUT/$N.json.tmp" 2>"$OUT/$N.err"

# Promote only a result that carries a verdict. A capped or errored response is left as .tmp
# (with its .err beside it) so it can be inspected, and the cell stays empty so the next sweep
# retries it rather than skipping it forever.
if has_verdict "$OUT/$N.json.tmp"; then
  mv "$OUT/$N.json.tmp" "$OUT/$N.json"
else
  echo "no verdict for $AC #$N (cap, refusal or error) — left at $OUT/$N.json.tmp" >&2
  exit 1
fi
