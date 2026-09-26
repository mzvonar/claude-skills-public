---
name: lessons
description: Capture durable lessons during ad-hoc work (outside your story orchestrator, if any) into a transient repo inbox, then on demand promote them to their real homes (skills, CLAUDE.md, ADRs, narrative docs, wiki, memory). THREE triggers. (1) CAPTURE — proactively, the moment ad-hoc work surfaces a reusable insight: a correction on how you should work, a non-obvious gotcha, a rejected approach and why, or a rule that should exist. Append it to the lessons inbox (default docs/lessons-inbox.md); do not wait to be asked. (2) PROCESS — when the user says "process the lessons", "harvest the lessons", "turn the lessons into skills/guidelines", "promote the lessons", or "drain the lessons inbox": route each inbox entry to its durable home or discard it. (3) SETUP — when the user says "set up lessons", "install the lessons skill", or the repo has no lessons inbox or capture rule yet. Not for lessons an orchestrated story flow already captures, nor for one-off notes with no lasting value.
---

# lessons — capture durable insights during ad-hoc work, promote them later

A story orchestrator (if the repo has one — see `orchestratorSkills`) captures lessons as it goes and, at "done", turns them into skill/guideline updates. **Ad-hoc prompting has no such pipeline** — so the corrections, gotchas, and rejected approaches that surface during free-form work get lost. This skill closes that gap with two lifetimes:

- **Inbox** (`inboxPath`, default `docs/lessons-inbox.md`) — a transient, append-only buffer. Cheap to write to mid-work.
- **Durable homes** — skills, `CLAUDE.md`, ADRs, a narrative doc, the wiki, memory. Where a lesson belongs once it has proven worth keeping.

Capture is a **standing CLAUDE.md rule** (always-on, fires without being invoked). Processing is **this skill, invoked on demand**. They meet at the inbox.

## Step 0 — is this session reading the CURRENT skill text?

```bash
bash "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/marketplaces/claude-skills-public/scripts/plugin-freshness.sh"
```

Local, no network, silent when current. **Exit 3** = this session is serving an older cached
version than the one installed — a session pins its version at the first call to a skill and never
moves, and nothing else reports it. Put it to the user with `AskUserQuestion`: reload
(`/reload-plugins`) and re-run, or carry on knowingly. Exit 2 or no such script = undetermined,
carry on. Why: `docs/conventions.md`.

## 0. Settings

Read `.claude/claude-skills.json` → key `lessons` if present; missing keys take the defaults in Configuration. Routes that are absent (no `adrDir`, no wiki, …) fall back as described under Portability.

## 1. Setup (run once per repo)

When the user asks to **"set up lessons" / "install the lessons skill"**, or the repo has no inbox / capture rule yet, run from the repo root:

```bash
node "${CLAUDE_PLUGIN_ROOT}/skills/lessons/scripts/setup.mjs"
```

(`CLAUDE_PLUGIN_ROOT` is the installed plugin directory; substitute the path where this skill lives if the variable is unset. An optional first argument overrides the repo root.) Idempotent: it (1) creates the inbox from a bundled template if missing, and (2) appends the standing capture rule to `CLAUDE.md` if not already there (creating `CLAUDE.md` if absent). It reads `orchestratorSkills`, `inboxPath` and `guidelinesSkill` from the config file to word both. Commits nothing. Re-running is safe; existing files/rules are skipped, not overwritten.

## 2. Capture (proactive, during ad-hoc work)

**Append the moment a durable lesson surfaces — do not wait for "process".** Chat scrollback isn't reliably re-scannable later, so an unwritten lesson is a lost lesson. What counts:

- **A correction on how you should work** — the user redirected your approach and you'd want that to stick ("don't do X, do Y because Z"). → usually CLAUDE.md / memory `feedback`.
- **A non-obvious gotcha** — a footgun, an environment quirk, a wrong assumption that cost a rewrite. → usually the narrative doc or a skill body.
- **A rejected approach + why** — you weighed A vs B and picked one for a reason worth preserving. → usually an ADR.
- **A rule that should exist** — a pattern you had to derive that future work should just follow. → usually CLAUDE.md + the matching skill.

Skip anything already covered by an existing rule, or that only mattered to the current task. When in doubt, capture; `process` can discard cheaply.

**Format** — append a `##` section at the **top of the log** (directly under the `<!-- LESSONS-LOG -->` marker in the inbox), newest first:

```markdown
## <YYYY-MM-DD> — short title of the lesson
- **Context:** what work / branch / file this came from
- **Lesson:** the durable insight, stated as an actionable rule (what to do, and why)
- **Candidate home:** (optional guess) skill:<name> · CLAUDE.md · ADR · anchor · wiki · memory · discard
```

Take the date from the session's current-date context (never guess). `Candidate home` is a hint for the process step; leave it blank if unsure. Use `Write`/`Edit` to append — never a shell-side write (heredoc, redirect, `sed -i`), which bypasses the hooks.

## 3. Process (on demand — "process the lessons")

1. **Read** the inbox. If it's empty (only the example row), say so and stop.
2. **Route each entry** to exactly one durable home using the table below, and draft the concrete change (the actual rule text / ADR / narrative / memory entry).
3. **Present the routing plan first** — a short list of `entry → home → proposed change` — and get confirmation before editing durable files. Promotion mutates curated, always-loaded files, so this is a real gate. Batch the plan; don't ask per-entry.
4. **Apply**, preferring the repo's existing machinery over hand-edits:
   - **CLAUDE.md rule / skill body change** → invoke `guidelinesSkill` (default `/workflow:update-guidelines`; it edits the guideline doc *and* propagates to the affected skills/agents). Do not hand-edit CLAUDE.md for a rule change when that skill is installed.
   - **Rejected approach / significant decision** → new ADR in `routes.adr` (next number; use its template if one exists); cross-link the wiki page it backs when there is one.
   - **Incident narrative behind a rule** → append to `routes.anchors`; cite it as `Anchor: …` wherever the rule lives.
   - **Business rule / domain / integration** → the matching page under `routes.wiki`.
   - **How-you-should-work fact / project state** → a memory entry (`feedback` or `project` type) with `**Why:**` / `**How to apply:**`, in `routes.memory` when set, else the agent's own memory.
   - **Already covered / not durable** → discard (state why).
5. **Drain** — remove each promoted or discarded entry from the inbox as it's handled, so the inbox holds only unprocessed lessons. Leave the header, marker, and example row intact.
6. **Report** what landed where, and remind the user nothing is committed (`commitPolicy`).

### Routing table

| Lesson kind | Durable home | Mechanism |
| --- | --- | --- |
| Rule about how code should be written; a correction that should always apply | CLAUDE.md + matching skill | `guidelinesSkill` |
| A gotcha / footgun / env quirk worth a war story | `routes.anchors` (+ a one-line rule cite) | Edit |
| Chose A over B for a reason worth preserving | ADR in `routes.adr` | Edit (template if present) |
| Business rule / domain concept / 3rd-party integration behaviour | `routes.wiki` page | Edit |
| A fact about how you should work with THIS user/project | Memory (`routes.memory` or agent memory) | `feedback`/`project` entry |
| Redundant with an existing rule, or one-off | — | Discard, say why |

## Portability

Self-contained: `SKILL.md` + `scripts/setup.mjs`, no deps beyond `node` + `git`. Capture and the inbox work anywhere unchanged. When a route is not configured and its conventional location does not exist (`docs/adr/`, a narrative doc, `docs/wiki/`), fall back to the nearest home that does: the primary guidelines doc for rules, a `docs/` note for decisions and narratives, agent memory for user/project facts. Say which fallback you used.

## Configuration

`.claude/claude-skills.json`, key `lessons`. All keys optional.

| Key | Default | Meaning |
| --- | --- | --- |
| `orchestratorSkills` | `[]` | Skills that run stories and own their own lesson pipeline (e.g. `["/story-orchestrator"]`). Empty → the wording "your story orchestrator, if any". |
| `inboxPath` | `docs/lessons-inbox.md` | The transient capture buffer. |
| `routes.adr` | none (falls back to `docs/adr/` if present) | Directory for decision records. |
| `routes.anchors` | none (falls back to `docs/engineering-anchors.md` if present) | Narrative doc for incidents behind rules. |
| `routes.wiki` | none (falls back to `docs/wiki/` if present) | Directory of domain / integration pages. |
| `routes.memory` | none (agent memory) | Directory for memory entries + their index. |
| `guidelinesSkill` | `/workflow:update-guidelines` | Skill used to change guideline rules and propagate them. |
| `commitPolicy` | `"never commit unless asked"` | Repeated in the process report. |

---
To change this skill, do not edit this copy: use `/dev-tools:update-skill`, or see `docs/updating-skills.md` in `mzvonar/claude-skills-public`.
