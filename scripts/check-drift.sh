#!/usr/bin/env bash
# check-drift.sh — are the plugins installed from this marketplace behind the catalog?
#
#   check-drift.sh [--marketplace <name>] [--offline] [--update] [--json] [plugin ...]
#
# Refreshes the marketplace catalog (unless --offline), then compares each installed plugin's
# version against the catalog entry. Exit 0 = all current, 1 = at least one stale, 2 = error.
# --update runs `claude plugin update <plugin>@<marketplace>` for every stale plugin.
# Only plugins installed at user scope, or at project/local scope for the current repo, are checked.
#
# Replaces the per-skill sync-skill.sh vendoring scripts: the plugin cache is the copy, the
# marketplace is the upstream, and the version field is the pin.
set -euo pipefail
MP="claude-skills-public"; OFFLINE=0; UPDATE=0; JSON=0; ONLY=()
while [ $# -gt 0 ]; do
  case "$1" in
    --marketplace) MP="$2"; shift 2 ;;
    --offline) OFFLINE=1; shift ;;
    --update) UPDATE=1; shift ;;
    --json) JSON=1; shift ;;
    -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "unknown option $1" >&2; exit 2 ;;
    *) ONLY+=("$1"); shift ;;
  esac
done
command -v claude >/dev/null 2>&1 || { echo "claude CLI not found" >&2; exit 2; }
PLUG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins"
INSTALLED="$PLUG/installed_plugins.json"
# The catalog lives wherever Claude Code registered the marketplace (git clone under plugins/marketplaces,
# or a local directory for a directory-sourced marketplace).
MP_DIR="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get(sys.argv[2],{}).get("installLocation",""))' "$PLUG/known_marketplaces.json" "$MP" 2>/dev/null || true)"
[ -n "$MP_DIR" ] || MP_DIR="$PLUG/marketplaces/$MP"
CATALOG="$MP_DIR/.claude-plugin/marketplace.json"

if [ "$OFFLINE" = 0 ]; then
  claude plugin marketplace update "$MP" >/dev/null 2>&1 || echo "warn: could not refresh marketplace '$MP' (offline?)" >&2
fi
[ -f "$CATALOG" ] || { echo "marketplace '$MP' is not known (add it: claude plugin marketplace add mzvonar/$MP)" >&2; exit 2; }
[ -f "$INSTALLED" ] || { echo "no plugins installed" >&2; exit 2; }

# Project-scope install records are keyed to the path the plugin was installed FROM. Inside a git
# worktree `--show-toplevel` returns the WORKTREE, which never matches a record written from the
# main checkout, so every project-scope plugin was filtered out while the table still printed a
# confident `stale:` line. Measured 2026-09-26 from a worktree: 2 rows where 10 belong — the two
# user-scope entries survived the filter and 8 project/local ones vanished. (Not 13: the install
# record held 15 entries, but 5 of them belong to other marketplaces and this script never reports
# those, so they were never the bug's to hide.)
#
# So we accept EITHER path, rather than swapping one for the other. A first attempt used
# `dirname(--git-common-dir)` alone, which fixes worktrees and breaks two other shapes — measured
# with git 2.43:
#
#   shape              dirname(--git-common-dir)    --show-toplevel
#   linked worktree    the main checkout  ✅         the worktree
#   submodule          <super>/.git/modules  ✗       <super>/sub  ✅
#   bare repo          <parent of repo.git>  ✗       (fails → pwd)
#
# i.e. it moved the same disappearing-rows bug to submodules, and broke a record installed from
# inside a worktree, which used to match. `--git-dir` equals `--git-common-dir` everywhere EXCEPT
# a linked worktree, so that inequality is the clean discriminator — no guessing from path shape.
TOP="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
GIT_DIR_ABS="$(git rev-parse --path-format=absolute --git-dir 2>/dev/null || true)"
GIT_COMMON_ABS="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
# git < 2.31 has no `--path-format`, and `rev-parse` ECHOES an unrecognised option and exits 0
# rather than failing — so `|| true` never fires and these hold a two-line string starting with
# the flag. `dirname` then errors out under `set -e` and the script exits 1, which its own header
# documents as "at least one stale". Accept only a single absolute path.
for _v in GIT_DIR_ABS GIT_COMMON_ABS; do
  eval "_val=\$$_v"
  case "$_val" in
    /*) [ "$_val" = "${_val%%$'\n'*}" ] || eval "$_v=''" ;;
    *)  eval "$_v=''" ;;
  esac
done
PROJECT="$TOP"
PROJECT_MAIN="$TOP"
if [ -n "$GIT_COMMON_ABS" ] && [ -n "$GIT_DIR_ABS" ] && [ "$GIT_DIR_ABS" != "$GIT_COMMON_ABS" ]; then
  PROJECT_MAIN="$(dirname "$GIT_COMMON_ABS")"   # a LINKED worktree, and only that
fi
export MP CATALOG INSTALLED PROJECT PROJECT_MAIN JSON
ONLY_CSV="$(IFS=,; echo "${ONLY[*]:-}")"; export ONLY_CSV

STALE=$(python3 - <<'PY'
import json, os, sys
mp, catalog, installed = os.environ["MP"], os.environ["CATALOG"], os.environ["INSTALLED"]
# Two acceptable paths, not one: the tree we are standing in, and — when that is a linked
# worktree — the main checkout a project-scope record would have been written from. Matching
# either is what stops a record disappearing for one repo shape or the other.
projects = {os.path.realpath(p) for p in (os.environ["PROJECT"], os.environ["PROJECT_MAIN"]) if p}
only = set(filter(None, os.environ["ONLY_CSV"].split(",")))
cat = {p["name"]: p.get("version") for p in json.load(open(catalog))["plugins"]}
inst = json.load(open(installed)).get("plugins", {})
rows = []
for key, entries in inst.items():
    name, _, m = key.rpartition("@")
    if m != mp or (only and name not in only): continue
    for e in entries:
        scope = e.get("scope")
        if scope in ("project", "local") and os.path.realpath(e.get("projectPath", "")) not in projects: continue
        have = e.get("version"); want = cat.get(name)
        state = "unknown" if want is None else ("current" if have == want else "stale")
        rows.append((name, scope, have, want, state))
if os.environ["JSON"] == "1":
    print(json.dumps([dict(zip(("plugin","scope","installed","catalog","state"), r)) for r in rows], indent=1), file=sys.stderr)
else:
    w = max([len(r[0]) for r in rows] + [6])
    print(f"{'plugin':<{w}}  {'scope':<7}  {'installed':<12}  {'catalog':<12}  state", file=sys.stderr)
    for r in rows: print(f"{r[0]:<{w}}  {r[1]:<7}  {str(r[2]):<12}  {str(r[3]):<12}  {r[4]}", file=sys.stderr)
    if not rows: print(f"(nothing from '{mp}' is installed for this scope)", file=sys.stderr)
print(" ".join(sorted({f"{r[0]}:{r[1]}" for r in rows if r[4] == "stale"})))
PY
)
if [ -z "$STALE" ]; then exit 0; fi
if [ "$UPDATE" = 1 ]; then
  for ps in $STALE; do p="${ps%%:*}"; sc="${ps##*:}"; echo "updating $p@$MP ($sc scope)" >&2; claude plugin update "$p@$MP" --scope "$sc"; done
  exit 0
fi
echo "stale: $(echo "$STALE" | sed -E "s/:[a-z]+//g")  (run: $0 --update, or: claude plugin update <plugin>@$MP --scope <scope>)" >&2
exit 1
