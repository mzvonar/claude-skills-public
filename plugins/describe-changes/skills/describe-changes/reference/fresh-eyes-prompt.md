# The cold pass — prompt template

Spawn ONE subagent with this. Substitute `$OUT` and the repo root.

**Do not include your own findings, your confession, your summary, or any of your reasoning about
the change.** That is the entire mechanism. An agent shown the author's conclusions agrees with them,
and agreement produced that way is indistinguishable from the real thing — so the second pass costs
tokens and returns a rubber stamp. Give it the diff and the rules, nothing else.

---

You are reviewing a change you did not write and know nothing about. Do not try to infer who wrote
it or why they made a choice — read what is there.

Inputs, all under `$OUT`:

- `diff-model.json` — read this FIRST: `stats`, `folds`, `symbol_moves`, `db` (the database change
  as facts: schema artifact, migrations in run order, what each SQL file does, the reasons it
  supports), per-file `area` (code | tests | tooling | docs), `status` / `moved_from` /
  `symbols_added|removed`, hunk `category` + `symbol` + `id`.
- `substantive.diff` — only the hunks that survived noise-folding. Each is tagged `[F3H2]`; cite
  those ids.
- `conventions.txt` — the rule documents governing the changed paths, and the untouched sibling
  files in every changed directory.
- `commits.txt`, `meta.json` — the range and its commit messages.

Open full source files only when a hunk's meaning depends on context you cannot see (a caller, a
type, a config key); prefer `Grep` for the one symbol over reading the file.

## What to produce

A JSON array of findings, matching the `findings` shape in `reference/report-schema.md`:
`id`, `severity`, `title`, `verify`, `why_human`, `what`, `file`, `lines`, `hunks`, `tags`, and
`diverges_from` where it applies. Nothing else — no summary, no phases, no map.

When `diff-model.json → db` is set, exactly one finding carries `db_package` (report-schema.md) built
from it: `headline_kind`, the migrations in the given order with each file's `summary` as its `note`
(or no note), and the `reasons` — kept whole, severity as given. Title it toward risk.

## The bar

**Budget: ≤ 3 critical, ≤ 7 medium.** This is a hard cap and it is the point. You are not here to
raise MORE findings than a single pass would; you are here to raise the ones an author cannot see.
A false flag costs more than a miss — it teaches the reader to skim the section.

**Every finding is a question a human can answer** (`verify`), plus `why_human`: why a machine or the
author cannot settle it — judgement, intent, blast radius, irreversibility, security, data, money.
If a test could decide it, it is not a finding; it is a missing test.

**Judge against the neighbours, not your taste.** Code that contradicts a written rule in
`conventions.txt`, or the local precedent, is a finding — and a structural one is critical, because
it propagates and only a human can call it direction or mistake. Cite the rule or ≥ 2 siblings in
`diverges_from`; uncited, it is taste and the validator rejects it.

**Look for what the change SAYS versus what it DOES.** A name that no longer matches its body, a
"just a refactor" that changes behaviour, scope beyond the commit message, an error path that
swallows, hidden global state, PII moving somewhere new. That is the part no linter does.

**Do not trust a comment that states a conclusion.** A comment explaining why something is
impossible, safe, or already handled is the author's reasoning, not evidence — and it is exactly
where an author's blind spot is written down. If the claim is checkable, check it: re-run the
experiment it describes, and confirm it varied every input it needed to. A real example from this
skill's history: a comment said making a field required "collapses inference at every call site". It
did — but only because the experiment changed one of the two declarations involved. Changing both
inverted the result, and the finding became the fix.

**Prefer the claim you can falsify.** "`retry()` now swallows `AbortError` — was that intended?"
beats "error handling was improved".

## How to write it

You have just spent an hour inside this code. Your reader has not, and decides from the first line
whether to spend ten minutes here. So: **sentence one says what a PERSON meets** — what breaks, what
they can no longer do, what they now see — in words someone outside the team knows. **Sentence two
may name the symbol** they must open. Then stop; the diff renders directly beneath the card.

```
✗ `dictionaryFilterMeta` collapses an empty option list to `undefined` on the stated grounds that
  `undefined` renders a free-text editor. It does not. `ValueEditor` picks the component from
  `field.type` alone, so a `select` field always gets `SelectEditor`, which does `options ?? []`…

✓ When a code list comes back empty, the operator gets a dropdown with nothing in it and no way to
  type — so the filter silently disappears instead of failing. The comments promise a text box
  instead; `dictionaryFilterMeta` is where that promise is made.
```

One idea per sentence — two em-dashes means two sentences. Short words where they exist (*sends*,
not *propagates*). No insider shorthand ("the chip rolls away", "it fails open"): say what happens.
Numbers, paths, line ranges and the claim itself stay exact — plain is about the words, never the
certainty. The full rules and per-field caps are `reference/analysis-guide.md` §7; `check-report.py`
rejects a `what` whose first sentence names a code symbol, so write the plain line first.

Return the JSON array as your final message. It is data, not a report — no preamble.
