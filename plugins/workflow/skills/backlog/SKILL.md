---
name: backlog
description: >-
  Keep a checked-in markdown backlog readable as it grows, and groom it against the work being
  scoped. Splits a monolithic list into an index plus one detail file per item (frontmatter holds
  the fields that decide what to work on), reads it through one script instead of a 3000-line
  file, and classifies every open item into promote-now / promote-separately / keep-deferred /
  kill with a paste-ready report. Use when picking what to do next, when the user says "groom the
  backlog", "check deferred work", "what should we pull in", "any debt to fold in", "review
  pending items", before a new story/task/epic is scoped or finalized, when a review defers a
  finding, when adopting the format in a new repo, or when the list has grown past the point of
  being read in full. Never fires mid-implementation or for one-line fixes.
---

# backlog

A backlog that lives in the repository, in markdown, stays workable past a few hundred items, and
is groomed against each piece of work before that work is finalized.

## The problem

A single append-only list works until it doesn't. Measured on one real corpus before adoption:
**3,622 lines, 251 items, 85 sections.** Every pass over it read the whole file to answer one
question about a handful of items, and every concurrent branch collided on the same trailing lines.

## Zero-config defaults

With no configuration the skill looks for `docs/backlog/index.md`; the detail files live in the
sibling directory named after the index's stem (`docs/backlog/index/`). Work items are referred to
generically — a *story*, *task* or *epic* are only examples of the vocabulary a repo may use.

## Configuration

Per-repo overrides live in `.claude/claude-skills.json` under the `backlog` key. Every key is
optional.

| key | default | meaning |
|---|---|---|
| `indexPath` | `docs/backlog/index.md` | The index file. The detail directory is its sibling named after the stem (`deferred-work.md` → `deferred-work/`). Keep an existing name when a tool appends to it by that name. |
| `paths` | `{}` | Related planning documents the grooming pass may consult, e.g. `{ "status": "docs/status.yaml", "roadmap": "docs/roadmap.md" }`. Read only what is listed; never guess at others. |
| `workItemVocab` | `["story", "task", "epic"]` | Words the repo uses for units of work; used in the report headings. |
| `orchestratorSkills` | `[]` | Skills (namespaced, e.g. `/workflow:something`) that call grooming as a discrete step before scoping. |
| `generators` | `[]` | Tools or skills that append entries to the index directly (see **Generators that append to the index**). |

```json
{
  "backlog": {
    "indexPath": "docs/planning/deferred-work.md",
    "paths": { "status": "docs/planning/sprint-status.yaml" },
    "workItemVocab": ["ticket", "milestone"],
    "generators": ["code-review"]
  }
}
```

## The shape

```
<dir>/index.md      the index: one entry per item, plus a `detail:` pointer
<dir>/index/        one file per item — frontmatter + the full record
```

A detail file:

```markdown
---
id: dw-014
summary: 'One sentence stating the item.'
status: open
trigger: 'the first change that touches the audit vocabulary'   # deferred-work policy only
---

- **The full record**, verbatim — evidence, anchors, measured numbers, the shape of the fix.
  Sub-bullets are context for the parent, not separate items.
```

Required on every item: `id`, `summary`, `status`. Everything else is free — the validator ignores
fields it does not know, so a repo can carry `priority`, `size`, `owner` or anything else without
changing this skill.

The index carries `summary` and `detail:` and **never repeats** the frontmatter fields, so the two
cannot disagree.

## Reading it

```bash
node scripts/backlog.mjs docs/backlog/index.md          # open items, one line each
node scripts/backlog.mjs docs/backlog/index.md --all    # include DONE / KILLED
node scripts/backlog.mjs docs/backlog/index.md --json   # for tooling
```

Frontmatter only — bodies are never read. On the corpus above that is **424 lines against 3,622**,
with closed items filtered rather than skimmed past. Open an item's detail file once you have
selected it.

**Never `Read` a large index whole.** A monolithic index that has outgrown the Read tool's limit
(roughly 256 KB / 25k tokens) fails the read and wastes a retry. `grep`/`rg` for the section
header or item you need, or `Read` with `offset`/`limit` on the matched line range; the same goes
for a bulky spec. **Pruning trigger:** if the file is over the limit because of accumulated
`**DONE**` / `**KILLED**` / closed-section entries, flag it to the user for archiving those into an
archive file next to the index — a bloated backlog costs every downstream reader a failed read.

## Policies

A policy says what makes an item **actionable**, and nothing else. It is declared in the index's own
frontmatter, so it is visible where you already look and there is no second config file to find:

```markdown
---
policy: deferred-work
---
```

| policy | an item is actionable when | requires |
|---|---|---|
| *(none — a plain backlog)* | you pick it | `id`, `summary`, `status` |
| `deferred-work` | its `trigger` has fired | the above, plus `trigger` on every open item |

An unrecognised policy is refused, not ignored — a typo must not silently drop the rules the author
was relying on.

### The `deferred-work` policy

For work parked with a reason rather than queued: debt, follow-ups, review deferrals. Every open
item sorts into exactly one bucket (see **Grooming**).

Two rules that matter more than the buckets:

- **A deferred entry is not a trustworthy primary source.** It records what was true when written.
  Verify against the code before promoting — an item can be silently already-done.
- **An open item with no `trigger` cannot be classified.** It is not "keep-deferred", it is
  **untriaged**, and the fix is to give it a trigger. Expect many on first adoption: the corpus
  above had **111 of 211** open items without one, which the monolith hid and this surfaces.

## Grooming

Grooming classifies every open item against the piece of work being scoped and returns a report.
It **never mutates the index** — the user (or the scoping step) applies the changes.

### When to fire

- Proactively, before a new unit of work is drafted or finalized — that is when promotions land
  cheaply instead of being noticed mid-implementation.
- Explicitly: "groom the backlog", "check deferred work", "review pending items".
- As a discrete step inside any skill listed in `orchestratorSkills`.
- At the start of a larger unit (an epic, a milestone) to find items that belong in its first
  cross-cutting task.

### When NOT to fire

- Mid-implementation of active work (creates churn).
- A bug fix or one-line edit — grooming is for work at story/task scale.
- A retrospective — that is a different pass with a different question.

### Inputs (always read fresh)

| Input | Purpose |
|---|---|
| the index + detail files | the backlog |
| the work being scoped | its draft spec if one exists; else the section of the roadmap that names it; else ask |
| `paths.*` from config | status file, roadmap, whatever the repo keeps — only what is listed |

### Buckets

| bucket | when | action |
|---|---|---|
| **promote-now** | the trigger fired, or the work touches the same code path / feature folder and the item is small (1–2 files) | fold into scope as a task |
| **promote-separately** | trigger fired but the item is cross-cutting (lint rule, test infra, schema-wide) or too large for this work | surface as its own piece of work, or as the first cross-cutting task of the larger unit |
| **keep-deferred** | the trigger has not occurred | leave it; say which trigger is being waited on |
| **kill** | contradicted by the current code, decision superseded, later work covered it | `status: KILLED (date)`, name what superseded it |

### Decision algorithm (first match wins)

1. **Already addressed?** Item contradicted by current code → **kill** (note what superseded it).
2. **Trigger satisfied?** Yes and it is this work → **promote-now**; yes but cross-cutting →
   **promote-separately**; no → continue.
3. **Same code path / feature folder?** Yes and small → **promote-now**; yes but large or
   cross-cutting → **promote-separately**; no → continue.
4. Otherwise → **keep-deferred**, noting the trigger being waited on.

### Defaults when uncertain

- Not sure whether an item should fire → **keep-deferred** with a note. False-promotion churn
  costs more than a false deferral.
- Not sure whether an item is already closed → check the closed items and any closed section;
  if still unsure, leave it and flag it in the report.
- Item references files or features that no longer exist → **kill candidate**, but ask the user
  to verify.

### Constraints

1. Never modify the index or a detail file during grooming — report only.
2. Every promotion or kill carries a one-line rationale — never classify without showing work.
3. Never classify items in a closed section or with a closed status.
4. Never discover new items by grepping the codebase — the backlog is the source of truth for
   what is deferred.

### Report format

Return inline markdown — do not write to disk. Use the repo's `workItemVocab` in place of "work".

```markdown
# Grooming Report — <work id>: <title>

Date: YYYY-MM-DD
Source: `<indexPath>`
Work being scoped: <link or summary>

## Promote now (N items)

### 1. <item summary>
- **From:** <section header or detail file>
- **Why promote:** <one sentence — which trigger fired or which file overlap>
- **Suggested task:** <one line, ready to paste into the task list>

## Promote separately (M items)

### 1. <item summary>
- **From:** <…>
- **Why separately:** <one sentence — cross-cutting or scope mismatch>
- **Suggested task:** <one line>

## Keep deferred (P items)

### 1. <item summary — first 80 chars + ellipsis>
- **From:** <…>
- **Trigger we're waiting on:** <what would un-defer this>

## Kill recommendations (Q items)

### 1. <item summary>
- **From:** <…>
- **Why:** <what superseded it>
- **Suggested change:** `status: KILLED (YYYY-MM-DD) — <reason>` in the detail file

## Summary

- Items reviewed: <total>
- Promoted now: N
- Promoted separately: M
- Kept deferred: P
- Recommended for kill: Q
- Items skipped (already closed): <count>

### Paste-ready additions for <work id>
- [ ] <task bullet>

### Paste-ready additions for the separate / cross-cutting task
- [ ] <task bullet>
```

## Generators that append to the index

Some tools — a code-review skill, a build step, a story-validation pass — append entries to the
index directly rather than creating detail files. List them under `generators` so the grooming
pass knows to expect their shape. That is why the index keeps its path and stays
**hand-maintained rather than generated**: a generated index would silently eat those appends on
the next regeneration.

A typical appended entry:

```markdown
- source_spec: `<spec>`
  summary: <one sentence>
  evidence: <why this is real>
```

Such an entry has no detail file, so no `status` and no `trigger`. Treat it as **open and
untriaged**; grooming promotes it into a detail file. `scripts/validate.mjs` counts them as
`UNPROMOTED_APPENDS`.

### Generator conventions (optional)

Generators that write to a monolithic index tend to organise it with section headers and inline
status markers. None of these are required by this skill; when the repo's generators use them, the
grooming pass parses them as follows:

| pattern | handling |
|---|---|
| `## Deferred from: code review of <work-id> [Group X] (YYYY-MM-DD)` | items inside are deferrals from that review; `[Group X]` is a batch label |
| `## Deferred from: <validation pass> of <work-id> (YYYY-MM-DD)` | same, from a validation pass |
| `## Post-<unit> N: <topic>` | evaluate only once the current unit is ≥ N |
| `## <work-id> spike: <topic>` | evaluate only if the spike is complete |
| `## <work-id> scope note (...)` | informational; classify normally |
| `## Architectural questions for <work-id>` | promote-now if that work is being scoped; else promote-separately if now blocking |
| `## Closed by <work-id>` | skip the whole section |
| a bullet wrapped in `~~…~~` | closed; skip |
| a bullet containing `**DONE (YYYY-MM-DD)**` or `**KILLED (YYYY-MM-DD)**` | closed; skip |

Item granularity: each top-level bullet is one item; sub-bullets are context for the parent, never
classified independently.

## Adopting it

```bash
python3 scripts/migrate.py <old-monolith.md> <output-dir>                 # index.md + index/
python3 scripts/migrate.py <old-monolith.md> <output-dir> --index-name deferred-work.md
node scripts/validate.mjs <output-dir>/index.md                          # structure, pointers, policy
```

`migrate.py` is **lossless by construction** — every item's original block is written verbatim into
its detail file, and frontmatter is derived from that block, never invented. A field the source does
not state is emitted empty and counted, so gaps are visible rather than guessed. It writes
`policy: deferred-work` into the index; delete that line to run a plain backlog. Pass `--index-name`
to keep the name a generator already appends to.

**Check the migration against an independent count before committing it.** Adoption is the one
moment the old format's inconsistencies must be parsed, and they are worse than they look — see
`reference/migration-traps.md` for the three that corrupted this migrator before they were found.

---
To change this skill, do not edit this copy: use `/dev-tools:update-skill`, or see `docs/updating-skills.md` in `mzvonar/claude-skills-public`.
