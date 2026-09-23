---
name: test-unit-audit
description: >
  Audit a unit/component test suite (Vitest, Jest, or similar) for duration and
  quality: pull a per-test timing profile from the runner first, audit the
  measured hot spots in parallel subagent batches, bucket the findings with
  fixed-cost config wins first, then implement bucket-by-bucket via subagents —
  each bucket benchmarked against a machine-local baseline and recorded in a
  markdown table, with a coverage diff proving deletions lost nothing. Use when
  asked to "audit the unit tests", "speed up the unit/test suite", "why is
  vitest/jest slow", "find duplicate or broken unit tests", "run a unit test
  audit", or to continue a previous audit's next bucket. For browser e2e suites
  (Playwright, Cypress) use /test:test-e2e-audit instead. Self-configures on
  first run in a repo: discovers the sanctioned commands, confirms them with the
  user, and writes .claude/claude-skills.json. Produces
  docs/test-unit-audit-<date>.md plus one docs/test-unit-benchmark-bucket<N>.md
  per implemented bucket.
---

# Unit Test Audit — timing profile → batch analysis → buckets → measured fixes

Ported from /test:test-e2e-audit (whose method came from a real ~570-test
Playwright audit). The phases and discipline are the same; what changes at the
unit tier is leverage:

- **The runner hands you a per-test timing profile for free.** At the e2e tier
  you fan out readers to *find* cost; here you MEASURE first and read second —
  batches and buckets are weighted by observed milliseconds, not suspicion.
- **Fixed costs dominate.** In a suite of thousands of small tests, the tax paid
  per FILE (environment boot, setup files, transform/import, worker isolation)
  usually outweighs the tests themselves. Config-level wins come first.
- **Coverage is cheap enough to be a proof.** A before/after coverage diff
  mechanically demonstrates zero coverage loss for a deletion/merge bucket —
  a guarantee the e2e tier can only approximate by reading.

The mechanics below name Vitest where a concrete command is needed (Jest
equivalents usually exist one flag away); substitute the project's runner.

## Configuration & first-run setup

Config lives in `.claude/claude-skills.json` under a top-level `test-unit-audit`
key. **On the first invocation in a repo (no key present), run SETUP before any
auditing** — repo-specific commands are easy to get wrong from name alone, and a
benchmark taken with the wrong command is worthless.

### Setup procedure

1. **Discover each key** (evidence, not guesses):
   - `fullSuiteCommand` — enumerate the package.json test scripts and READ each
     candidate's definition. Watch for tier mixing: many repos' bare `test`
     script runs unit AND integration projects together (Vitest `projects`, Jest
     `projects`) — if slow integration tests (real DB, real services) share the
     command, record the unit-only invocation (e.g.
     `<pm> vitest run --project unit`) as `fullSuiteCommand` and note the
     combined command separately in `notes`. **The command must be the
     one-shot run form** (`vitest run`, `jest`), never the watch-mode default
     (`vitest` alone starts a watcher that never exits).
   - `timingCommand` — the full-suite run with a machine-readable per-test
     reporter (Vitest: `--reporter=json --outputFile=tmp/unit-timing.json`;
     Jest: `--json --outputFile=...`). Verify it actually emits per-test
     durations before recording it.
   - `listCommand` — the collect-only check proving specs parse without running
     (Vitest: `vitest list`; Jest: `jest --listTests`).
   - `typecheckCommand` — from scripts (`typecheck`, else `tsc --noEmit`).
   - `coverageCommand` — the suite with coverage on (usually
     `<fullSuiteCommand> --coverage`); confirm the provider is installed rather
     than assuming — a missing `@vitest/coverage-v8` fails only at run time.
   - `docsDir` — where audit + benchmark docs land (default `docs`).
   - `notes` — free-text repo facts the audit must respect, harvested from
     CLAUDE.md / testing docs: machine-wide run locks shared with other suites,
     env files the tests need, worker-count env vars, projects CI runs
     separately, any "never do X while testing" rules.
2. **Confirm with the user** before writing: show the discovered block and ask
   them to correct anything ambiguous — especially when several plausible
   full-suite commands exist; never pick between plausible arbiters silently.
3. **Write** the confirmed block to `.claude/claude-skills.json` (create the
   file if absent, merge if it exists). Example result:

```json
{
  "test-unit-audit": {
    "fullSuiteCommand": "pnpm vitest run --project unit",
    "timingCommand": "pnpm vitest run --project unit --reporter=json --outputFile=tmp/unit-timing.json",
    "listCommand": "pnpm vitest list --project unit",
    "typecheckCommand": "pnpm typecheck",
    "coverageCommand": "pnpm vitest run --project unit --coverage",
    "docsDir": "docs",
    "noiseFloorPct": 10,
    "notes": "bare `pnpm test` also runs the integration project (real DB); e2e suite takes a machine-wide lock — don't benchmark while it runs"
  }
}
```

4. **Keep it current**: after the Phase 3 baseline, write the measured
   `noiseFloorPct` back into the config. On later runs, read the config first;
   if a configured command fails or no longer exists, re-run discovery for that
   key and update the file, telling the user what changed.

## Non-negotiables

- **Every claim is measured or file:line-cited** — a finding names the file,
  line, mechanism, an S/M/L effort and an impact estimate in milliseconds where
  the timing profile provides one. No "probably slow".
- **Zero coverage loss, proven.** A bucket that deletes or merges tests runs
  the coverage command before and after; the diff must show no line previously
  covered going uncovered (a `diff` of the two coverage summaries per touched
  source file is enough). Reading both tests is still required to fold unique
  assertions into a survivor — coverage proves lines, not assertions.
- **One-shot mode always.** Every scripted run uses the runner's non-watch form
  and is checked for actual exit; a watcher mistaken for a run poisons every
  wall-clock number after it.
- **Read result counters by grepping the whole log — any run, always.** Never
  read pass/fail off a fixed-size tail; runners interleave summaries with
  reporter output, and a red run can read green from its last lines.
- **A measuring run owns the box.** No typecheck, lint, builds, or other suites
  (including the repo's e2e suite and its lock) while a benchmark is in flight;
  write-subagents stay paused. A run competing for cores measures noise.
- **Config experiments are results either way.** A parallelism/isolation change
  that measures WORSE gets reverted and the measurement written into a comment
  beside the setting — otherwise the next audit re-flags it and re-runs the
  experiment.
- **Commits only when the user explicitly asks.** One commit per bucket,
  message carrying the measured delta.

## Phase 0 — Recon + timing profile (orchestrator)

1. **Timing profile first.** Run `timingCommand` once and reduce the output to
   two ranked tables kept as scratch files: top ~30 FILES by total duration and
   top ~30 TESTS by duration. Also capture the runner's phase breakdown —
   Vitest prints `transform Xs, setup Xs, collect Xs, tests Xs, environment Xs,
   prepare Xs` — because the ratio decides the audit's center of gravity:
   - `tests` dominant → the tests themselves are slow (Phase 1 finds why).
   - `transform`+`collect` dominant → import weight (heavy module graphs).
   - `environment`+`setup` dominant → per-file fixed tax (config bucket).
2. **Fixed-cost floor.** Time one trivial control test (a new file asserting
   `1 === 1`, deleted afterward) through the same command. Its wall time is the
   per-file tax every spec pays; multiply by file count to size the ceiling on
   config wins.
3. Inventory: test file count, tests per file, the runner config(s) — per-file
   or per-project `environment` (jsdom/happy-dom vs node), `setupFiles` and
   what each one imports and does, `pool`/`isolate`/`fileParallelism`/worker
   settings and any comment justifying caps, globals, fake-timer defaults —
   and which projects/suites CI actually runs (grep the workflows; a suite no
   workflow invokes is itself a finding, and its first hand-run gets its own
   bucket row with a triage + repair budget).
4. Smell greps (each hit is a lead for Phase 1, not yet a finding): real
   `setTimeout`/sleep helpers awaited in tests; `fetch(`/`axios`/DB client
   imports in unit specs; `bcrypt`/`argon2`/key-derivation with production cost
   factors; `toMatchSnapshot` density and any obsolete-snapshot warnings in the
   baseline log; `test.skip|todo|fixme`; `catch` blocks around assertions;
   barrel imports (`from "@/lib"`, `from "../index"`) in the top-cost files;
   `console.log` flooding (a suite printing megabytes measurably slows runs).

## Phase 1 — Audit fan-out (read-only subagents)

Partition the suite into batches — but weight by MEASURED time, not just line
count: the top-cost files from the timing profile get the most reader
attention; a long tail of sub-100ms files can be batched coarsely or skipped
with the timing table as justification. One agent per batch (6–8 agents),
launched together. Each brief carries the relevant slice of the timing table
and is READ-ONLY; agents read every batch file fully plus the helpers/factories
it leans on, so setup cost is understood.

Report three categories as tables of
`file:line | what | why | fix | effort S/M/L | est. impact (ms where measured)`:

1. **DURATION** — real timers awaited (sleeps, debounce waits, retry backoffs
   → fake timers); real crypto/hash rounds at production cost; per-test
   construction of never-mutated fixtures (→ hoist to module scope or a shared
   frozen factory); heavy `beforeEach` re-seeding data most tests don't touch;
   render-the-world component tests asserting one prop (→ shallow scope or
   split); N tests re-running one identical expensive arrange to assert one
   extra fact each (→ merge into one test or a `describe` with shared arrange);
   jsdom environment on pure-logic files (→ per-file node environment
   pragma); imports of heavy modules the test then fully mocks anyway (the
   import cost is paid BEFORE `vi.mock` saves anything if the mock factory
   pulls the real module); snapshot files so large that serialization itself
   is the cost.
2. **DUPLICATES / UNNECESSARY / WRONG TIER** — same behavior tested twice
   (often once directly and once through a thin wrapper); tests of third-party
   or framework behavior (asserting a library does what its docs say); tests
   asserting TypeScript-guaranteed shapes; unit specs secretly doing
   integration work (real DB, real network, real filesystem → move to the
   integration tier or mock the boundary); integration-tier tests that a pure
   unit could cover at 100× less cost (the reverse move — flag, don't assume);
   snapshot tests that re-assert what an explicit assertion nearby already
   pins.
3. **BROKEN (silently weak)** — the unit-tier always-green patterns:
   missing `await` on `expect(...).rejects` / `resolves` (the assertion floats
   and the test passes before it settles); async work fired without await and
   never asserted; `expect.assertions` absent in try/catch-shaped tests (the
   catch path silently asserts nothing); `vi.fn()` created but never asserted;
   tautological mock tests (mock returns X, test asserts X — the test verifies
   the mock, not the code); mock drift — a mock's return shape the real module
   no longer produces (check `vi.mocked`/`satisfies` typing; an untyped mock
   factory is a standing drift risk); fake timers installed and never
   run/restored (later tests inherit frozen time); obsolete or blindly
   `--update`d snapshots (grep the baseline log for "obsolete"); tests
   asserting on `Date.now()`/`Math.random()`/locale/timezone without pinning
   them (latent flakes); `test.skip`/`todo` older than the code they cover.
   Quote exact lines.

Agents VERIFY suspicious guards (is that env-var skip ever false in any run
mode?) rather than assume.

Meanwhile the orchestrator audits what no batch owns: runner config(s), every
setup file line by line (each import there is paid per file × per worker —
polyfills, MSW servers, global mocks only some files need are candidates for
per-project setup splits), and shared factory/helper hot paths (a slow helper
× its call count from the timing profile).

## Phase 2 — Bucket report

Write `<docsDir>/test-unit-audit-<date>.md` with buckets in THIS order:

1. **Fixed-cost & config wins** — S-effort, suite-wide: environment downgrades
   (jsdom → node for pure files), setup-file splits/diet, obviously dead
   config. Usually the largest guaranteed win; land it first so later
   per-file deltas aren't confounded by it.
2. **Hot-file surgery** — the top of the timing table: fake timers for real
   waits, hoisted fixtures, merged repeat-arranges, mock-instead-of-import.
   Each row cites its measured per-file cost so the payoff is predicted.
3. **Merges, dedup & tier moves** — duplicates folded, wrong-tier tests moved,
   snapshot pruning. The coverage-diff proof applies here.
4. **Broken tests** — correctness at ~0 runtime cost, grouped: always-pass /
   mock-drift / nondeterminism / dead-skipped.
5. **Parallelism & isolation experiments** — `isolate: false` for suites with
   no module-state leakage, pool choice (threads vs forks), worker-count
   sweep, `fileParallelism`, `test.concurrent` for I/O-bound groups. Explicitly
   experimental: each lands only with a measured win and reverts with a
   recorded measurement otherwise. `isolate: false` in particular trades
   safety for speed — a suite that passes only under isolation has a real
   state-leak bug this experiment will surface; budget triage time for it.

Cite each finding as file:line PLUS a short quoted anchor — line numbers drift
as earlier buckets land, so executors locate by content, never by line alone.

Include a **"What NOT to touch"** list: deliberate seams the agents verified —
integration-shaped tests that exist because a unit mock would lie (the mock
drift the suite once shipped), timer tests that genuinely need real timers,
snapshots that are the sanctioned contract format for a serializer.

## Phase 3 — Baseline on this machine

- Unit suites usually fit a foreground tool call — run `fullSuiteCommand` in
  the foreground with a generous timeout, THREE times (unit noise floors are
  proportionally larger because absolute times are small; three runs bound
  it). Only fall back to the e2e skill's detached
  `setsid nohup … ; echo $? > tmp/runN-exit` protocol when a run genuinely
  exceeds tool timeouts.
- Record in the audit doc, per run: wall clock, the runner's own duration line
  AND its phase breakdown (transform/setup/collect/tests/environment),
  pass/fail/skip/todo counts, collected test count. Derive `noiseFloorPct`
  from the spread and write it into the config.
- Triage every failure and every "obsolete snapshot" warning BEFORE calling
  the baseline valid; preserve logs under dated names. A pre-existing failure
  becomes a bucket-4 row, not a silent baseline feature.
- Worktree gotcha (from the e2e audit, still true here): a `node_modules`
  symlink into another checkout breaks transforms — do a real install in the
  worktree and regenerate gated postinstall artifacts (ORM clients).

## Phase 4 — Implement a bucket (write subagents)

- 3–6 agents per bucket with **disjoint file ownership**. The ORCHESTRATOR is
  sole owner of shared files — runner configs, setup files, shared
  factories/mocks — and applies its pass AFTER all agents land, avoiding both
  conflicts and half-states (an `isolate: false` flip whose spec-side state
  cleanup hasn't landed).
- Every brief carries the hard rules: no full-suite runs (an agent MAY run
  only the specific files it owns — unit tier makes that cheap and it beats
  collect-only for catching behavioral breakage — but never during a
  benchmark); no shared-file edits; no commits; read files fully before
  editing; after deletions grep for dangling imports, orphaned factories and
  fixtures, and stale snapshot files (`.snap` orphans linger after their test
  dies — delete them with the test).
- Point agents at the repo's own MODEL-CITIZEN specs: the file that already
  uses fake timers correctly, the typed mock factory, the per-file
  `@vitest-environment node` pragma — grep for these and cite them in briefs
  instead of abstract instructions.
- **Interruption resilience**: agents killed mid-flight keep their transcripts
  — check `git status` for partial writes, then resume each agent with
  "re-check current on-disk state first" rather than restarting from zero.
- After all land: diff review + typecheck + `listCommand`, then the bucket
  benchmark.

## Phase 5 — Benchmark the bucket

- Full suite, same protocol as the baseline, two–three runs per side. A delta
  smaller than the noise floor is reported as "within noise", never spun.
- **Attribute before averaging**: for hot-file surgery buckets, also time just
  the touched files (`vitest run <files>`) before/after — per-file deltas
  attribute the win to specific changes even when the full-suite delta sits
  near noise, and they're nearly free at this tier.
- **Deletion/merge buckets attach the coverage diff** (Phase 3's coverage
  baseline vs post-bucket) as the zero-coverage-loss proof.
- **Parallelism experiments get the paired protocol**: default config vs
  experiment on the SAME tree, interleaved (A,B,A,B) so machine drift can't
  masquerade as a win; a worse result is reverted and recorded beside the
  setting.
- Write `<docsDir>/test-unit-benchmark-bucket<N>.md`: a results table
  (run | tree | config variant | wall | runner-reported phases |
  pass/fail/skip | collected), the coverage-diff verdict where applicable, an
  honest "reading" section (attribute the delta or admit noise), what was
  deferred and why, and a cross-link from the previous bucket's doc.
- **First-execution rule**: a bucket that adds, un-skips, or materially
  rewrites tests gets its validation run triaged test-by-test. A new failure
  goes back to the SAME agent (it holds the context) for a repair round and a
  re-run before the bucket is done. When the failure is the PRODUCT's — the
  rewritten assertion is simply the first thing ever to actually look — file
  it to the repo's deferred-work/issue ledger with an ID, keep the rest of the
  test strict, and point the test's comment at the ID.

## Recurring unit-tier mechanisms worth checking in any audit

- **The import graph is the hidden suite.** A test importing a barrel that
  transitively pulls an ORM client, a server SDK, or a component library pays
  that transform+evaluate cost per file (× per worker under isolation). Deep
  imports or a boundary mock cut it; the transform/collect phase numbers say
  whether it's worth chasing.
- **Setup files are a multiplier, not a constant.** Everything in `setupFiles`
  runs once per test FILE per worker. One team's MSW server + polyfill +
  i18n-init setup at ~300ms × 400 files is two minutes of pure tax; splitting
  setups per project (DOM files vs node files) refunds most of it.
- **Fake timers pay twice.** They delete real waits AND they surface hidden
  `setInterval` leaks (a test that only passes with real timers because a
  leaked interval "eventually" fires is a bucket-4 finding wearing a
  bucket-2 costume).
- **Crypto/hashing cost factors**: password hashers and key derivation at
  production rounds turn microsecond tests into 200ms tests; a test-env cost
  factor (or a boundary mock) is standard practice, but change it in test
  config only — never the production default.
- **Snapshot entropy**: giant snapshots assert everything and therefore
  nothing (every refactor "fails" them, so they get `--update`d blind).
  Replace with targeted assertions; keep snapshots for genuine serialization
  contracts.
- **Nondeterminism debt**: unpinned `Date.now`, `Math.random`, locale,
  timezone, and object-key iteration order are tomorrow's flakes. Pin them at
  the setup level (fixed system time, seeded RNG, fixed TZ in the runner env)
  so individual tests stop hand-rolling it.
- **Stdout as a cost center**: a suite logging heavily (debug prints, React
  `act()` warnings, prop-type noise) measurably slows runs and buries real
  signals; silencing warnings by FIXING their causes is a legitimate duration
  finding.
- **`test.concurrent` is for I/O-bound tests only** — CPU-bound tests gain
  nothing (workers already parallelize files) and shared-state tests corrupt
  each other; verify statelessness before flagging it.
- **A "slow test" can be a slow product function.** When one pure function
  measurably dominates its file, that's a product performance finding —
  report it as such rather than weakening the test around it.
