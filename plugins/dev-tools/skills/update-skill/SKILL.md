---
name: update-skill
description: Change a skill that was installed from the claude-skills-public marketplace (any `/dev-tools:*`, `/workflow:*`, `/next-js:*`, `/prisma:*`, `/describe:*`, `/refdiff:*`, `/svc:*` skill) the right way — upstream in a sibling checkout, validated, version-bumped, then rolled out with a plugin update. Use whenever the user asks to update, fix, improve, extend, or reword one of these skills, says a skill "is wrong" or "should also…", or you are about to edit a file under ~/.claude/plugins/cache/ or copy a plugin skill into .claude/skills/. ALSO use it to release or version-bump `refdiff` or `svc` for ANY change, code-only included ("ship it", "release", "bump the version") — their listing here needs a second push. Never edit the cached copy and never vendor it into the repo.
---

# Update a marketplace skill

Plugin skills are read-only copies under `~/.claude/plugins/cache/claude-skills-public/`. An edit
there is overwritten by the next update; a copy in the repo's `.claude/skills/` silently shadows the
plugin forever. The fix goes upstream, then comes back through the marketplace.

## Before you begin — is this session reading the CURRENT skill text?

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-freshness.sh" "${CLAUDE_PLUGIN_ROOT}"
```

Local, no network, and **silent** unless something is wrong. Exit **3** — this session is serving
an older cached copy of THIS plugin than the one installed; a session pins its version at the first
call to a skill and never moves, so a mid-session update never reaches it. Put it to the user
(`AskUserQuestion`): reload (`/reload-plugins`) and re-run, or carry on knowingly. Exit **2** —
could not determine; that is not a pass, say so. Exit **4**, or `No such file` / exit **127** —
this call is wired wrong and the check did nothing; report it rather than carrying on. Why:
`docs/conventions.md` in `mzvonar/claude-skills-public`.

It matters most HERE: step 5 ends by telling the user their change is rolled out, and it is the one
place where saying that against stale text would be self-defeating.

**This skill CREATES the skew**, because step 5 runs `claude plugin update` and that is exactly
what makes `loaded < installed` true. The check is stateless and will report it on every later
skill in the session, so put the question once, then note the repeats and carry on. Deduplicating
it is your job, not the script's — an in-script acknowledgement was tried and removed, because a
stamp file can only record that a call happened, never that the user was asked.

## 0. Identify the skill and its plugin

`/<plugin>:<skill>` tells you both. Find the installed copy to read it:

```bash
ls ~/.claude/plugins/cache/claude-skills-public/<plugin>/*/skills/<skill>/
```

Skills of `refdiff` and `svc` live in their own repos (`mzvonar/refdiff`, `mzvonar/svc`); everything
else is in `mzvonar/claude-skills-public` under `plugins/<plugin>/skills/<skill>/`.

### Releasing `refdiff` or `svc` — every release, not only a skill edit

A release of either is **two pushes**, and the second is the one that gets forgotten, because
nothing about a release in THEIR repo ever looks at this one:

1. In the plugin's repo: bump `.claude-plugin/plugin.json` and push it with the change. This is the
   version `claude plugin update` compares — the push that actually ships (§4 has the measurement).
2. Here: set the plugin's entry in `.claude-plugin/marketplace.json` to the same version, run
   `bash scripts/check-all.sh`, commit `chore: <plugin> <version> in the listing`, push `main`, and
   watch the CI run that push started (§4). Skipped, the listing lies and `validate.sh` fails on it.

Check the pair from the plugin's side, before and after:

```bash
bash "$REPOS/claude-skills-public/scripts/check-listing.sh" "<plugin checkout>"               # working tree
bash "$REPOS/claude-skills-public/scripts/check-listing.sh" "<plugin checkout>" --published   # origin/main
```

Exit 0 agrees, 1 disagrees (it prints both versions and the fix), 2 could not tell — never a pass.
A code-only release (refdiff's annotator, svc's CLI) needs this exactly as much as a skill edit:
refdiff 1.8.0 shipped from its own repo with the listing left at 1.7.3.

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

Bump `version` in `plugins/<plugin>/.claude-plugin/plugin.json` AND the plugin's entry in
`.claude-plugin/marketplace.json` (patch: fix or wording; minor: new skill or config key; major:
renamed skill or changed default). No bump means no consumer ever receives the change. Then run
exactly what CI runs — the `validate` workflow calls this same script:

```bash
cd "$REPOS/claude-skills-public"
bash scripts/check-all.sh          # validate.sh + every plugin and maintainer test suite; exit 0 or do not push
```

It must exit 0. Do not run a subset and do not swallow a failure (this step used to read
`tests/run.sh 2>/dev/null || true`): the suites that only CI ran — `describe-changes`' version
parity above all — were red on eleven pushes that had each been reported as done.

Commit and push `main`, subject to the user's commit and push policy, then **watch the run the push
started** — a push is not shipped until it is green:

```bash
sleep 5; RUN=$(gh run list --repo mzvonar/claude-skills-public --branch main --commit "$(git rev-parse HEAD)" --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN" --repo mzvonar/claude-skills-public --exit-status   # blocks ~1-2 min; non-zero = red
```

Red: read `gh run view "$RUN" --log-failed`, fix, push, watch again — and say so, never "done". An
empty `RUN` means the run has not registered yet; wait and ask again rather than skipping the watch.

`claude plugin tag plugins/<plugin>` checks the two manifests agree and tags the release — cheaper
than learning of a mismatch from a consumer that never received the update.

For `refdiff` / `svc` the version that gates updates lives in THEIR repo, not here. Bump
`.claude-plugin/plugin.json` there and push it with the change; that manifest is what the installed
copy reports and what `claude plugin update` compares. Bump the marketplace entry here to match, so
the listing does not lie — but the entry alone changes nothing. Measured: with the entry at 1.1.0
and the repo's manifest still 1.0.0, `claude plugin update` reported "already at the latest version
(1.0.0)" against a cache four days stale, and the only way through was uninstalling and deleting the
cache directory by hand. Note also that `claude plugin tag` compares two manifests in ONE repo, so
for these it cannot see the pair — `scripts/check-listing.sh` does (see "Releasing `refdiff` or
`svc`" under §0), and `validate.sh` runs the same script when their repo is checked out beside this.

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
