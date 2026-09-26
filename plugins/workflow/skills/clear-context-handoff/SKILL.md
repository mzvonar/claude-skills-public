---
name: clear-context-handoff
description: 'Prepare a clean-context handoff. Use when the user asks to "hand off", "prepare a clear-context handoff", "write a handoff", or otherwise wants to /clear and continue in a fresh session. Produces a committed handoff doc (what we''re doing, what''s done, ordered next steps, research/open questions) plus a kickoff prompt to paste into the fresh context.'
---

# Clear-context handoff

**Goal:** capture everything a fresh context needs to continue the work, in a durable doc,
and hand back a ready-to-paste kickoff prompt. Two deliverables: (1) a **handoff doc**,
(2) a **kickoff prompt**.

## Steps

0. **Is this session reading the CURRENT skill text?**
   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-freshness.sh" "${CLAUDE_PLUGIN_ROOT}"
   ```
   Local, no network, **silent** unless something is wrong. Exit **3** — this session is serving
   an older cached copy of THIS plugin than the one installed; a session pins its version at the
   first call and never moves. Put it to the user (`AskUserQuestion`): reload (`/reload-plugins`)
   and re-run, or carry on knowingly — and if you already put this question for this plugin in this
   session, just note it and carry on; the check is stateless and will keep reporting. Exit **2** —
   could not determine, which is not a pass. Exit **4**, or `No such file` / exit **127** — wired
   wrong, checked nothing; report it. Why: `docs/conventions.md` in `mzvonar/claude-skills-public`.
1. **Resolve settings.** Read `.claude/claude-skills.json` → key `clear-context-handoff` if it
   exists; every missing key takes its default from Configuration. Detect what isn't configured
   (verify command, commit convention) before writing anything.
2. **Write/refresh the handoff doc** at `<handoffDir>/<handoffFilePattern>` (default
   `docs/handoffs/handoff-<YYYY-MM-DD>.md`; take the date from the session's current-date context).
   One canonical "latest" doc per workstream: same day → rewrite it, git keeps history. **When a
   new date replaces an older handoff, delete the old dated file and update every pointer to it**
   (`grep -rn '<old-filename>'` across the repo; planner docs first). Use the template below. Be
   concrete — cite file paths, exact symbols, commit SHAs, and **measured numbers, not adjectives**
   (test counts, timings, sizes, finding counts; "faster" or "most" tells a fresh context nothing).
   A future you with **no memory of this session** must be able to continue.
   If `plannerDocs` is set, **keep each planner doc in step** in the same change: mark finished
   items DONE and point its "DO NEXT" at the right item.
3. **Commit it** so the tree is clean for the fresh session — subject per `commitConvention`
   (e.g. `docs: refresh handoff for <workstream>`). Then apply `pushPolicy` (default: ask).
4. **Give the kickoff prompt** in chat (code block) using the template below.

## Handoff doc template

```md
# <Project> — Handoff (<date>, current)

<One line: what this is, branch, repo, toolchain. Note it's the canonical latest handoff.>

## State of play
<1 short paragraph: what we're building, overall status, what's committed/pushed (latest SHA).>

## What's DONE
- <bullets, each with the file(s)/package and, where useful, the commit SHA>

## What REMAINS (in order)
### 1. <next step> ← DO FIRST
<concrete: which files, the approach, the decision to make>
### 2. <next step> ← DO SECOND
<…>
### Later / future reference
- <deferred items, scope expansion>
### Needs research / open questions
- <unknowns to investigate; questions only the user can answer>

## How to run
```<commands to build/verify/run the relevant harnesses, tests, stories>```

## Key facts / decisions
- <the real business logic, constraints, why-decisions, source-of-truth pointers, measured numbers>

## Env gotchas
- <toolchain quirks, hook behaviors, commit rules, anything that bit us>
```

## Kickoff prompt template

Lines in `[brackets]` appear only when the named setting is non-empty.

```
Continue <project> on branch `<branch>`.

START HERE: read <handoff-doc path> — full state, run commands, decisions, gotchas.
[plannerDocs: Read <planner doc> first (item <n> is the task), then the handoff.]

Status: <1–2 lines>. Committed (latest <sha>); <pushed to <remote/branch> | NOT pushed — I push myself>.

Do these in order:
  1. <next step 1, one line>
  2. <next step 2, one line>

(Future, noted in the handoff: <short list>.)

[kickoffHardRules: Hard rules: <one line per rule>.]

Verify via `<verifyCommand>`. Commit per repo conventions; <push only when I ask | never push | push after committing>.
```

## Notes
- Prefer ONE canonical handoff doc per workstream over many; keep it current.
- Don't dump the whole session — distill. The doc replaces conversation memory, so favor decisions,
  paths, numbers, and next actions over narration.
- Cross-link durable detail (skills, memories, `/workflow:lessons` inbox entries) instead of inlining it.
- Always pair the doc with the kickoff prompt; the prompt's first instruction is to read the doc.

## Configuration

`.claude/claude-skills.json`, key `clear-context-handoff`. All keys optional.

| Key | Default | Meaning |
| --- | --- | --- |
| `handoffDir` | `docs/handoffs` | Directory the handoff doc lives in. |
| `handoffFilePattern` | `handoff-<date>.md` | Filename; `<date>` becomes `YYYY-MM-DD`. |
| `plannerDocs` | `[]` | Planner/plan docs to keep in step (DONE / DO NEXT) and cite in the kickoff prompt. Empty → those sentences are omitted. |
| `commitConvention` | auto-detect | Free text. Default: obey a commitlint config (`commitlint.config.*`, `.commitlintrc*`, `package.json` `commitlint` key) if present, else the commit rules in the repo's `CLAUDE.md`, else plain conventional commits (`docs: …`). |
| `pushPolicy` | `ask` | `ask` — ask before pushing; `never` — never push, say so in the prompt; `auto` — push after the commit. |
| `kickoffHardRules` | `[]` | One-line rules the fresh session must never break; printed verbatim in the prompt. |
| `verifyCommand` | auto-detect | Default: package manager from the lockfile (`pnpm-lock.yaml`, `yarn.lock`, `package-lock.json`, `bun.lockb`); `<pm> typecheck && <pm> test` when both scripts exist in `package.json`, else `<pm> test`; `gradlew` → `./gradlew test`. |

Example:

```json
{
  "clear-context-handoff": {
    "handoffDir": "docs",
    "plannerDocs": ["docs/plan-next.md"],
    "pushPolicy": "never",
    "kickoffHardRules": [
      "FP only — pure stages, typed Ok|Err results, effects only in adapters",
      "suppressed findings stay visible under `suppressed`, never silently dropped"
    ],
    "verifyCommand": "pnpm typecheck && pnpm test && pnpm build"
  }
}
```

---
To change this skill, do not edit this copy: use `/dev-tools:update-skill`, or see `docs/updating-skills.md` in `mzvonar/claude-skills-public`.
