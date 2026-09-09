#!/usr/bin/env bash
# Every test in the workflow plugin. node stdlib + python3 only — no install, no network.
# Paths resolve from this file's location, so it runs from any cwd:
#   bash plugins/workflow/tests/run.sh
set -euo pipefail
cd "$(dirname "$0")/.."
for f in skills/*/scripts/*.mjs; do node --check "$f"; done
for f in skills/*/scripts/*.py; do python3 -m py_compile "$f"; done
for f in skills/*/scripts/*.sh; do bash -n "$f"; done
node --test "tests/*.test.mjs"
