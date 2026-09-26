---
name: diff
description: Show a rich visual diff of git changes. Generates an HTML side-by-side diff (like JetBrains) served over HTTP with the LAN URL printed (plus a Tailscale URL if Tailscale is installed). Falls back to formatted markdown if diff2html-cli is unavailable. Use when the user asks to "show the diff", "visual diff", "review my changes", or wants to see a diff on another device.
argument-hint: "[--markdown] [--staged | HEAD~2..HEAD | -- path/to/file]"
user-invocable: true
allowed-tools: Bash(*)
---

Generate a visual diff of the current git repository's changes.

Arguments passed through to `git diff`: $ARGUMENTS

## Steps

0. **Is this session reading the CURRENT skill text?**
   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-freshness.sh" "${CLAUDE_PLUGIN_ROOT}"
   ```
   Local, no network, **silent** unless something is wrong. Exit **3** — this session is serving
   an older cached copy of THIS plugin than the one installed; a session pins its version at the
   first call and never moves. Put it to the user (`AskUserQuestion`): reload (`/reload-plugins`)
   and re-run, or carry on knowingly. Asks once per plugin per session. Exit **2** — could not
   determine, which is not a pass. Exit **4** — wired wrong, checked nothing; report it.
1. Run the diff script:
   ```
   bash "${CLAUDE_PLUGIN_ROOT}/skills/diff/scripts/generate-diff.sh" $ARGUMENTS
   ```

2. **If URLs are printed** (HTML mode succeeded):
   - Report the URLs clearly so the user can open them on their phone or browser.
   - Note the server PID.
   - Do not print the full diff in the conversation — the HTML viewer is sufficient.

3. **If `MARKDOWN_FALLBACK_START` appears in the output** (diff2html-cli not installed, or `--markdown` flag was passed):
   - Extract the raw diff between `MARKDOWN_FALLBACK_START` and `MARKDOWN_FALLBACK_END`.
   - Format it as a readable diff with:
     - A header showing changed files and total stats (lines added/removed per file)
     - Each file's changes in a fenced ` ```diff ` block with the filename as a subheading
     - Files sorted by change size (most changed first)
   - If `--markdown` was NOT passed, suggest installing diff2html-cli: `npm install -g diff2html-cli`

## Common argument examples

| Command | What it diffs |
|---------|--------------|
| `/diff` | All uncommitted changes (staged + unstaged + untracked) vs HEAD |
| `/diff --markdown` | Same, but output as formatted markdown (no HTML viewer) |
| `/diff --staged` | Only staged changes |
| `/diff HEAD~3` | Last 3 commits |
| `/diff main` | Current branch vs main |
| `/diff -- src/foo.ts` | Single file only |
| `/diff --markdown -- src/foo.ts` | Single file, markdown output |

## Configuration

No config-file keys. The HTML is written to `$TMPDIR` (else `/tmp`) as `diff-review.html` and served on port 9876; set the `DIFF_REVIEW_PORT` env var to use another port.

---
To change this skill, do not edit this copy: use `/dev-tools:update-skill`, or see `docs/updating-skills.md` in `mzvonar/claude-skills-public`.
