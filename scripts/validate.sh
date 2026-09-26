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


def _extra_version_sites(pdir):
    """Every place inside a plugin that also declares a version: (label, value) pairs.

    Two shapes exist today — a `VERSION` file beside a SKILL.md, and a `version:` in SKILL.md
    frontmatter. Both are discovered rather than listed, so a plugin that grows one is covered
    without anybody remembering to add it here.
    """
    out = []
    for dirpath, _dirs, files in os.walk(os.path.join(pdir, "skills")):
        if "VERSION" in files:
            p = os.path.join(dirpath, "VERSION")
            out.append((os.path.relpath(p, root), open(p, encoding="utf-8").read().strip()))
        if "SKILL.md" in files:
            p = os.path.join(dirpath, "SKILL.md")
            head = re.match(r"^---\n(.*?)\n---\n", open(p, encoding="utf-8").read(), re.S)
            if head:
                vm = re.search(r'^version:\s*"?([^"\s]+)"?\s*$', head.group(1), re.M)
                if vm:
                    out.append((os.path.relpath(p, root) + " (frontmatter)", vm.group(1)))
    return out
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
        # A plugin may declare its version in MORE places than the two manifests — describe-changes
        # carries a `VERSION` file its own runtime reads and a `version:` in the skill frontmatter.
        # A marketplace-wide bump does not know about those, and three in a row walked past them:
        # the manifests reached 1.30.1 while both extra sites still said 1.28.0, so lessons and
        # discovery metadata named a release two minors old. Only that plugin's OWN test caught it,
        # in CI, after the push. This check runs on every bump, for every plugin, which is where a
        # version-parity rule belongs.
        for extra, got in _extra_version_sites(pdir):
            if got != e.get("version"):
                print(f"FAIL: {name}: {extra} declares {got} != marketplace {e.get('version')}"); ok = False
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
        # A github-sourced plugin keeps its manifest in ITS OWN repo, so the version pairing above
        # cannot run here: check-drift compares the install RECORD to the catalog and never opens
        # the repo manifest, and `claude plugin tag` compares two manifests inside ONE repo, so
        # neither can see this pair. When a sibling checkout is present beside this repo, compare
        # them; when it is not (CI, a fresh clone), say SKIPPED rather than printing nothing — an
        # absent check and a passing one must not look the same.
        #
        # What it can tell you is narrow, and worth stating: the sibling is a WORKING TREE, so a
        # disagreement means "these two numbers differ", never "the listing is wrong". The one hit
        # this produced on introduction was a sibling clone nine days stale, not a publishing
        # mismatch — go and look, do not assume.
        repo = src.get("repo", "").rstrip("/")
        if not repo:
            pass          # already reported as "external source missing repo" above
        else:
            sib = os.path.normpath(os.path.join(root, "..", repo.split("/")[-1]))
            sibpj = os.path.join(sib, ".claude-plugin", "plugin.json")
            if os.path.exists(sibpj):
                # A corrupt sibling manifest must FAIL this entry, not raise out of the loop and
                # leave every later plugin unvalidated behind a traceback.
                try:
                    sv = json.load(open(sibpj)).get("version")
                except Exception as exc:
                    print(f"FAIL: {name}: {sibpj} is unreadable ({exc.__class__.__name__})"); ok = False
                else:
                    if sv != e.get("version"):
                        print(f"FAIL: {name}: {sibpj} version {sv} != marketplace {e.get('version')}"); ok = False
            else:
                print(f"note: {name}: external repo not checked out beside this one — version pairing SKIPPED, not verified")
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
  # `plugins/*/` with no match expands to ITSELF, so an unguarded loop hands the literal glob to
  # the CLI and reports a failure for a plugin that does not exist. Latent in this repo (six
  # plugins always match) and caught only by the synthetic marketplace in scripts/tests — which is
  # the point of having one.
  for d in plugins/*/; do
    [ -d "$d" ] || continue
    claude plugin validate "$d" >/dev/null 2>&1 || err "claude plugin validate: $d"
  done
else
  echo "note: claude CLI not found, skipping 'claude plugin validate'"
fi

[ "$fail" = 0 ] && echo "validate: OK" || { echo "validate: FAILED" >&2; exit 1; }
