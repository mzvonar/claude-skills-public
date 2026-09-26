# Skill conventions for this marketplace

Every skill here is installed into repos the author has never seen. These rules keep them portable.

## Zero-config first
A skill must work with no configuration by detecting its environment:
- package manager: `pnpm-lock.yaml` → pnpm, `yarn.lock` → yarn, `package-lock.json` → npm, `bun.lockb` → bun, `gradlew` → gradle
- base branch: `git symbolic-ref refs/remotes/origin/HEAD`, falling back to `main`, then `master`
- forge: `git remote get-url origin` (github.com → GitHub, otherwise GitLab)
- dev port: `svc` if installed, then `PORT` in `.env.local` / `.env`, then `-p`/`--port` in the `dev` script, then an explicit argument, then 3000

## One optional config file
Per-repo overrides live in `.claude/claude-skills.json`, one top-level key per skill:
```json
{
  "clear-context-handoff": { "handoffDir": "docs/handoffs" },
  "update-guidelines": { "budgets": { "CLAUDE.md": { "lines": 400, "chars": 40000 } } }
}
```
Document every key the skill reads in a `## Configuration` section of its SKILL.md, with the default.

## Never ship
- project names, hostnames, absolute or `~` paths, container names, story/epic/PR anchors
- assumptions about a specific planning-artifact layout, Supabase, Inngest, or any single stack unless the skill is about that stack; gate such content behind a detection check or an optional `references/` file
- hard references to skills outside this marketplace; name them as configurable roles instead

## Cross references
Skills reference each other in namespaced form, e.g. `/workflow:lessons`, `/next-js:clean-dev`, `/svc:dev-services`, `/dev-tools:worktree`.

## Is the session even reading THIS version?

**A skill with a pre-flight, a setup step, or anything it calls "step 1" runs
`scripts/plugin-freshness.sh` there**, before the work. No network, no arguments — it reads
`$CLAUDE_PLUGIN_ROOT`. Exit `0` = current, `3` = put it to the user (`AskUserQuestion`, two real
options: reload, or carry on knowingly), `2` = could not determine.

**Why `check-drift.sh` does not cover it.** Three versions are in play and that script compares
two of them:

| | what it is |
| --- | --- |
| catalog | what the marketplace publishes |
| installed | what `claude plugin update` last wrote into the install record |
| **loaded** | **the cache directory THIS SESSION resolved at its first call to the skill** |

`loaded` is pinned at session start and never moves, while the cache keeps every version side by
side — nine directories for one plugin, measured. An update made during a session therefore writes
a directory that session will never read, and **nothing reports it**: the update prints success,
`check-drift.sh` prints "current", and the session goes on reading the old file. The one visible
tell is the `Base directory for this skill:` line the Skill tool prints on invocation.

Measured 2026-09-25: a session served `refdiff` 1.4.0 from its first call to its last while the
install records read 1.6.0 and 1.6.1. The two rules that session most needed had shipped in 1.6.1
and were absent from the 1.4.0 text (`grep`: 0 vs 1 for each marker; 424 lines against 470). It
followed them only because a human had restated them in a handoff.

`refdiff` and `svc` are separate repos whose whole tree is cached, so they carry their own copy of
the script beside their skill and call that instead — refdiff's `preflight.sh` is the worked
example, and its `skill_freshness` row reports `stale-session <loaded> < <installed>`. **Change
`scripts/plugin-freshness.sh` first, then copy it across**; the copies are byte-identical apart
from a provenance paragraph.

## Frontmatter
`name` must equal the directory name. `description` says what the skill does and when to trigger it, in one paragraph, under 1024 characters.

## Versioning
The plugin is the unit of versioning. Bump `version` in the plugin's `plugin.json` and the matching entry in `.claude-plugin/marketplace.json` in the same commit; `scripts/validate.sh` fails when they disagree.

## Maintaining
How to work on a live skill, release, and roll the update out: [updating-skills.md](updating-skills.md).
