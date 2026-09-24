---
name: test-integration-audit
description: >
  Audit an integration test suite (Vitest, Jest, or similar running against a
  real database or real services) for duration and quality: pull TWO timing
  profiles — the runner's per-test clock AND the database's own accounting
  (pg_stat_statements, per-test query counts) — decompose the fixed
  infrastructure costs, audit the measured hot spots in parallel subagent
  batches, bucket the findings with infrastructure wins first, then implement
  bucket-by-bucket via subagents — each bucket benchmarked under the repo's
  run lock against a machine-local baseline, with a coverage diff proving
  deletions lost nothing. Use when asked to "audit the integration tests",
  "speed up the integration suite", "integration tests take too long", "why
  are the repository/DB tests slow", "find duplicate or broken integration
  tests", "run an integration test audit", or to continue a previous audit's
  next bucket. For pure unit/component suites use /test:test-unit-audit; for
  browser e2e suites (Playwright, Cypress) use /test:test-e2e-audit.
  Self-configures on first run in a repo: discovers the sanctioned commands,
  the isolation strategy and the database guardrails, confirms them with the
  user, and writes .claude/claude-skills.json. Produces
  docs/test-integration-audit-<date>.md plus one
  docs/test-integration-benchmark-bucket<N>.md per implemented bucket.
---

# Integration Test Audit — two-sided profile → batch analysis → buckets → measured fixes

Ported from /test:test-unit-audit (itself ported from /test:test-e2e-audit,
whose method came from a real ~570-test Playwright audit). The phases and
discipline are the same; what changes at the integration tier is where the
time hides:

- **The database is half the suite.** A unit test's cost is CPU in one
  process; an integration test's cost is round-trips × latency + query cost +
  fixture volume, paid in a SECOND process the runner's profile cannot see
  into. So this audit runs TWO profiles: the runner's per-test timing AND the
  database's own accounting. A test slow on the runner's clock but cheap on
  the DB's is *waiting* (app-side sleeps, polls, serialization); slow on both
  is *querying badly*; cheap per query but chatty is paying a *round-trip
  tax*. The join of the two tables is the audit's map.
- **Isolation strategy is the biggest lever.** How the suite gets clean state
  per test — transaction rollback, truncate, re-seed, DB-per-worker — usually
  dominates every per-test finding. Name the strategy FIRST and audit against
  it: half the duration findings at this tier are tests paying for a second
  isolation strategy on top of the one already in force (hand-rolled cleanup
  under a rollback environment), and the worst correctness findings are code
  paths that silently *escape* it.
- **Fixed costs are infrastructure.** Container start, migrations, and global
  seed are per-RUN; environment boot is per-FILE; clean+seed rituals are
  per-TEST. Decompose all three layers before hunting per-test wins — a
  minute of `migrate deploy` replay dwarfs any single test.
- **Coverage is still a proof.** Same runner as the unit tier, so a
  deletion/merge bucket keeps the mechanical before/after coverage-diff
  guarantee.

First field run (2026-09, a ~2,100-test / 184-file suite): 104.8s → 76.5s
(−27%), with the DB measured at **4%** of suite cost, ~10s of real sleeps,
~5s of fixture seed loops, and **56 files that never touched the database**
misfiled into the DB project. Several lessons from that run are folded in
below, marked "(measured)".

The mechanics below name Vitest + Postgres (+ Prisma where an ORM hook is
needed) where a concrete command is required; substitute the project's runner,
database, and data layer — the method is stack-agnostic.

## Configuration & first-run setup

Config lives in `.claude/claude-skills.json` under a top-level
`test-integration-audit` key. **On the first invocation in a repo (no key
present), run SETUP before any auditing** — and at this tier the stakes are
higher than wrong benchmarks: integration setups are routinely DESTRUCTIVE
(drop schema, truncate, re-migrate), so a wrong command or a wrong database
URL destroys real state, not just numbers.

### Setup procedure

1. **Discover each key** (evidence, not guesses):
   - `fullSuiteCommand` — enumerate the package.json test scripts and READ
     each candidate's definition. Two traps are standard at this tier:
     *tier mixing* (a bare `test` script running unit AND integration
     projects together — record the integration-only invocation) and
     *serialization wrappers* (repos that share one test database across
     sessions/worktrees often wrap the run in a machine-wide lock script —
     the sanctioned command is the WRAPPED one; a bare `vitest run --project
     integration` that routes around the lock can wipe another session's
     schema mid-run). **One-shot form always** — never the watch-mode
     default.
   - `timingCommand` — the full-suite run with a machine-readable per-test
     reporter (Vitest: `--reporter=json --outputFile=tmp/integration-timing.json`),
     wrapped in the same lock. Verify it emits per-test durations.
   - `listCommand` — collect-only parse check (`vitest list --project …`).
     Confirm whether it triggers the DB global setup; if it does, note it —
     "cheap" verification that drops and re-migrates a schema is not cheap
     and not safe while anything else runs.
   - `typecheckCommand` — from scripts (`typecheck`, else `tsc --noEmit`).
   - `coverageCommand` — the suite with coverage on; confirm the provider
     package is installed rather than assuming.
   - `dbStartCommand` / `dbSetupCommand` — how the test database is brought
     up and migrated/seeded (compose file, `db:test:*` scripts, testcontainers
     inline). Read what setup actually DOES — note every destructive step.
   - `dbShellCommand` — a psql (or equivalent) invocation reaching the TEST
     database, for the DB-side profile (e.g.
     `docker compose -f docker-compose.test.yml exec db psql -U postgres uctoinak_integration`).
   - `dbName` — the test database's name, verbatim. The audit refuses to run
     anything until it has confirmed, via `dbShellCommand`, that the
     configured URL lands on this database and no production-shaped one.
   - `isolationStrategy` — one of `tx-rollback` | `truncate` | `reseed` |
     `db-per-worker` | `none`, discovered by reading the test environment and
     setup files, not the README. This drives which findings are redundant
     cost and which are load-bearing.
   - `docsDir` — where audit + benchmark docs land (default `docs`).
   - `auditModel`, `auditDepth` — as in /test:test-unit-audit: optional
     cheaper model for the read-only fan-out (user-set, never silent), and
     `"full"` vs `"weighted"` reading depth justified by the timing table.
   - `notes` — one-paragraph repo facts the audit must respect: which lock
     serializes runs, which OTHER suites share the box or the DB server (an
     e2e suite on the same Postgres instance contends for it even from a
     different database), env files, CI topology (services block vs compose).
   - `notesFile` — optional markdown file of richer project specifics, shared
     with the sibling audit skills (see "Project notes file" in
     /test:test-unit-audit — same contract: read in full before any command;
     update it when discovery contradicts it).
2. **Confirm with the user** before writing — especially `fullSuiteCommand`
   (wrapped vs bare) and `dbName`. Never pick between plausible arbiters
   silently, and never guess a database name.
3. **Write** the confirmed block to `.claude/claude-skills.json` (create or
   merge). Example result:

```json
{
  "test-integration-audit": {
    "fullSuiteCommand": "pnpm test:integration",
    "timingCommand": "bash scripts/with-integration-lock.sh vitest run --project integration --reporter=json --outputFile=tmp/integration-timing.json",
    "listCommand": "pnpm vitest list --project integration",
    "typecheckCommand": "pnpm typecheck",
    "coverageCommand": "bash scripts/with-integration-lock.sh vitest run --project integration --coverage",
    "dbStartCommand": "pnpm db:test:start",
    "dbSetupCommand": "pnpm db:test:setup integration",
    "dbShellCommand": "docker compose -f docker-compose.test.yml exec -T db psql -U postgres uctoinak_integration",
    "dbName": "uctoinak_integration",
    "isolationStrategy": "tx-rollback",
    "docsDir": "docs",
    "auditDepth": "full",
    "noiseFloorPct": 10,
    "notesFile": "docs/test-audit-notes.md",
    "notes": "runs are serialized by scripts/with-integration-lock.sh (setup drops the schema); e2e shares the Postgres CONTAINER on another database — don't benchmark while e2e runs"
  }
}
```

4. **Keep it current**: write the measured `noiseFloorPct` back after the
   baseline; on later runs re-verify any command that fails and tell the user
   what changed.

## Non-negotiables

- **Every claim is measured or file:line-cited** — a finding names the file,
  line, mechanism, an S/M/L effort and an impact estimate in milliseconds
  where a profile provides one. Duration findings at this tier say WHICH
  clock (app-side, DB-side, or round-trips). No "probably slow".
- **Confirm the target database before any run.** Query the connected DB's
  name via `dbShellCommand` (`SELECT current_database()`) and check the
  suite's own guardrail (an assert that refuses to run against the wrong
  DB). A suite with a destructive setup and NO such guardrail gets one as a
  bucket-1 finding — that is a safety fix, not an optimization.
- **Zero coverage loss, proven — with LINE identity.** Deletion/merge buckets
  run the coverage command before and after with BOTH `json-summary` and
  `lcov` reporters; the summary diff finds a regressed file, the lcov pair
  names the exact lines. Reading both tests is still required to fold unique
  assertions into a survivor — coverage proves lines, not assertions.
- **One-shot mode always**, and **read result counters by grepping the whole
  log** — never a fixed-size tail; a red run can read green from its last
  lines.
- **A measuring run owns the box AND the database server.** No typecheck,
  lint, builds, or other suites while a benchmark is in flight — including
  suites on a DIFFERENT database of the same server (shared buffer cache,
  shared disk, shared CPU), and write-subagents stay paused. The saturation
  signature at this tier: timeouts in `beforeEach` seed/clean hooks of files
  the diff never touched ⇒ the run is INVALID; rerun on a quiet box.
- **Respect the serialization wrapper, never route around it.** If the repo
  locks integration runs, every scripted run in this audit — benchmarks,
  scoped verifications, coverage — goes through the wrapper. Queueing behind
  it is a cost; wiping another session's schema is an incident.
- **Warm state is part of the protocol.** The first run after a container
  start pays cold caches (DB page cache, ORM engine, module transforms) —
  discard a warm-up run before measuring, and record container state per run.
- **Config experiments are results either way.** An isolation/parallelism/
  DB-tuning change that measures WORSE gets reverted with the measurement
  written beside the setting — otherwise the next audit re-runs the
  experiment.
- **Commits only when the user explicitly asks.** One commit per bucket,
  message carrying the measured delta.

## Phase 0 — Recon + two-sided profile (orchestrator)

1. **Runner profile.** Run `timingCommand` once (after a warm-up run) and
   reduce to two ranked scratch tables: top ~30 FILES by total duration, top
   ~30 TESTS by duration. Capture the runner's phase breakdown (transform /
   setup / collect / tests / environment) — at this tier `tests` usually
   dominates, but a fat `setup` line means the per-file environment boot
   (DB connect, per-file migrate checks) is the story.
2. **DB-side profile.** In the TEST container only:
   - `CREATE EXTENSION IF NOT EXISTS pg_stat_statements;` (compose:
     `command: postgres -c shared_preload_libraries=pg_stat_statements`) —
     **in the MAINTENANCE database (`postgres`), not the test DB** when the
     per-run setup drops the test schema: the drop deletes the extension's
     functions mid-audit while the preload keeps collecting (measured: the
     first reset call failed exactly this way). Reset stats, run the suite
     once, then rank by `total_exec_time` and by `calls`. The `calls` column is the round-trip census: a 0.2ms query
     called 40,000 times is a fixture-design finding no per-query profile
     shows.
   - **Per-test query counts**: hook the ORM's query event (Prisma:
     `$on('query')`, or the driver's log) into a counter reset per test and
     emitted alongside the timing profile. The top-N tests by query count
     are Phase 1's priority reading list next to the top-N by duration.
   - Join the two clocks for the hot tests: `app-time − db-time = waiting`.
     A big residue means sleeps, polls, or serialization — not SQL.
   - **State the suite-level verdict as a fraction**: db-time ÷ tests-phase.
     The first field run measured 4% — a number that flips the whole audit's
     center of gravity to app-side mechanics (sleeps, import churn, fixture
     CPU, misfiled unit tests) and justifies skipping DB tuning outright.
3. **Fixed-cost decomposition.** Time separately, once each: container start
   (cold), `dbSetupCommand` (the migrate/seed replay), the runner's global
   setup, and one trivial control test (connect + begin/rollback + `SELECT 1`,
   deleted afterward) — its wall time is the per-file/per-test floor every
   spec pays; multiply out by counts to size the ceiling on infrastructure
   wins before reading any test.
4. **Inventory**: the isolation strategy AND its enforcement mechanism (which
   setup file, which environment package, what actually rolls back);
   worker/pool topology — workers × connections-per-worker vs the server's
   `max_connections`, and any comment justifying caps; global seed content
   (what every test may assume exists); which projects CI actually runs
   (grep the workflows — a suite no workflow invokes is itself a finding);
   how CI provisions the DB (services block vs compose — a template-DB or
   tuning win must land in both or be honestly scoped).
5. **Smell greps** (leads for Phase 1, not findings): per-test
   `cleanDb`/`TRUNCATE`/`deleteMany` rituals under a rollback strategy; `new
   PrismaClient(`/`new Pool(`/`createConnection` in code paths under test
   (transaction-escape suspects); `create(` in loops inside fixture helpers
   (→ `createMany`); real `setTimeout`/sleep/retry helpers; `fetch(`/SMTP/S3
   clients hitting real networks from "integration" tests; `NOW()`/
   `CURRENT_TIMESTAMP` in queries whose tests pin JS time; ordering asserts
   with no `ORDER BY` in the query; hardcoded sequence IDs; bcrypt/argon2 at
   production cost in seed helpers; `test.skip|todo|fixme`; `catch` around
   assertions.

## Phase 1 — Audit fan-out (read-only subagents)

Partition by MEASURED cost as in the unit tier: top files by duration and by
query count get the most reader attention; the sub-100ms tail can be batched
coarsely under `auditDepth: "weighted"` with the timing table as declared
justification. 6–8 read-only agents launched together, honoring `auditModel`.
Each brief carries the relevant slice of BOTH profiles (time + query counts)
plus the named `isolationStrategy` — an agent that doesn't know rollback is
in force cannot recognize redundant cleanup. Agents read every batch file
fully plus the fixture/seed helpers it leans on.

Report three categories as tables of
`file:line | what | why | fix | effort S/M/L | est. impact (ms / queries where measured)`:

1. **DURATION** — fixture graphs seeding N entities to assert on 1 (→ minimal
   factories; cite the query count); per-test re-creation of state the global
   seed or the rollback already guarantees; hand-rolled cleanup under
   `tx-rollback` (pure cost — the environment rolls it back anyway); `create`
   loops in helpers (→ `createMany`/batch, or one `$transaction` round-trip);
   chatty assertion styles (a SELECT per field → one fetch, many asserts);
   real sleeps around polling for DB state (→ tighter poll interval, or
   assert the durable outcome directly — the write is synchronous in a
   transaction); **real retry/backoff waits in adapters under test** (→
   inject a sleeper — an optional ctor/param defaulting to the real one —
   and assert the SCHEDULE: exact delays called, which is stronger than any
   wall-clock bound; measured −8.9s in one file, and the "fake timers
   deadlock" folklore blocking it was a misdiagnosis); **per-test
   `vi.resetModules()` + re-import of heavy service graphs** (~700-800ms per
   cycle measured — only env-flip tests need a fresh graph; group by env
   config and import once per group; a barrel import maximizes the graph
   paid per reset); connection churn (per-test client construction);
   per-test schema checks or migrate calls; heavy module imports the test
   never uses at runtime (transform cost, same as unit tier);
   production-cost hashing in seeded identities (→ test-env cost factor,
   config-only).
2. **DUPLICATES / UNNECESSARY / WRONG TIER** — the same repository path
   exercised once directly and once per caller; tests asserting the ORM or
   the database does what its docs say (cascade deletes, unique-violation
   error codes) — UNLESS deliberately pinning a schema contract, then say so;
   pure-function logic wearing a DB costume (seed → read → assert on an
   in-memory transform: move to unit with a captured fixture literal);
   integration files that mock the entire data layer (a unit test paying
   integration env boot — move projects); multi-actor journeys driven
   through repositories that duplicate an e2e spec (fold or re-tier); tests
   that assert the same seed-shaped invariant N times across files.
3. **BROKEN (silently weak)** — the integration-tier cannot-fail signatures:
   **assertions satisfied by the seed rather than the tested action** (the
   test still passes with the action commented out — the tier's most common
   lie; the fix is delta-form assertions: capture before, act, assert the
   CHANGE); ordering assertions over queries with no `ORDER BY` (pass by
   insertion-order accident, flake under parallelism or a different plan);
   count assertions against shared seed (break when an unrelated test adds a
   row to global seed); **transaction escapes** — code under test opening
   its own client/pool: its writes COMMIT for real (state leaks across
   tests; the suite passes only serially) and its reads cannot see the test
   transaction's data (tests then "fix" this with real writes + manual
   cleanup — flag the whole cluster as one finding); floating
   `expect(...).rejects` without await; catch blocks swallowing constraint
   violations the test meant to assert; `NOW()` in SQL diverging from a
   pinned JS clock (assertions with time-window tolerances that sometimes
   miss); **ordering asserts on DB-defaulted timestamps** — inside the test
   transaction every `DEFAULT CURRENT_TIMESTAMP` row gets the SAME
   `transaction_timestamp()`, so an `ORDER BY createdAt` with no tiebreaker
   returns tie-order and the test passes on insertion accident (fix: seed
   explicit distinct timestamps NEWEST-FIRST so only the ORDER BY can pass
   the test; recommend an `id` tiebreaker in the product query);
   hardcoded auto-increment/sequence expectations; `test.skip`/`todo`
   older than the code they cover. Quote exact lines.

Agents VERIFY suspicious guards and claimed redundancies (is that cleanup
really covered by rollback, or does this one file run under a different
project/environment?) rather than assume.

Meanwhile the orchestrator audits what no batch owns: the test environment
package/config itself, every setup file line by line (paid per file × per
worker), the global seed (every row in it is load-bearing for someone — or
nobody: a seed entity no test reads is cost and confusion), fixture-helper
hot paths (helper cost × call count from the profile), and the compose
file / DB server flags.

## Phase 2 — Bucket report

Write `<docsDir>/test-integration-audit-<date>.md` with buckets in THIS order:

1. **Infrastructure & fixed-cost wins** — suite-wide, mostly config:
   - **Durability off for throwaway data**: `fsync=off`,
     `synchronous_commit=off`, `full_page_writes=off` on the TEST container
     (one compose line; safe precisely because the data is disposable). Often
     the single largest integration win and it costs nothing per-test.
   - **Template-database migration**: replace the per-run migrate replay with
     `CREATE DATABASE … TEMPLATE` from a once-migrated template (re-templated
     only when migrations change — key on a migrations-dir hash). Measure the
     replay first; land only if it pays.
   - Setup-file diet, connection-pool right-sizing, missing DB guardrail
     (the safety finding from Non-negotiables).
   Land bucket 1 first so later per-test deltas aren't confounded by it, and
   scope each change honestly across local AND CI provisioning.
2. **Hot-test surgery** — the top of the joined profile: seed diets, batch
   inserts, redundant-clean removal, poll tightening, chatty-assert folding.
   Each row cites its measured cost on the RIGHT clock (app ms, DB ms, or
   query count) so the payoff is predicted and attributable.
3. **Merges, dedup & tier moves** — duplicates folded, wrong-tier tests moved
   both directions. Expect the tier-move pile to be LARGE — suffix-routed
   projects rot silently and the first field run found 56 DB-free files
   (~30% of the project) paying the DB env. The coverage-diff proof applies
   to deletions/merges; for MOVES the proof is **run-mode collected totals
   across all projects before/after** (list-mode counts drift on
   dynamic/env-driven cases — measured ±5 — while run-mode reconciled
   exactly). A move DOWN to unit must
   carry mock fidelity (the new mock typed against the real module —
   `vi.mocked`/`satisfies` — because an untyped mock is the drift this tier
   exists to catch), and a move OUT of the arbiter command triggers Phase 5's
   relocated-vs-saved decomposition.
4. **Broken tests** — correctness at ~0 runtime cost, grouped: seed-satisfied
   / ordering-accident / tx-escape / swallowed-failure / clock-drift /
   dead-skipped. **Every repaired cannot-fail test is verified by a
   red-probe**: break the product query or guard in a scratch edit (comment
   out the write, flip the filter), watch the NEW assertion go red, revert,
   prove the revert with an empty product diff. Tx-escape findings repair the
   PRODUCT seam where possible (inject the client) — that is a product
   change; if it can't land now, file it to the deferred-work ledger with an
   ID and keep the test cluster's manual cleanup with a comment pointing at
   the ID.
5. **Parallelism & isolation experiments** — explicitly experimental, each
   lands only with a measured win and reverts with a recorded measurement:
   worker-count sweep BOUNDED by the connection budget (workers ×
   pool-per-worker ≤ `max_connections` with headroom — compute it before
   sweeping, don't discover it as `FATAL: too many connections` mid-run);
   `fileParallelism`; `isolate: false` where module state allows;
   **DB-per-worker** (each worker on its own template-cloned database —
   removes cross-worker contention and lock waits; the biggest structural
   experiment, land only with the paired protocol's blessing).

Cite each finding as file:line PLUS a short quoted anchor — executors locate
by content, never by line alone. Include a **"What NOT to touch"** list:
deliberate integration seams the agents verified — tests that exist because a
unit mock lied once, real-timer polls that mirror a production race window,
ORM-contract pins, timeouts and caps with measured justifications in their
comments (re-read those comments; a rejected experiment recorded there must
not be re-run).

## Phase 3 — Baseline on this machine

- Confirm the database (Non-negotiable #2), start the container, run
  `dbSetupCommand`, then ONE warm-up run (discarded), then `fullSuiteCommand`
  THREE times through the lock, foreground with a generous timeout —
  integration suites are usually minutes, not the e2e tier's tens of minutes;
  fall back to the detached `setsid nohup … ; echo $? > tmp/runN-exit`
  protocol only if a run genuinely exceeds tool timeouts.
- Record per run: wall clock, the runner's duration line and phase breakdown,
  pass/fail/skip counts, collected count, container state (warm/cold), and
  the DB-side totals (`pg_stat_statements` sum) so later buckets can claim
  DB-side deltas honestly. Derive `noiseFloorPct` from the spread and write
  it into the config — expect it to be worse than the unit tier's (a real
  database breathes: autovacuum, checkpoints, page cache).
- Coverage baseline in the same pass (json-summary + lcov), preserved under a
  dated name — reconstructing a pre-tree lcov later costs several scoped
  re-runs (measured at the unit tier).
- Triage every failure BEFORE calling the baseline valid; a pre-existing
  failure becomes a bucket-4 row, not a silent baseline feature.
- Worktree gotcha, extended for this tier: a worktree needs a real install
  (no `node_modules` symlink), regenerated ORM clients (`prisma generate`),
  AND the env files/compose project the DB setup reads — verify the worktree
  run reaches the SAME test database as the root checkout would, then let
  the lock serialize them.

## Phase 4 — Implement a bucket (write subagents)

- 3–6 agents per bucket, **disjoint file ownership**, launched in **staggered
  batches of 2–3** (prompt-cache races, rate-limit blast radius, core
  oversubscription — same reasoning as the sibling skills). The ORCHESTRATOR
  is sole owner of shared files — runner config, compose/DB config, setup
  files, global seed, shared fixture factories — and applies its pass AFTER
  all agents land, avoiding half-states (a fixture-helper batching change
  whose call sites haven't landed).
- Every brief carries the hard rules: **never run `git stash`** (measured
  incident: one agent's stash/pop reverted three agents' finished edits);
  **never run DB setup, reset, or compose commands** — the orchestrator owns
  the database; scoped verification runs go ONLY through the sanctioned
  lock-wrapped command (they queue behind each other — budget for it, and
  prefer batching several owned files into one run), and never during a
  benchmark; no shared-file edits; no commits; read files fully before
  editing; after deletions grep for dangling imports, orphaned fixture
  helpers, and seed rows now referenced by nothing.
- **Premise corrections are a deliverable.** Executors verify each finding's
  premise before acting — at this tier especially the redundancy claims (is
  this cleanup REALLY covered by rollback, or does the code under test
  commit out-of-band?). A wrong premise is a report-back, never a forced
  edit, and the orchestrator writes each correction into the audit doc.
- Point agents at the repo's MODEL-CITIZEN specs: the minimal-factory test,
  the delta-form assertion, the correctly injected client — grep and cite
  them in briefs instead of abstract instructions.
- **Interruption resilience**: reconcile `git status` against each agent's
  ownership list before resuming; resume with "re-check current on-disk
  state first" rather than restarting.
- After all land: diff review + typecheck + `listCommand` + **the repo's own
  policy ratchets/scanners** (count ratchets, style scans) — audit edits trip
  them in BOTH directions (measured: inlined fixture defaults carried banned
  casts into new code; deletion buckets LOWERED the count — lower the
  baseline to lock a drop in), then the bucket benchmark.

## Phase 5 — Benchmark the bucket

- Full suite through the lock, same warm-up-then-measure protocol, two–three
  runs per side. A delta smaller than the noise floor is "within noise",
  never spun.
- **Attribute on the right clock.** Hot-test buckets also time just the
  touched files before/after, and buckets that claimed DB-side wins attach
  the `pg_stat_statements` before/after (total time and CALLS — a fixture
  batching fix should show the round-trip count falling even when wall time
  sits near noise).
- **Deletion/merge buckets attach the coverage diff** as the
  zero-coverage-loss proof.
- **Decompose relocated vs saved** when tests moved tier or project: cost
  that moved gets its own timed row AND its CI wiring in the same bucket — a
  relocation reported as savings is dishonest, and a suite no workflow
  invokes rots silently.
- **Infra and parallelism experiments get the paired protocol**: default vs
  experiment on the SAME tree, interleaved A,B,A,B so machine and DB drift
  can't masquerade as a win; DB-tuning experiments also restart the
  container between sides so cache state is symmetric. A worse result is
  reverted and recorded beside the setting. Per-FILE times inside a parallel
  run carry worker-scheduling noise (measured ±200ms on untouched files) —
  a micro-optimization that regresses in-suite with no identifiable
  mechanism and no clean solo adjudicator gets REVERTED and recorded, not
  argued with (field case: a per-config import cache, logic-verified sound,
  +856ms in-suite — reverted).
- **Saturation flakes are triage, not regressions**: real-concurrency tests
  (uncontained clients, row-lock racers) can flake under an all-projects
  combined run on a small box (measured once: a lock-window race red at 4×
  oversubscription, green in isolation and under the arbiter). Verify
  green-in-isolation on a quiet box before treating it as yours.
- Write `<docsDir>/test-integration-benchmark-bucket<N>.md`: results table
  (run | tree | config variant | wall | runner phases | pass/fail/skip |
  collected | DB warm/cold), the DB-side delta where claimed, the coverage
  verdict where applicable, an honest "reading" section, deferrals, and a
  cross-link from the previous bucket's doc.
- **First-execution rule**: a bucket that adds, un-skips, or materially
  rewrites tests gets its validation run triaged test-by-test; new failures
  go back to the SAME agent for repair and re-run. When the failure is the
  PRODUCT's — a delta-form rewrite is often the first thing ever to actually
  check the write happened — file it to the deferred-work ledger with an ID,
  keep the rest strict, and point the test's comment at the ID.

## Recurring integration-tier mechanisms worth checking in any audit

- **The double-isolation tax.** Suites accrete cleanup rituals across eras:
  truncate helpers from before the rollback environment, `deleteMany`
  cascades "just in case". Under `tx-rollback` they are pure cost — but
  verify per file (a file in a different project, or a tx-escaping code
  path, may genuinely need its cleanup; deleting THAT one turns green runs
  red a week later). The keep-list test that held up in the field: a wipe
  stays when the SUT itself READS unscoped — a cross-org scheduler/cron
  asserted with exact global counts (2 of 13 flagged wipes were kept for
  exactly this). And the unscoped `deleteMany({})` wipes you do delete were
  more than waste: they take row locks on OTHER workers' committed
  escape-hatch fixtures — a documented cross-worker deadlock vector.
- **The transaction-escape hatch is two findings in one.** Code constructing
  its own client/pool escapes the test transaction: a correctness hole (its
  reads can't see test data, its writes leak and create order coupling) AND
  a duration cost (the cluster of tests working around it with real writes
  and manual cleanup). Fix the seam (inject the client), then delete the
  workaround cluster.
- **Round-trips beat query time.** ORMs make N+1 effortless — in fixtures
  (a loop of `create`), in code under test (a missing `include`), and in
  assertions (a query per field). The `calls` column finds all three; the
  fix differs (batch / product finding / fold), so attribute before fixing.
- **A slow test can be a slow query — which is a product finding.** When one
  query dominates on the DB clock, `EXPLAIN ANALYZE` it. A missing index on
  a test-hot path is often missing on the production-hot path too; report it
  as product performance, don't bury it in test cleanup.
- **Durability is the test DB's biggest tax.** Postgres spends most of a
  test suite's write time on crash-safety for data nobody will miss;
  `fsync=off` + `synchronous_commit=off` on the throwaway container is the
  sanctioned cheat. Never let those flags near a real environment — keep
  them in the test compose file only.
- **Migration replay grows monotonically.** Every audit, re-measure
  `dbSetupCommand`: repos accumulate migrations and the replay silently
  becomes the largest fixed cost. Template databases (or a periodic squash)
  reset it.
- **Connection budget arithmetic.** workers × pool-per-worker vs
  `max_connections` — compute it, comment it where the worker count is
  configured, and re-check after any parallelism experiment. Exhaustion
  presents as flaky timeouts, not as a clear error.
- **Global seed is a shared contract.** Every test may assume it; nobody
  owns it. Rows no test reads are cost; rows many tests COUNT are coupling
  (any addition breaks them — that's the count-assert finding). Delta-form
  assertions immunize tests against seed drift.
- **Clock skew between two runtimes.** Faking JS time does not fake
  `NOW()`; a query filtering on DB time while the test pins app time drifts
  by exactly the suite's runtime. Pin by injecting a clock into the code
  under test, or assert with explicit tolerances — never by sleeping.
- **Real external services don't belong here.** A real SMTP/S3/HTTP
  dependency in the integration tier is a flake seed and a policy question:
  containerized fake (compose it next to the DB) or move the test to e2e
  where the full stack is already paid for.
- **Nondeterminism debt, DB edition**: unpinned ordering, sequence values,
  UUID sort order, timezone-sensitive date bucketing. Pin at the seed/setup
  level so individual tests stop hand-rolling it.
- **Suite-local knobs belong in the project's `env` block**, not in shared
  dotenv files: a cost threshold (hashing rounds, a seeded-rows gate) or
  `LOG_LEVEL` set in the runner config's per-project `env` scopes to that
  suite only, wins over CI's inherited env, and carries its own comment
  (measured: a trust-gate threshold 50→3 seeded 16× fewer rows with
  identical semantics because tests referenced it symbolically; log level
  raised to fatal killed error-path stdout noise without touching spies —
  level filtering happens inside the logger).
- **Stdout as a cost center** — same as the unit tier, with one addition: a
  query-logging hook left at debug level can double a chatty suite's wall
  time all by itself. Profile hooks are for profiling runs, not the default.
