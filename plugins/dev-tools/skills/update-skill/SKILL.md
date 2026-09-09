---
name: update-skill
description: Change a skill that was installed from the claude-skills-public marketplace (any `/dev-tools:*`, `/workflow:*`, `/next-js:*`, `/prisma:*`, `/describe-changes:*`, `/refdiff:*`, `/svc:*` skill) the right way — upstream in a sibling checkout, validated, version-bumped, then rolled out with a plugin update. Use whenever the user asks to update, fix, improve, extend, or reword one of these skills, says a skill "is wrong" or "should also…", or you are about to edit a file under ~/.claude/plugins/cache/ or copy a plugin skill into .claude/skills/. Never edit the cached copy and never vendor it into the repo.
---

# Update a marketplace skill

Plugin skills are read-only copies under `~/.claude/plugins/cache/claude-skills-public/`. An edit
there is overwritten by the next update; a copy in the repo's `.claude/skills/` silently shadows the
plugin forever. The fix goes upstream, then comes back through the marketplace.

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

```bash
claude --plugin-dir "$REPOS/claude-skills-public/plugins/<plugin>"
```

That session uses the edited skill under its normal `/<plugin>:<skill>` name. Repeat until it does
what the user wanted. If a symlink into `.claude/skills/` is unavoidable for the test, add it to
`.git/info/exclude` and delete it before step 5.

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

For `refdiff` / `svc`: commit and push in their repo, then bump only the marketplace entry here.

## 5. Roll it out here

```bash
claude plugin marketplace update claude-skills-public
claude plugin update <plugin>@claude-skills-public --scope project    # or the scope it was installed with
```

or `"$REPOS/claude-skills-public/scripts/check-drift.sh" --update`. Tell the user to restart
Claude Code, and that other repos get the change the same way.

## Configuration

None. The marketplace checkout location is derived from this repo's parent directory.
