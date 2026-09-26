#!/usr/bin/env bash
# Falsification for the two maintainer scripts, both of which shipped with no test at all.
#
#   bash scripts/tests/maintainer-scripts.test.sh
#
# check-drift.sh's project resolution is a 3-row table in a comment and nothing pinned it: a review
# reverted it with ONE line (PROJECT_MAIN="$TOP") and the only observable was a row count nobody
# asserted — the exact "2 rows where 10 belong" bug, restored silently. validate.sh's external
# version pairing had never been observed to fire at all.
#
# Both run against SYNTHETIC repos and a synthetic CLAUDE_CONFIG_DIR, so nothing here depends on
# what happens to be installed or checked out on the machine running it.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %s\n     %s\n' "$1" "$2"; }
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
export GIT_CEILING_DIRECTORIES="$TMP"   # git walks UP; stop it escaping the fixture

echo "[ maintainer-scripts self-test ]"

# ============ check-drift.sh ================================================
# A stub `claude` on PATH: the script exits 2 without one, and we must not touch the real CLI.
STUB="$TMP/bin"; mkdir -p "$STUB"
printf '#!/usr/bin/env bash\nexit 0\n' > "$STUB/claude"; chmod +x "$STUB/claude"

mkrepo() { git init -q "$1"; git -C "$1" -c user.email=a@b -c user.name=t commit -q --allow-empty -m init; }
mkcfg() { # mkcfg <cfgdir> <projectPath>  — one project-scope record keyed to <projectPath>
  mkdir -p "$1/plugins/marketplaces/claude-skills-public/.claude-plugin"
  printf '{"plugins":{"thing@claude-skills-public":[{"scope":"project","projectPath":"%s","version":"1.0.0"}]}}\n' "$2" \
    > "$1/plugins/installed_plugins.json"
  printf '{"claude-skills-public":{"installLocation":"%s/plugins/marketplaces/claude-skills-public"}}\n' "$1" \
    > "$1/plugins/known_marketplaces.json"
  printf '{"plugins":[{"name":"thing","version":"1.0.0"}]}\n' \
    > "$1/plugins/marketplaces/claude-skills-public/.claude-plugin/marketplace.json"; }

drift_rows() { # drift_rows <cwd> <cfgdir> → number of `thing` rows reported
  ( cd "$1" && PATH="$STUB:$PATH" CLAUDE_CONFIG_DIR="$2" \
      bash "$HERE/scripts/check-drift.sh" --offline 2>&1 | grep -c '^thing ' ) || true; }

MAIN="$TMP/main"; mkrepo "$MAIN"
CFG="$TMP/cfg"; mkcfg "$CFG" "$MAIN"

# 1. From the main checkout the record matches — the baseline everything else is measured against.
R=$(drift_rows "$MAIN" "$CFG")
[ "$R" = 1 ] && ok "check-drift: project-scope record visible from its own checkout" \
  || bad "drift/main" "expected 1 row, got $R"

# 2. THE FIX. From a linked worktree the record is still keyed to the MAIN checkout; before the
#    change `--show-toplevel` returned the worktree and every project-scope row vanished.
git -C "$MAIN" worktree add -q -b wt "$TMP/wt" 2>/dev/null
R=$(drift_rows "$TMP/wt" "$CFG")
[ "$R" = 1 ] && ok "check-drift: record survives when run from a linked worktree" \
  || bad "drift/worktree" "expected 1 row, got $R — the worktree fix has regressed"

# 3. A record keyed to the WORKTREE must also match, from inside it. The first attempt at the fix
#    swapped one path for the other and broke this direction instead.
CFGW="$TMP/cfgw"; mkcfg "$CFGW" "$TMP/wt"
R=$(drift_rows "$TMP/wt" "$CFGW")
[ "$R" = 1 ] && ok "check-drift: a record keyed to the worktree itself also matches" \
  || bad "drift/worktree-own" "expected 1 row, got $R"

# 4. SUBMODULE. `dirname(--git-common-dir)` is <super>/.git/modules there — not a checkout — so a
#    path-shaped discriminator reintroduces the disappearing rows. The git-dir/common-dir
#    inequality does not.
SUP="$TMP/super"; CHILD="$TMP/child"; mkrepo "$SUP"; mkrepo "$CHILD"
git -C "$SUP" -c protocol.file.allow=always submodule add -q "$CHILD" mysub 2>/dev/null
if [ -d "$SUP/mysub" ]; then
  CFGS="$TMP/cfgs"; mkcfg "$CFGS" "$SUP/mysub"
  R=$(drift_rows "$SUP/mysub" "$CFGS")
  [ "$R" = 1 ] && ok "check-drift: a record inside a submodule work tree still matches" \
    || bad "drift/submodule" "expected 1 row, got $R"
else
  ok "check-drift: submodule row SKIPPED (git refused to add one here)"
fi

# 5. OLD GIT. `rev-parse` ECHOES an unrecognised option and exits 0 rather than failing, so on git
#    < 2.31 `--path-format=absolute --git-dir` yields TWO lines, the first of them the flag itself.
#    Unguarded, that string reaches `dirname`, which reads a leading `--` as an option of its own
#    ("dirname: unrecognized option"), fails under `set -e`, and takes the whole script with it —
#    exiting 1, which the header documents as "at least one stale". So it must run from a LINKED
#    WORKTREE, the only shape that reaches `dirname` at all, against a record keyed to the worktree
#    itself, which matches through `PROJECT` either way: then the ONLY thing this row measures is
#    whether the script survived.
OLDGIT="$TMP/oldgit"; mkdir -p "$OLDGIT"
REALGIT="$(command -v git)"
cat > "$OLDGIT/git" <<EOF
#!/usr/bin/env bash
# Emulate git < 2.31: echo each unrecognised --path-format, pass everything else through.
args=()
for a in "\$@"; do
  case "\$a" in --path-format=*) printf '%s\n' "\$a" ;; *) args+=("\$a") ;; esac
done
exec "$REALGIT" "\${args[@]}"
EOF
chmod +x "$OLDGIT/git"
OUT=$( cd "$TMP/wt" && PATH="$OLDGIT:$STUB:$PATH" CLAUDE_CONFIG_DIR="$CFGW" \
       bash "$HERE/scripts/check-drift.sh" --offline 2>&1 ); E=$?
R=$(printf '%s\n' "$OUT" | grep -c '^thing ') || true
[ "$R" = 1 ] && ok "check-drift: survives a git with no --path-format (exit $E, table printed)" \
  || bad "drift/oldgit" "expected the table, got exit=$E out='$(printf '%s' "$OUT" | tail -3)'"

# ============ validate.sh external pairing ==================================
# A whole synthetic marketplace, so the real one is never the fixture.
mkmp() { # mkmp <root> <catalog-version>
  mkdir -p "$1/.claude-plugin" "$1/plugins" "$1/scripts"
  cp "$HERE/scripts/validate.sh" "$1/scripts/validate.sh"
  printf '{"name":"m","owner":{"name":"t"},"plugins":[{"name":"ext","source":{"source":"github","repo":"t/ext"},"version":"%s","description":"d","author":{"name":"t"},"category":"c"}]}\n' "$2" \
    > "$1/.claude-plugin/marketplace.json"; }
mksib() { mkdir -p "$1/.claude-plugin"; printf '{"name":"ext","version":"%s"}\n' "$2" > "$1/.claude-plugin/plugin.json"; }

W="$TMP/w1/mp"; mkmp "$W" "1.0.0"
OUT=$( cd "$W" && bash scripts/validate.sh 2>&1 ); E=$?
case "$E:$OUT" in 0:*SKIPPED*) ok "validate: no sibling → SKIPPED and said so (not silently OK)" ;;
  *) bad "validate/absent" "exit=$E out='$OUT'" ;; esac

W="$TMP/w2/mp"; mkmp "$W" "1.0.0"; mksib "$TMP/w2/ext" "1.0.0"
OUT=$( cd "$W" && bash scripts/validate.sh 2>&1 ); E=$?
case "$E" in 0) ok "validate: sibling versions match → OK" ;;
  *) bad "validate/match" "exit=$E out='$OUT'" ;; esac

W="$TMP/w3/mp"; mkmp "$W" "1.0.0"; mksib "$TMP/w3/ext" "0.0.1"
OUT=$( cd "$W" && bash scripts/validate.sh 2>&1 ); E=$?
case "$E:$OUT" in 1:*"0.0.1"*) ok "validate: sibling MISMATCH → FAIL naming both versions" ;;
  *) bad "validate/mismatch" "exit=$E out='$OUT'" ;; esac

W="$TMP/w4/mp"; mkmp "$W" "1.0.0"; mkdir -p "$TMP/w4/ext/.claude-plugin"
printf '{oops' > "$TMP/w4/ext/.claude-plugin/plugin.json"
OUT=$( cd "$W" && bash scripts/validate.sh 2>&1 ); E=$?
case "$E:$OUT" in 1:*unreadable*) ok "validate: corrupt sibling manifest → clean FAIL, not a traceback" ;;
  *) bad "validate/corrupt" "exit=$E out='$(printf '%s' "$OUT" | tail -3)'" ;; esac

# A trailing slash in `repo` is legal in the catalog and makes `split("/")[-1]` the empty string,
# so the sibling path resolves to the PARENT directory, no manifest is found there, and the pair
# reports SKIPPED — an absent check wearing the costume of a clean one.
W="$TMP/w5/mp"; mkmp "$W" "1.0.0"
sed -i 's#"repo":"t/ext"#"repo":"t/ext/"#' "$W/.claude-plugin/marketplace.json"
mksib "$TMP/w5/ext" "0.0.1"
OUT=$( cd "$W" && bash scripts/validate.sh 2>&1 ); E=$?
case "$E:$OUT" in 1:*"0.0.1"*) ok "validate: trailing slash in repo still finds the sibling" ;;
  *) bad "validate/trailing-slash" "exit=$E out='$OUT'" ;; esac

echo ""
echo "  ${PASS} passed, ${FAIL} failed"
[ "$FAIL" = 0 ] || exit 1
