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

A skill with a pre-flight, a setup step, or anything it calls "step 1" runs the freshness check
there, as its own step 0 — **from its own plugin, and passing its own root**:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-freshness.sh" "${CLAUDE_PLUGIN_ROOT}"
```

Exit `0` = current and silent · `3` = ask the user · `2` = could not determine, which is not a
pass · `4` = this call is wired wrong.

**Pass the root; never rely on the variable reaching the shell.** `${CLAUDE_PLUGIN_ROOT}` is a
token substituted into SKILL.md *text* when a skill loads — it is **not** an exported environment
variable, measured: fifteen `CLAUDE_*` vars reach a Bash call and that is not one of them. The
first version of this rule told skills to call the script with no argument; every call exited
"undetermined", every skill's own text said "carry on", and the check did nothing in thirteen
skills while looking installed. Hence exit `4` as a category of its own, and hence
`scripts/tests/plugin-freshness.test.sh`, which resolves the path every SKILL.md names and fails
if it does not exist or is not passed an argument. That test is the rule; this paragraph only
explains it.

**Why `check-drift.sh` does not cover this.** Three versions are in play and it compares two:

| | what it is |
| --- | --- |
| catalog | what the marketplace publishes |
| installed | what `claude plugin update` last wrote into the install record |
| **loaded** | **the cache directory THIS SESSION resolved at its first call to the skill** |

`loaded` is pinned at session start and never moves, while the cache keeps every version side by
side. **OBSERVATION, not an invariant:** on 2026-09-26 the `refdiff` cache held 12 version
directories — it read "nine, measured" here when written a day earlier — and the eight plugins
ranged from 3 to 12. Only "more than one" has to hold for the rest of this section to stand, so
re-measure (`ls ~/.claude/plugins/cache/<marketplace>/<plugin>/`) instead of trusting or repairing
the figure. An update made mid-session writes a directory
that session will never read, and nothing reports it: the update prints success, `check-drift.sh`
prints "current", and the only tell is the `Base directory for this skill:` line the Skill tool
prints on invocation. Measured 2026-09-25: a session served `refdiff` 1.4.0 from first call to
last while the records read 1.6.0 then 1.6.1, missing two rules it needed (`grep`: 0 vs 1 for each
marker; 424 lines against 470).

**The script is stateless: it reports what it measures, every time.** That matters because the
check is self-triggering — `/dev-tools:update-skill` ends by running `claude plugin update`, which
is exactly what makes `loaded < installed` true — so a session can meet the same true answer
repeatedly. **Deduplication belongs in the calling skill, not the script:** if you have already put
this question to the user for this plugin in this session, note it and carry on.

A once-per-session acknowledgement was tried in the script (a stamp file keyed on
`$CLAUDE_CODE_SESSION_ID`) and removed the same day with four defects, all from one mistake — a
stamp records *that a call happened*, not *that the user was asked*, and a script cannot observe
the second. It made refdiff's preflight report a stale session as `current`; it never covered the
`unknown` path, so persistent causes still repeated; it omitted which arm fired, suppressing the
"now reload" follow-up in the very workflow that causes it; and subagents inherit the parent's
session id while having no way to ask, so a subagent spent the single ask. The agent knows whether
it has asked. The script never can.

**The script is copied into each plugin that ships it**, since a plugin's cache directory carries
only its own subtree. `scripts/plugin-freshness.sh` is canonical; change it there and copy across,
and the test asserts the copies are byte-identical. `refdiff` and `svc` are separate repos and
carry their own: refdiff calls it from `preflight.sh` (its `skill_freshness` row is the worked
example), svc from `dev-services`' step 0.

**Every skill in this marketplace that has a numbered first step is wired** — 20 of them, a count
`scripts/tests/plugin-freshness.test.sh` pins as an invariant so one silently deleted fails rather
than just removing a green row. The skills with no numbered steps are exempt by shape, not by
oversight; re-derive the census with:

```bash
for f in $(find plugins -name SKILL.md); do grep -q plugin-freshness "$f" || \
  { grep -qE '^\s*(###? )?[*]{0,2}1\.' "$f" && echo "unwired: $f"; }; done
```

A `github`-sourced entry keeps its manifest in its own repo, so `validate.sh` can only pair the
versions when that repo is checked out beside this one — it does, and **says SKIPPED when it
cannot**, because an absent check and a passing one must not look alike.

Be precise about what it can and cannot tell you, because the first version of this paragraph was
not. It compares the listing against **whatever is in the sibling working tree**, which may be a
stale clone, a dirty tree, or a branch nobody published. The one hit it produced on introduction
was exactly that: a sibling checkout nine days behind reading 1.0.0 against a listing of 1.1.0 —
the *published* states had agreed since 88 seconds after the bump. This paragraph originally
reported that as a real publishing mismatch with a consumer-visible symptom, which was false and
is the kind of claim the section above exists to stop. It cannot distinguish "the listing is
wrong" from "your clone is old"; it flags that two numbers disagree, and you go and look.
It also never runs in CI, which checks out this repo alone — so CI always prints SKIPPED, and the
pairing is enforced on a maintainer's machine only.

## Frontmatter
`name` must equal the directory name. `description` says what the skill does and when to trigger it, in one paragraph, under 1024 characters.

## Versioning
The plugin is the unit of versioning. Bump `version` in the plugin's `plugin.json` and the matching entry in `.claude-plugin/marketplace.json` in the same commit; `scripts/validate.sh` fails when they disagree.

## Maintaining
How to work on a live skill, release, and roll the update out: [updating-skills.md](updating-skills.md).
