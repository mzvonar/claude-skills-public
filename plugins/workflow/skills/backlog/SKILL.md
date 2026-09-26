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
**3,622 lines, 247 items, 85 sections.** Every pass over it read the whole file to answer one
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

Frontmatter only — bodies are never read. On the corpus above that is **390 lines against 3,622**,
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
  above had **97 of 194** open items without one, which the monolith hid and this surfaces.

## Wiring grooming into a workflow

Grooming only happens if something makes it happen. Whatever you wire it into — a story-creation
hook, a PR template, a checklist, a skill listed under `orchestratorSkills` — that gate **names
WHEN and WHERE. It never restates WHAT.**

The buckets, the untriaged rule and the not-a-primary-source rule live in this file. A gate that
copies them creates two homes for one contract, and the copy drifts silently because nothing
type-checks prose. Measured on the first adoption: the gate restated the policy in 51 lines, and
its copy of the untriaged count was wrong twice before anyone noticed.

A gate that fits in a paragraph, and does not:

```text
Groom the backlog before scoping this work, using `/workflow:backlog`.
READ ITS `deferred-work` POLICY AND GROOMING SECTIONS AND FOLLOW THEM: the four buckets, what
makes an item untriaged rather than keep-deferred, and why a deferred entry is not a trustworthy
primary source all live there, and are deliberately not repeated here.

<this repo's index, read through scripts/backlog.mjs rather than by opening the file>

REPORT ONLY. This pass never edits the backlog; promotions and kills are applied by whoever
scopes the work, after the gate.
```

Keep in the gate only what is genuinely the *workflow's* and not the backlog's — that report-only
division of labour, and any repo-local rule about where an agent may write. Everything else is a
pointer.

**Then guard it, because its failure is silent.** A gate that is deleted, emptied, renamed, or given
a syntax error does not fail loudly — grooming simply stops happening and the backlog rots with
nothing to notice. On the first adoption the predecessor's own tooling *promised* a fallback gate
and never checked it, so the promise pointed at an empty list for months. Whatever holds your gate,
assert that it still resolves to a live step, and that it still points here.

**Guard the structure too, with the same validator.** Ids come from the working tree, so two branches
that each take the next free id collide when one merges the other. Git reports at most a conflict
in the index. `scripts/validate.mjs` names that (`DUPLICATE_ID`), along with pointers to nothing
and files nothing points at. Run it in CI with `--defects-only`:

```bash
node scripts/validate.mjs <index.md> --defects-only
```

That fails only on a structural defect. It still prints the grooming states (`NO_TRIGGER`,
`UNPROMOTED_APPENDS`, `RAW_APPEND`), but it does not fail on them. Each state is work waiting for a
person, not drift, and a build must not block on a judgment that nobody made yet. `STATES` in the
script is that list. A code that the scanner adds later counts as a defect until it is listed there.

## Grooming

**Step 0 — is this session reading the CURRENT skill text?**

```bash
bash "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/marketplaces/claude-skills-public/scripts/plugin-freshness.sh"
```

Local, no network, silent when current. **Exit 3** = this session is serving an older cached
version than the one installed — a session pins its version at the first call to a skill and never
moves, and nothing else reports it. Put it to the user with `AskUserQuestion`: reload
(`/reload-plugins`) and re-run, or carry on knowingly. Exit 2 or no such script = undetermined,
carry on. Why: `docs/conventions.md`.

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

Appends come in two shapes, and which one a repo gets depends on the generator and its installed
version — **check what the repo actually runs, do not assume the newest:**

```markdown
keyed   - source_spec: `<spec>`        bare   - <one bullet per finding, with description>
          summary: <one sentence>
          evidence: <why this is real>
```

Either shape has no detail file, so no `status` and no `trigger`. Treat it as **open and
untriaged**; grooming promotes it into a detail file. `scripts/validate.mjs` reports both
(`UNPROMOTED_APPENDS` for the keyed shape, `RAW_APPEND` for the bare one) — it keyed only on the
keyed shape until a repo running a bare-bullet generator showed that an append could land in the
index with nothing reporting it at all.

The closed vocabulary (`DONE`, `KILLED`, `CLOSED`, `SUPERSEDED`, `RETIRED`, `RESOLVED`) is shared
by `backlog.mjs`, `validate.mjs`, `verify-migration.mjs` and `migrate.py`. It is corpus data: if
your ledger retires items with another word, add it to all four, or those items read as open.

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

Migrate to a **scratch directory**, prove nothing was lost, then move it into place at `indexPath`.
The source is the only copy of the thing you are checking against, so never migrate over it.

```bash
LEDGER=<old-monolith.md>; OUT=$(mktemp -d)

python3 scripts/migrate.py "$LEDGER" "$OUT"            # index.md + index/
node scripts/verify-migration.mjs "$LEDGER" "$OUT"     # ← the gate. non-zero = do not commit
node scripts/validate.mjs "$OUT/index.md"              # structure, pointers, policy
```

Pass `--index-name <name>.md` to `migrate.py` and `verify-migration.mjs` to keep the name a
generator already appends to (the detail directory takes the stem).

`migrate.py` is **lossless for items by construction** — every item's block is written verbatim into
its detail file, and frontmatter is derived from that block, never invented. A field the source does
not state is emitted empty and counted, so gaps are visible rather than guessed. It also prints what
it refuses to decide: untriaged items, statuses it inferred, and open items under a retired heading.
Each of those lines is a task, not a statistic. A record need not contain a bullet — a section whose
heading is its own text is folded into an item, one per `### ` run or one for the whole section, and
the folded count is printed. It writes `policy: deferred-work` into the index; delete that line to
run a plain backlog.

`verify-migration.mjs` asks the two questions the counts cannot. **Did all of the source's content
reach the output?** — every item body verbatim and whole, and every other non-blank line by a
trimmed match, which is content-level rather than byte-level: re-indentation is not loss. On the
one measured corpus the bodies read a clean 251/251 while 23 section intros and one whole item
were on the floor. **Does a second extractor agree on WHICH items are closed?** — the two disagreed
44 against 40, and diffing them as *sets* rather than sizes is what turned a plausible near-match
into four named items.

Both of those fired on the first real adoption. **`reference/adopting.md` is the runbook** — the
order, what to do with each reported count, and the two decisions to make explicitly.
`reference/migration-traps.md` is why: twelve silent corruptions, each live against a real ledger —
including one the gate itself could not see, because both extractors were missing the same word,
and one where the gate exited 0 without running at all.
