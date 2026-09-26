#!/usr/bin/env bash
# check-listing.sh — does this marketplace's listing carry a plugin's current version?
#
#   bash <marketplace>/scripts/check-listing.sh <plugin-repo-dir> [--published]
#
# For a plugin whose source is its OWN repo (the `github` entries — refdiff, svc) a release is TWO
# pushes. The version `claude plugin update` compares lives in that repo's
# .claude-plugin/plugin.json; the entry in THIS repo's .claude-plugin/marketplace.json has to be
# bumped to match by hand, in a second push here, or the listing lies. validate.sh has paired the two
# for a while — but it runs only in THIS repo, and a release happens in the OTHER one, so nothing on
# the path of a release ever looked. refdiff 1.8.0 (2026-09-26) shipped from the refdiff repo alone
# and the listing stayed at 1.7.3 until someone asked. This is that pairing, callable from the
# plugin's side; validate.sh calls it too, so there is one implementation of the comparison.
#
#   <plugin-repo-dir>  the plugin's checkout; its .claude-plugin/plugin.json gives name and version
#   --published        compare against the listing on this repo's origin/main (fetched first), not
#                      the working tree — the question AFTER both pushes, where a bump made here and
#                      never pushed must not read as done
#
# exit: 0 the two agree
#       1 they disagree, or the listing has no entry for the plugin (both sides printed, and the fix)
#       2 could not determine (an unreadable manifest, no origin) — never a pass
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_DIR="${1:-}"
MODE="${2:-}"
[ -n "$PLUGIN_DIR" ] || { echo "usage: check-listing.sh <plugin-repo-dir> [--published]" >&2; exit 2; }
case "$MODE" in "" | --published) ;; *) echo "check-listing: unknown option '$MODE'" >&2; exit 2 ;; esac

if [ "$MODE" = --published ]; then
  git -C "$ROOT" fetch -q origin main 2>/dev/null \
    || { echo "check-listing: could not fetch origin main in $ROOT — not verified"; exit 2; }
  LISTING=$(git -C "$ROOT" show origin/main:.claude-plugin/marketplace.json 2>/dev/null) \
    || { echo "check-listing: origin/main in $ROOT has no .claude-plugin/marketplace.json — not verified"; exit 2; }
  WHERE="origin/main of $ROOT"
else
  LISTING=$(cat "$ROOT/.claude-plugin/marketplace.json" 2>/dev/null) \
    || { echo "check-listing: $ROOT/.claude-plugin/marketplace.json is missing — not verified"; exit 2; }
  WHERE="$ROOT, working tree"
fi

LISTING="$LISTING" python3 - "$PLUGIN_DIR" "$WHERE" <<'PY'
import json, os, sys
pdir, where = sys.argv[1], sys.argv[2]
pj = os.path.join(pdir, ".claude-plugin", "plugin.json")
try:
    p = json.load(open(pj))
except Exception as exc:
    print(f"check-listing: {pj} is unreadable ({exc.__class__.__name__}) — not verified"); sys.exit(2)
try:
    mp = json.loads(os.environ["LISTING"])
except Exception as exc:
    print(f"check-listing: the listing ({where}) is unreadable ({exc.__class__.__name__}) — not verified"); sys.exit(2)
name, version = p.get("name"), p.get("version")
entry = next((e for e in mp.get("plugins", []) if e.get("name") == name), None)
if entry is None:
    print(f"check-listing: {name}: no entry in the listing ({where})"); sys.exit(1)
if entry.get("version") != version:
    print(f"check-listing: {name}: {pj} version {version} != listing {entry.get('version')} ({where})")
    print(f"  fix: set the \"{name}\" entry's \"version\" to {version} in .claude-plugin/marketplace.json,")
    print(f"       commit \"chore: {name} {version} in the listing\" and push main")
    sys.exit(1)
print(f"check-listing: {name} {version} — the listing agrees ({where})")
PY
