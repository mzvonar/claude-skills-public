# Updating a skill

Inside a consumer repo, `/dev-tools:update-skill` walks Claude through exactly this loop.

Plugin skills are read-only copies in `~/.claude/plugins/cache/`. Never edit them there and never
copy them into a consumer's `.claude/skills/` to tweak them: a project-level copy silently shadows
the plugin and the edit is lost on the next update. Fix the skill upstream, then update.

## 1. Check the marketplace out as a sibling

```bash
cd <your-repos-dir>                  # wherever your repos live; the checkout becomes a sibling
git clone git@github.com:mzvonar/claude-skills-public.git
```

If you found the problem while working in a consumer repo, keep that repo open; the checkout sits
next to it.

## 2. Work on the live skill from the checkout

**Recommended: load the plugin from the working tree.** The skill keeps its namespaced name, nothing
is written into the consumer, and edits are live on the next invocation:

```bash
cd <consumer-repo>
claude --plugin-dir <your-repos-dir>/claude-skills-public/plugins/workflow
```

`--plugin-dir` can be repeated for several plugins. The working-tree plugin replaces the installed
one for that session only.

**Alternative: symlink into the consumer.** Useful when you need the bare name or want to test
exactly what a vendored layout would see:

```bash
cd <consumer-repo>
ln -s <your-repos-dir>/claude-skills-public/plugins/workflow/skills/lessons .claude/skills/lessons
echo '.claude/skills/lessons' >> .git/info/exclude      # keep it out of git
```

Caveats: the skill answers to `/lessons`, not `/workflow:lessons`, and while the link exists it
shadows the installed plugin skill. Remove the link before you finish, or the plugin update you are
about to publish will never reach this repo.

## 3. Validate and test

```bash
cd <your-repos-dir>/claude-skills-public
scripts/validate.sh                              # manifests, frontmatter, forbidden strings, script syntax
bash plugins/<plugin>/tests/run.sh               # where the plugin has tests
```

Keep the change general (see [conventions.md](conventions.md)). Anything project-specific becomes a
key in `.claude/claude-skills.json` with a documented default, not a hardcoded value.

## 4. Release

Bump the plugin version in both places, in the same commit:

- `plugins/<plugin>/.claude-plugin/plugin.json` → `version`
- `.claude-plugin/marketplace.json` → the plugin's entry `version`

Patch for a fix or wording, minor for a new skill or a new config key, major for a renamed skill or a
changed default. `scripts/validate.sh` fails when the two versions disagree. Commit, push to `main`.

Without a version bump nobody receives the change: Claude Code keeps the cached copy until the
catalog's version moves.

## 5. Update the consumers

In each repo that uses the plugin:

```bash
claude plugin marketplace update claude-skills-public
claude plugin update <plugin>@claude-skills-public --scope project     # or --scope user
```

or run `scripts/check-drift.sh --update` from the repo, which does both for every stale plugin.
Restart Claude Code to pick up the new version. Remove any symlink from step 2.

## External plugins (refdiff, svc)

Their source lives in their own repos. Edit and push there, then bump the entry's `version` in this
repo's `.claude-plugin/marketplace.json` so consumers see an update.
