---
name: test-audit
description: >
  Audit a test suite for duration and quality in parallel subagent batches, bucket
  the findings with low-hanging fruit first, measure a machine-local baseline so
  deltas are attributable, then implement bucket-by-bucket via subagents — each
  bucket benchmarked and recorded in a markdown table. Use when asked to "audit the
  tests", "speed up the e2e/test suite", "find duplicate or broken tests", "why is
  CI slow", "run a test audit", or to continue a previous audit's next bucket.
  Produces docs/test-audit-<date>.md plus one docs/test-benchmark-bucket<N>.md per
  implemented bucket.
---

# Test Audit — batch analysis → buckets → measured fixes

Origin: a real audit of a ~570-test Playwright e2e suite (suite 618s → 396s best,
62 duplicate tests folded away, 6 worker-serialization caps lifted, ~22
always-green/vacuous tests made honest). The method is framework-agnostic; the
mechanics below name Playwright where a concrete command is needed — substitute the
project's equivalents.

## Configuration (optional, `.claude/claude-skills.json`)

```json
{
  "test-audit": {
    "fullSuiteCommand": "pnpm test:e2e:built",
    "flakeLedger": "docs/known-flakes.md",
    "docsDir": "docs"
  }
}
```

- `fullSuiteCommand` — the sanctioned, reproducible full-suite entry point. Default:
  detect from package.json scripts, preferring a production-build/CI-shaped script
  (`test:e2e:built`, `test:e2e:ci`, `test:e2e`, then `test`). Benchmarks must use a
  server/build mode that is reproducible — never a dev-server reuse mode.
- `flakeLedger` — the file listing known pre-existing flaky/failing tests. Default:
  grep docs and planning artifacts for a deferred-work / known-flakes / quarantine
  file; if none exists, CREATE one during Phase 3 from the baseline's triaged
  failures.
- `docsDir` — where audit + benchmark docs land. Default `docs`.

## Non-negotiables

- **Every claim is measured or file:line-cited** — a finding names the file, line,
  mechanism, an S/M/L effort and an impact estimate. No "probably slow".
- **The flake ledger gates every benchmark.** Before trusting a run, check each
  failing test against the ledger. A run is comparable only if its failure set stays
  within the known list; a failure in a file the audit changed is YOURS until proven
  otherwise (did it fail before the change? does the error match the documented
  signature?).
- **Zero coverage loss.** Delete a test only after folding its unique assertions
  into a survivor — verified by reading both tests, never by comparing titles.
- **Commits only when the user explicitly asks.** One commit per bucket, message
  carrying the measured delta.
- If the project serializes test runs machine-wide (a lock script, a shared test
  DB), respect it — never run two suites concurrently.

## Phase 0 — Recon (orchestrator)

1. Inventory: spec files, tests per file, line counts, every test config, and which
   suites CI actually runs (grep the CI workflows) — a suite no workflow invokes is
   itself a finding (it rots silently).
2. Serialization map: every `workers: 1` / `fullyParallel` (or equivalent) with the
   comment justifying it. Shared-identity caps — parallel tests racing a
   unique-constraint upsert on one seeded user/row — are usually the biggest
   wall-clock lever.
3. Timing sources: CI step durations, any benchmark docs, the last local run log.
   Note the documented run-to-run noise floor; you will need it for honest deltas.
4. Smell greps: fixed sleeps (`waitForTimeout`), `networkidle`, `test.skip|fixme`,
   `catch`, `toBeDefined()`, slow `expect.poll`, raw unchecked seed/API calls.

## Phase 1 — Audit fan-out (read-only subagents)

Partition specs by domain directory into batches of ~3–4k lines (~10–20 files); one
agent per batch (6–8 agents), launched together. Each brief:

- READ-ONLY; read every batch file fully plus the helpers it leans on (seeding,
  auth), so setup COST is understood (API-seeded vs UI-driven).
- Report three categories as tables of
  `file:line | what | why | fix | effort S/M/L | est. impact`:
  1. **DURATION** — fixed sleeps; `networkidle`; raised timeouts; slow polls;
     per-test provisioning of never-mutated data (→ shared fixture); N tests
     re-driving one identical journey to assert one extra fact each (→ merge);
     redundant reloads; mirror role-A/role-B specs both driving the full flow;
     tests that could lift a worker cap by minting per-test identities.
  2. **DUPLICATES / UNNECESSARY** — same behavior tested twice; static
     render/string assertions that belong in unit/component tier; superseded
     tests; stub files whose surface shipped elsewhere.
  3. **BROKEN (silently weak)** — assertions inside `if` blocks;
     `click().catch(() => {})` before a negative; try/catch swallowing failures;
     no-assertion bodies (all comments); `expect(locator).toBeDefined()` (cannot
     fail); negatives without a positive control (pass on a 404/blank page);
     idempotency `expect.poll(...).toBe(before)` that passes on the FIRST read;
     tests "verifying" a write by re-seeding it (an idempotent upsert cannot fail
     for the claimed reason); declaration-form `test.skip("title", fn)` dead in
     every project; loops that `break` on `isVisible()` and silently under-assert;
     order-coupled pairs that only pass while a mutation does NOT persist;
     titles/constants that overclaim (two "different" tests asserting the identical
     string). Quote exact lines.
- Agents VERIFY suspicious guards (is `test.skip(!ENV)` ever true in any run mode?)
  rather than assume.

Meanwhile the orchestrator audits config/CI/setup itself: global setup cost, unused
pre-minted sessions, helper hot paths (a helper probing the WRONG signal first —
e.g. a 5s title probe before the common testid — multiplied by its call count).

## Phase 2 — Bucket report

Write `<docsDir>/test-audit-<date>.md` with buckets in THIS order:

1. **Low-hanging fruit** — S-effort config/helper changes and no-analysis deletions.
2. **Merges & shared fixtures** — S-effort per item, spread across specs.
3. **Structural** — serialization/identity work (M/L; biggest wall-clock).
4. **Broken tests** — correctness at ~0 runtime cost, grouped: always-pass /
   dead-stale / order-coupled / misleading.
5. **Wrong tier / policy** — tests that belong in unit/component tier; naming.

Include a **"What NOT to touch"** list: deliberate anti-flake seams the agents
verified (bounded error swallows with rationale, sampling loops that exit into hard
asserts, load-bearing reloads) — so later passes don't "optimize" them away.

## Phase 3 — Baseline on this machine

- Full-suite runs usually exceed foreground tool timeouts → run detached with
  timing markers and watch with a completion monitor:

  ```bash
  date +%s > tmp/runN-start && setsid nohup bash -c \
    '<fullSuiteCommand> > tmp/runN.log 2>&1; echo $? > tmp/runN-exit; date +%s > tmp/runN-end' \
    > /dev/null 2>&1 & disown
  ```

  The monitor polls for `tmp/runN-exit` (plus a process-gone guard) and then
  reports wall time and ALL result counters (`passed|failed|skipped|flaky`) — never
  read results off a fixed-size tail; the failure line prints first.
- Triage every failure against the flake ledger BEFORE calling the baseline valid;
  preserve the log with a dated name.
- Record in the audit doc: wall clock, reported suite duration, pass/fail/skip,
  collected test count, and the delta rule ("compare suite duration; build time is
  a constant; a run is comparable only if its failure set stays within the ledger").
- Worktree gotcha: a `node_modules` symlink into another checkout breaks bundler
  production builds — do a real install in the worktree (and regenerate any gated
  postinstall artifacts, e.g. ORM clients).

## Phase 4 — Implement a bucket (write subagents)

- 3–6 agents per bucket with **disjoint file ownership**. The ORCHESTRATOR is sole
  owner of shared files (test configs, shared helpers) and applies its pass AFTER
  all agents land — avoiding both conflicts and half-states (a config change whose
  spec-side prerequisite hasn't landed).
- Every brief carries the hard rules: no test runs; no shared-file edits; no
  commits; read files fully before editing; verify with the framework's collect-only
  mode (`playwright test --list` — proves parse + collection without running) and
  grep for dangling references and orphaned constants after deletions.
- Point agents at the repo's own MODEL-CITIZEN specs (grep for existing per-test
  identity helpers, session-minting fixtures) instead of abstract instructions.
  Identity de-serialization shapes that worked: per-FILE identity + storage state
  with the project set to keep a file's tests serial while files parallelize
  (Playwright: project-level `fullyParallel: false` — a per-file identity is
  race-free only then); single-file projects need per-TEST identities instead;
  fixture-resolution ordering matters (a storage-state file consumed by fixtures
  must exist before hooks run — pre-create a placeholder).
- **Interruption resilience**: agents killed mid-flight (rate limits) keep their
  transcripts — check `git status` for partial writes, then resume each agent with
  "re-check current on-disk state first", rather than restarting from zero.
- After all land: diff review + typecheck + the collect-only check.

## Phase 5 — Benchmark the bucket

- Same protocol as the baseline. **Two runs per side** once local noise is known —
  a delta smaller than the noise floor is reported as "within noise", never spun.
  When a bucket de-serializes, add a run at a higher worker count: flat-at-default
  plus faster-at-width is the honest signature that the caps (not the tests) were
  the constraint.
- Write `<docsDir>/test-benchmark-bucket<N>.md`: a results table
  (run | tree | workers | suite | wall | pass/fail/skip | collected), a failure-set
  validity paragraph mapping each failure to its ledger entry, an honest "reading"
  section (attribute the delta or admit noise), what was deferred and why, and a
  cross-link from the previous bucket's doc.
- **First-execution rule**: a bucket that implements or un-skips tests gets its
  validation run triaged test-by-test. A new test failing gets a repair round —
  send the failure output plus the framework's error-context snapshots back to the
  SAME agent (it holds the context) — and a re-run before the bucket is done.
  A documented `test.fixme` with a tracked reason is the fallback only after repair
  is exhausted.

## Recurring mechanisms worth checking in any audit

- Helpers probing the wrong signal first (rare-case probe with a fixed timeout
  before the common-case check) — multiply the burn by call count.
- Setup-scoped state clears (`goto("/") + localStorage.clear()` per test) — verify
  with evidence whether the state can ever be non-empty (fresh context per test +
  empty storage-state origins usually means the clear is pure cost: delete it).
- "Durability" asserts on deliberately session-scoped state are deterministically
  red — read the product code first and assert what the action durably writes.
- Cron/idempotency tests need a run-#2 COMPLETION signal (a sentinel entity whose
  state must change) before the stability assert — otherwise the poll passes
  instantly and a duplicating re-run stays green.
