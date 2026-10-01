---
name: plan
version: "2.1.0"
description: >
  Present a PLAN to the person who must steer it, before anyone implements it — an ad-hoc plan from
  the conversation, a story or task spec, a change proposal, or a whole epic. Plain words on what will
  be different for a person, a before/after map of what goes where, data-model and code sketches
  (types, signatures, endpoints, ports, components) in the project's own languages, the acceptance
  criteria, what stays the same, and the few steering points a human should settle first — each with
  the plan's answer, the alternative and its cost. Every path and symbol the plan names is checked
  against the repository; the page takes comments anywhere. Use whenever the user says "describe the
  plan", "walk me through the plan", "what are we going to build", "review / steer / judge this plan,
  epic, story or proposal", or "/describe:plan". Not for an implemented change — that is /describe:changes.
argument-hint: "[--epic N | --story KEY | --from FILE[#HEADING]... | --grep-from FILE REGEX...] [--slug NAME] [--chat-only] [--port N]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob
---

# describe:plan

**Goal:** let a person judge a plan's direction in ten minutes and steer it BEFORE anyone builds it.
The plan is written for builders; this page is written for the one who has to say "yes, but change
these two things". You allocate their attention; you do not paste the plan back at them.

**Division of labour (hard rule):** scripts do everything mechanical — assembling the plan's text
from files and headings, checking every path and symbol it names against the tree, quoting the code
as it is today, HTML, feedback capture. You do only what scripts cannot: say what the plan *means*
in plain words, draw the map, sketch the shapes in the project's own languages, and decide the ~3
steering points a human should settle first. Never write HTML, never paste the plan into chat.

## Before you begin — is this session reading the CURRENT skill text?

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-freshness.sh" "${CLAUDE_PLUGIN_ROOT}"
```

Local, no network, and **silent** unless something is wrong. Exit **3** — this session is serving
an older cached copy of THIS plugin than the one installed; a session pins its version at the first
call and never moves. Put it to the user (`AskUserQuestion`): reload (`/reload-plugins`) and re-run,
or carry on knowingly — and if you already put this question for this plugin in this session, just
note it and carry on; the check is stateless and will keep reporting. Exit **2** — could not
determine, which is not a pass. Exit **4**, or `No such file` / exit **127** — this call is wired
wrong and checked nothing; report it. Why: `docs/conventions.md` in `mzvonar/claude-skills-public`.

## 0. Resolve paths and inputs

```bash
SKILL_DIR=<dir containing this SKILL.md>        # ${CLAUDE_PLUGIN_ROOT}/skills/plan
S="$SKILL_DIR/scripts"                          # this skill's own scripts
CH="$SKILL_DIR/../changes/scripts"              # the SHARED ones: serve.py, feedback.py — one copy for both skills
```

**What is the plan?** Documents, never a planning tool's layout. In priority order: what the user
named (`--from`, `--epic`, `--story`) → the plan the conversation just produced (write it to a file
first, e.g. `.describe-changes/plan/<slug>/sources/adhoc.md`, and pass it with `--from`) → the story
or task file the session is working from. Say which one you took.

Arguments: `--from FILE` a whole file; `--from FILE#HEADING` one heading's subtree (substring,
case-insensitive; `#re:^Epic 15\b` for a regex — use the regex form for a number, or "Epic 1"
matches "Epic 15"); `--grep-from FILE REGEX` the paragraphs of a file matching a regex (a status
block, a dependencies paragraph); `--epic N` and `--story KEY` are sugar over those, resolved
through `.claude/claude-skills.json` (→ Configuration) and refused with a message when the keys are
not set; `--slug NAME` names the output dir; `--chat-only` skips the page; `--port N` for the server.

## 1. Collect + ground (script)

```bash
OUT=$(python3 "$S/collect-plan.py" [--epic 15 | --story 15-2 | --from docs/plans/x.md ...] | tail -1 | sed 's/^OUT=//')
```

Produces `$OUT/{sources/,plan.md,meta.json,structure.json,citations.json}`. **Read `plan.md` whole**,
then `structure.json` (the units — a plan's stories, tasks or steps — and their acceptance lines) and
`citations.json`: every repo path the plan names with `exists`/`in_range`, every backticked
identifier with the count of files that contain it. A missing path or an unknown symbol is either
a typo in the plan or a thing the plan will create — you decide which, and a stale citation is a
steering point (the plan is reasoning about code that is not there).

`structure.json → verbatim` holds the plan's **own acceptance criteria and open questions, word for
word**: every heading or bold label named that way (`## Acceptance Criteria`, `**Acceptance
Criteria:**` inside an epic's story, `## Open questions for T2`, `Decisions needed`, …), each with the
file and the lines it came from. Found by what a section is called, never by a planning tool's
layout; the collector prints `verbatim: N … sections`. The page shows them as written — you never
retype them (step 3).

`meta.json → languages` is the tree's language census. **Sketches are written in those languages**
— the one the file you are sketching is in — never in pseudocode, because the reader knows the
project's languages and can diff a sketch against the real file in their head; pseudocode they
cannot. Exit 2 = nothing to describe; stop and say so.

## 2. Read the plan AND the code it will touch

A plan describes a delta against code the reader has not opened. Before you write anything:

- **Open every file the plan says it will change** (`citations.json → paths` with `exists: true`,
  and the files a unit's acceptance criteria imply). The sketches quote them, with real line numbers.
- **For every shape the plan changes** — a type, a schema, a function signature, an endpoint, a
  port, a component's props, a table — find its current definition. The `datamodel` view and the
  sketches are before → after over THAT, not over what the plan says the code looks like.
- **Read the rules that govern the touched paths** (the repo's `CLAUDE.md`/`AGENTS.md`, the nearest
  README, an ADR the plan cites) and open one neighbour per touched directory. A plan that
  contradicts a written rule or the local precedent is a steering point with a citation — the
  reader decides whether that is a new direction or a mistake.
- **Separate what is DECIDED from what is OPEN.** A plan carries rulings with a date and an author
  (a proposal's decisions block, a gate answer, "owner, 2026-09-29"). Those render apart, dated, so
  nobody re-litigates one by accident; a steering point is a decision the plan made WITHOUT that,
  or one the code makes look different from how the plan imagined it.

If the plan is bigger than one sitting (`plan.md` > ~2500 lines), split it by unit and read the
units in the order the plan builds them; do not skim the whole and call it analysis.

## 3. Analyse → write `$OUT/report.json`

Follow `reference/analysis-guide.md` and the exact shape in `reference/plan-schema.md`. The
non-negotiables:

- **Plain words first, everywhere.** `plain` (the page's opening) is three to five sentences someone
  outside the team can read: what will be different for a person, and why — no symbol names. Every
  unit, steering point and sketch carries its own `plain`; the validator rejects one that opens on a
  code symbol. Mechanism goes in `detail`, `current`/`alternative`, or the sketch.
- **Steering budget:** ≤ 3 `critical` (settle first — building on the wrong answer costs a rewrite),
  ≤ 7 `medium` (weigh — worth a minute), the rest `low` (note). Each is a decision, not a doubt:
  `question` the reader can answer, `current` (what the plan says), `alternative`, `cost` (what
  changing it would cost, or not changing it), `why_human`. Sources, strongest first: a decision the
  plan made with no recorded ruling; a plan claim the tree contradicts (a cited path or symbol that
  is not there, a shape that differs from the plan's description); a rule or neighbour the plan
  diverges from; a cross-team or irreversible dependency; scope the plan does not name.
- **Sketches quote the code as it is today.** `before.lines` points into the real file, with a line
  range the validator checks; `after` is the planned shape in the same language — types,
  signatures, endpoints, props, DDL — never bodies, and never a promise: it is labelled *sketch* on
  the page. A new file has `status: "new"` and no `before`; a removal has no `after`.
- **Units** in the plan's own order, each with its acceptance criteria as written (`acs[].text`,
  with a `plain` twin when the criterion is dense), the files it `touches` (`new / changed /
  removed / unchanged`), what it `depends_on`, who reviews, a `size` (S/M/L). When the plan's
  acceptance-criteria section is in `structure.json → verbatim`, the page already shows every word
  of it: a unit's `acs[].text` may then be each criterion's own title line, its meaning in `plain`.
- **The plan's own words stay the plan's.** Its acceptance criteria and open questions render
  verbatim in their own band (`verbatim` above). Do not paraphrase them into `plain` or `summary`,
  and when a steering point IS one of the plan's open questions, say so in its `current` ("the plan
  asks this as Q2 and recommends (a)"), so the reader answers it once, in the plan's terms.
- **Views** (`../changes/reference/visualizations.md`, the shared toolset): a `datamodel` view
  whenever a stored or exchanged shape changes; a `flow` for the runtime path of one concrete user
  action; a `screen` for UI chrome; an `adoption` for a shared thing several places will use. The
  `graph` is the before/after map: nodes with `change` meaning "will be" — `added`, `modified`,
  `removed`, `unchanged` for an anchor the reader needs. ≤ ~25 nodes.
- **What stays the same** (`invariants`), **assumptions** each tagged `measured` / `read` /
  `assumed`, **how you'll try it** (`how_to_check`, future tense, one card per unit that a person
  can drive), **who else is involved** (`people`), a four-term **glossary**, the plan's dated
  **decisions**.
- Every `file` the report names must exist in the tree, except a `touches` or sketch entry whose
  status is `new`. Cite `path:line` so the page opens the lines.
- **`grounding_note`** — one sentence over `citations.json`: what the red rows are (a typo, another
  repository, a thing the plan creates). The rows are mechanical; this is the judgement a reader
  needs on top of them.

## 4. Validate (must pass)

```bash
python3 "$S/check-plan.py" "$OUT/report.json"
```

Fix every `ERROR`. Treat the prose warnings as errors too — length, sentence count, symbol count on
a `plain`, a `question`, a `title` — they are the difference between a page a person reads and one
they skim, which is the whole failure this skill exists to prevent.

## 5. Render + serve

```bash
python3 "$S/render-plan.py" --dir "$OUT"
nohup python3 "$CH/serve.py" "$OUT" --port ${PORT:-8791} > "$OUT/serve.log" 2>&1 &
sleep 0.5; cat "$OUT/serve.log"
```

Give the user the **LAN and Tailscale URLs** (phone-friendly) and the local path. **Pass the URLs
exactly as printed — each carries a `?k=…` token** minted for this run; the server binds 0.0.0.0 and
refuses any request without the token or the cookie the first open sets (named per port, so a plan
on 8791 and a change report on 8790 keep their own). The page is self-contained except the mermaid
renderer (CDN); the map degrades to its text list. Every path on the page opens the file **as it is
today**. The page has two levels, each fronted by a band: the **5-minute version** — the plain words,
the pictures and the steering points — then **the detail**, whose band is also a fold: open by default,
one tap shuts it, any link into it unfolds it; there is no mode to switch. Between them, when the plan
has any, sits **As written in the plan**: its acceptance criteria and open questions word for word,
in a band and fold of their own, every line numbered as it is in the plan file and commentable there.
If the `Artifact` tool is
available and the user is remote, you may also
publish `$OUT/index.html`. Skip all of this with `--chat-only`.

## 6. Present in chat (altitude 0 — short)

Exactly this shape, nothing more:

1. **The plain words, once** — the same 3–5 sentences as `report.plain`. Then one line of counts:
   `N units · N sketches · grounding X/Y paths found`.
2. **Steering points** as `S1 · title → question` for critical and medium; low as a count.
3. **Decided already** as one line: "N dated decisions, listed on the page".
4. **Units** as a numbered list, one line each (id · title · size).
5. The URLs. For `--chat-only`, inline the map as a ```mermaid``` block between 1 and 2, and the
   full steering list.

Do not paste sketches or acceptance criteria into chat. The chat is the page's top label.

## 7. Answer, collect the steering, apply it

Stay in this mode until the user moves on. The page takes input the same five ways the changes
report does — select any text and *Ask about this*, tap a line number beside any code line (a
sketch's planned lines included: they carry `sketch:<id>:<line>`; a line of the plan's own words
carries the plan file and its line — the address of the amendment), a note on a steering card, a
verdict button on it, a reply in a thread — and `comments` returns all of them:

```bash
python3 "$CH/feedback.py" comments --dir "$OUT" --open
python3 "$CH/feedback.py" notes --dir "$OUT"          # notes typed into steering cards, threads or not
python3 "$CH/feedback.py" answer --dir "$OUT" --id <id> --improvement "<what the page should have said>" --text "<answer>"
python3 "$S/render-plan.py" --dir "$OUT"              # the answer appears in Conversation; same URL
```

**The verdict buttons on a steering point mean:** ▲ *settle first* (the reader wants it decided
before work starts) · ▼ *fine as is* (the plan's answer stands) · ✕ *not a decision* (drop it from
the list) · ✓ *keep as planned*. They arrive as `more` / `less` / `noise` / `checked` events in
`$OUT/feedback.jsonl` (one JSON object per line, `finding` = the point's id; an `undo` event
retracts one) — read them from there, latest per point wins, and a ▲ with a note is an instruction.

**Turning the steering into the plan:** once the reader has spoken, draft the amendments — which
document, which section, the sentence as it would read — and put them in chat. **Edit the plan's
files only when told to**, and never a settled decision without its author: the page is a proposal
surface, the plan documents are the record. When you do edit, re-run steps 1–5 (same `--slug`) so
the page reflects the steered plan, and say so.

Log what the page failed to answer: `python3 "$CH/feedback.py" question "<the question>" --dir "$OUT" [--finding S1]`.

## 8. Close the learning loop

```bash
[ -f "$OUT/feedback.jsonl" ] && python3 "$CH/feedback.py" ingest "$OUT/feedback.jsonl" --dir "$OUT"
python3 "$CH/feedback.py" push      # no-op unless a shared backend is configured
```

Mention in one line how many lessons were recorded. The store and the digest are the ones the
changes skill uses (`../changes/reference/learning-loop.md`); a steering point's verdicts arrive as
the same `more / less / noise / checked` events.

## Configuration

Optional, in the consuming repo's `.claude/claude-skills.json`, under `describe` → `plan`. Nothing is
required: `--from` and `--grep-from` work everywhere. The keys exist so `--epic N` and `--story KEY`
can find a planning layout the skill deliberately knows nothing about.

```json
{
  "describe": {
    "plan": {
      "epics": "docs/planning/epics.md",
      "status": "docs/planning/status.yaml",
      "stories": "docs/stories",
      "proposals": "docs/planning/change-proposal-*.md",
      "outDir": ".describe-changes/plan",
      "verbatim": { "acceptance": ["kryteria akceptacji\\b"], "questions": ["points to settle\\b"] }
    }
  }
}
```

| Key | Default | Meaning |
|---|---|---|
| `epics` | unset | The file that holds `## Epic N` sections. `--epic N` extracts every heading matching `\bEpic N\b` and the paragraphs matching `Epic N dependencies`. |
| `status` | unset | A status file; `--epic N` includes the lines/paragraphs matching `epic-N` or `N-<story>` keys. |
| `stories` | unset | The directory of story/task files; `--story KEY` includes `<stories>/<KEY>*.md`. |
| `proposals` | unset | A glob; a proposal file the extracted epic text names is included whole. |
| `outDir` | `.describe-changes/plan` | Where a plan's report dir lands (the changes skill's directory, already gitignored in every consumer). |
| `verbatim` | unset | More section names the page shows word for word, as regexes matched from the start of a heading or bold label (case-insensitive; emphasis, a leading number and a trailing colon stripped). `acceptance` and `questions` each EXTEND the built-in English names — acceptance criteria / tests / scenarios, `AC`/`ACs`; open questions / issues / decisions, unresolved or outstanding questions, questions for …, decisions needed, `Questions` — and never replace them. |

## Style rules for everything you write

The reader is deciding, from the first line, whether to spend ten minutes here — and they have not
opened the code, may never have seen the plan, and are reading on a phone.

- **Plain first.** Sentence one says what a PERSON will meet — what they can do, what they no
  longer can, what they will see — in words someone outside the team knows. Sentence two may name
  the one symbol they must open. `check-plan.py` rejects a `plain` that opens on a symbol.
- **One idea per sentence.** Two em-dashes is two sentences. *sends* not *propagates*, *stops* not
  *precludes*. No insider shorthand; say what happens.
- **A steering point is a question with a cost**, not a worry. "Should the lookup live in the
  browser or the server? The plan says browser; the server would need one more endpoint and ties the
  screen to it" — that a person can answer.
- **Plain is about the words, not the certainty.** Numbers, paths, line ranges, quoted identifiers
  and the claim itself stay exact. A sketch is labelled a sketch; a decision carries its date.
- **Important first, short first.** The reader may stop at any line.

---
To change this skill, do not edit this copy: use `/dev-tools:update-skill`, or see `docs/updating-skills.md` in `mzvonar/claude-skills-public`.
