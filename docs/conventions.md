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

## Frontmatter
`name` must equal the directory name. `description` says what the skill does and when to trigger it, in one paragraph, under 1024 characters.

## Versioning
The plugin is the unit of versioning. Bump `version` in the plugin's `plugin.json` and the matching entry in `.claude-plugin/marketplace.json` in the same commit; `scripts/validate.sh` fails when they disagree.

## Maintaining
How to work on a live skill, release, and roll the update out: [updating-skills.md](updating-skills.md).
