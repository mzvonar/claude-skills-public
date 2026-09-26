#!/usr/bin/env bash
# validate.sh — structural checks for every plugin in this marketplace. Run from anywhere.
#   - plugin.json version == marketplace.json entry version
#   - every skills/<dir>/SKILL.md has frontmatter name == <dir> and a description <= 1024 chars
#   - no machine-, user- or project-specific strings (see FORBIDDEN)
#   - `claude plugin validate` on the marketplace and each plugin, when the CLI is available
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
fail=0; err() { echo "FAIL: $*" >&2; fail=1; }

FORBIDDEN='/Users/|~/Development|\.claude-shared|uctoinak|population-registry|innovatrics|gitlab\.ba|/root/uctoinak|SABID-[0-9]'
# abis is a common substring (e.g. "abis" inside other words); match it as a path segment or word.
FORBIDDEN_WORD='(^|[^a-z])abis([^a-z]|$)'

python3 - <<'PY' || fail=1
import json, os, re, sys
root = os.getcwd()
mp = json.load(open(".claude-plugin/marketplace.json"))
entries = {p["name"]: p for p in mp["plugins"]}
ok = True
for name, e in entries.items():
    src = e["source"]
    if isinstance(src, str):
        pdir = os.path.normpath(os.path.join(root, src))
        pj = os.path.join(pdir, ".claude-plugin", "plugin.json")
        if not os.path.exists(pj):
            print(f"FAIL: {name}: missing {pj}"); ok = False; continue
        p = json.load(open(pj))
        if p.get("name") != name:
            print(f"FAIL: {name}: plugin.json name is {p.get('name')!r}"); ok = False
        if p.get("version") != e.get("version"):
            print(f"FAIL: {name}: plugin.json version {p.get('version')} != marketplace {e.get('version')}"); ok = False
        skills_dir = os.path.join(pdir, "skills")
        if not os.path.isdir(skills_dir):
            print(f"FAIL: {name}: no skills/ dir"); ok = False; continue
        for d in sorted(os.listdir(skills_dir)):
            sd = os.path.join(skills_dir, d)
            if not os.path.isdir(sd): continue
            sk = os.path.join(sd, "SKILL.md")
            if not os.path.exists(sk):
                print(f"FAIL: {name}/{d}: no SKILL.md"); ok = False; continue
            text = open(sk, encoding="utf-8").read()
            m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
            if not m:
                print(f"FAIL: {name}/{d}: no frontmatter"); ok = False; continue
            fm = m.group(1)
            nm = re.search(r"^name:\s*(.+)$", fm, re.M)
            if not nm or nm.group(1).strip().strip('"\'') != d:
                print(f"FAIL: {name}/{d}: frontmatter name != dir"); ok = False
            dm = re.search(r"^description:\s*(.*)$", fm, re.M)
            if not dm:
                print(f"FAIL: {name}/{d}: no description"); ok = False
            else:
                # folded/multi-line descriptions: collect indented continuation lines
                desc = dm.group(1)
                after = fm[dm.end():]
                for line in after.splitlines():
                    if line.startswith(" ") or line.startswith("\t"): desc += " " + line.strip()
                    else: break
                if len(desc) > 1024:
                    print(f"FAIL: {name}/{d}: description {len(desc)} chars > 1024"); ok = False
    else:
        for k in ("source", "repo"):
            if k not in src: print(f"FAIL: {name}: external source missing {k}"); ok = False
sys.exit(0 if ok else 1)
PY

# forbidden strings (skills + manifests + docs, not tests fixtures)
if grep -rEn --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=fixtures --exclude-dir=__pycache__ -i "$FORBIDDEN" plugins .claude-plugin README.md docs 2>/dev/null | grep -v 'validate.sh'; then
  err "forbidden machine/project-specific strings found (above)"
fi
if grep -rEn --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=fixtures --exclude-dir=__pycache__ -i "$FORBIDDEN_WORD" plugins .claude-plugin 2>/dev/null | grep -v 'validate.sh'; then
  err "project name 'abis' found (above)"
fi

# script syntax
while IFS= read -r f; do
  case "$f" in
    *.sh) bash -n "$f" || err "bash syntax: $f" ;;
    *.py) python3 -m py_compile "$f" 2>/dev/null || err "python syntax: $f" ;;
    *.mjs|*.js) command -v node >/dev/null && { node --check "$f" 2>/dev/null || err "node syntax: $f"; } ;;
  esac
# `scripts` as well as `plugins`: this repo's own maintainer scripts sat outside every sweep —
# not syntax-checked here, and not reached by the plugin test runners, which glob
# `skills/*/scripts/*.sh`. A broken `check-drift.sh` or `plugin-freshness.sh` would have shipped
# green. Found by review, 2026-09-26.
done < <(find plugins scripts -type f \( -name '*.sh' -o -name '*.py' -o -name '*.mjs' -o -name '*.js' \) -not -path '*/node_modules/*' -not -path '*/fixtures/*')
find plugins scripts -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

# claude CLI validation
if command -v claude >/dev/null 2>&1; then
  claude plugin validate . >/dev/null 2>&1 || err "claude plugin validate: marketplace"
  for d in plugins/*/; do
    claude plugin validate "$d" >/dev/null 2>&1 || err "claude plugin validate: $d"
  done
else
  echo "note: claude CLI not found, skipping 'claude plugin validate'"
fi

[ "$fail" = 0 ] && echo "validate: OK" || { echo "validate: FAILED" >&2; exit 1; }
