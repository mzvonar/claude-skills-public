#!/usr/bin/env bash
# check-all.sh — everything the `validate` CI workflow runs, in the same order. Run it before every
# push; .github/workflows/validate.yml runs THIS file, so the two cannot drift apart.
#
#   bash scripts/check-all.sh
#
# Why one entry point: the workflow ran five steps and the release instructions named one
# (validate.sh). Of 16 red runs on main by 2026-09-26, eleven were the `describe-changes tests`
# version-parity check — a step that ran only in CI — and every one of them was pushed as "done"
# and surfaced only as a failure e-mail. None was flaky; each was a real defect.
#
# Unlike the workflow it does not stop at the first failure: locally you want every red step in
# one pass. Exit 0 only when all of them pass.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
failed=()
step() { # step <name> <command...>
  local name="$1"; shift
  echo "== $name"
  "$@" || failed+=("$name")
}

step "validate marketplace and plugins" scripts/validate.sh
step "describe tests" bash plugins/describe/tests/run.sh
step "workflow tests" bash plugins/workflow/tests/run.sh
# Asserts the WIRING, not only the logic: every SKILL.md calling plugin-freshness.sh must name a
# path that resolves from its own plugin root and must pass it an argument. The first rollout of
# that check was wired to a command that could never work, and nothing went red.
step "plugin-freshness tests" bash scripts/tests/plugin-freshness.test.sh
# check-drift.sh, validate.sh and check-listing.sh are maintainer scripts; synthetic repos and a
# synthetic CLAUDE_CONFIG_DIR, so nothing here reads the machine's own installed plugins.
step "maintainer-script tests" bash scripts/tests/maintainer-scripts.test.sh

echo ""
if [ "${#failed[@]}" -eq 0 ]; then
  echo "check-all: OK — what CI runs passed"
else
  printf 'check-all: FAILED — %s\n' "${failed[@]}"
  exit 1
fi
