#!/usr/bin/env bash
# Falsification for scripts/plugin-freshness.sh and for the way skills CALL it.
#
#   bash scripts/tests/plugin-freshness.test.sh
#
# The first group is the one that matters most, and it is the test that did not exist when this
# check first shipped: the 2026-09-26 rollout wired thirteen skills to a command that could never
# work — no argument, relying on $CLAUDE_PLUGIN_ROOT, which is a SKILL.md text substitution and
# not an exported variable — so every call exited "undetermined" and every skill's own text said
# "carry on". Nothing was red. A gate that cannot fire reads exactly like one that passed, which
# is the failure this whole script exists to detect, committed inside it.
#
# So: assert the wiring, not only the logic. Every SKILL.md that invokes the script must name a
# path that RESOLVES from that plugin's root, and must pass an argument.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$HERE/scripts/plugin-freshness.sh"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %s\n     %s\n' "$1" "$2"; }

echo "[ plugin-freshness self-test ]"

# ---- 1. THE WIRING ---------------------------------------------------------
# For every skill that calls the script, the path it names must exist relative to its plugin root,
# and the call must pass a directory argument.
WIRED=0
while IFS= read -r f; do
  WIRED=$((WIRED+1))
  plugin_root="${f%/skills/*}"
  line="$(grep -h 'plugin-freshness\.sh' "$f" | head -1)"
  # the path as written, with the placeholder resolved to this plugin's root
  rel="$(printf '%s' "$line" | sed -n 's|.*bash "\([^"]*\)".*|\1|p' | sed "s|\${CLAUDE_PLUGIN_ROOT}|$plugin_root|")"
  if [ -z "$rel" ]; then
    bad "wiring: $f" "could not parse the invocation from: $line"; continue
  fi
  [ -f "$rel" ] || { bad "wiring: $f" "path does not resolve: $rel"; continue; }
  case "$line" in
    *'plugin-freshness.sh" "${CLAUDE_PLUGIN_ROOT}"'*) ;;
    *) bad "wiring: $f" "must PASS the plugin root as an argument; got: $line"; continue ;;
  esac
  ok "wiring: $(basename "$(dirname "$f")") names a path that resolves, and passes it"
done < <(grep -rl 'plugin-freshness\.sh' "$HERE"/plugins/*/skills/*/SKILL.md 2>/dev/null)
# INVARIANT, not an observation: the number of wired skills is pinned, so a block silently deleted
# from one SKILL.md fails here instead of just removing a green row nobody counts. Adding a skill
# to the rollout means bumping this number in the same change — that is the point of it.
EXPECT_WIRED=13
[ "$WIRED" = "$EXPECT_WIRED" ] \
  && ok "wiring: exactly $EXPECT_WIRED skills invoke the check" \
  || bad "wiring count" "$WIRED skills invoke plugin-freshness.sh, expected $EXPECT_WIRED — a rollout was added or lost; update EXPECT_WIRED deliberately"

# ---- 2. THE COPIES ---------------------------------------------------------
# Every plugin that ships the script must ship the SAME script. Prose said "byte-identical" and
# nothing enforced it; two copies of a drift detector that drift is not a joke worth keeping.
while IFS= read -r c; do
  cmp -s "$SCRIPT" "$c" && ok "copy identical: ${c#$HERE/}" || bad "copy drift: ${c#$HERE/}" "differs from scripts/plugin-freshness.sh"
done < <(find "$HERE/plugins" -path '*/scripts/plugin-freshness.sh' 2>/dev/null)

# ---- 3. BEHAVIOUR ----------------------------------------------------------
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
mkcache() { # mkcache <root> <version> → echoes the fake skill dir
  local d="$1/plugins/cache/mp/thing/$2/skills/thing"; mkdir -p "$d"; echo "$d"; }
mkcfg() {  # mkcfg <cfg> <installed> <catalog>
  mkdir -p "$1/plugins/marketplaces/mp/.claude-plugin"
  printf '{"plugins":{"thing@mp":[{"scope":"local","version":"%s"}]}}\n' "$2" > "$1/plugins/installed_plugins.json"
  printf '{"mp":{"installLocation":"%s/plugins/marketplaces/mp"}}\n' "$1" > "$1/plugins/known_marketplaces.json"
  printf '{"plugins":[{"name":"thing","version":"%s"}]}\n' "$3" > "$1/plugins/marketplaces/mp/.claude-plugin/marketplace.json"; }
run() { CLAUDE_CONFIG_DIR="$1" CLAUDE_CODE_SESSION_ID="${3:-}" bash "$SCRIPT" "$2" 2>&1; }

CFG="$TMP/cfg"; mkcfg "$CFG" "2.0.0" "2.0.0"

# 3a. CONTROL. Equal versions: silent, exit 0. Without this row every row below passes against a
#     script that reports a problem unconditionally.
OUT=$(run "$CFG" "$(mkcache "$TMP/a" 2.0.0)"); E=$?
[ "$E" = 0 ] && [ -z "$OUT" ] && ok "control: up to date → SILENT, exit 0" || bad "control" "exit=$E out='$OUT'"

# 3b. The session is behind the record → ask, exit 3.
OUT=$(run "$CFG" "$(mkcache "$TMP/b" 1.0.0)"); E=$?
case "$E:$OUT" in 3:*"SERVING thing 1.0.0"*) ok "session behind the record → ask (exit 3)" ;;
  *) bad "stale session" "exit=$E out='$OUT'" ;; esac

# 3c. AHEAD is not drift.
OUT=$(run "$CFG" "$(mkcache "$TMP/c" 9.9.9)"); E=$?
[ "$E" = 0 ] && ok "session ahead of the record → not a problem (exit 0)" || bad "ahead" "exit=$E out='$OUT'"

# 3d-f. UNKNOWN IS NOT CURRENT — absent, malformed, and silent-about-this-plugin.
D=$(mkcache "$TMP/d" 1.0.0)
CFG_ABS="$TMP/cfgabs"; mkcfg "$CFG_ABS" "2.0.0" "2.0.0"; rm -f "$CFG_ABS/plugins/installed_plugins.json"
OUT=$(run "$CFG_ABS" "$D"); E=$?
case "$E:$OUT" in 2:*UNKNOWN*) ok "record absent → UNKNOWN, exit 2 (never 'current')" ;;
  *) bad "unknown/absent" "exit=$E out='$OUT'" ;; esac

CFG_BAD="$TMP/cfgbad"; mkcfg "$CFG_BAD" "2.0.0" "2.0.0"; printf '{oops' > "$CFG_BAD/plugins/installed_plugins.json"
OUT=$(run "$CFG_BAD" "$D"); E=$?
case "$E:$OUT" in 2:*UNKNOWN*) ok "record malformed → UNKNOWN, exit 2" ;;
  *) bad "unknown/malformed" "exit=$E out='$OUT'" ;; esac

CFG_OTHER="$TMP/cfgother"; mkcfg "$CFG_OTHER" "2.0.0" "2.0.0"
printf '{"plugins":{"somethingelse@mp":[{"scope":"local","version":"9.9.9"}]}}\n' > "$CFG_OTHER/plugins/installed_plugins.json"
OUT=$(run "$CFG_OTHER" "$D"); E=$?
case "$E:$OUT" in 2:*UNKNOWN*) ok "record names no version for THIS plugin → UNKNOWN, exit 2" ;;
  *) bad "unknown/other" "exit=$E out='$OUT'" ;; esac

# 3g-h. WIRING BUGS are exit 4, distinct from 'could not determine'.
OUT=$(CLAUDE_CONFIG_DIR="$CFG" bash "$SCRIPT" 2>&1); E=$?
case "$E:$OUT" in 4:*"WIRING BUG"*) ok "no argument and no env var → WIRING BUG, exit 4" ;;
  *) bad "wiring/no-arg" "exit=$E out='$OUT'" ;; esac

OUT=$(CLAUDE_CONFIG_DIR="$CFG" bash "$SCRIPT" '${CLAUDE_PLUGIN_ROOT}' 2>&1); E=$?
case "$E:$OUT" in 4:*"WIRING BUG"*) ok "unexpanded placeholder → WIRING BUG, exit 4" ;;
  *) bad "wiring/placeholder" "exit=$E out='$OUT'" ;; esac

# 3i. A malformed cache path must not parse into garbage and report clean.
SHORT="$TMP/short/plugins/cache/onlymp"; mkdir -p "$SHORT"
OUT=$(CLAUDE_CONFIG_DIR="$CFG" bash "$SCRIPT" "$SHORT" 2>&1); E=$?
case "$E:$OUT" in 2:*"not a <marketplace>/<plugin>/<version>"*) ok "short cache path → exit 2, not a bogus 'current'" ;;
  *) bad "short path" "exit=$E out='$OUT'" ;; esac

# 3j. Not a plugin install at all (dev symlink, vendored copy) → silent, exit 0, not this script's business.
mkdir -p "$TMP/plain"
OUT=$(CLAUDE_CONFIG_DIR="$CFG" bash "$SCRIPT" "$TMP/plain" 2>&1); E=$?
[ "$E" = 0 ] && [ -z "$OUT" ] && ok "not a plugin install → silent, exit 0" || bad "non-cache dir" "exit=$E out='$OUT'"

# 3k. ASK ONCE PER SESSION. Stateless re-asking is what made this self-triggering: the skill that
#     runs `claude plugin update` CREATES the skew it then complains about, for every later skill.
D2=$(mkcache "$TMP/k" 1.0.0)
E1=$(run "$CFG" "$D2" "sess-$$" >/dev/null 2>&1; echo $?)
E2=$(run "$CFG" "$D2" "sess-$$" >/dev/null 2>&1; echo $?)
E3=$(run "$CFG" "$D2" "other-$$" >/dev/null 2>&1; echo $?)
case "$E1:$E2:$E3" in 3:0:3) ok "asks once per session, re-arms for a different session" ;;
  *) bad "session ack" "first=$E1 second=$E2 other-session=$E3 (want 3:0:3)" ;; esac
rm -f "${TMPDIR:-/tmp}"/claude-plugin-freshness.sess-$$.* "${TMPDIR:-/tmp}"/claude-plugin-freshness.other-$$.*

echo ""
echo "  ${PASS} passed, ${FAIL} failed"
[ "$FAIL" = 0 ] || exit 1
