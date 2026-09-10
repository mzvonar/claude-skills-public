# claude-skills-public

Martin Zvonár's general-purpose [Claude Code](https://code.claude.com) skills, packaged as a plugin marketplace.
Skills are grouped into plugins by how they are installed together; the plugin is the unit of versioning.

## Install

```
/plugin marketplace add mzvonar/claude-skills-public
/plugin install dev-tools@claude-skills-public
```

Or make a repo pull them in for everyone who opens it, in `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "claude-skills-public": { "source": { "source": "github", "repo": "mzvonar/claude-skills-public" } }
  },
  "enabledPlugins": {
    "dev-tools@claude-skills-public": true,
    "workflow@claude-skills-public": true
  }
}
```

## Plugins

| Plugin | Skills | Source |
|---|---|---|
| `test` | test-audit | this repo |
| `dev-tools` | diff, html-report, ngrok, codebase-map, worktree, update-skill | this repo |
| `workflow` | clear-context-handoff, update-guidelines, lessons, backlog, check-acs, showcase | this repo |
| `next-js` | cache-invalidation, clean-dev | this repo |
| `prisma` | prisma-migrate, prisma7-setup-postgres, prisma7-setup-libsql | this repo |
| `describe-changes` | describe-changes | this repo |
| `refdiff` | refdiff | [mzvonar/refdiff](https://github.com/mzvonar/refdiff) |
| `svc` | dev-services | [mzvonar/svc](https://github.com/mzvonar/svc) |

Skills are namespaced by plugin: `/workflow:lessons`, `/next-js:clean-dev`, `/svc:dev-services`.

## Configuration

Every skill works with zero configuration by detecting the package manager, base branch, forge and dev port.
Per-repo overrides go in one file, `.claude/claude-skills.json`, one key per skill; each SKILL.md documents its keys under `## Configuration`. Conventions for authoring are in [docs/conventions.md](docs/conventions.md).

## Updating

Publishing: change the skill, bump `version` in the plugin's `plugin.json` and its entry in `.claude-plugin/marketplace.json`, push. The full maintainer loop, including how to work on a live skill from a sibling checkout, is in [docs/updating-skills.md](docs/updating-skills.md).

Consuming: `claude plugin marketplace update claude-skills-public` then `claude plugin update <plugin>@claude-skills-public`, or turn on auto-update for this marketplace in `/plugin` → Marketplaces.

`scripts/check-drift.sh` reports which installed plugins are behind the catalog for the current repo and, with `--update`, updates them. Wire it into a preflight step where you want a "you are N versions behind" prompt.

## Development

```
scripts/validate.sh                       # manifests, frontmatter, forbidden strings, script syntax, claude plugin validate
bash plugins/describe-changes/tests/run.sh
bash plugins/workflow/tests/run.sh
claude --plugin-dir plugins/dev-tools     # try a plugin from the working tree
```
