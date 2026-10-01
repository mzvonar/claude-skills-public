#!/usr/bin/env bash
# tests/plan.sh — the plan skill (/describe:plan) on a synthetic repo, no LLM involved: collect a plan
# from files and headings, ground it against the tree, validate a report the way the analyst is told
# to write it, render the page through the SHARED shell, refuse the reports the schema forbids, and
# drive the shared feedback loop from the plan's own report dir. Run by tests/run.sh; runnable alone.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$HERE/../skills/plan/scripts"; CH="$HERE/../skills/changes/scripts"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export DESCRIBE_CHANGES_HOME="$T/home"
fail() { echo "FAIL: $*" >&2; exit 1; }
[ -n "$T" ] && [ -d "$T" ] || { echo "FATAL: no scratch dir" >&2; exit 1; }
cd "$T" || { echo "FATAL: cannot enter scratch dir" >&2; exit 1; }
git rev-parse --show-toplevel >/dev/null 2>&1 && { echo "FATAL: '$T' is inside an existing git repo" >&2; exit 1; }
git init -q -b main . && git config user.email t@t && git config user.name t
printf '.describe-changes/\nhome/\n' > .gitignore
mkdir -p src/domain docs/plans
cat > src/domain/schema.ts <<'F'
export interface CodeValue {
  code: string;
  active: boolean;
  order: number;
}
export interface Codelist {
  codelistId: string;
  values: CodeValue[];
}
export const alphaThing = (x: number): number => x * 2;
F
cat > src/domain/map.ts <<'F'
import type { CodeValue } from "./schema";
export const toCodeValue = (dto: unknown): CodeValue => dto as CodeValue;
F
cat > docs/plans/codes.md <<'F'
# Plan: code values from the platform

## Background
Today `src/domain/schema.ts:2-5` holds `CodeValue`. The mapper is `map.ts`. The old `src/domain/gone.ts:3` is cited but missing, and `src/domain/map.ts:40-50` cites past the end.

## Epic 9: Codes

### Story 9.1: The domain grows
**Acceptance Criteria:**
**Given** the platform's snapshot
**When** it is mapped
**Then** `CodeValue` carries `status`
**And** `alphaThing` stays

### Story 9.2: Not this
Unrelated. `nowhereSymbol` is not in the tree.

## Epic 10: Other
### Story 10.1: Nope
F
# A story-shaped plan: its own acceptance criteria and open questions, which the page must show WORD FOR
# WORD. The traps: a criterion's own heading (`AC-1 — …`) is part of the section, not a section; a
# table and a thematic break; a heading-shaped line inside a fence is not a heading; a label nested in
# a section already taken stays part of it; a section name only a config key knows.
cat > docs/plans/story.md <<'F'
# Story 7.2: Something

## Story
As a reader.

## Acceptance Criteria

### AC-1 — first
- one `CodeValue`
- two

### AC-2 — second
| a | b |
|---|---|
| 1 | 2 |

---

## Tasks
- [ ] do

```md
## Acceptance Criteria
fake, inside a fence
```

## Open questions for the gate

### Group 1 — rules
#### R1 — a rule
- (a) yes, recommended

**Open questions:**
a label inside a section already taken

## Dev Notes
nothing

## Points to settle
- only a configured name finds this
F
git add -A && git commit -qm init

# ---- 1. collect + ground ------------------------------------------------------------------------
OUT="$(python3 "$S/collect-plan.py" --from 'docs/plans/codes.md#re:^Epic 9\b' --grep-from docs/plans/codes.md 'Background' --slug epic-9 | tail -1 | sed 's/^OUT=//')"
[ -f "$OUT/plan.md" ] || fail "no plan.md"
case "$OUT" in "$T/.describe-changes/plan/epic-9") ;; *) fail "output dir is not <root>/.describe-changes/plan/<slug>: $OUT" ;; esac
grep -q 'Story 9.1' "$OUT/plan.md" || fail "epic subtree not extracted"
grep -q 'Story 10.1' "$OUT/plan.md" && fail "a sibling epic leaked into the subtree"
grep -q '^## Epic 9: Codes' "$OUT/plan.md" || fail "the heading line itself is missing"
grep -q '<!-- source: docs/plans/codes.md#Epic 9: Codes -->' "$OUT/plan.md" || fail "no source marker"
ls "$OUT/sources" | grep -q '^01-' || fail "sources/ not written"
python3 - "$OUT" <<'PY'
import json, os, sys
d = sys.argv[1]
c = json.load(open(os.path.join(d, "citations.json")))
p = {x["path"]: x for x in c["paths"]}
assert p["src/domain/schema.ts"]["exists"] and p["src/domain/schema.ts"]["ranges"] == [[2, 5]], p["src/domain/schema.ts"]
assert p["src/domain/schema.ts"]["out_of_range"] == [], p["src/domain/schema.ts"]
assert not p["src/domain/gone.ts"]["exists"], p["src/domain/gone.ts"]
assert p["src/domain/map.ts"]["out_of_range"] == [[40, 50]], p["src/domain/map.ts"]
bare = {x["name"]: x for x in c["bare_files"]}
assert bare["map.ts"]["resolved"] == "src/domain/map.ts", bare
sym = {x["symbol"]: x for x in c["symbols"]}
assert sym["CodeValue"]["files"] >= 2 and sym["alphaThing"]["files"] == 1, sym
assert sym["nowhereSymbol"]["files"] == 0, sym["nowhereSymbol"]
s = c["summary"]
assert s["paths"] == 3 and s["paths_found"] == 2 and s["paths_out_of_range"] == 1, s
st = json.load(open(os.path.join(d, "structure.json")))
units = {u["heading"]: u for u in st["units"]}
assert "Story 9.1: The domain grows" in units and units["Story 9.1: The domain grows"]["acceptance_lines"] == 4, units
assert "Story 10.1: Nope" not in units, units
m = json.load(open(os.path.join(d, "meta.json")))
assert m["languages"].get("TypeScript") == 2, m["languages"]
assert m["slug"] == "epic-9" and m["root"] == os.path.realpath(os.getcwd()) or m["root"] == os.getcwd(), m
print("collect + grounding OK")
PY
# The sugar refuses, with the key named, when the layout is not configured.
if python3 "$S/collect-plan.py" --epic 9 >/dev/null 2>"$T/err"; then fail "--epic without config must exit non-zero"; fi
grep -q 'describe.plan.epics' "$T/err" || fail "--epic refusal must name the config key: $(cat "$T/err")"
# …and works with the config file the consumer would write.
mkdir -p .claude && printf '{"describe":{"plan":{"epics":"docs/plans/codes.md"}}}\n' > .claude/claude-skills.json
# Its own slug: the default would be `epic-9`, the dir the first run wrote and the rest of this file reads.
OUT2="$(python3 "$S/collect-plan.py" --epic 9 --slug epic-9-via-config | tail -1 | sed 's/^OUT=//')"
grep -q 'Story 9.2' "$OUT2/plan.md" || fail "--epic through config did not extract the epic"
grep -q 'Story 10.1' "$OUT2/plan.md" && fail "--epic 9 leaked Epic 10"
rm .claude/claude-skills.json
# Nothing to describe: exit 2, never a silent empty report dir.
if python3 "$S/collect-plan.py" >/dev/null 2>&1; then fail "no inputs must exit 2"; fi
echo "collect OK"

# ---- 1b. the plan's own words: acceptance criteria and open questions, verbatim ------------------
OUTS="$(python3 "$S/collect-plan.py" --from docs/plans/story.md --slug story-7-2 | tail -1 | sed 's/^OUT=//')"
OUTB="$(python3 "$S/collect-plan.py" --grep-from docs/plans/codes.md 'Background' --slug bg-only | tail -1 | sed 's/^OUT=//')"
mkdir -p .claude && printf '{"describe":{"plan":{"verbatim":{"questions":["points to settle\\\\b"]}}}}\n' > .claude/claude-skills.json
OUTC="$(python3 "$S/collect-plan.py" --from docs/plans/story.md --slug story-7-2-config | tail -1 | sed 's/^OUT=//')"
rm .claude/claude-skills.json
python3 - "$OUT" "$OUTS" "$OUTB" "$OUTC" <<'PY'
import json, os, sys
epic, story, bg, conf = sys.argv[1:5]
V = lambda d: json.load(open(os.path.join(d, "structure.json")))["verbatim"]
def lines_of(path, a, b): return open(path, encoding="utf-8").read().splitlines()[a - 1:b]
# A heading section: its subtree, the criteria's own headings inside it, trailing blank and --- trimmed.
v = V(story)
assert [(x["kind"], x["title"]) for x in v] == [("acceptance", "Acceptance Criteria"), ("questions", "Open questions for the gate")], v
src = open("docs/plans/story.md", encoding="utf-8").read().splitlines()
ac, oq = v
assert ac["file"] == "docs/plans/story.md" and ac["context"] == "Story 7.2: Something", ac
assert src[ac["start"] - 1] == "## Acceptance Criteria" and src[ac["end"] - 1] == "| 1 | 2 |", (ac["start"], ac["end"])
assert ac["text"].split("\n") == lines_of("docs/plans/story.md", ac["start"], ac["end"]), "not word for word"
assert "fake, inside a fence" not in ac["text"] and sum(1 for x in v if "fence" in x["text"]) == 0, "a fenced heading was read"
assert src[oq["end"] - 1] == "a label inside a section already taken", oq["end"]
assert oq["text"].split("\n") == lines_of("docs/plans/story.md", oq["start"], oq["end"])
# An epic's bold label: from the label to the next heading, with the FILE's line numbers even though
# the source is a heading subtree that starts mid-file.
e = V(epic)
assert len(e) == 1 and e[0]["kind"] == "acceptance" and e[0]["title"] == "Acceptance Criteria" and e[0]["context"] == "Story 9.1: The domain grows", e
codes = open("docs/plans/codes.md", encoding="utf-8").read().splitlines()
assert codes[e[0]["start"] - 1] == "**Acceptance Criteria:**" and codes[e[0]["end"] - 1] == "**And** `alphaThing` stays", e[0]
assert e[0]["text"].split("\n") == lines_of("docs/plans/codes.md", e[0]["start"], e[0]["end"])
# A plan without such a section has none; a configured name extends the defaults and never replaces them.
assert V(bg) == [], V(bg)
c = V(conf)
assert [x["title"] for x in c] == ["Acceptance Criteria", "Open questions for the gate", "Points to settle"] and c[2]["kind"] == "questions", c
print("verbatim OK")
PY
grep -q '^verbatim: 1 acceptance-criteria section, 1 open-questions section' <(python3 "$S/collect-plan.py" --from docs/plans/story.md --slug story-7-2) \
  || fail "collect-plan does not report the verbatim sections"

# ---- 2. a report, the way the analyst writes it --------------------------------------------------
cat > "$OUT/report.json" <<'J'
{ "kind": "plan", "title": "Code values from the platform",
  "intent": "Stop shipping our own code lists; read them from the platform.",
  "plain": "Today the screen's dropdown lists come from a copy inside this service. After this plan they come from the platform, so a value an administrator adds shows up without a release. Labels stay ours.",
  "summary": "Each code will carry whether it is retired and where it sorts. The old relations list goes.",
  "scope": {"in": ["the dropdown lists"], "out": ["the field document"]},
  "units": [
    {"id": "9.1", "title": "The domain grows", "plain": "One code will know whether it is retired and where it sorts.",
     "detail": "`CodeValue` gains `status` and `position`; `active`/`order` go.",
     "acs": [{"id": "AC1", "text": "**Given** the platform's snapshot **When** it is mapped **Then** `CodeValue` carries `status`", "plain": "A code coming from the platform keeps its retired flag."}],
     "touches": [{"file": "src/domain/schema.ts", "status": "changed"}, {"file": "src/domain/snapshot.ts", "status": "new", "note": "the wire shape"}, {"file": "src/domain/map.ts", "status": "changed"}],
     "depends_on": [], "reviewers": "one reviewer", "size": "S"},
    {"id": "9.2", "title": "Not this", "plain": "Nothing for a person changes here.", "touches": [], "depends_on": ["9.1"], "size": "S"}
  ],
  "decisions": [{"text": "Labels stay in our own catalogs.", "by": "owner", "when": "2026-09-29", "source": "plan §Background"}],
  "findings": [
    {"id": "S1", "severity": "critical", "title": "The plan cites a file that is not there",
     "plain": "The plan reasons about a mapper file that does not exist, so a builder would start by looking for it. Either it is a typo or the plan means to create it.",
     "question": "Is `src/domain/gone.ts` a typo for `map.ts`, or a file this plan creates?",
     "current": "The plan cites gone.ts as if it existed.", "alternative": "Cite map.ts, which holds the mapper today.",
     "cost": "One line in the plan.", "why_human": "Only the author knows what they meant.",
     "file": "docs/plans/codes.md", "lines": "4", "unit": "9.1", "tags": ["grounding"]},
    {"id": "S2", "severity": "medium", "title": "Sort order comes from the platform, not the catalog",
     "plain": "Lists will sort the way the platform says, not alphabetically by label. A French list may not read alphabetically.",
     "question": "Should lists follow the platform's position or the label's alphabet?", "current": "Platform position.", "alternative": "Sort by label in the screen.",
     "why_human": "A product call about what operators expect.", "file": "src/domain/schema.ts", "lines": "4", "unit": "9.1"}
  ],
  "sketches": [
    {"id": "K1", "unit": "9.1", "title": "A code value gains status and position", "plain": "One code will say whether it is retired and where it sorts.",
     "language": "TypeScript", "file": "src/domain/schema.ts", "status": "changed", "before": {"lines": "1-5"},
     "after": "export interface CodeValue {\n  code: string;\n  status: \"active\" | \"retired\";\n  position: number;\n}"},
    {"id": "K2", "unit": "9.1", "title": "The wire shape of a snapshot", "plain": "A new file will describe exactly what the platform sends.",
     "language": "TypeScript", "file": "src/domain/snapshot.ts", "status": "new", "after": "export interface SnapshotValue {\n  code: string;\n  status: \"active\" | \"retired\";\n}"}
  ],
  "views": [
    {"kind": "datamodel", "title": "One code, today and after",
     "entities": [{"id": "CodeValue", "label": "CodeValue", "change": "modified", "file": "src/domain/schema.ts", "lines": "1-5",
                   "fields": [{"name": "code", "type": "string", "change": "unchanged"}, {"name": "active", "type": "boolean", "change": "removed"}, {"name": "status", "type": "'active' | 'retired'", "change": "added"}]},
                  {"id": "SnapshotValue", "label": "SnapshotValue", "change": "added", "file": "src/domain/snapshot.ts", "fields": [{"name": "code", "type": "string", "change": "added"}]}],
     "relations": [{"from": "SnapshotValue", "to": "CodeValue", "kind": "refs", "label": "maps to", "change": "added"}]},
    {"kind": "flow", "title": "Opening a record", "steps": [{"label": "screen asks the platform", "change": "added", "file": "src/domain/map.ts"}]}
  ],
  "graph": {"nodes": [{"id": "screen", "label": "Screen", "kind": "component", "change": "modified"},
                      {"id": "platform", "label": "Platform config service", "kind": "external", "change": "unchanged"},
                      {"id": "map", "label": "toCodeValue()", "kind": "function", "change": "modified", "file": "src/domain/map.ts"}],
            "edges": [{"from": "screen", "to": "platform", "kind": "reads", "label": "snapshot"}, {"from": "screen", "to": "map", "kind": "calls"}]},
  "invariants": ["A record stores the code string and nothing else about a list."],
  "assumptions": [{"text": "The platform's contract is stable across its last two tags.", "checked_by": "measured", "note": "byte-compared"},
                  {"text": "No screen sorts by label today.", "checked_by": "assumed"}],
  "how_to_check": [{"id": "V1", "unit": "9.1", "feature": "A retired code still shows on an old record", "surface": "ui", "where": "/records/{id}", "steps": ["Retire a value.", "Open a record holding it."], "expect": "The label shows, marked retired."}],
  "people": [{"who": "platform team", "role": "loads the tables", "needed_for": "9.1"}],
  "glossary": [{"term": "snapshot", "plain": "one whole list as it is at one moment"}]
}
J
python3 "$S/check-plan.py" "$OUT/report.json" > "$T/chk" || { cat "$T/chk"; fail "check-plan rejected a valid report"; }
grep -q 'grounding: paths 2/3 found' "$T/chk" || fail "check-plan does not report the grounding: $(cat "$T/chk")"
grep -q 'WARN: plan cites paths not in the tree' "$T/chk" || fail "a missing cited path must warn"
grep -q 'WARN: plan cites line ranges past' "$T/chk" || fail "an out-of-range citation must warn"
python3 "$S/render-plan.py" --dir "$OUT" > "$T/rnd" || fail "render failed"
H="$OUT/index.html"
grep -q 'class="pw"' "$H" || fail "plain-words block missing"
grep -q 'id="summary" class="q"' "$H" && grep -q 'id="findings" class="q"' "$H" || fail "5-minute sections not marked"
# Two levels, each fronted by a band: the 5-minute version, then the detail — ONE fold, open at
# render time, that any link into it unfolds when the reader has shut it. There is no toggle to switch a mode.
grep -q 'class="part part-1"' "$H" || fail "the 5-minute band is missing"
grep -q 'id="detail" class="detail"><h2 class="sec-t part part-2" data-collapsed="0"' "$H" || fail "the detail is not one fold, open by default, fronted by a band"
grep -q 'section.detail>h2.sec-t.part' "$H" || fail "plan.css not injected into the shell"
grep -q "\['as-written','detail'\]" "$H" && grep -q "dcOpenSection(D.id)" "$H" || fail "a link into a fold (the detail, the plan's own words) does not unfold it"
if grep -q 'id="quick"' "$H"; then fail "the 5-minute toggle is back — the 5-minute version is the page's first part, not a mode"; fi
# The plan's own words: a band and a fold of their own, between the 5-minute version and the detail,
# every line numbered as it is IN THE PLAN FILE and commentable there.
grep -q 'id="as-written" class="detail as-written"><h2 class="sec-t part part-v" data-collapsed="0"' "$H" || fail "the as-written band is missing, not a fold, or not open by default"
grep -q 'href="#as-written"' "$H" || fail "the TOC does not link the plan's own words"
AS_AT="$(python3 -c 'import json,sys; v=json.load(open(sys.argv[1]))["verbatim"][0]; print(v["start"])' "$OUT/structure.json")"
grep -q "data-f=\"docs/plans/codes.md\" data-n=\"$AS_AT\"" "$H" || fail "an as-written line does not carry the plan file's own line number ($AS_AT)"
grep -q 'section.as-written>h2.sec-t.part' "$H" || fail "the as-written band's styles are not injected"
python3 - "$H" <<'PY' || fail "page order"
import sys
h = open(sys.argv[1], encoding="utf-8").read()
at = lambda s: h.index(s)
assert at('id="summary"') < at('id="findings"') < at('id="as-written"') < at('<!-- /as-written -->') < at('id="detail"') < at('id="decisions"') < at('id="units"') < at('id="glossary"') < at('<!-- /detail -->') < at('id="conversation"'), "the 5-minute part, the plan's own words, then the fold, then the conversation outside it"
assert h.count('<!-- /detail -->') == 1 and h.count('<!-- /as-written -->') == 1
print("page order OK")
PY
# A plan without an acceptance-criteria or open-questions section renders no band and no TOC link.
python3 - "$OUT" "$T/nov" <<'PY'
import json, os, shutil, sys
src, dst = sys.argv[1:3]; shutil.copytree(src, dst)
p = os.path.join(dst, "structure.json"); s = json.load(open(p)); s["verbatim"] = []; json.dump(s, open(p, "w"))
PY
python3 "$S/render-plan.py" --dir "$T/nov" >/dev/null || fail "render without verbatim sections failed"
if grep -q 'id="as-written"\|href="#as-written"' "$T/nov/index.html"; then fail "an empty as-written band was rendered"; fi
grep -q 'The detail follows, one level down.' "$T/nov/index.html" || fail "the 5-minute band promises a section that is not there"
grep -q 'data-id="S1" data-key="' "$H" || fail "steering card lacks a content key"
grep -q 'class="steer-word">settle first' "$H" || fail "steering severity word missing"
grep -q 'data-t="more">▲ Settle first' "$H" || fail "verdict buttons not relabelled"
grep -q 'class="fpath" data-open="src/domain/schema.ts" data-st="modified"' "$H" || fail "a touched file does not open, or lacks its status"
grep -q 'class="fplan" data-st="added" title="src/domain/snapshot.ts' "$H" || fail "a planned new file must render as an inert + chip"
grep -q 'class="datamodel"' "$H" && grep -q 'class="dm-ent dm-modified" data-ent="CodeValue"' "$H" || fail "datamodel view missing"
grep -q 'class="flow"' "$H" || fail "flow view missing"
grep -q 'class="mermaid"' "$H" && grep -q 'id="map-canvas"' "$H" || fail "map missing"
grep -q '{{&quot;Platform config service&quot;}}' "$H" || fail "an external node is not drawn as a hexagon"
# Sketch: today's lines carry REAL numbers and the real path; planned lines carry the sketch id.
grep -q 'data-f="src/domain/schema.ts" data-n="2" data-side="new"' "$H" || fail "sketch before-lines lack real line numbers"
grep -q 'data-f="sketch:K1" data-n="1"' "$H" || fail "sketch after-lines lack the sketch anchor"
grep -q 'class="diff planned" data-file="sketch:K1"' "$H" || fail "planned block not marked"
grep -q 'class="hl-k"' "$H" || fail "sketches are not syntax-highlighted"
grep -q 'sketch · planned' "$H" || fail "a sketch is not labelled as one"
# The store opens the cited lines, marked, and never a planned file.
python3 - "$H" <<'PY' || fail "file store"
import json, re, sys
h = open(sys.argv[1], encoding="utf-8").read()
store = json.loads(re.search(r'id="file-store">(.*?)</script>', h, re.S).group(1).replace("<\\/", "</"))
assert "src/domain/schema.ts" in store and "src/domain/map.ts" in store, list(store)
assert "src/domain/snapshot.ts" not in store, "a planned file must not be in the store"
assert 'class="l c cited" data-f="src/domain/schema.ts" data-n="2"' in store["src/domain/schema.ts"]["html"], "cited lines not marked"
assert "As it is today" in store["src/domain/schema.ts"]["html"]
dead = sorted(set(re.findall(r'data-open="([^"]+)"', h)) - set(store))
assert not dead, f"dead controls: {dead}"
data = json.loads(re.search(r'id="report-data">(.*?)</script>', h, re.S).group(1).replace("<\\/", "</"))
assert data["report_id"] and data["range_label"] == "plan · epic-9" and [f["id"] for f in data["findings"]] == ["S1", "S2"], data
print("file store OK")
PY
grep -q 'id="grounding"' "$H" && grep -q 'not in the tree' "$H" || fail "grounding table missing or blind to the missing path"
grep -q 'nowhereSymbol' "$H" || fail "an unknown symbol is not listed"
grep -q 'id="decisions"' "$H" && grep -q '2026-09-29' "$H" || fail "decided-already list missing"
grep -q 'class="chk chk-assumed"' "$H" || fail "assumption tags missing"
grep -q 'id="conversation"' "$H" && grep -q 'id="sheet-x"' "$H" || fail "shell parts missing"
grep -q '__DATA__' "$H" && fail "template placeholder survived"
echo "render OK"

# ---- 3. the reports the schema forbids, each rejection naming its rule ----------------------------
python3 - "$OUT" <<'PY'
import copy, json, os, sys
d = sys.argv[1]; r = json.load(open(os.path.join(d, "report.json")))
def w(name, mut):
    x = copy.deepcopy(r); mut(x); json.dump(x, open(os.path.join(d, name), "w"))
w("bad-budget.json", lambda x: x["findings"].extend(dict(x["findings"][0], id=f"S{i}") for i in range(3, 7)))
w("bad-plain.json", lambda x: x.__setitem__("plain", "`CodeValue` gains `status`. Then nothing else."))
w("bad-unit-plain.json", lambda x: x["units"][0].__setitem__("plain", "`CodeValue` will grow."))
w("bad-touch.json", lambda x: x["units"][0]["touches"].append({"file": "src/domain/missing.ts", "status": "changed"}))
w("bad-range.json", lambda x: x["sketches"][0].__setitem__("before", {"lines": "1-99"}))
w("bad-assume.json", lambda x: x["assumptions"].append({"text": "x", "checked_by": "guessed"}))
w("bad-edge.json", lambda x: x["graph"]["edges"].append({"from": "screen", "to": "ghost", "kind": "calls"}))
w("bad-kind.json", lambda x: x.__setitem__("kind", "changes"))
w("bad-view.json", lambda x: x["views"].append({"kind": "pie", "title": "no"}))
w("bad-steer.json", lambda x: x["findings"][0].pop("alternative"))
w("bad-escape.json", lambda x: x["findings"][0].__setitem__("file", "../outside.md"))
PY
reject() {  # fixture, phrase the message must carry
  local msg; msg="$(python3 "$S/check-plan.py" "$OUT/$1.json" 2>&1 || true)"
  python3 "$S/check-plan.py" "$OUT/$1.json" >/dev/null 2>&1 && fail "check-plan accepted $1"
  case "$msg" in *"$2"*) ;; *) fail "$1 rejected without naming the rule ($2): $msg" ;; esac
}
reject bad-budget     "> budget 3"
reject bad-plain      "opens on a code symbol"
reject bad-unit-plain "unit 9.1: 'plain' opens on a code symbol"
reject bad-touch      "no such file in the repo; a file the plan creates is status 'new'"
reject bad-range      "is outside src/domain/schema.ts"
reject bad-assume     "checked_by must be measured|read|assumed"
reject bad-edge       "references unknown node"
reject bad-kind       "kind must be 'plan'"
reject bad-view       "kind must be one of"
reject bad-steer      "missing 'alternative'"
reject bad-escape     "points outside the repo"
# Warnings must fire and must not fail: a `new` file that exists, a language outside the census.
python3 - "$OUT" <<'PY'
import copy, json, os, sys
d = sys.argv[1]; r = json.load(open(os.path.join(d, "report.json")))
x = copy.deepcopy(r)
x["units"][0]["touches"][1] = {"file": "src/domain/map.ts", "status": "new"}
x["sketches"][0]["language"] = "Haskell"
json.dump(x, open(os.path.join(d, "warn.json"), "w"))
PY
WMSG="$(python3 "$S/check-plan.py" "$OUT/warn.json" 2>&1)" || fail "warnings must not fail the report: $WMSG"
case "$WMSG" in *"is 'new' but the file exists"*) ;; *) fail "an existing 'new' file must warn: $WMSG" ;; esac
case "$WMSG" in *"'Haskell' is not in the tree's census"*) ;; *) fail "a language outside the census must warn: $WMSG" ;; esac
echo "validator OK"

# ---- 4. the shared feedback loop, driven from the plan's report dir --------------------------------
KEY="$(python3 - "$OUT" "$CH" <<'PY'
import json, os, sys
sys.path.insert(0, sys.argv[2]); from report_keys import finding_key
r = json.load(open(os.path.join(sys.argv[1], "report.json")))
print(finding_key(next(f for f in r["findings"] if f["id"] == "S2")))
PY
)"
printf '%s\n' '{"ts":"2026-01-01T00:00:00Z","type":"more","finding":"S1","report_id":"x"}' \
  "{\"ts\":\"2026-01-01T00:00:01Z\",\"type\":\"note\",\"finding\":\"S2\",\"finding_key\":\"$KEY\",\"text\":\"sort by label, please\"}" \
  '{"ts":"2026-01-01T00:00:02Z","type":"comment","id":"cplan1","text":"why a new file?","anchor":{"text":"SnapshotValue","context":"…","section":"sketches","finding":"K2","file":"sketch:K2","line":1,"side":"new"}}' \
  > "$OUT/feedback.jsonl"
python3 "$CH/feedback.py" comments --dir "$OUT" --open > "$T/cm" || fail "comments"
grep -q '\[cplan1\] OPEN' "$T/cm" || fail "a comment on a sketch line is not listed"
grep -q 'at:        sketch:K2:1' "$T/cm" || fail "a sketch-line comment does not report its anchor: $(cat "$T/cm")"
grep -q "\[note-$KEY\] OPEN · note" "$T/cm" || fail "a steer note is not listed as a thread: $(cat "$T/cm")"
python3 "$CH/feedback.py" answer --dir "$OUT" --id cplan1 --improvement "say why the wire shape is its own file" --text "It mirrors the platform's contract, generated from it." | grep -q "answered cplan1" || fail "answer"
python3 "$S/render-plan.py" --dir "$OUT" >/dev/null
grep -q 'id="t-cplan1"' "$H" && grep -q "mirrors the platform" "$H" || fail "the answer is not rendered into Conversation"
grep -q 'sort by label, please</textarea>' "$H" || fail "the steer note is not replayed into its card"
grep -q "id=\"t-note-$KEY\"" "$H" || fail "the steer note has no thread"
# Answered threads stay OPEN on the page: the reader comes back for the answers, and a collapsed
# section read as "no answers" on a phone.
grep -q '<section id="conversation"><h2 class="sec-t" data-collapsed="0"' "$H" || fail "the Conversation section is collapsed by default"
python3 "$CH/feedback.py" ingest "$OUT/feedback.jsonl" --dir "$OUT" | grep -q "ingested 3" || fail "ingest"
python3 "$CH/feedback.py" digest | grep -q "under-rated" || fail "a ▲ verdict does not reach the digest"
# serve: the same server, the same gate, from a plan dir.
# A FREE port, not a fixed one: a maintainer's box has live report servers on the 879x range, and a
# fixed port made this row curl a stranger's server (403 for the wrong reason) while ours died on
# "address already in use".
PORT="$(python3 -c 'import socket; s = socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()')"
python3 "$CH/serve.py" "$OUT" --port "$PORT" --token plantoken >"$T/serve.log" 2>&1 & SP=$!; sleep 0.7
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
# `kill … || true`: under `set -e` a server that never came up makes the kill itself the failing
# command, and the group exits before `fail` can say what was wrong. The log is the diagnosis.
stop() { kill "$SP" 2>/dev/null || true; wait "$SP" 2>/dev/null || true; }
[ "$(code "localhost:$PORT/index.html")" = 403 ] || { stop; fail "serve: a plan page must be gated too — $(cat "$T/serve.log")"; }
[ "$(code "localhost:$PORT/?k=plantoken")" = 200 ] || { stop; fail "serve: the printed URL must open the plan page — $(cat "$T/serve.log")"; }
grep -q 'report ready' "$T/serve.log" || { stop; fail "serve: no banner — $(cat "$T/serve.log")"; }
stop
echo "feedback loop OK"

echo "plan suite OK"
