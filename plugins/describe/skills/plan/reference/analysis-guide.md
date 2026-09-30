# Analysis guide — how to present a plan so a person can steer it

Four principles, inherited from the changes skill and turned towards the future: **the human is the
bottleneck** (they read the page in the ten minutes before they say go), **credibility is the only
currency** (a page that flags everything steers nothing), **plain words carry the decision** (a
reader who has to decode symbol names never reaches the question), and **a plan is a claim about
code** — the page checks the claim against the tree, so the reader does not have to.

## 1. What the reader is doing

They are deciding two things: *is this the right direction?* and *what would I change before we
start?* Everything on the page serves one of those. The order of the page is the order of that
decision: plain words → pictures → the steering points → then the walkthrough, the sketches and the
evidence for whoever wants to check.

## 2. Plain words — the rule and the test

Sentence one says what a PERSON meets: what they will be able to do, what they no longer can, what
they will see. Sentence two may name the one symbol they must open. Never the reverse — the
validator rejects a `plain` whose first sentence names a backticked symbol.

```
✗ `CodelistRelationSchema` is removed and `CodeValueSchema` gains `status`, `position`, `parents`
  and `aliases`, mapped from `SnapshotValue` by a new `toCodeTable` in `map.ts`.

✓ A code on a record will know whether it is retired, where it sorts, and which region it belongs
  to — the same facts the platform keeps. The register's own "relations" list goes, because the
  platform sends each code with its parents instead.
```

Same content. The second one can be read on a phone by the product owner. The test for every
`plain`: *could the person who asked for this feature read it without opening a file?*

Habits that produce the first shape, and what to do instead: opening on a symbol (reorder);
chained clauses (split); stacked nouns ("the per-table snapshot revalidation path" → "asking the
platform whether a list changed"); insider shorthand ("fails open", "the tier goes advisory" — say
what happens); explaining the whole mechanism (name where it starts, the sketch has the rest).

**What plain never touches:** numbers, paths, line ranges, identifiers inside a `detail`, the
claim itself. Plain is about the words, not the certainty.

## 3. Steering points — the budget and what earns one

| Bucket | Cap | Meaning | Test |
|---|---|---|---|
| **critical** — settle first | 3 | Building on the wrong answer costs a rewrite, a migration, or another team's time. | "If they change this after unit 2 ships, what is thrown away?" — something. |
| **medium** — weigh | 7 (soft) | Worth sixty seconds; wrong would cost a fix-forward. | "Would the owner ask about this at the gate?" |
| **low** — note | — | Nice to know; collapsed by default. | Everything else you would still mention. |

Demote by *reversibility*, never by interest: when the cap bites, the point that can be changed
cheaply later goes down.

A steering point is a **decision with a cost**, and every one has the same five parts: the
`question` a person can answer, `current` (what the plan says), `alternative`, `cost` (of changing
it — or of not changing it), `why_human`. Sources, strongest first:

1. **A decision the plan made without a ruling.** The plan chose an answer and no dated decision
   covers it. Cite the sentence.
2. **A claim the tree contradicts.** `citations.json` says a path is missing or a symbol is nowhere;
   the current definition of a shape differs from how the plan describes it; a "one URL swap"
   that the code shows is a client and a mapper. Cite `path:line`. This is the class only the
   grounding pass can find, and the most valuable one: the plan is reasoning about code that is
   not there.
3. **A rule or neighbour the plan diverges from** — the repo's `CLAUDE.md`/`AGENTS.md`, an ADR, the
   way every sibling does it. Cite the rule (`path:line`) or two neighbours; uncited it is taste.
4. **A dependency that is irreversible or cross-team** — a contract another team must change, a
   migration, a realm, a credential, a published API. Say who and what.
5. **Scope the plan does not name** — a screen, a job, a consumer that reads the thing the plan
   changes and is not in any unit. Name the consumer.
6. **An assumption the plan rests on that nobody measured.** It also goes in `assumptions` as
   `assumed`; it becomes a steering point when a wrong guess changes the design.

Not a steering point: a preference of yours; anything a linter, a type checker or a test will
settle; a doubt with no alternative. **Decided already** is a separate list — a dated, attributed
ruling renders there and never as a steering point, even if you disagree; if you must reopen one,
say so as a steering point that names the ruling and the new fact that was not available when it
was made.

## 4. Sketches — the code as it is, then the code as it will be

A sketch is the plan's `after` set beside the tree's `before`. The rules:

- **Before is real.** `before.lines` points at the file as it is today; the page renders those
  lines with their real numbers, so a comment on one is a location a builder can open. Quote the
  definition that changes, not the whole file — 10 to 40 lines.
- **After is a shape, not an implementation.** Types, interfaces, signatures, a route with its
  method and status codes, a port, a component's props, a table's DDL. Never a function body,
  never test code. The page labels it *sketch*.
- **Same language as the file.** The census in `meta.json → languages` is the project's; a sketch in
  a language the project does not use warns. Pseudocode is refused by the reader before the
  validator gets to it.
- **One sketch per shape that changes**, ordered by the unit that lands it. The shapes a reader
  most needs: the domain types, the wire/DTO types, the port or client interface, the endpoint, the
  component props, the persisted table. A rename alone is not a sketch; say it in the unit.
- **A new file** has `status: "new"` and only an `after`; **a removal** has only a `before`.
  Something the plan deletes deserves a sketch as much as something it adds — the reader sees what
  goes.

## 5. Views and the map for a plan

`change` means "will be". The `datamodel` view is usually the centrepiece — one entity box per type
that changes, each field with its own `+ − ~`, relations beneath — because "what will we hold" is
the question a plan reader asks first. A `flow` view for the runtime path of ONE concrete action
(an operator opens a record: today the screen asks the register; after, it asks the platform through
the edge) reads better than a second graph. `screen` when chrome changes; `adoption` when several
places will use one new thing. The `graph` is the before/after map of the pieces: services, modules,
endpoints, stores — `kind: service | system | external` draws a hexagon for what lives outside this
repo. ≤ ~25 nodes; when the plan is bigger, map the riskiest unit and say so in `graph.narrative`.

## 6. The rest of the page, and why each part earns its place

- **Units** — the plan's own structure with its acceptance criteria as written. A dense criterion
  gets a `plain` twin; the original stays, because the builder reads that one.
- **What stays the same** — the invariants the plan preserves (nothing persisted changes; the URL
  stays; the write path is untouched). Cheap to write, and the first thing a nervous reader looks
  for.
- **Assumptions** — each tagged `measured` (a number, a byte comparison, a probe), `read` (a
  document, a source file) or `assumed` (nobody checked). The tag is the whole value: a page that
  says "assumed" out loud is trusted more than one that hides it.
- **How you'll try it** — future tense, per unit, what a person will click and see once it lands.
  The reader's way to stop trusting the page later.
- **Who else is involved** — teams, reviewers, the second signature a protected change needs.
- **Grounding** — every cited path and symbol, found or not. Rendered from `citations.json`;
  nothing to write, everything to read before you decide what is a typo and what is a plan.
- **Glossary** — four terms, plain. Not a taxonomy: the terms the page could not avoid.

## 7. Writing — the caps

| field | shape |
|---|---|
| `plain` (page) | 3–5 sentences, ≤ 800 chars, no symbol in sentence one, ≤ 2 anywhere |
| `plain` (unit / point / sketch) | 1–2 sentences, ≤ 300 chars, no symbol in sentence one |
| `title` | the claim or the decision, ≤ 80 chars (hard cap 130) |
| `question` | ONE question a person can answer; not its justification |
| `current` / `alternative` | one sentence each; the alternative is a real option, not a straw man |
| `cost` | what changing it costs — in units, files, other teams, time — or what not changing it costs |
| `detail` | 1–3 sentences; symbols welcome; the sketch carries the rest |

Plain is about the words, not the certainty. Keep no praise, no "successfully", verbs over
adjectives, and every sentence either tells the reader what will be different or what they must decide.
