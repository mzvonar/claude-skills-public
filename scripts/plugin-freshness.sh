#!/usr/bin/env bash
# plugin-freshness.sh — is the skill text THIS SESSION is serving the current one?
#
#   plugin-freshness.sh [<skill-or-plugin-dir>] [--quiet] [--json]
#
# Defaults to $CLAUDE_PLUGIN_ROOT, which Claude Code sets to the plugin root of the skill
# being run — so a skill calls it with no arguments.
#
# WHY THIS EXISTS, and why check-drift.sh does not cover it.
#
# check-drift.sh compares the INSTALL RECORD against the marketplace CATALOG: "is what is
# installed behind what is published". That is one of three versions in play, and it is blind
# to the one that actually bites.
#
#   catalog    what the marketplace publishes
#   installed  what `claude plugin update` last wrote into the install record
#   loaded     the cache directory THIS SESSION resolved when it first loaded the skill
#
# `loaded` is pinned at session start and never moves again. The cache keeps every version
# side by side (nine directories for one plugin, measured), so a long session goes on serving
# the text it booted with while an update writes a new directory beside it and the record
# points at that one instead. Nothing reports this: the update prints success, check-drift
# prints "current", and the session keeps reading the old file.
#
# Measured 2026-09-25: a session served refdiff 1.4.0 for its entire length while the install
# records read 1.6.0 and 1.6.1. The two rules that session most needed — a comp's frames FORK,
# and re-run every pair after a shared-component fix — landed in 1.6.1 and were absent from
# the 1.4.0 text it was reading. It followed them only because a human had restated them in a
# handoff. The tell was one line nobody looks at: the "Base directory for this skill" the Skill
# tool prints on invocation.
#
# Exit: 0 = current · 3 = ask the user (a version is behind) · 2 = could not determine.
# 3 rather than 1 on purpose: the skill still MEASURES correctly, it may simply not know a
# newer rule, so "carry on" stays a legitimate answer and the only thing ruled out is settling
# it silently. That is the same contract refdiff's preflight uses for `action = ask`.
set -uo pipefail

DIR="" ; QUIET=0 ; JSON=0
while [ $# -gt 0 ]; do
  case "$1" in
    --quiet) QUIET=1; shift ;;
    --json)  JSON=1; shift ;;
    -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "unknown option $1" >&2; exit 2 ;;
    *) DIR="$1"; shift ;;
  esac
done
DIR="${DIR:-${CLAUDE_PLUGIN_ROOT:-}}"
[ -n "$DIR" ] || { echo "plugin-freshness: no dir and no CLAUDE_PLUGIN_ROOT" >&2; exit 2; }
DIR="$(cd "$DIR" 2>/dev/null && pwd)" || { echo "plugin-freshness: no such dir" >&2; exit 2; }

say() { [ "$QUIET" = 1 ] || printf '%s\n' "$*"; }

# ---- parse …/plugins/cache/<marketplace>/<plugin>/<version>/… ---------------
# Anything not under a plugin cache is a dev symlink or a vendored copy; those have their own
# freshness story (the owning skill's preflight) and are not this script's business.
case "$DIR" in
  */plugins/cache/*) ;;
  *) say "plugin_freshness   = skipped-not-a-plugin-install ($DIR)"; exit 0 ;;
esac
REST="${DIR#*/plugins/cache/}"
MP="${REST%%/*}"        ; REST="${REST#*/}"
PLUGIN="${REST%%/*}"    ; REST="${REST#*/}"
LOADED="${REST%%/*}"
[ -n "$MP" ] && [ -n "$PLUGIN" ] && [ -n "$LOADED" ] || {
  echo "plugin-freshness: could not read marketplace/plugin/version from $DIR" >&2; exit 2; }

PLUGROOT="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins"

# ---- installed: the highest version recorded for this plugin, any scope -----
# Several records are normal (a plugin installed at project AND local scope, as measured), and
# they can disagree, so take the highest — that is the one an update just wrote.
INSTALLED="$(python3 - "$PLUGROOT/installed_plugins.json" "$PLUGIN@$MP" <<'PY' 2>/dev/null || true
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    sys.exit(0)
recs = (d.get("plugins") or {}).get(sys.argv[2]) or []
if isinstance(recs, dict):
    recs = [recs]
vs = [r.get("version") for r in recs if isinstance(r, dict) and r.get("version")]
print(max(vs, key=lambda v: [int(x) for x in v.split(".") if x.isdigit()]) if vs else "")
PY
)"

# ---- catalog: what the marketplace publishes -------------------------------
MP_DIR="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf-8")); print(d.get(sys.argv[2],{}).get("installLocation",""))' \
  "$PLUGROOT/known_marketplaces.json" "$MP" 2>/dev/null || true)"
[ -n "$MP_DIR" ] || MP_DIR="$PLUGROOT/marketplaces/$MP"
CATALOG="$(python3 - "$MP_DIR/.claude-plugin/marketplace.json" "$PLUGIN" <<'PY' 2>/dev/null || true
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    sys.exit(0)
for p in d.get("plugins") or []:
    if p.get("name") == sys.argv[2]:
        print(p.get("version") or "")
        break
PY
)"

behind() { # behind A B  → true when A < B
  [ -n "$1" ] && [ -n "$2" ] && [ "$1" != "$2" ] && \
    [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)" = "$1" ]
}

say "  plugin             = $PLUGIN@$MP"
say "  loaded             = $LOADED"
say "  installed          = ${INSTALLED:-unknown}"
say "  catalog            = ${CATALOG:-unknown}"

ACTION="proceed"; MSG=""
if behind "$LOADED" "${INSTALLED:-}"; then
  ACTION="ask"
  MSG="This session is SERVING $PLUGIN $LOADED while $INSTALLED is installed. The version a session loads is pinned when it first runs the skill and never moves, so an update made during the session does not reach it. PUT IT TO THE USER: reload (/reload-plugins, or restart) and re-run, so the newer text is the one being followed -- or carry on with $LOADED, which still works and may simply not know a newer rule."
elif behind "${INSTALLED:-}" "${CATALOG:-}"; then
  ACTION="ask"
  MSG="$PLUGIN $INSTALLED is installed while the catalog publishes $CATALOG. PUT IT TO THE USER: update (claude plugin update $PLUGIN@$MP, or scripts/check-drift.sh --update) then reload -- or carry on."
fi
say "  action             = $ACTION"

if [ "$JSON" = 1 ]; then
  printf '{"plugin":"%s","marketplace":"%s","loaded":"%s","installed":"%s","catalog":"%s","action":"%s"}\n' \
    "$PLUGIN" "$MP" "$LOADED" "${INSTALLED:-}" "${CATALOG:-}" "$ACTION"
fi

if [ "$ACTION" = "ask" ]; then
  say ""
  say "ASK: $MSG"
  exit 3
fi
say ""
say "CURRENT"
exit 0
