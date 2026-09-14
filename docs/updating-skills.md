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

**Fixing it mid-task? You need none of the machinery below.** A skill is a SKILL.md plus some
scripts, and both are readable from any path. Edit the checkout, then use it in the session you are
already in:

- **scripts** are executed by path, so a script edit is live the moment you save it — run
  `<checkout>/plugins/<plugin>/skills/<skill>/scripts/<script>` instead of the cached copy.
- **SKILL.md** is just a file; read the edited one from the checkout and follow it.

Registration only buys auto-discovery and `/namespaced` invocation. Reach for the options below when
you want those during development; reach for nothing when you simply want the fix working now.

**Load the plugin from the working tree.** The skill keeps its namespaced name, nothing is written
into the consumer, and edits are live on the next invocation. Note this is a session-start flag, so
it means relaunching:

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

Caveats: the skill answers to `/lessons`, not `/workflow:lessons`. Remove the link before you
finish, or the plugin update you are about to publish will never reach this repo.

**A symlink does not necessarily replace the installed skill — it can sit beside it.** Observed with
a user-level link (`~/.claude/skills/<name>`, which auto-loads as `<name>@skills-dir`): with the
plugin also installed, both registered at once, the link under its bare name and the plugin under
its namespaced one. Two live copies of the same skill is worse than a stale one, because a trigger
phrase can fire either and nothing says which you got. Treat a link as temporary, always.

**Anything under `~/.claude/skills/` is invisible to `check-drift.sh`.** It has no version to
compare, so it never reports stale and never updates — a linked checkout can sit many commits
behind upstream with nothing to tell you. If you use a skill rather than develop it, install it as a
plugin and delete the link.

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

`claude plugin tag plugins/<plugin>` checks the two manifests agree and creates a
`{name}--v{version}` release tag — cheaper than discovering the mismatch from a consumer that never
received the update.

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

Installing one clones its repo, unlike the plugins that ship inside this one — so these are the
entries that hit the clone problem below.

## Troubleshooting

**`claude plugin install` fails to clone.** Entries with a `github` source are cloned over SSH. On a
machine authenticated with `gh` over HTTPS and no SSH key, that fails two ways — `No ED25519 host
key is known for github.com` first, then `Permission denied (publickey)`. Route git's GitHub SSH
URLs over HTTPS, where the `gh` credential helper already works:

```bash
git config --global url."https://github.com/".insteadOf "git@github.com:"
```

If the host-key error persists, add the keys — but verify them rather than trusting the scan:
compare `ssh-keyscan github.com` against the `ssh_keys` array of `https://api.github.com/meta`,
which arrives over TLS, and only append once the two agree.

**A plugin loads but `check-drift.sh` never mentions it.** Being listed in a repo's
`.claude/settings.json` `enabledPlugins` is not the same as being installed: the skills resolve, but
with no record in `~/.claude/plugins/installed_plugins.json` there is no version to compare, so the
plugin silently never updates. `check-drift.sh` lists what is genuinely tracked — anything enabled
but missing from that table should be installed properly:

```bash
claude plugin install <plugin>@claude-skills-public --scope project
```

**Two records for one plugin at the same scope.** An interrupted update can leave an orphan, and
`claude plugin uninstall` removes the current record while the stale one survives — after which it
reports the plugin as installed in another scope and refuses to touch the leftover. Back up
`~/.claude/plugins/installed_plugins.json`, drop the orphaned entry from the plugin's array, then
re-run `check-drift.sh` to confirm one row per scope.
