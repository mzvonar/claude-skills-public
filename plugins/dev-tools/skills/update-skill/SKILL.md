---
name: update-skill
description: Change a skill that was installed from the claude-skills-public marketplace (any `/dev-tools:*`, `/workflow:*`, `/next-js:*`, `/prisma:*`, `/describe-changes:*`, `/refdiff:*`, `/svc:*` skill) the right way — upstream in a sibling checkout, validated, version-bumped, then rolled out with a plugin update. Use whenever the user asks to update, fix, improve, extend, or reword one of these skills, says a skill "is wrong" or "should also…", or you are about to edit a file under ~/.claude/plugins/cache/ or copy a plugin skill into .claude/skills/. Never edit the cached copy and never vendor it into the repo.
---

# Update a marketplace skill

Plugin skills are read-only copies under `~/.claude/plugins/cache/claude-skills-public/`. An edit
there is overwritten by the next update; a copy in the repo's `.claude/skills/` silently shadows the
plugin forever. The fix goes upstream, then comes back through the marketplace.

## Step 0 — is this session reading the CURRENT skill text?

```bash
bash "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/marketplaces/claude-skills-public/scripts/plugin-freshness.sh"
```

Local, no network, silent in the normal case. **Exit 3** means this session is serving an older
cached version than the one installed: a session pins a plugin's version at its first call to the
skill and never moves, so an update made mid-session never reaches it — and nothing else reports
this, because the update prints success and `check-drift.sh` prints "current". Put it to the user
with `AskUserQuestion`: reload (`/reload-plugins`) and re-run, or carry on knowingly. Exit 2, or
the script not being present, means undetermined — carry on. Background: `docs/conventions.md`.

It matters most HERE. This skill ends by telling the user their change is rolled out, and step 5
is where a session would otherwise report success while still reading the text it booted with.

## 0. Identify the skill and its plugin

`/<plugin>:<skill>` tells you both. Find the installed copy to read it:

```bash
ls ~/.claude/plugins/cache/claude-skills-public/<plugin>/*/skills/<skill>/
```

Skills of `refdiff` and `svc` live in their own repos (`mzvonar/refdiff`, `mzvonar/svc`); everything
else is in `mzvonar/claude-skills-public` under `plugins/<plugin>/skills/<skill>/`.

## 1. Get a checkout next to this repo

```bash
REPOS="$(dirname "$(git rev-parse --show-toplevel)")"
[ -d "$REPOS/claude-skills-public" ] || git clone git@github.com:mzvonar/claude-skills-public.git "$REPOS/claude-skills-public"
git -C "$REPOS/claude-skills-public" pull --ff-only
```

If the clone fails you have no write access: describe the change to the user as a proposed diff and
stop. Do not fall back to editing the cache or vendoring.

## 2. Make the change upstream, keep it general

Edit `$REPOS/claude-skills-public/plugins/<plugin>/skills/<skill>/`. Read
`docs/conventions.md` there first. The rule that matters most: anything specific to THIS repo
(paths, ports, names, commands) is not written into the skill; it becomes a key in this repo's
`.claude/claude-skills.json` under the skill's name, with a documented default in the skill's
`## Configuration` section. If the skill already has the key, set it here instead of changing the skill.

## 3. Try it live from the working tree

**To use the fix in THIS session you need no plugin machinery at all.** A skill is a SKILL.md plus
scripts, and both are readable from any path: run the checkout's script by its path instead of the
cached one, and read the checkout's SKILL.md and follow it. A script edit is live the moment it is
saved. Registration only buys auto-discovery and `/namespaced` invocation — never tell the user to
restart for a change they want working now.

When the polished invocation matters during development:

```bash
claude --plugin-dir "$REPOS/claude-skills-public/plugins/<plugin>"
```

That session uses the edited skill under its normal `/<plugin>:<skill>` name — but it is a
session-start flag, so it means relaunching. Repeat until it does what the user wanted. If a symlink
into `.claude/skills/` is unavoidable for the test, add it to `.git/info/exclude` and delete it
before step 5: a link can register ALONGSIDE the installed plugin rather than replacing it, and two
live copies of one skill mean a trigger phrase may fire either with nothing to say which you got.

Never leave a link in `~/.claude/skills/` for a skill the user merely uses. It auto-loads as
`<name>@skills-dir` carrying no version, so `check-drift.sh` cannot see it and it drifts behind
upstream in silence. Install the plugin and delete the link.

## 4. Validate, bump, push

```bash
cd "$REPOS/claude-skills-public"
scripts/validate.sh
bash plugins/<plugin>/tests/run.sh 2>/dev/null || true     # where tests exist
```

Bump `version` in `plugins/<plugin>/.claude-plugin/plugin.json` AND the plugin's entry in
`.claude-plugin/marketplace.json` (patch: fix or wording; minor: new skill or config key; major:
renamed skill or changed default). Commit both with the change and push `main`, subject to the
user's commit and push policy. No bump means no consumer ever receives the change.

`claude plugin tag plugins/<plugin>` checks the two manifests agree and tags the release — cheaper
than learning of a mismatch from a consumer that never received the update.

For `refdiff` / `svc` the version that gates updates lives in THEIR repo, not here. Bump
`.claude-plugin/plugin.json` there and push it with the change; that manifest is what the installed
copy reports and what `claude plugin update` compares. Bump the marketplace entry here to match, so
the listing does not lie — but the entry alone changes nothing. Measured: with the entry at 1.1.0
and the repo's manifest still 1.0.0, `claude plugin update` reported "already at the latest version
(1.0.0)" against a cache four days stale, and the only way through was uninstalling and deleting the
cache directory by hand. Note also that `claude plugin tag` compares two manifests in ONE repo, so
for these it cannot see the pair — check them by eye.

## 5. Roll it out here

```bash
claude plugin marketplace update claude-skills-public
claude plugin update <plugin>@claude-skills-public --scope project    # or the scope it was installed with
```

or `"$REPOS/claude-skills-public/scripts/check-drift.sh" --update`. Tell the user to restart
Claude Code, and that other repos get the change the same way — `check-drift.sh --update` is the
one command per repo.

Run `check-drift.sh` without `--update` first and read the table: it lists only plugins with an
install record, so a plugin the user's `.claude/settings.json` ENABLES but never installed is absent
from it, loads fine, and can never update. Install those properly before claiming a repo is current.

## Troubleshooting

**`claude plugin install` fails to clone** (`refdiff` / `svc`, the entries with their own repos).
A `github` source is cloned over SSH; on a machine authenticated with `gh` over HTTPS and no SSH key
that fails as `No ED25519 host key is known for github.com`, then `Permission denied (publickey)`.
Route git's GitHub SSH URLs over HTTPS, where the `gh` credential helper already works:

```bash
git config --global url."https://github.com/".insteadOf "git@github.com:"
```

Should a host-key error remain, verify before trusting: compare `ssh-keyscan github.com` against the
`ssh_keys` array of `https://api.github.com/meta` (TLS), and append only once the two agree.

**Two records for one plugin at one scope.** An interrupted update can orphan one, and
`claude plugin uninstall` then removes the CURRENT record while the stale one survives, after which
it reports the plugin as living in another scope and refuses the leftover. Back up
`~/.claude/plugins/installed_plugins.json`, drop the orphaned entry, re-run `check-drift.sh`.

## Configuration

None. The marketplace checkout location is derived from this repo's parent directory.
