# Analysis guide — how to decide what a human must check

The report's only job: make the reviewer's signature honest at the lowest attention cost. Every rule
below descends from four principles: **the human is the bottleneck**, **credibility is the only
currency** (a false flag costs more than a miss), **fresh ignorance is a feature** (lead with questions,
not explanations), and **human points, AI investigates** (a gut-flag is an order to dig, not a verdict).

## 1. Budget first

| Bucket | Hard cap | Meaning | Test |
|---|---|---|---|
| **critical** | 3 | If this is wrong the change must not ship, and only a human can tell. | "Would I page someone if this were wrong in prod?" *and* "Can a test/linter/the author settle it?" → no |
| **medium** | 7 (soft) | Worth 60 seconds of a human's attention; wrong would cost a fix-forward, not an incident. | "Would a careful senior ask about this in review?" |
| **low** | — | Nice to know; collapsed by default. | Everything else you'd still mention. |

When you exceed a cap, **demote the least irreversible item** — not the least interesting.
Ranking between classes when the cap bites: irreversible damage (data, auth, money) > a structural
convention divergence (it propagates — the next change copies it) > a localised correctness question.
Rather than 5 criticals, produce 3 criticals and put the other two first in medium.
Zero findings is a valid report. Say so plainly; the "Everything else" list carries the honesty.
That list is grouped by each file's `area` from `diff-model.json` into four buckets, in this order —
**Code**, **Tests**, **Tooling**, **Docs** — so a reader can give code the glance and skip the rest as
a block. An empty **Tests** bucket still renders (`Tests · 0 files`): "did they test it?" is the
commonest question asked of that list, and its emptiness is the answer. Every other empty bucket is
omitted. The grouping is mechanical; do not restate it in prose. A file lands in the **first** bucket
that matches (the implementation is `area()` in `classify-diff.py`; keep the two in step):

| # | Bucket | Matches |
|---|---|---|
| 1 | **Tests** | a test dir segment (`tests/`, `test/`, `__tests__/`, `spec/`, `e2e/`, `fixtures/`, `__snapshots__/`, `__mocks__/`), or a basename like `*.test.*`, `*.spec.*`, `*_test.*`, `test_*.py`, `conftest.py` — fixtures and snapshots under a test dir included |
| 2 | **Tooling** | dot-dirs (`.github/`, `.vscode/`, `.claude/`, …) and root dotfiles, CI configs, lockfiles, manifests (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, …), `Dockerfile`, `Makefile`, `*.config.*`, `tsconfig*.json`, root-level `*.yml`/`*.yaml`, root-level `scripts/`, `CLAUDE.md`/`AGENTS.md` |
| 3 | **Docs** | `*.md`, `*.mdx`, `*.rst`, `*.adoc`, `*.txt`, `README`/`CHANGELOG`/`LICENSE`-class names, anything under `docs/`, `doc/`, `wiki/`, `adr/`, `rfcs/` |
| 4 | **Code** | everything else — the default, never empty by rule |

Tooling is decided before docs so a skill's `SKILL.md` or a `CLAUDE.md` counts as tooling, not prose.
DB files never reach this list: the schema artifact and its migrations are owned by the DB package (§8).

## 2. What earns a flag (signals, strongest first)

1. **Divergence** — what the code does ≠ what it claims. Misleading names (`hint` holding a secret,
   `isValid` that also mutates), a "refactor" that changes behaviour, a helper doing more than its
   caller expects, scope beyond the task. Tag `divergence`.
2. **Convention divergence** — the code contradicts a written rule or the local precedent: an
   architecture/layering rule, a pattern every sibling file follows, a library or technology the
   project standardised on (or deliberately does not use), a naming/error/logging convention.
   **Critical when the divergence is structural** — a layer skipped, a second way to do something
   the codebase already does one way, a dependency that duplicates an existing one — because it
   *propagates*: the next change copies it, and only a human can say "deliberate new direction" or
   "mistake". Localised or cosmetic → medium/low. Tag `convention`.
   **A convention finding MUST cite its authority in `diverges_from`**: the rule
   (`CLAUDE.md:161`, `docs/adr/0010-…md`) or **≥ 2 neighbours** that do it the other way
   (`src/features/x/service/a.ts:44`). `$OUT/conventions.txt` lists the rule documents that govern
   the changed paths and the untouched siblings in each changed directory — read it before judging.
   Without a citation it is taste, and taste is not a finding: the validator rejects it.
3. **Blast radius × reversibility** — migrations, data deletion, auth/permission checks, money,
   public API shapes, persisted formats, background jobs, retries. Tag `blast-radius`, `data`,
   `auth`, `api`, `money`.
4. **PII / secrets flow** — a field renamed, wrapped, logged, serialised, sent, stored. Follow the
   value, not the keyword. Tag `pii`, `secret`.
5. **Confidence × blast-radius mismatch** — a big-impact change the author was *very* confident
   about, or justified at length, deserves a second look precisely because of that. Tag `confidence`.
6. **Author confession** — spots the implementer (you, in this session) was unsure of, guessed, or
   could not exercise. Always at least medium. Tag `confession`.
7. **Error paths and edges** — swallowed exceptions, new `catch {}`, defaults that hide failure,
   off-by-one at boundaries, time zones, concurrency, ordering. Tag `errors`, `concurrency`, `edge`.
8. **Tests that prove less than they look** — tests asserting the mock, deleted/skipped tests,
   snapshot churn. Tag `tests`.
9. **Intent gap** — an acceptance criterion with no visible implementation, or an implementation
   with no criterion. Tag `intent`.

Not a flag: style and naming *taste*, "could be simpler", anything a formatter/linter/type-checker
already enforces, anything already in the folded noise. Put those in `low` only if they'd mislead a
future reader. The line between taste and signal #2 is the citation: "I would have written it the
other way" is taste; "this is the only place in the codebase that does it this way, and `CLAUDE.md`
says not to" is a finding.

## 3. Shape of a finding

- `title` — the claim, ≤ 80 chars, falsifiable: "`saveUser` now upserts instead of inserting".
- `verify` — one question the human can answer by looking: "Is silently overwriting an existing
  row the intended behaviour for duplicate emails?"
- `why_human` — why a machine can't settle it (intent, judgement, domain, irreversibility).
- `what` — 1–2 sentences of mechanism, optional. Lead with the question, not the lecture.
- `file`, `lines` (new-side line or range), `hunks` (`["F3H2"]`) — the renderer fetches the code.
- `tags` — from the list above; they become filter buttons and feed the learning loop.
- `diverges_from` — required on a `convention` finding: the rule or the neighbours it contradicts,
  as `path` / `path:line` strings, each with a short `why` when the path alone does not show it.
  These render next to the finding, so the reviewer can open the rule and the code side by side.

## 4. Phases (altitude 1)

Group by **dependency**, not by file or commit: types/schema → core logic → integration/wiring →
UI → tests/docs. Each phase: a title a stranger understands, 1–3 sentences, the files. 2–6 phases;
a one-file change gets one phase.

## 5. The map (altitude 1, visual)

Nodes are *symbols the change touched that matter*: functions, components, types, modules, stores,
tables, endpoints. Mark each `added | modified | removed | moved | renamed | split | unchanged`
(`unchanged` only for an anchor the reader needs, e.g. the caller that was not touched). Edges:
`calls`, `dataflow` (a value travels), `imports`, `renders`, `extends`, `moved_to`, `split_into`,
`reads`, `writes`. Label edges with the *payload or purpose* when it isn't obvious (`user row`,
`JWT`, `POST /orders`). ≤ ~25 nodes — if the change is bigger, map the riskiest phase and say so in
`graph.narrative`. Use `symbol_moves` and `moved_from` from `diff-model.json` for moves/splits;
never guess a move the script didn't see.

## 6. Noise — trust the script, then be honest about its limits

`diff-model.json` already folded: pure renames (+ the import rewrites that follow them), moves,
splits, whitespace-only and format-only hunks (not in whitespace-sensitive languages), comment-only
hunks, lockfiles, generated/snapshot/binary files, **prop threading** (a prop declared once and
passed at N call sites — the declaration stays visible, the pass-sites fold under a flow of the
components it travels through), **index/registry rows** whose link target is a file this change
adds, and **working notes** (plans, handoffs, journals, a lessons inbox — never an ADR, a wiki page,
a README or a changelog, which are the "why" a reviewer needs most).
Copy its `folds` into `report.folded`. If you
notice a fold that hides a real change (a "rename" at 52% similarity that also changed logic, a
snapshot that changed because behaviour did), surface that as a finding — that is exactly the
"P0 buried in the noise" failure this tool exists to prevent.

## 7. Writing

Plain English for a stranger. Name code in backticks. Verbs over adjectives. No praise, no
"successfully". Every sentence either tells the reviewer what to look at or why — delete the rest.

## 8. The DB schema package

A database change is **one entry** in the ranked list, whatever its file count: the authored schema
artifact is the headline, the migrations are a muted sidecar beneath it. Not a section of its own,
not pinned to the top — its position follows its severity like any other finding, so an additive
index sits below a real correctness bug. It is present **whenever the diff touches a DB file** (the
validator refuses a report without it), and its severity varies.

Everything mechanical is already in `diff-model.json → db`; copy it, do not re-derive it:

- `headline_kind` / `headline` — `"schema"` when the schema artifact changed, else `"migrations"`
  (the first migration is then the headline). A project with no schema concept — raw SQL, an ORM
  with migrations only — is the second branch of the same rule, not a degraded view.
- `migrations[]` — in run order (filename/timestamp), each with the operations the SQL parser found,
  its own severity, and a `summary` line. The line names **operations, not severity** (`drops 2
  columns; runs 1 UPDATE`), exists only for files with a critical/medium operation, and is capped
  at 100 chars. **Use it verbatim as the file's `note`, or leave the note out.** Every operation it
  names is literally in the file; a plausible-sounding line the parser did not produce is a
  confident claim a reviewer will act on, in the one section that exists to direct attention.
- `reasons[]` — bullets the SQL supports, each with a kind, a fixed severity and a reviewer
  question. Keep all of them (you may add one for a non-SQL migration you read yourself); rewrite
  `detail` toward risk if the parser's phrasing is flat.

| reason | fires when | severity | the reviewer's question |
|---|---|---|---|
| `destructive_ddl` | DROP COLUMN/TABLE, NOT NULL without default, type change, FK/cascade change, TRUNCATE | critical | what data does this lose, and is it recoverable? |
| `unrepresented_ddl` | DDL present in a migration but absent from the schema | critical | will it survive the next generated migration? |
| `data_mutation` | any DML (UPDATE/INSERT/DELETE/MERGE) | critical | does the predicate match the intended rows; is it idempotent? |
| `ordering` | 2+ migrations with data in one and structure in another | medium | does the backfill run before or after the structural change? |
| `schema_migration_drift` | schema diff present, no migration | critical | why is there no migration? |
| `structural_ddl` | new table/relation, unique constraint on existing data | medium | is this the intended shape; does existing data satisfy it? |
| `additive_ddl` | nullable column, plain index, dropped NOT NULL | low | is anything here more than additive? |

Severity comes **from the SQL**, never from the schema diff and never from filenames — a schema diff
can look innocuous while the generated SQL drops a cascade. The per-kind severity is decided in one
place (`REASON_SEVERITY` in `classify-diff.py`, mirrored in the validator); `data_mutation` is
critical there for irreversibility — if backfills prove routine enough that a constantly-firing
critical dulls the section, change it there, not per report.

**`unrepresented_ddl` has three detectors, and the reason says which fired** (`detected_by`), so a
heuristic hit can be discounted:

- `no_schema_diff` — migrations carry DDL and the schema artifact did not change, in a project that
  has one. Genuine drift: the ORM does not know the object exists and its next generated migration
  can silently drop it. Say **that**, never "handwritten migration". A DML-only migration with no
  schema diff is *not* drift — it is `data_mutation`, flagged for irreversibility.
- `config` — the repo lists its unmanaged SQL (`describe-changes.unmanagedSql` or
  `prisma-migrate.unmanagedSql` in `.claude/claude-skills.json`): an unmanaged object dropped and
  not re-created is drift; one re-asserted is the documented workflow and is not flagged.
- `heuristic` — no such config: object types ORMs typically do not model (`USING hnsw`/`gin`/…,
  partial indexes, triggers, functions, views, policies, CHECK constraints). False positives happen;
  a missed drift is worse.

The schema legitimately appears in a **phase** too, as shape ("Organization becomes the tenant
root"); the package in the findings carries **risk** ("drops 9 cascade edges; verify the backfill
predicate and its ordering"). If the two would read identically, the package's text is wrong —
rewrite it toward risk, do not delete it.
