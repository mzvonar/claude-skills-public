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
# A plan whose criteria are a numbered LIST and whose questions are PARAGRAPHS: no sub-headings to split
# on, so the items come from the list's entries (a bold lead is the title; otherwise the first sentence,
# the rest the body) and from the paragraphs.
cat > docs/plans/listy.md <<'F'
# Listy plan

## Acceptance criteria
1. **Login works:** the page shows the list.
2. The second criterion has `code` and **bold**. It continues here
   on a wrapped line.
   - and a nested point

## Decisions needed
First paragraph question. With more text after.

Second paragraph question?
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
OUTL="$(python3 "$S/collect-plan.py" --from docs/plans/listy.md --slug listy | tail -1 | sed 's/^OUT=//')"
python3 - "$OUT" "$OUTS" "$OUTB" "$OUTC" "$OUTL" <<'PY'
import json, os, sys
epic, story, bg, conf, listy = sys.argv[1:6]
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
# Each section is split into its ITEMS, one card each on the page: a criterion's or a question's own
# heading gives its id and title, a parent heading with no text of its own is a GROUP, and every item
# keeps the plan file's own line numbers.
it = ac["items"]
assert [(x["id"], x["label"], x["title"]) for x in it] == [("AC-1", "AC-1", "first"), ("AC-2", "AC-2", "second")], it
assert src[it[0]["start"] - 1] == "### AC-1 — first" and it[0]["text"] == "- one `CodeValue`\n- two", it[0]
assert it[1]["text"] == "| a | b |\n|---|---|\n| 1 | 2 |" and it[1]["end"] == ac["end"], it[1]
assert ac["intro"] == "" and ac["groups"] == [], ac
q = oq["items"]
assert [(x["id"], x["title"], x["group"]) for x in q] == [("R1", "a rule", "Group 1 — rules")], q
assert oq["groups"] == [{"title": "Group 1 — rules", "intro": ""}] and "a label inside a section already taken" in q[0]["text"], oq
# An epic's Given/When/Then lines: one item each, the keyword as the label, the FILE's line numbers.
ei = e[0]["items"]
assert [(x["label"], x["title"]) for x in ei] == [("Given", "the platform's snapshot"), ("When", "it is mapped"),
                                                   ("Then", "`CodeValue` carries `status`"), ("And", "`alphaThing` stays")], ei
assert [x["id"] for x in ei] == ["given-1", "when-2", "then-3", "and-4"], ei
assert codes[ei[2]["start"] - 1] == "**Then** `CodeValue` carries `status`", ei[2]
# A list: one item per top-level entry — a bold lead or the first sentence is the title, the rest the
# body, nothing said twice; paragraphs, when there is nothing else to split on.
assert [(x["label"], x["title"], x["text"]) for x in c[2]["items"]] == [("1", "only a configured name finds this", "")], c[2]["items"]
la, lq = V(listy)
assert [(x["label"], x["title"], x["text"]) for x in la["items"]] == [
    ("1", "Login works", "the page shows the list."),
    ("2", "The second criterion has `code` and **bold**.", "It continues here on a wrapped line.\n- and a nested point")], la["items"]
assert [(x["label"], x["title"], x["text"]) for x in lq["items"]] == [
    ("1", "First paragraph question.", "With more text after."), ("2", "Second paragraph question?", "")], lq["items"]
listy_src = open("docs/plans/listy.md", encoding="utf-8").read().splitlines()
assert listy_src[la["items"][1]["start"] - 1].startswith("2. The second") and listy_src[la["items"][1]["end"] - 1] == "   - and a nested point", la["items"][1]
# Every item carries a content key (report_keys.item_key), unique across the page.
keys = [x["key"] for v in V(story) + V(epic) + V(listy) for x in v["items"]]
assert all(keys) and len(keys) == len(set(keys)), keys
print("verbatim OK")
PY
grep -q '^verbatim: 1 acceptance-criteria section, 1 open-questions section — 2 criteria and 1 question, one card each on the page' <(python3 "$S/collect-plan.py" --from docs/plans/story.md --slug story-7-2) \
  || fail "collect-plan does not report the verbatim sections and their items"

# ---- 1c. the Markdown a card renders: safe first, then readable ----------------------------------
python3 - "$S" <<'PY' || fail "mdlite"
import sys
sys.path.insert(0, sys.argv[1])
from mdlite import md_to_html as md, inline
# Safe: everything escaped, only known tags out, a link opens only for http(s).
assert md("a <script>x</script> & `<b>`") == "<p>a &lt;script&gt;x&lt;/script&gt; &amp; <code>&lt;b&gt;</code></p>"
assert "href" not in md("[bad](javascript:alert(1)) text") and "alert(1)" not in md("[bad](javascript:alert(1)) text").split("title=")[0]
assert md("[doc](https://x.test/a?b=1&c=2)") == '<p><a href="https://x.test/a?b=1&amp;c=2" target="_blank" rel="noopener noreferrer">doc</a></p>'
# Readable: emphasis, but never inside identifiers; a plan's escaped backtick inside a code span is a backtick.
assert md("keep SOME_ENV_VAR and snake_case plain, _this_ is em") == "<p>keep SOME_ENV_VAR and snake_case plain, <em>this</em> is em</p>"
assert inline("exactly once: `**Pinned tag:** \\`0.6.0\\``") == "exactly once: <code>**Pinned tag:** `0.6.0`</code>"
assert "" not in md("[`a`](https://x.test) and \\* and `x`")
assert md("- one\n- two\n  - nested **b**\n- three\n  continued") == \
    "<ul><li>one</li><li><p>two</p><ul><li>nested <strong>b</strong></li></ul></li><li>three continued</li></ul>"
assert md("3. third\n4. fourth") == '<ol start="3"><li>third</li><li>fourth</li></ol>'
assert md("```yaml\nk: <v>\n```\nafter") == "<pre><code>k: &lt;v&gt;</code></pre><p>after</p>"
assert md("| a | b |\n|---|---|\n| 1 | `2` |") == '<div class="md-table"><table><thead><tr><th>a</th><th>b</th></tr></thead><tbody><tr><td>1</td><td><code>2</code></td></tr></tbody></table></div>'
# A code span naming a repository path can become a button that opens the file.
assert inline("see `src/a.ts:3`", code_link=lambda c: "<B>" if c.startswith("src/") else None) == "see <B>"
print("mdlite OK")
PY

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
# The plan's own words: a band and a fold of their own, between the 5-minute version and the detail —
# a list of cards, ONE per criterion or question, each its text rendered from the plan's Markdown and a
# comment box of its own. Never raw Markdown, never numbered source lines.
grep -q 'id="as-written" class="detail as-written"><h2 class="sec-t part part-v" data-collapsed="0"' "$H" || fail "the as-written band is missing, not a fold, or not open by default"
grep -q 'href="#as-written"' "$H" || fail "the TOC does not link the plan's own words"
grep -q 'section.as-written>h2.sec-t.part' "$H" || fail "the as-written band's styles are not injected"
python3 - "$H" "$OUT/structure.json" <<'PY' || fail "as-written cards"
import json, re, sys
h = open(sys.argv[1], encoding="utf-8").read()
items = json.load(open(sys.argv[2]))["verbatim"][0]["items"]
band = h[h.index('<section id="as-written"'):h.index("<!-- /as-written -->")]
cards = re.findall(r'<div class="card it it-acceptance" data-id="([^"]+)" data-item="[^"]+" data-key="([^"]+)">', band)
assert cards == [(x["id"], x["key"]) for x in items], ("one card per item, keyed by its content key", cards)
assert band.count('<div class="it-fb"><textarea') == len(items) == 4, "every criterion needs its own comment box"
assert '<span class="pill it-id">Then</span><div class="title"><code>CodeValue</code> carries <code>status</code>' in band, "a title is not rendered from Markdown"
assert 'class="l p' not in band and 'data-n=' not in band, "the band still prints numbered source lines"
visible = re.sub(r"<[^>]+>", " ", re.sub(r"<code>.*?</code>|<pre>.*?</pre>", " ", band, flags=re.S))
assert "**" not in visible and "`" not in visible, "raw Markdown left in the band"
assert "codes.md:" in band, "a card does not say where it sits in the plan"
print("as-written cards OK")
PY
# The other shapes, rendered: headings with a group (the story), a numbered list and paragraphs (listy).
for D in "$OUTS" "$OUTL"; do cp "$OUT/report.json" "$D/report.json" && python3 "$S/render-plan.py" --dir "$D" >/dev/null || fail "render of $D failed"; done
python3 - "$OUTS/index.html" "$OUTL/index.html" <<'PY' || fail "as-written shapes"
import re, sys
st, li = (open(p, encoding="utf-8").read() for p in sys.argv[1:3])
assert re.findall(r'class="card it it-(\w+)[^"]*" data-id="([^"]+)"', st) == [("acceptance", "AC-1"), ("acceptance", "AC-2"), ("questions", "R1")], "story cards"
assert '<h3 class="it-group">Group 1 — rules</h3>' in st, "a group heading is missing"
assert "<ul><li>one <code>CodeValue</code></li><li>two</li></ul>" in st, "a criterion's list is not rendered"
assert "<table><thead><tr><th>a</th><th>b</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr></tbody></table>" in st, "a criterion's table is not rendered"
assert '<span class="pill it-id">1</span><div class="title">Login works' in li, "a bold lead is not the title"
assert "The second criterion has <code>code</code> and <strong>bold</strong>." in li and "<li>and a nested point</li>" in li, "a list item's title and body"
assert re.findall(r'class="card it it-questions[^"]*" data-id="([^"]+)"', li) == ["1", "2"], "paragraph questions"
print("as-written shapes OK")
PY
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
# A comment typed into one of the plan's own criteria cards: the epic's Given line, by its content key.
IKEY="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["verbatim"][0]["items"][0]["key"])' "$OUT/structure.json")"
ILINE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["verbatim"][0]["items"][0]["start"])' "$OUT/structure.json")"
printf '%s\n' '{"ts":"2026-01-01T00:00:00Z","type":"more","finding":"S1","report_id":"x"}' \
  "{\"ts\":\"2026-01-01T00:00:01Z\",\"type\":\"note\",\"finding\":\"S2\",\"finding_key\":\"$KEY\",\"text\":\"sort by label, please\"}" \
  '{"ts":"2026-01-01T00:00:02Z","type":"comment","id":"cplan1","text":"why a new file?","anchor":{"text":"SnapshotValue","context":"…","section":"sketches","finding":"K2","file":"sketch:K2","line":1,"side":"new"}}' \
  "{\"ts\":\"2026-01-01T00:00:03Z\",\"type\":\"item_note\",\"item\":\"given-1\",\"item_key\":\"$IKEY\",\"text\":\"which snapshot?\"}" \
  > "$OUT/feedback.jsonl"
python3 "$CH/feedback.py" comments --dir "$OUT" --open > "$T/cm" || fail "comments"
grep -q '\[cplan1\] OPEN' "$T/cm" || fail "a comment on a sketch line is not listed"
grep -q 'at:        sketch:K2:1' "$T/cm" || fail "a sketch-line comment does not report its anchor: $(cat "$T/cm")"
grep -q "\[note-$KEY\] OPEN · note" "$T/cm" || fail "a steer note is not listed as a thread: $(cat "$T/cm")"
grep -q "\[itemnote-$IKEY\] OPEN · comment on an acceptance criterion · as written · Given" "$T/cm" || fail "a comment on a criterion card is not listed as a thread: $(cat "$T/cm")"
grep -q "at:        docs/plans/codes.md:$ILINE" "$T/cm" || fail "a criterion comment does not say where the criterion sits in the plan: $(cat "$T/cm")"
python3 "$CH/feedback.py" notes --dir "$OUT" | grep -q '\[item given-1\]' || fail "notes does not list a criterion comment"
python3 "$CH/feedback.py" answer --dir "$OUT" --id cplan1 --improvement "say why the wire shape is its own file" --text "It mirrors the platform's contract, generated from it." | grep -q "answered cplan1" || fail "answer"
python3 "$CH/feedback.py" answer --dir "$OUT" --id "itemnote-$IKEY" --text "It is the platform snapshot of the table." | grep -q "answered itemnote-$IKEY" || fail "answer on a criterion comment"
python3 "$S/render-plan.py" --dir "$OUT" >/dev/null
grep -q 'id="t-cplan1"' "$H" && grep -q "mirrors the platform" "$H" || fail "the answer is not rendered into Conversation"
grep -q 'sort by label, please</textarea>' "$H" || fail "the steer note is not replayed into its card"
grep -q "id=\"t-note-$KEY\"" "$H" || fail "the steer note has no thread"
grep -q 'class="card it it-acceptance noted" data-id="given-1"' "$H" || fail "a commented criterion card is not marked"
grep -q 'which snapshot?</textarea>' "$H" || fail "the criterion comment is not replayed into its card"
grep -q "id=\"t-itemnote-$IKEY\"" "$H" && grep -q "It is the platform snapshot of the table." "$H" || fail "the criterion comment and its answer are not in Conversation"
# Answered threads stay OPEN on the page: the reader comes back for the answers, and a collapsed
# section read as "no answers" on a phone.
grep -q '<section id="conversation"><h2 class="sec-t" data-collapsed="0"' "$H" || fail "the Conversation section is collapsed by default"
python3 "$CH/feedback.py" ingest "$OUT/feedback.jsonl" --dir "$OUT" | grep -q "ingested 4" || fail "ingest"
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
