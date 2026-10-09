---
name: update-guidelines
description: |
  Updates the repo's canonical guideline docs (CLAUDE.md, AGENTS.md, architecture docs) and propagates the change to every project agent and skill that generates code. Use when the user says "update the guidelines", "update CLAUDE.md / AGENTS.md", "update the architecture", "incorporate this research"; when a convention changes systematically (naming, layering, validation, dependency, test or commit rules); when a lesson promoted by /workflow:lessons needs a guideline gist plus a skill body; or when the user asks to make CLAUDE.md leaner / slimmer / shorter, do "CLAUDE.md hygiene", trim / de-bloat it, or retire rules piling up in project skills (then the hygiene runbook is the whole job). Invoke proactively on any systematic change to how code is written. Always runs every phase and never stops after one doc: a stale assertion is worse than a missing one. CLAUDE.md stays an index of one-line gists under 400 lines / 40,000 chars; rule bodies live in project skills; the whole corpus is budgeted.
---

## Overview

- 5-phase skill: read → update the canonical doc(s) → **Phase 3 hygiene runbook** (re-lean) → analyse managed files → apply; **all phases mandatory**. A "make it leaner / hygiene" request enters at Phase 3, which is then the whole job. Phase 6 (impact check) is optional and on-demand only.
- Two modes (`mode` in Configuration): **`runbook`** (default) applies routine trims directly and proposes only big rewrites; **`propose`** presents every hygiene action as a batch and waits for confirmation.
- Leanness model: the always-on doc is an **index + invariant register** — every rule is a one-line *actionable* gist (imperative + trigger) plus a pointer to the home holding the body. Bodies load on demand from **the repo's own project skills** (those under `.claude/skills/` marked `managed-by: project`): the harness advertises a skill by its `description` (strong pull), whereas a plain reference doc has only a passive link (weak pull) and tends to be bypassed. So must-load detail goes in a skill or a self-sufficient gist — never a stray reference doc.
- **The rule corpus is what an agent actually reads**: the canonical docs plus every project skill, project agent and `corpusFiles` entry, each loaded whole when it is invoked. It is measured and budgeted as a whole (Phase 3), because moving a body from `CLAUDE.md` into a skill relocates it without shrinking anything an agent reads, and rules otherwise only accumulate.
- **Spine of this skill:** a behaviour change and the sentence that describes it travel in the same change. Ending state is checked by `grep -n "<old-term>"` (Phase 5).

## Phase 0 — Resolve settings and the homes table

**First, is this session reading the CURRENT skill text?**

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-freshness.sh" "${CLAUDE_PLUGIN_ROOT}"
```

Local, no network, and **silent** unless something is wrong. Exit **3** — this session is serving
an older cached copy of THIS plugin than the one installed; a session pins its version at the first
call and never moves. Put it to the user (`AskUserQuestion`): reload (`/reload-plugins`) and re-run,
or carry on knowingly — and if you already put this question for this plugin in this session, just
note it and carry on; the check is stateless and will keep reporting. Exit **2** — could not
determine, which is not a pass. Exit **4**, or `No such file` / exit **127** — this call is wired
wrong and checked nothing; report it. Why: `docs/conventions.md` in `mzvonar/claude-skills-public`.

Read `.claude/claude-skills.json` → key `update-guidelines` if present; missing keys take the defaults in Configuration. Then fix the **homes table** for this run — where each kind of guidance lives:

| Home | Holds | Loaded |
| --- | --- | --- |
| `canonicalDocs[].path` with role `agent entry point` (default `CLAUDE.md`; plus `AGENTS.md` when present) | hard rules, design principles, commands, test and commit rules — **gists, not bodies** | every session |
| `canonicalDocs[]` with role `architecture` (auto-detected `docs/architecture*.md`) | the structural spec and the *why*: layers, dependency direction, module boundaries, decisions with dates | on demand |
| the repo's project skills (`managed-by: project`) | rule bodies: statement + enforcement ref + mechanism, one skill per topic | on demand, strong pull |
| `narrativeHome` (optional) | incident narratives behind rules, cited from the gist as `Anchor: …` | on demand |
| `adrDir` (optional) | decision records: context, alternatives, rationale | on demand |
| `gapClassesFile` (optional) | this repo's own gap classes for Phase 4 | by this skill |

**Default for new content:** is it a coding rule (→ gist in the agent entry point, body in the owning project skill), a structural invariant (→ architecture doc), or a decision/narrative (→ `adrDir` / `narrativeHome`)? If it fits none, it is probably too narrow to be a repo-wide invariant — propose a new project skill and leave a one-line pointer where the rule surfaces. Never bloat a thin entry point that merely imports `AGENTS.md`; content goes to the imported doc.

## Phase 1 — Read input

- Read **all** input before touching any file: the change itself (a diff, a `/workflow:lessons` entry, research, a decision), then every canonical doc top-to-bottom, then the project skill or doc that currently asserts the behaviour being changed: `grep -rn "<old-term>" <canonical docs> .claude/skills/ docs/`.
- Read `inputGlobs` when configured (planning artifacts, PRDs, specs). Read the lessons inbox if `/workflow:lessons` is installed — an unprocessed entry may be the same lesson.
- For a pure hygiene request, measure first (`wc -l -c` over every canonical doc and every corpus file — Phase 3, step 1) and inventory bloat for Phase 3.
- Identify the delta: **new** vs **contradicts** an old rule vs **removes** one. For a removal, list every sentence that described the old behaviour — those read as authoritative and will be believed.

## Phase 2 — Update the canonical doc(s), lean form

- Pick the destination with the homes table. Never duplicate a rule across docs; one canonical statement, the other side gets a pointer.
- **A new or changed rule is a one-line actionable gist** in the always-on doc with the body in the project skill owning the topic — never a fat inline paragraph, never a new stand-alone reference doc. Extend an existing skill by topic before creating one.
- Edit a rule inline only for the protected spine (Phase 3) or a rule with no skill home that is complete in two sentences.
- Inline prose stays actionable: the rule, the trigger, the enforcement (a test path, a grep, a command) — never the story of how it was learned; that goes to `narrativeHome` / `adrDir`.
- Edit the relevant section only; prefer extending a section over adding one.
- **Code examples use this repo's domain.** With `domainEntities` configured: use `allowed`, reject `forbidden`. Otherwise derive entities from the code (schema, model, or domain directories) — never generic placeholders (`order`, `user`, `task`) and never leftovers from another project.
- **Code style of examples** follows the repo's own lint/format config (Biome, ESLint, Prettier, ktlint, …) — read it rather than assuming.

## Phase 3 — Hygiene runbook (mandatory; user-gated for big rewrites)

Run after Phase 2 on every invocation, and as the whole job on a hygiene request.

1. **Measure.** `wc -l -c CLAUDE.md` (and every other canonical doc). **Hard default budget for `CLAUDE.md`: under 400 lines AND under 40,000 characters** — a Claude Code loading constraint, not a taste. Other docs default to the same budget unless `budgets` overrides them; an architecture spec may be given more. If Phase 2 pushed a doc up or over, hygiene is required this run; flag overage explicitly.
   **Then measure the rule corpus** (Overview): the canonical docs, every file `list-managed-files.sh` lists (Phase 4), and every `corpusFiles` entry. Report each file against its budget — a file with no `budgets` entry inherits the CLAUDE.md character budget — and the total against `corpusBudget` when set. Compare the total with the last line of `hygieneLog`: growth above `growthAlertPercent` since the last pass, or a file over its budget, makes the corpus scan (classes g–j) part of this run. No log yet → this run writes its first line and the scan runs only when asked.
2. **Scan for the bloat classes** — a–f over the canonical docs on every run; d–j over the whole corpus when the corpus scan runs (a hygiene request, the growth alert above, or the user asking to clean up rules):
   - **a.** a rule body inline that belongs in a project skill or the architecture doc (>~1 short paragraph, or a section >~80 lines / >2 code examples)
   - **b.** history-anchored or incident prose inline ("we used to do X", round-by-round stories, file lists, commit hashes) where a one-line why + pointer would do
   - **c.** N-site / N-step / per-case prose that reads better as a numbered checklist or table
   - **d.** the same rule stated in two places (two docs, a doc + a skill, two skills)
   - **e.** stale or self-contradictory — a retired command, tool, flag or flow; two sections that disagree (grep the old framing)
   - **f.** dangling reference — a `/skill`, doc path, section anchor, command or test path that no longer exists (verify each on disk)
   - **g.** provenance attached to a rule — "added on <date> in <change>", "anchor: …", the measurement that once justified it — where one clause of why would do
   - **h.** a rule that a check now enforces — a test, guard, lint rule, CI job or hook fails on the violation — still stated in full
   - **i.** a dormant rule: nothing in the last `dormantAfterDays` days cited or exercised it — no lesson, review finding, incident or change touched it (cheap probe: `git log -S'<distinctive phrase>' --since=<date>` over the corpus and the lessons and ledger homes)
   - **j.** a one-incident rule that a broader rule in the corpus already covers
3. **Apply per class** (`runbook` mode: routine trims just happen, a BIG rewrite is proposed first as one batch with per-item line/char savings + destination; `propose` mode: everything is proposed first — if the user declines all or nothing is found, output `Canonical-doc hygiene scan: no proposals` and continue):
   - **a →** ensure the body (rule + enforcement + mechanism) is in its owning skill (create it with `managed-by: project` if needed); leave the gist + `/<skill>` trigger; delete the inline body.
   - **b →** one-line why inline; the narrative goes to `narrativeHome` / `adrDir` in the SAME pass (if neither exists, trim to the current rule only and say what was dropped).
   - **c →** convert; cut hedging, restated rationale, blow-by-blow.
   - **d →** keep one canonical statement; the duplicate becomes a pointer. For merged skills, delete the merged file and `grep -rn '/<old-name>'` to fix every cross-reference.
   - **e →** fix or drop; re-grep the old framing until empty.
   - **f →** repoint or remove.
   - **g →** keep at most one clause of why on the rule; move the rest to `historyHome` in the SAME pass, under the rule's first words so it stays findable.
   - **h →** one line naming the check and what it catches; drop the restated body (the check's failure message is the documentation).
   - **i →** always PROPOSED, in both modes: each candidate with where it was last cited (or "never") and what could go wrong without it. The owner decides; a retired rule's text moves to `historyHome` with the date it was retired.
   - **j →** fold it into the broader rule, keeping its distinct case as one clause if it adds one.
4. **Protected — never extract or trim:** the doc's opening voice/principles section, the orientation spine (architecture pointer + read-before triggers, the commands quick-reference, layer and dependency-direction tables), commit policy, and any standing-instruction blocks other skills planted (e.g. the lessons-capture rule). When unsure whether something is spine, ask. A rule with no skill home stays as a complete inline gist.
5. **VERIFY nothing was lost (do not skip).** Extract every enforcement/test ref, `/skill` pointer, doc link, command and decision date from the prose you moved or deleted, and grep-confirm each still resolves in a canonical doc, a skill, `narrativeHome` or `adrDir`; confirm no dangling links remain; every note moved under g or i is present in `historyHome`. **Never delete hard-won context — relocate it**; git history is not a discoverable home.
6. **Re-measure & report.** `wc -l -c` before → after vs budget for each canonical doc and corpus file, the corpus total before → after with its growth since the last logged pass, and where each moved body landed. Append one line to `hygieneLog`: `<date> corpus=<total chars> files=<n>` followed by `<path>=<chars>` per file. Nothing to do → `Canonical-doc hygiene: lean, no changes` (and still log the line).

**Run the corpus scan regularly, not only on request.** The growth alert catches drift at the next guideline change; also invoke this skill with "hygiene" at each retrospective or milestone close, so rules retire at the rate lessons add them.

## Phase 4 — Analyse managed files

- Run `list-managed-files.sh` (bundled beside this SKILL.md) from the repo root. Its output is the **authoritative** list: it scans `.claude/agents/*.md` and `.claude/skills/*/SKILL.md` for `managed-by: project` frontmatter and skips vendored or externally managed files. Drop anything listed in `excludeSkills`; add the non-skill homes from the table (architecture docs, `narrativeHome`, a live plan doc if one is running).
- Never expand to the user's home-level profile unless explicitly asked.

For each file, check the gap classes below; skip a file if none apply — most files are untouched by most updates.

**Generic gap classes**
- **Contradiction** — a sentence asserting the behaviour that Phase 2 just changed.
- **Missing new pattern** — a file that should reference the new rule and doesn't.
- **Stale command** — a script, flag or tool that no longer exists (`verifyCommands` or the detected package-manager scripts are the truth).
- **Wrong base branch** — `git diff main...HEAD` where the detected base (`git symbolic-ref refs/remotes/origin/HEAD`, else `main`, else `master`) is different.
- **Wrong package manager / registry** — commands for a package manager the lockfile does not declare; internal packages routed to the wrong registry.
- **Dangling reference** — a `/skill`, `CLAUDE.md §section`, doc path or test path that isn't there (`ls .claude/skills/` when a skill is named).
- **Off-domain examples** — generic placeholders or another project's entities (`domainEntities.forbidden`).

**Project gap classes** live in `gapClassesFile` (default `.claude/update-guidelines-gap-classes.md`), one bold heading per area, each bullet "what a wrong instruction looks like → the correct rule". They mirror the canonical docs, never aspirations; extend that file as the repo's conventions solidify. This SKILL.md never holds them.

## Phase 5 — Apply all changes

- Apply directly (do not propose again). Priority: (1) contradictions to the updated guidelines, (2) missing new patterns, (3) stale descriptions.
- Rewritten examples use the repo's domain. Do not touch files outside the Phase 4 list; vendored skills and agents without `managed-by: project` are off-limits.
- Do not commit — never commit unless asked.
- **HARD RULE — finish with the check:** `grep -rn "<old-term>" <canonical docs> .claude/skills/ docs/` must come back empty, or hit only a deliberate historical note.

## Phase 6 — Impact check (optional, on-demand; token-intensive)

Never runs automatically. After a big rewrite, offer: _"want me to verify the slimmed guidelines still get the rule applied?"_ On confirmation, for each rule MOVED out of a canonical doc, spawn a read-only agent with a realistic task that DEPENDS on that rule, as a DRY RUN ("plan only, no edits; end with `RULE_APPLIED:` and `FILES_CONSULTED:`"). Pick tasks a guessing model would plausibly get wrong. The fat baseline is compliant by construction, so **lean-arm compliance is the degradation measure**: compliant from gist + skill = the design works; a miss = restore the gist or strengthen the skill's `description`. Make each probe echo a sentinel (`wc -l -c CLAUDE.md`, or a grep of a new gist line) — a spawned agent inherits the SESSION's working directory, not a worktree you edited by absolute path, so an unverified probe may test the old file.

## Spawn strategy

- Phases 1–3 inline — judgement and user interaction.
- Phases 4–5 may go to one agent when the file list is long; hand it the Phase 2 diff, the owning skill's changed body, the verbatim managed-file list, the gap classes (generic + `gapClassesFile`), absolute paths, and the instruction to apply (not propose). Verify its edits with the Phase 5 grep.

## Output

One summary: what changed per canonical doc (± lines, `wc -l -c` before → after vs budget); where each moved body landed; hygiene actions per bloat class + the verify-nothing-lost result (in `propose` mode: proposed / approved / declined / applied); gaps found and fixed per managed file; files checked but unchanged; the final `grep -n "<old-term>"` result.

## Configuration

`.claude/claude-skills.json`, key `update-guidelines`. All keys optional.

| Key | Default | Meaning |
| --- | --- | --- |
| `mode` | `"runbook"` | `runbook` applies routine trims, proposes big rewrites; `propose` proposes every hygiene action first. |
| `canonicalDocs` | `[{ "path": "CLAUDE.md", "role": "agent entry point" }]` + auto-detected `AGENTS.md` (role `agent entry point`) and `docs/architecture*.md` (role `architecture`) when present | `{ path, role, editWhen }` — `editWhen` is free text describing which kind of change lands there. |
| `budgets` | `{ "CLAUDE.md": { "lines": 400, "chars": 40000 } }` | Per-doc override; docs without an entry inherit the CLAUDE.md budget. |
| `inputGlobs` | `[]` | Extra material to read in Phase 1 (planning artifacts, PRDs, specs). |
| `gapClassesFile` | `.claude/update-guidelines-gap-classes.md` | Project-specific gap classes for Phase 4; ignored when absent. |
| `domainEntities` | `{ "allowed": [], "forbidden": [] }` | Entities examples must use / must not use. Empty → derive from the code. |
| `verifyCommands` | auto-detect | Commands examples may cite; default from the lockfile's package manager (`<pm> typecheck`, `<pm> lint`, `<pm> test` when the scripts exist; `./gradlew build` / `test` with a `gradlew`). |
| `narrativeHome` | none | Doc for incident narratives behind rules (e.g. `docs/engineering-anchors.md`). |
| `adrDir` | none | Decision-record directory (e.g. `docs/adr`). |
| `lessonsSkill` | `/workflow:lessons` | The lessons skill whose inbox Phase 1 reads. |
| `excludeSkills` | `[]` | Skill names to leave out of the managed list even though they carry `managed-by: project` (e.g. symlinked shared skills). |
| `corpusFiles` | `[]` | Further files agents are told to read (e.g. an orchestration overlay); measured and scanned with the project skills. |
| `corpusBudget` | none | Character budget for the whole corpus; unset → reported, never enforced. |
| `growthAlertPercent` | `10` | Corpus growth since the last logged pass that makes the corpus scan part of the run. |
| `dormantAfterDays` | `90` | Class i: a rule nothing cited or exercised for this long is proposed for retirement. |
| `historyHome` | `HISTORY.md` beside a skill's `SKILL.md`; for any other file `narrativeHome`, else `<file-name>.history.md` beside it | Where classes g and i relocate provenance and retired rules. Nothing loads it by default. |
| `hygieneLog` | `.claude/update-guidelines-corpus.log` | One line per hygiene pass — date, corpus total, per-file sizes — the baseline for the growth alert. |

Measure at any time with `wc -l -c CLAUDE.md`.

---
To change this skill, do not edit this copy: use `/dev-tools:update-skill`, or see `docs/updating-skills.md` in `mzvonar/claude-skills-public`.
