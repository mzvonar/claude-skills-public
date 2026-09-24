---
name: test-e2e-audit
description: >
  Audit an end-to-end/browser test suite (Playwright, Cypress, or similar) for
  duration and quality in parallel subagent batches, bucket the findings with
  low-hanging fruit first, measure a machine-local baseline so deltas are
  attributable, then implement bucket-by-bucket via subagents — each bucket
  benchmarked and recorded in a markdown table. Use when asked to "audit the e2e
  tests", "speed up the e2e suite", "find duplicate or broken e2e tests", "why is
  e2e CI slow", "run an e2e test audit", or to continue a previous audit's next
  bucket. For unit/component suites (Vitest, Jest) use /test:test-unit-audit
  instead; for suites against a real database or real services use
  /test:test-integration-audit instead. Self-configures on first run in a repo:
  discovers the sanctioned full-suite command, flake ledger and repo constraints, confirms them with the
  user, and writes .claude/claude-skills.json. Produces docs/test-e2e-audit-<date>.md
  plus one docs/test-e2e-benchmark-bucket<N>.md per implemented bucket.
---

# E2E Test Audit — batch analysis → buckets → measured fixes

Origin: a real audit of a ~570-test Playwright e2e suite (suite 618s → 396s best,
62 duplicate tests folded away, 6 worker-serialization caps lifted, ~22
always-green/vacuous tests made honest). The method is framework-agnostic; the
mechanics below name Playwright where a concrete command is needed — substitute the
project's equivalents.

## Configuration & first-run setup

Config lives in `.claude/claude-skills.json` under a top-level `test-e2e-audit`
key (a legacy `test-audit` key is read as a fallback — migrate it to the new name
when touching the file). **On the first invocation in a repo (neither key
present), run SETUP before any auditing** — repo-specific commands are easy to get wrong from name alone, and a
benchmark taken with the wrong command is worthless.

### Setup procedure

1. **Discover each key** (evidence, not guesses):
   - `fullSuiteCommand` — enumerate the package.json test scripts and READ each
     candidate's definition. The right one is the repo's *arbiter*: reproducible and
     CI-shaped — it builds the app or targets a production server, never a
     dev-server "reuse whatever is listening" mode. Name suffixes (`:built`, `:ci`)
     are hints, not proof, and the arbiter is often documented only in prose — grep
     CLAUDE.md and testing docs for "full-suite", "arbiter", "production build",
     "reuseExistingServer" before deciding.
   - `listCommand` — the collect-only check that proves specs parse without running
     them (Playwright: `<pm> exec playwright test --list --reporter=line`).
   - `typecheckCommand` — from scripts (`typecheck`, else `tsc --noEmit`).
   - `flakeLedger` — grep docs and planning-artifact dirs for a deferred-work /
     known-flakes / quarantine file that lists failing specs by path. If none
     exists, leave it unset here; Phase 3 creates one from the baseline's triaged
     failures and writes the path back.
   - `docsDir` — where audit + benchmark docs land (default `docs`).
   - `notes` — one-paragraph repo facts the audit must respect, harvested from
     CLAUDE.md / testing docs: machine-wide run locks or shared test DBs, suites CI
     never runs, label-gated suites, seeding/identity constraints, worker-count env
     vars, any "never do X while testing" rules.
   - `notesFile` — optional path to a markdown file of richer project specifics
     (see "Project notes file" below). When the harvested facts outgrow one
     paragraph, offer to create it during setup and move `notes` content there;
     `notes` then keeps only the one-line pointers that must never be missed.
2. **Confirm with the user** before writing: show the discovered block and ask them
   to correct anything ambiguous — especially `fullSuiteCommand` when several
   candidates exist; never pick between plausible arbiters silently.
3. **Write** the confirmed block to `.claude/claude-skills.json` (create the file if
   absent, merge if it exists). Example result:

```json
{
  "test-e2e-audit": {
    "fullSuiteCommand": "pnpm test:e2e:built",
    "listCommand": "pnpm exec playwright test --list --reporter=line",
    "typecheckCommand": "pnpm typecheck",
    "flakeLedger": "docs/known-flakes.md",
    "docsDir": "docs",
    "noiseFloorPct": 8,
    "notesFile": "docs/test-audit-notes.md",
    "notes": "e2e runs take a machine-wide lock (scripts/*lock*); banking suite is manual-only; realtime suite runs only on labeled PRs"
  }
}
```

4. **Keep it current**: after the Phase 3 baseline, write the measured
   `noiseFloorPct` back into the config. On later runs, read the config first; if a
   configured command fails or no longer exists, re-run discovery for that key and
   update the file, telling the user what changed.

### Project notes file

When `notesFile` is set, **read it in full at the start of every run, before any
command is executed** — it ranks with this skill's own rules for the repo it
lives in. It is plain markdown, owned by the repo (committed, reviewable), and
both audit skills may point at the same file. Suggested sections: **Commands**
(why the arbiter is what it is, which script is a trap), **Constraints** (locks,
shared boxes, "never run X while Y"), **Suite map** (which suites exist, which
CI runs, which are manual-only), **Known quirks** (env pinning, worktree
gotchas), **History** (past audits and their docs). During an audit, when a
discovered fact contradicts the file, tell the user and update the file — it is
the durable memory the next audit starts from. If the notes file or the skill
config exists only as UNCOMMITTED state in another checkout/worktree, ASK the
user before copying it in — it is another session's working state, not yours to
take; once copied with consent, commit it with the audit's setup so no future
run repeats this.

## Non-negotiables

- **Every claim is measured or file:line-cited** — a finding names the file, line,
  mechanism, an S/M/L effort and an impact estimate. No "probably slow".
- **The flake ledger gates every benchmark.** Before trusting a run, check each
  failing test against the ledger. A run is comparable only if its failure set stays
  within the known list; a failure in a file the audit changed is YOURS until proven
  otherwise (did it fail before the change? does the error match the documented
  signature?).
- **Zero coverage loss.** Delete a test only after folding its unique assertions
  into a survivor — verified by reading both tests, never by comparing titles —
  and **record the fold**: the bucket doc lists every deleted test with the
  survivor (file + test title) that now carries each of its unique
  assertions, or the stated reason an assertion was dropped on purpose
  (measured at the unit tier: a dedup bucket with a green line-coverage proof
  still lost seven pins; the recorded rationale is also what answers a
  reviewer challenging a deliberate drop in one reply).
- **Commits: settle the policy at audit start, then commit per bucket at
  bucket close.** Before Phase 0, ask the user whether you may commit each
  bucket as it lands — explicitly, and especially where repo policy
  otherwise bans agent commits; never commit unasked. When authorized,
  commit AT BUCKET CLOSE (bucket edits + benchmark doc together), message
  carrying the measured delta. Do not defer all commits to the end: buckets
  overlap on files and git stages whole files — an end-of-audit split
  cannot produce honest per-bucket history (measured on the integration
  tier: four deferred commits all needed overlap disclaimers).
- If the project serializes test runs machine-wide (a lock script, a shared test
  DB), respect it — never run two suites concurrently. **A lock only
  serialises processes that TAKE it**: verify the wrapper exists on YOUR
  branch and in every checkout/worktree that can run the suite (a worktree
  cut from a base branch that predates the wrapper has the bare run while its
  docs describe the lock) — half-taken, it is worse than none, because the
  belief stops manual coordination. **Your own harness is a writer too**: a
  turn-end hook that runs a suite makes "start the run in the background and
  end the turn to wait" TWO runs, and a hook pinned to the checkout the
  session STARTED in runs a different tree's suite — run benchmarks in the
  foreground-monitored form below, never end a turn with a run in flight,
  and check where hooks `cd` before trusting a hook-driven gate from a
  worktree.
- **A measuring run owns the whole box, not just the lock.** While a benchmark or
  validation run is in flight the orchestrator runs nothing heavy (no typecheck,
  lint, or unit tests) and write-subagents stay paused — their verification
  commands starve the app server under test. The saturation signature: several
  tests failing on seed/API-POST or `goto` timeouts in files the diff never
  touched ⇒ the run is INVALID — mark it so, rerun on a quiet box, and never
  triage those timeouts as regressions.
- **Read result counters by grepping the whole log — any run, always, not just the
  monitored ones.** Playwright prints the failure line FIRST in its summary, so any
  `| tail`/fixed-window read shows only `skipped/passed` and a red run reads green.

## Phase 0 — Recon (orchestrator)

1. Inventory: spec files, tests per file, line counts, every test config, and which
   suites CI actually runs (grep the CI workflows) — a suite no workflow invokes is
   itself a finding (it rots silently), and its first hand-run becomes its own
   bucket row with a triage + repair + re-run budget: stale copy drift and racy
   asserts are near-certain, and Phase 5's first-execution rule applies to the
   whole suite, not just new tests.
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

Write `<docsDir>/test-e2e-audit-<date>.md` (when continuing an audit started under
the old skill name, look for `test-audit-<date>.md` too) with buckets in THIS order:

1. **Low-hanging fruit** — S-effort config/helper changes and no-analysis deletions.
2. **Merges & shared fixtures** — S-effort per item, spread across specs.
3. **Structural** — serialization/identity work (M/L; biggest wall-clock).
4. **Broken tests** — correctness at ~0 runtime cost, grouped: always-pass /
   dead-stale / order-coupled / misleading. Every repaired cannot-fail test is
   verified by a red-probe (flip the product behavior in a scratch edit, watch
   the new assertion go red, revert with a proven-empty diff) — a repair never
   seen red is the same class of test it replaced.
5. **Wrong tier / policy** — tests that belong in unit/component tier; naming.

Cite each finding as file:line PLUS a short quoted anchor — line numbers are
as-of-audit and drift as earlier buckets land, so executors locate by content,
never by line alone.

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
- **Baseline the receiving lane too when bucket 5 (wrong tier) looks likely**:
  one timed run of the unit/component suite NOW, pre-move — a relocation
  reported as savings needs the receiving lane's before/after, and the
  "before" cannot be reconstructed once the moves land.
- Record in the audit doc: wall clock, reported suite duration, pass/fail/skip,
  collected test count, the box as MEASURED (`nproc`, RAM — never copied from
  a config comment), and the delta rule ("compare suite duration; build time is
  a constant; a run is comparable only if its failure set stays within the ledger").
- Worktree gotcha: a `node_modules` symlink into another checkout breaks bundler
  production builds — do a real install in the worktree (and regenerate any gated
  postinstall artifacts, e.g. ORM clients).

## Phase 4 — Implement a bucket (write subagents)

- 3–6 agents per bucket with **disjoint file ownership**, launched in **staggered
  batches of 2–3** (simultaneous launches race the shared prompt-cache prefix and
  a mid-flight rate limit kills the whole cohort instead of one batch; interrupted
  agents re-read files on resume, so blast radius is token cost). The ORCHESTRATOR
  is sole owner of shared files (test configs, shared helpers) and applies its
  pass AFTER all agents land — avoiding both conflicts and half-states (a config
  change whose spec-side prerequisite hasn't landed).
- Every brief carries the hard rules: **never run `git stash`** (in a shared
  worktree it reverts every OTHER agent's uncommitted work — measured in a real
  run: one agent's stash/pop reverted three agents' finished edits); no test
  runs; no shared-file edits; no commits; read files fully before editing; verify
  with the framework's collect-only mode (`playwright test --list` — proves
  parse + collection without running) and grep for dangling references and
  orphaned constants after deletions — and prose (docs, skills, guideline
  files, comments) after renames. **Test-code hygiene**: no audit-narration
  comments in spec files (`// bucket 2: merged from …` — the benchmark doc is
  the record; a comment explaining an anti-flake SEAM stays, one narrating the
  task goes), no pasted finding text, and the repo's own conventions; when
  several agents hand-roll the SAME helper, the orchestrator's after-pass
  extracts it into the shared fixtures.
- **Premise corrections are a deliverable**: executors verify each finding's
  premise before acting; a wrong premise is a report-back, never a forced edit,
  and the orchestrator writes the correction into the audit doc.
- Point agents at the repo's own MODEL-CITIZEN specs (grep for existing per-test
  identity helpers, session-minting fixtures) instead of abstract instructions.
  Identity de-serialization shapes that worked: per-FILE identity + storage state
  with the project set to keep a file's tests serial while files parallelize
  (Playwright: project-level `fullyParallel: false` — a per-file identity is
  race-free only then); single-file projects need per-TEST identities instead;
  fixture-resolution ordering matters (a storage-state file consumed by fixtures
  must exist before hooks run — pre-create a placeholder).
- **Interruption resilience**: agents killed mid-flight (rate limits) keep their
  transcripts — reconcile `git status` against each agent's OWNERSHIP LIST (an
  unowned modification, or an owned file unexpectedly clean, means something
  reverted work; treat any stash as evidence to reconcile, not noise), then
  resume each agent with "re-check current on-disk state first", rather than
  restarting from zero.
- After all land: diff review + typecheck + the collect-only check + **the
  repo's own policy ratchets/scanners** (count ratchets, banned-cast scans,
  style lints) — audit edits trip them in both directions: a rewritten block
  carries a banned construct the original had (a reviewer flags it as new,
  and since the block was rewritten it is fair to fix), and deletions LOWER
  count baselines — lower the baseline to lock the drop in.

## Phase 5 — Benchmark the bucket

- Same protocol as the baseline. **Two runs per side** once local noise is known —
  a delta smaller than the noise floor is reported as "within noise", never spun.
  When a bucket de-serializes, add a run at a higher worker count: flat-at-default
  plus faster-at-width is the honest signature that the caps (not the tests) were
  the constraint. When bucket 5 moves tests to another tier, decompose
  relocated vs saved: the receiving lane is measured as interleaved pairs of
  base-commit vs branch, same box, same session, the CI-shaped command —
  never against a number from another day, branch or worktree (measured at
  the integration tier: a borrowed day-old figure was off by a fifth) — and
  the relocated tests' CI wiring lands in the same bucket, pinned by a test
  that reads the runner config, package scripts and workflow file. A worker bump that measures WORSE (saturation flake for seconds
  saved) is a result, not a failure: revert it and write the measurement into the
  config comment beside the cap — otherwise the next audit re-flags the cap as
  vestigial and re-runs the experiment.
- Write `<docsDir>/test-e2e-benchmark-bucket<N>.md`: a results table
  (run | tree | workers | suite | wall | pass/fail/skip | collected), a failure-set
  validity paragraph mapping each failure to its ledger entry, an honest "reading"
  section (attribute the delta or admit noise), what was deferred and why, and a
  cross-link from the previous bucket's doc.
- **First-execution rule**: a bucket that implements or un-skips tests gets its
  validation run triaged test-by-test. A new test failing gets a repair round —
  send the failure output plus the framework's error-context snapshots back to the
  SAME agent (it holds the context) — and a re-run before the bucket is done.
  A documented `test.fixme` with a tracked reason is the fallback only after repair
  is exhausted. And when the failure is the PRODUCT's, not the test's — the new
  assert is simply the first thing ever to look (an accessibility scan finding real
  contrast violations, a policy check finding real drift) — file the finding to the
  flake ledger / deferred-work with an ID, exclude the SPECIFIC failing rule or
  assert (never the whole test), keep everything else strict, and point the test's
  title or comment at the ID so re-enabling is findable when the product fix lands.

## Phase 6 — Wrap up (orchestrator)

The audit is not done when the last benchmark is green:

- **Ledger dispositions.** Close every flake-ledger / deferred-work item the
  audit fixed (append a resolution note); file every finding it deliberately
  did NOT fix — product defects surfaced by honest tests, quarantined rules,
  recommendations — with an ID, and point the affected test's title or
  comment at that ID.
- **notesFile.** Append a History entry (branch, docs produced, headline
  numbers, what was deferred and why) and new Lessons; correct anything the
  audit proved wrong. This is the durable memory the next audit starts from.
- **Config write-back.** `noiseFloorPct`, `flakeLedger` if Phase 3 created
  one, any command that changed, and pointers to rejected experiments (a
  reverted worker bump) so nobody re-runs them blind.
- **Cross-links.** Each benchmark doc links its predecessor; the audit doc
  gains an implementation-status footer stating what landed and what didn't.
- **Commits/push per the policy agreed at the start.** If per-bucket
  commits were not authorized, state exactly what is uncommitted and offer
  the commits — do not leave the user to discover a 100-file working tree.
- **Session memory / handoff notes**, if the environment keeps them.
- **Review.** An audit PR is large by construction (150–200 files in the
  field). Check the AI reviewer's file cap and force its run explicitly — a
  silent no-review is NOT a clean pass (measured: one over-cap PR got no
  notice at all where earlier over-cap PRs had posted one). Expect the
  review to challenge every deliberate deletion — the bucket docs' recorded
  rationale is the answer, and a finding you cannot answer from them is a
  finding.

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
  instantly and a duplicating re-run stays green. And an EXCLUSION filter (a
  dismissed/opted-out entity must not be processed) is provable only when the
  excluding state change happens BEFORE the first emission: a stable-count assert
  after an initial emission is equally explained by a dedup guard, so it cannot
  fail for the filter's absence — restructure to exclude-first, run once, assert
  ZERO.
- Asserts on a TRANSIENT intermediate UI state (a resolved-fade before a queue
  eviction, a spinner before a redirect) are races — a server refresh can evict the
  state before the expect ever observes it, and with a single-item queue the
  transient state may be unobservable outright. Assert the durable outcome with an
  either/or poll (resolved OR evicted, never stuck pending), bounded to the
  stack's real latency, not the optimistic one.
- Whole-page scans (axe, screenshot diffs) assert whatever has STREAMED IN so far —
  under streamed metadata a scan can beat the `<title>` into the document and fail
  on a phantom violation. Gate every scan on a render signal (title, heading,
  testid) before running it.
- A suite "blocked on unhealthy infra" is a claim to verify, not a fact: read what
  the container's healthcheck actually tests (a stale check can 401 on a now
  auth-gated ping while the service answers in under a millisecond) and what the
  dependents actually require (`service_started` vs healthy) before writing the
  suite off — then just try the sanctioned run command.
