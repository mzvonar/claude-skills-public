#!/usr/bin/env bash
# tests/diverges-from.sh — every citation in a finding's `diverges_from` opens, like every other file
# name on the page.
#
# A convention finding is settled by reading what it cites, and it used to render each citation as
# a copy-only chip: the reader tapped the rule and nothing opened. Most citations name files the
# change does not touch — a rule document, an untouched neighbour — so there is no diff to show;
# those open the cited lines as they are on disk. A changed file cited at a line its diff never
# reaches opens its source too, or the reader lands on unrelated hunks. Run by tests/run.sh;
# runnable alone.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$HERE/../skills/changes/scripts"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export DESCRIBE_CHANGES_HOME="$T/home"
fail() { echo "FAIL: $*" >&2; exit 1; }
[ -n "$T" ] && [ -d "$T" ] || { echo "FATAL: no scratch dir" >&2; exit 1; }

# The repo is one level down so a citation can climb OUT of it and still land inside the scratch dir:
# `../outside.md` must exist to prove the refusal is the containment check and not a missing file.
echo "must never reach the report" > "$T/outside.md"
mkdir "$T/repo" && cd "$T/repo"
git init -q -b main . ; git config user.email t@t; git config user.name t
printf '.describe-changes/\nhome/\n' > .gitignore

mkdir -p src docs
# The rule, cited at line 3. Never touched by the change.
cat > docs/rules.md <<'F'
# Rules
- one way to do a thing
- services never touch the database directly
- tests sit beside the code
F
# A neighbour that follows the rule. Never touched either.
cat > src/sibling.ts <<'F'
export const sibling = () => repository.load();
F
# A file the change DOES touch — at line 8, while the citation points at line 2.
cat > src/real.ts <<'F'
// line 1
// line 2: the precedent the finding cites
// line 3
// line 4
// line 5
// line 6
// line 7
export const add = (a: number, b: number): number => a + b;
F
git add -A && git commit -qm "base"

sed -i 's/a + b;/a + b + 0;/' src/real.ts
OUT=$(bash "$S/collect-diff.sh" | tail -1 | sed 's/^OUT=//')
[ -n "$OUT" ] || fail "collect produced no OUT"

OUT="$OUT" python3 - <<'PY'
import json, os
d = os.environ["OUT"]
json.dump({
    "title": "t", "intent": "t", "summary": "One file changed; a finding cites the rule it breaks.",
    "phases": [{"id": "p1", "title": "p", "narrative": "n", "files": ["src/real.ts"]}],
    "graph": {"nodes": [], "edges": []}, "folded": [], "unreviewed_notes": {},
    "findings": [{
        "id": "C1", "severity": "critical", "title": "A service reads the database directly",
        "verify": "Is this a new direction?", "why_human": "Only the owner can call it.",
        "file": "src/real.ts", "lines": "8", "tags": ["convention"],
        "diverges_from": [
            {"ref": "docs/rules.md:3", "why": "the rule"},
            {"ref": "src/sibling.ts", "why": "a neighbour, no line"},
            {"ref": "src/real.ts:8", "why": "a line the diff shows"},
            {"ref": "src/real.ts:2", "why": "a line the diff does not reach"},
            {"ref": "docs/missing.md:4", "why": "a file that does not exist"},
            {"ref": "../outside.md:1", "why": "a path out of the repo"},
        ],
    }],
}, open(os.path.join(d, "report.json"), "w"))
PY
# The validator refuses the two citations that name nothing readable — and only those two.
if CHECK=$(python3 "$S/check-report.py" "$OUT/report.json" 2>&1); then fail "the validator accepted a missing and an escaping citation"; fi
grep -q "docs/missing.md:4' — no such file in the repo" <<<"$CHECK" || fail "the missing file is not reported: $CHECK"
grep -q "../outside.md:1' — points outside the repo" <<<"$CHECK" || fail "the escaping path is not reported: $CHECK"
[ "$(grep -c '^ERROR' <<<"$CHECK")" = 2 ] || fail "expected exactly two errors, got: $CHECK"
echo "the validator rejects a missing and an escaping citation   OK"

# …and the renderer, handed that report anyway, still reads nothing it should not.
python3 "$S/render-report.py" --dir "$OUT" >/dev/null || fail "render"

OUT="$OUT" python3 - <<'PY' || fail "a citation does not open what it cites"
import json, os, re
page = open(os.path.join(os.environ["OUT"], "index.html"), encoding="utf-8").read()
store = json.loads(re.search(r'id="file-store"[^>]*>(\{.*?\})</script>', page, re.S).group(1).replace("<\\/", "</"))
start = page.index('data-id="C1"')
card = page[start:page.index('</section>', start)]
opens = dict(re.findall(r'<button class="fpath" data-open="([^"]+)"[^>]*>([^<]+)</button>', card))

# The rule, which the change never touched: opens a SOURCE view, stored under the citation itself.
assert opens.get("docs/rules.md:3") == "docs/rules.md:3", f"the rule citation does not open: {opens}"
rule = store["docs/rules.md:3"]["html"]
assert "Not part of this change" in rule, "the source view does not say it is not a diff"
cited = re.findall(r'<div class="l c cited"[^>]*data-n="(\d+)"', rule)
assert cited == ["3"], f"the cited line is not the one marked: {cited}"
assert "services never touch the database directly" in rule, "the cited line's text is missing"
print("an untouched rule opens at its cited line, marked          OK")

# A neighbour cited with no line opens from its top.
assert "src/sibling.ts" in opens, "the neighbour citation does not open"
assert 'data-n="1"' in store["src/sibling.ts"]["html"], "the neighbour view does not start at line 1"
print("a citation with no line opens the file from its top        OK")

# A changed file, cited at a line its diff SHOWS: opens the diff, keyed by the path like every
# other reference to that file.
assert opens.get("src/real.ts") == "src/real.ts:8", f"a line inside a hunk does not open the diff: {opens}"
print("a line the diff shows opens the diff                       OK")

# The same changed file, cited at a line its diff does NOT reach: the source, with a banner that
# says the file changed elsewhere rather than claiming it did not change at all.
assert opens.get("src/real.ts:2") == "src/real.ts:2", "an untouched line of a changed file does not open its source"
untouched = store["src/real.ts:2"]["html"]
assert "Untouched by this change" in untouched and "Not part of this change" not in untouched, \
    "the banner misstates what happened to the file"
print("an untouched line of a changed file opens its source       OK")

# Nothing to open stays a copy-only chip — never a control that does nothing.
for ref in ("docs/missing.md:4", "../outside.md:1"):
    assert ref not in opens.values(), f"{ref} renders as a control with nothing behind it"
    assert f'<span class="loc-plain">{ref}</span>' in card, f"{ref} lost its plain text"
assert not any(k.startswith("..") for k in store), "a path out of the repo was read into the store"
assert "must never reach the report" not in page, "a file outside the repo was read into the page"
print("a missing file and an escaping path stay copy-only         OK")

# Every citation keeps its copy control.
assert card.count('<span class="loc cp" data-loc=') >= 7, "a citation lost its copy control"
print("every citation still copies                                OK")
PY

echo "DIVERGES-FROM TESTS PASSED"
