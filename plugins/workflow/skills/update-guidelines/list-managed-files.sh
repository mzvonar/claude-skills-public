#!/usr/bin/env bash
# List project-managed agent and skill files.
#
# Scans .claude/agents/*.md and .claude/skills/*/SKILL.md and prints the paths
# of files whose YAML frontmatter contains `managed-by: project`. Files without
# that field (BMad, Playwright, and other externally managed tooling) are
# skipped.
#
# Run from the project root:
#   .claude/skills/update-guidelines/list-managed-files.sh
#
# Exit code is always 0 when the scan completes, even if no matches are found.

set -euo pipefail

for f in .claude/agents/*.md .claude/skills/*/SKILL.md; do
  [ -f "$f" ] || continue
  if awk '
    NR == 1 && $0 != "---" { exit 1 }
    NR == 1 { next }
    /^---$/ { exit }
    /^managed-by:[[:space:]]*project[[:space:]]*$/ { found = 1 }
    END { exit !found }
  ' "$f" 2>/dev/null; then
    echo "$f"
  fi
done | sort
