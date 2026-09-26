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
# One scratch tree for the whole run: section 1 needs it to build cache-shaped roots, section 3
# for its fixtures. Created here rather than beside the fixtures so both can use it.
TMPDIR_T=$(mktemp -d); trap 'rm -rf "$TMPDIR_T"' EXIT
SCRIPT="$HERE/scripts/plugin-freshness.sh"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %s\n     %s\n' "$1" "$2"; }

echo "[ plugin-freshness self-test ]"

# ---- 1. THE WIRING ---------------------------------------------------------
# This section was rewritten after a review demonstrated that its first version passed the ORIGINAL
# INCIDENT. Six corruptions of a SKILL.md all went green: the block moved into a trailing appendix
# the skill never reaches; a second, wrong invocation after a good one (it read `head -1`); a path
# that resolves in the repo but cannot in a plugin cache; the heading rewritten to "Never run the
# freshness check; it is obsolete"; and — the incident verbatim — every exit-code instruction
# stripped and "not a pass" reverted to "undetermined, carry on".
#
# The lesson is that a wiring test which checks only the COMMAND STRING certifies a gate it has not
# shown to be reachable or obeyed. So each wired skill is now checked four ways: the path resolves
# in a CACHE-SHAPED tree (not the repo's), EVERY invocation line is the canonical one, the block
# appears before the skill's first real step, and the text still tells the agent what the exit
# codes mean.
#
# A cache root is `<cache>/<marketplace>/<plugin>/<version>` — `scripts/` sits directly under it.
# In the repo the same relative path also resolves from `plugins/<plugin>/`, which is why a
# `../../scripts/...` escape (the shape the reverted rollout used) passed before.
CACHE="$TMPDIR_T/cache/mp"
mkdir -p "$CACHE"
CANON_CALL='bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-freshness.sh" "${CLAUDE_PLUGIN_ROOT}"'
WIRED_SET=""
while IFS= read -r f; do
  skill="$(basename "$(dirname "$f")")"
  plugin="$(basename "${f%/skills/*}")"
  WIRED_SET="${WIRED_SET}${plugin}/${skill}"$'\n'
  # Build a cache-shaped root for this plugin: its own subtree at <cache>/mp/<plugin>/0.0.0/.
  root="$CACHE/$plugin/0.0.0"
  [ -d "$root" ] || { mkdir -p "$(dirname "$root")"; cp -r "${f%/skills/*}" "$root"; }

  bad_file=0
  # (a) EVERY line that mentions the script must be the canonical invocation — not just the first.
  n_lines=0
  while IFS= read -r line; do
    n_lines=$((n_lines+1))
    case "$line" in
      *"$CANON_CALL"*) ;;
      *) bad "wiring: $plugin/$skill" "non-canonical invocation: $(printf '%s' "$line" | sed 's/^ *//')"; bad_file=1 ;;
    esac
    # (b) the path it names must resolve inside a CACHE-shaped root
    rel="$(printf '%s' "$line" | sed -n 's|.*bash "\([^"]*\)".*|\1|p' | sed "s|\${CLAUDE_PLUGIN_ROOT}|$root|")"
    [ -n "$rel" ] && [ -f "$rel" ] || { bad "wiring: $plugin/$skill" "path does not resolve in a plugin cache: ${rel:-<unparsed>}"; bad_file=1; }
  done < <(grep -h 'plugin-freshness\.sh' "$f")
  [ "$n_lines" -gt 0 ] || { bad "wiring: $plugin/$skill" "no invocation found"; bad_file=1; }

  # (c) SEMANTICS. The incident was not a bad path — it was text telling the agent to ignore the
  # result. The block must still say what 3, 2 and 4 mean, and must not tell the reader to carry on
  # from a 2.
  body="$(cat "$f")"
  case "$body" in *'**3**'*) ;; *) bad "wiring: $plugin/$skill" "no exit-3 instruction"; bad_file=1 ;; esac
  case "$body" in *'**4**'*) ;; *) bad "wiring: $plugin/$skill" "no exit-4 instruction"; bad_file=1 ;; esac
  case "$body" in *'not a pass'*) ;; *) bad "wiring: $plugin/$skill" "exit 2 is not described as 'not a pass'"; bad_file=1 ;; esac
  # The HEADING is pinned for the same reason the command is: a block whose mechanics are intact
  # under a heading reading "Never run the freshness check; it is obsolete" passed every other
  # assertion here. Six wordings are in use and all share this phrase.
  grep -qi 'session reading the CURRENT skill text' "$f" \
    || { bad "wiring: $plugin/$skill" "block heading does not introduce the freshness check"; bad_file=1; }

  # (d) REACHABILITY, approximated the only way a text check can: the block must come before the
  # skill's first numbered step, and before any other bash fence.
  blk="$(grep -n 'plugin-freshness\.sh' "$f" | head -1 | cut -d: -f1)"
  # The same two step STYLES the census matches, or this check is blind to a skill whose first
  # instruction is a `## Step 1 —` heading rather than a `1.` list item — and a block moved below
  # one of those would pass the very assertion written to catch it.
  first_step="$(grep -nE '^\s*(###? )?[*]{0,2}1\.|^## Step 1' "$f" | head -1 | cut -d: -f1)"
  if [ -n "$first_step" ] && [ "$blk" -gt "$first_step" ]; then
    bad "wiring: $plugin/$skill" "block at line $blk comes AFTER the first numbered step at $first_step"; bad_file=1
  fi
  [ "$bad_file" = 0 ] && ok "wiring: $plugin/$skill resolves in a cache, is canonical, keeps its exit-code contract, and precedes step 1"
done < <(grep -rl 'plugin-freshness\.sh' "$HERE"/plugins/*/skills/*/SKILL.md 2>/dev/null | sort)

# ---- 1b. THE CENSUS, derived rather than counted ---------------------------
# A hand-kept count catches a block that is DELETED and misses one that is never ADDED — measured:
# adding a skill with numbered steps and no block left the count at 20 and the suite green, which
# is the original failure displaced into the future. A compensating pair (remove one, add one)
# passed too. So compare SETS: every skill with a numbered first step must be wired, except an
# explicit exemption list that has to name a reason.
EXEMPT="next-js/cache-invalidation"   # reference page: headings only, no numbered steps
MISSING=""
while IFS= read -r f; do
  grep -q 'plugin-freshness\.sh' "$f" && continue
  grep -qE '^\s*(###? )?[*]{0,2}1\.|^## Step 1' "$f" || continue
  skill="$(basename "$(dirname "$f")")"; plugin="$(basename "${f%/skills/*}")"
  case " $EXEMPT " in *" $plugin/$skill "*) continue ;; esac
  MISSING="${MISSING}${plugin}/${skill} "
done < <(find "$HERE/plugins" -name SKILL.md | sort)
[ -z "$MISSING" ] \
  && ok "census: every skill with a numbered first step is wired (exempt: $EXEMPT)" \
  || bad "census" "unwired skills with a numbered first step: $MISSING"

# ---- 2. THE COPIES ---------------------------------------------------------
# Every plugin that ships the script must ship the SAME script. Prose said "byte-identical" and
# nothing enforced it; two copies of a drift detector that drift is not a joke worth keeping.
while IFS= read -r c; do
  cmp -s "$SCRIPT" "$c" && ok "copy identical: ${c#$HERE/}" || bad "copy drift: ${c#$HERE/}" "differs from scripts/plugin-freshness.sh"
done < <(find "$HERE/plugins" -path '*/scripts/plugin-freshness.sh' 2>/dev/null)

# 2b. The copies in the OTHER TWO REPOS. `refdiff` and `svc` ship their own plugins from their own
# repos, so their copies are the two this suite could never see — and nothing else could either,
# which left the parity claim in docs/conventions.md resting on somebody remembering. When a
# checkout sits beside this one, check it; when it does not, say SKIPPED rather than nothing.
#
# The rule is CODE identity, not byte identity: a copy may add a provenance comment naming the
# canonical file (refdiff's does), and forbidding that would fail the honest copy while catching no
# drift. Every line that can BEHAVE must still match exactly.
code_only() { grep -vE '^\s*(#|$)' "$1"; }
for ext in refdiff:skills/refdiff/plugin-freshness.sh svc:scripts/plugin-freshness.sh; do
  repo="${ext%%:*}"; rel="${ext#*:}"
  cand="$(dirname "$HERE")/$repo/$rel"
  if [ ! -f "$cand" ]; then
    ok "copy parity: $repo not checked out beside this one — SKIPPED, not verified"
    continue
  fi
  if diff -q <(code_only "$SCRIPT") <(code_only "$cand") >/dev/null; then
    ok "copy parity: $repo/$rel matches line for line, comments aside"
  else
    bad "copy parity: $repo/$rel" "executable lines differ from scripts/plugin-freshness.sh:
     $(diff <(code_only "$SCRIPT") <(code_only "$cand") | head -8 | tr '\n' '|' | sed 's/|/\n     /g')"
  fi
done

# ---- 3. BEHAVIOUR ----------------------------------------------------------
TMP="$TMPDIR_T/behaviour"; mkdir -p "$TMP"
mkcache() { # mkcache <root> <version> → echoes the fake skill dir
  local d="$1/plugins/cache/mp/thing/$2/skills/thing"; mkdir -p "$d"; echo "$d"; }
mkcfg() {  # mkcfg <cfg> <installed> <catalog> [extra-record-json]
  mkdir -p "$1/plugins/marketplaces/mp/.claude-plugin"
  if [ -n "${4:-}" ]; then
    printf '{"plugins":{"thing@mp":%s}}\n' "$4" > "$1/plugins/installed_plugins.json"
  else
    printf '{"plugins":{"thing@mp":[{"scope":"local","version":"%s"}]}}\n' "$2" > "$1/plugins/installed_plugins.json"
  fi
  printf '{"mp":{"installLocation":"%s/plugins/marketplaces/mp"}}\n' "$1" > "$1/plugins/known_marketplaces.json"
  printf '{"plugins":[{"name":"thing","version":"%s"}]}\n' "$3" > "$1/plugins/marketplaces/mp/.claude-plugin/marketplace.json"; }
# CLAUDE_CODE_SESSION_ID is pinned to empty on every call, not just inside run(): rows below that
# invoke the script directly used to inherit the REAL session id from the environment, which is
# ambient state leaking into a fixture — the same class refdiff's selftest had to fix.
# FLAGS are forwarded: four mutation survivors existed purely because this helper could not pass
# --quiet / --json / --verbose, so nothing exercised them.
run() { local cfg="$1" dir="$2"; shift 2
  CLAUDE_CONFIG_DIR="$cfg" CLAUDE_CODE_SESSION_ID="" bash "$SCRIPT" "$dir" "$@" 2>&1; }

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

# 3k. STATELESS. A once-per-session ack lived here briefly and was removed with four defects (see
#     the script header). This row pins the property that replaced it: the same skew reports the
#     same way every time, and the script leaves nothing behind between calls. A reintroduced
#     stamp would turn the second call into exit 0 and fail here.
D2=$(mkcache "$TMP/k" 1.0.0)
# Count the ARTIFACT, not the directory: /tmp is shared and busy, so a whole-directory count drifts
# under any concurrent process and makes this row flaky. Name what must not appear.
BEFORE=$(find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'claude-plugin-freshness.*' 2>/dev/null | wc -l)
E1=$(run "$CFG" "$D2" >/dev/null 2>&1; echo $?)
E2=$(run "$CFG" "$D2" >/dev/null 2>&1; echo $?)
E3=$(run "$CFG" "$D2" >/dev/null 2>&1; echo $?)
AFTER=$(find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'claude-plugin-freshness.*' 2>/dev/null | wc -l)
case "$E1:$E2:$E3" in 3:3:3) ok "stateless: the same skew reports identically on every call" ;;
  *) bad "statelessness" "exits were $E1:$E2:$E3 (want 3:3:3) — has a per-session ack come back?" ;; esac
[ "$BEFORE" = "$AFTER" ] && ok "stateless: writes no ack/stamp file" \
  || bad "statelessness" "claude-plugin-freshness.* files went $BEFORE -> $AFTER"

# 3l. SEVERAL RECORDS, take the HIGHEST. Documented in the reader's comment as a measured real
#     shape (a plugin installed at project AND local scope); `max` -> `min` survived every row.
CFGM="$TMP/cfgmulti"
mkcfg "$CFGM" "" "3.0.0" '[{"scope":"project","version":"1.0.0"},{"scope":"local","version":"2.0.0"}]'
OUT=$(run "$CFGM" "$(mkcache "$TMP/l" 1.0.0)" --quiet --json); E=$?
case "$E:$OUT" in 3:*'"installed":"2.0.0"'*) ok "several records → takes the highest (2.0.0, not 1.0.0)" ;;
  *) bad "max-of-records" "exit=$E out='$OUT'" ;; esac

# 3m. A record that arrives as a bare OBJECT rather than a list — the other real shape the reader
#     normalises, and also unpinned until now.
CFGD="$TMP/cfgdict"
mkcfg "$CFGD" "" "3.0.0" '{"scope":"local","version":"2.0.0"}'
OUT=$(run "$CFGD" "$(mkcache "$TMP/m" 1.0.0)" --quiet --json); E=$?
case "$E:$OUT" in 3:*'"installed":"2.0.0"'*) ok "record as a bare object → normalised, not UNKNOWN" ;;
  *) bad "dict-shaped record" "exit=$E out='$OUT'" ;; esac

# 3n. THE SECOND ASK ARM: install behind catalog. Every earlier fixture passed catalog == installed,
#     so this arm never fired here — `elif false` survived — and its remedy is the opposite one.
CFGC="$TMP/cfgcat"; mkcfg "$CFGC" "1.0.0" "2.0.0"
OUT=$(run "$CFGC" "$(mkcache "$TMP/n" 1.0.0)"); E=$?
case "$E:$OUT" in 3:*"claude plugin update"*) ok "install behind catalog → ask naming UPDATE, not reload" ;;
  *) bad "catalog arm" "exit=$E out='$OUT'" ;; esac

# 3o. THE JSON CONTRACT, per action value. refdiff's preflight branches on this ONE field and this
#     repo owns the script, yet nothing here invoked --json: hardcoding `action` to "proceed"
#     survived, which is precisely what would resurrect the affirmative-currency bug downstream.
J_OK=1
for spec in "2.0.0:proceed" "1.0.0:ask"; do
  v="${spec%%:*}"; want="${spec##*:}"
  OUT=$(run "$CFG" "$(mkcache "$TMP/j$want" "$v")" --quiet --json)
  case "$OUT" in *"\"action\":\"$want\""*) ;; *) bad "json contract" "loaded=$v wanted action=$want, got: $OUT"; J_OK=0 ;; esac
done
OUT=$(run "$CFG_ABS" "$(mkcache "$TMP/junk" 1.0.0)" --quiet --json)
case "$OUT" in *'"action":"unknown"'*) ;; *) bad "json contract" "unreadable record wanted action=unknown, got: $OUT"; J_OK=0 ;; esac
[ "$J_OK" = 1 ] && ok "--json reports each action value (proceed / ask / unknown)"

# 3p. --quiet SUPPRESSES the human block, --verbose RESTORES it. Both were unreachable from this
#     file until run() learned to forward flags.
OUT=$(run "$CFG" "$(mkcache "$TMP/p" 1.0.0)" --quiet)
[ -z "$OUT" ] && ok "--quiet on an ask prints nothing" || bad "--quiet" "expected silence, got: $OUT"
OUT=$(run "$CFG" "$(mkcache "$TMP/p2" 2.0.0)" --verbose)
case "$OUT" in *CURRENT*) ok "--verbose on a clean run restores the facts" ;;
  *) bad "--verbose" "expected the fact block, got: '$OUT'" ;; esac

# 3q. A DEGRADED RUN IS NEVER SILENT. An unreadable catalog leaves only half the check able to run;
#     that note used to sit behind --verbose, making it identical to a clean pass.
CFGNC="$TMP/cfgnocat"; mkcfg "$CFGNC" "1.0.0" "1.0.0"
rm -f "$CFGNC/plugins/marketplaces/mp/.claude-plugin/marketplace.json"
OUT=$(run "$CFGNC" "$(mkcache "$TMP/q" 1.0.0)"); E=$?
case "$E:$OUT" in 0:*"catalog version unknown"*) ok "catalog unreadable → says so, never a silent pass" ;;
  *) bad "half-check silent" "exit=$E out='$OUT'" ;; esac

# 3r. python3 missing names ITSELF as the cause. Otherwise an agent on a Mac without CLT is sent to
#     inspect an install record that is perfectly fine, on every invocation of every wired skill.
FAKEBIN="$TMP/nopy"; mkdir -p "$FAKEBIN"
for c in bash sed grep cat ls printf sort head dirname basename mktemp cp mkdir rm cmp find; do
  p="$(command -v "$c" 2>/dev/null)" && ln -sf "$p" "$FAKEBIN/$c"
done
OUT=$(CLAUDE_CONFIG_DIR="$CFG" CLAUDE_CODE_SESSION_ID="" PATH="$FAKEBIN" bash "$SCRIPT" "$(mkcache "$TMP/r" 1.0.0)" 2>&1); E=$?
case "$E:$OUT" in 2:*python3*) ok "python3 missing → UNKNOWN naming python3, not the install record" ;;
  *) bad "no python3" "exit=$E out='$OUT'" ;; esac

# 3s. An unknown FLAG is a caller bug (4), not "could not determine" (2) — every skill block tells
#     the agent to carry on from a 2, so a typo'd flag used to disable the gate silently.
OUT=$(run "$CFG" "$(mkcache "$TMP/s" 1.0.0)" --nonsense); E=$?
case "$E:$OUT" in 4:*"WIRING BUG"*) ok "unknown flag → WIRING BUG, exit 4 (not 2)" ;;
  *) bad "unknown flag" "exit=$E out='$OUT'" ;; esac

# 3t. The "no such dir" error must NAME the directory. A failed command substitution clears the
#     variable before the || body runs, so this used to print an empty path.
OUT=$(run "$CFG" "$TMP/definitely-not-here"); E=$?
case "$E:$OUT" in 4:*"definitely-not-here"*) ok "unresolvable dir → exit 4 naming the path" ;;
  *) bad "no such dir" "exit=$E out='$OUT'" ;; esac

echo ""
echo "  ${PASS} passed, ${FAIL} failed"
[ "$FAIL" = 0 ] || exit 1
