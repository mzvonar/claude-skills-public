---
name: worktree
description: >
  Create a new git worktree on a new branch (off the repo's default branch unless
  another base is stated) and switch to working inside it for the rest of the
  session. Use this skill whenever the user asks to "create a worktree", "new
  worktree", "spin up a worktree", "work from a fresh worktree/branch", "branch off
  main/master and work from it", or otherwise wants isolated work that must not
  touch the root checkout. Also covers what a fresh worktree is missing before
  tests, dev servers, or docker-compose stacks will run from it.
---

# Worktree

Create a new git worktree + branch and make it the working directory for the session.

## Why

Worktrees keep a session's edits isolated from the root checkout, which may have its own
uncommitted state or be driven by another process (an orchestrator, a watcher, a colleague's
terminal). All edits, commands, and commits for the isolated task happen inside the new
worktree — never in the root checkout.

## Resolving `<root>` and `<base>`

- **Root:** `git rev-parse --show-toplevel` from the current directory. If you are already
  inside a worktree, the main checkout is the first entry of `git worktree list`.
- **Base branch:** `worktree.baseBranch` from config if set; otherwise
  `git symbolic-ref --short refs/remotes/origin/HEAD` with the `origin/` prefix stripped; if
  that fails, `main` if it exists, else `master`. Only use another base if the user
  explicitly says so.

```bash
ROOT=$(git rev-parse --show-toplevel)
BASE=$(git -C "$ROOT" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')
: "${BASE:=$(git -C "$ROOT" show-ref -q --verify refs/heads/main && echo main || echo master)}"
```

## Steps

### 0. Is this session reading the CURRENT skill text?

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-freshness.sh" "${CLAUDE_PLUGIN_ROOT}"
```

Local, no network, and **silent** unless something is wrong. Exit **3** — this session is serving
an older cached copy of THIS plugin than the one installed; a session pins its version at the first
call and never moves. Put it to the user (`AskUserQuestion`): reload (`/reload-plugins`) and re-run,
or carry on knowingly. Asks once per plugin per session. Exit **2** — could not determine, which is
not a pass. Exit **4** — this call is wired wrong and checked nothing; report it.

### 1. Pick the name

Derive a short kebab-case branch name from the task the user described (e.g.
`feat/login-form`, `fix-search-pagination`). If there's no task yet, use a dated name like
`wip-2026-01-15`. The worktree directory uses the same name with `/` replaced by `-`.

### 2. Make sure the base is current

```bash
git -C <root> fetch origin <base> 2>&1 | tail -3
git -C <root> log --oneline -1 origin/<base>
```

Branch off `origin/<base>` rather than the local branch — the local one may be behind.

### 3. Create the worktree + branch

Worktrees live under `<root>/<worktreesDir>` (default `.claude/worktrees`). First make sure
that path is gitignored (one-time): if `.gitignore` has no `<worktreesDir>/` entry, add one —
otherwise the worktree shows up as an untracked directory in the root checkout.

```bash
cd <root> && git worktree add -b <name> <worktreesDir>/<dir-name> origin/<base>
```

This creates branch `<name>` at the base's tip and checks it out into the new worktree dir.

### 4. Confirm

```bash
cd <root>/<worktreesDir>/<dir-name> && git status -sb && git log --oneline -1
```

## Working in the worktree afterwards

**The shell cwd resets to the session's configured primary directory after every command** —
it does NOT stay in the new worktree. So you cannot rely on a one-time `cd`. For every
subsequent command, prefix with the worktree path:

```bash
cd <root>/<worktreesDir>/<dir-name> && <command>
```

Use absolute paths under the worktree for file reads/edits. Tell the user the worktree path
and branch once, then keep all work there for the session.

## Before running tests, dev servers, or compose stacks from a worktree

A fresh worktree is a clean checkout: it has everything git tracks and nothing else. Each
missing piece fails with an unrelated-looking error, so do these up front:

1. **Install dependencies** — there is no `node_modules` (`<tool>: command not found`).
   Detect the package manager from the lockfile (`pnpm-lock.yaml` → `pnpm install
   --frozen-lockfile`, `yarn.lock` → `yarn install --frozen-lockfile`,
   `package-lock.json` → `npm ci`, `bun.lockb` → `bun install`). JVM repos: run the wrapper
   once (`./gradlew` / `./mvnw`) to warm the daemon and pull dependencies.
2. **Copy gitignored env files** from the root checkout — `.env.local`, `.env.*.local`, and
   anything else the app reads that git doesn't track. Symptoms: "X must be set", missing
   DB URLs, failing ORM/migration CLIs.
3. **Pin the docker-compose project name.** `docker compose` derives its project name from
   the cwd basename, so from a worktree it tries to bring up a *second* copy of every stack.
   Stacks that bind fixed host ports then fail with `Bind for 0.0.0.0:<port> failed: port is
   already allocated`, and partial bring-ups leave orphaned containers. Decide per stack:
   - **Share it** (databases, mocks, brokers with fixed ports):
     `export COMPOSE_PROJECT_NAME=<composeProjectPrefix>` so the worktree reuses the root
     checkout's containers.
   - **Isolate it** (only if the compose file maps no fixed host ports):
     `COMPOSE_PROJECT_NAME=<composeProjectPrefix>-<dir-name>`.
4. **Give the worktree its own dev-server port.** Two worktrees cannot both bind the default
   port. If `svc` is installed, register the worktree as its own service via
   `/svc:dev-services` so it gets its own port; otherwise pass `PORT`/`-p` explicitly.
   A per-worktree port breaks Playwright's `reuseExistingServer` unless
   `playwright.config.*` reads the port from env — if it doesn't, let Playwright spawn its
   own server rather than pointing it at the root checkout's.
5. **Run e2e with one worker when sharing a database** (`--workers=1` or the project's
   equivalent env var). Parallel workers from two worktrees against one DB produce flaky,
   order-dependent failures. A fresh worktree also has cold build caches, so the first run
   is slower — don't read that as a hang.

## Notes

- Package-manager and build-tool commands run from the project root — inside the worktree,
  that root is the worktree's own directory, so `cd <worktree> && pnpm …` is correct.
- To remove a worktree later (only when asked):
  `git -C <root> worktree remove <worktreesDir>/<dir-name>` (add `--force` if it has
  untracked files such as `node_modules`), then `git branch -d <name>` if the branch is done.
- Do not commit unless the user explicitly asks.

## Configuration

Optional overrides in `.claude/claude-skills.json` under the `worktree` key:

```json
{
  "worktree": {
    "baseBranch": "develop",
    "worktreesDir": ".claude/worktrees",
    "composeProjectPrefix": "myapp"
  }
}
```

| Key | Default | Meaning |
|---|---|---|
| `baseBranch` | `origin/HEAD` → `main` → `master` | Branch new worktrees branch off |
| `worktreesDir` | `.claude/worktrees` | Directory (relative to root) that holds worktrees; must be gitignored |
| `composeProjectPrefix` | repo directory basename | `COMPOSE_PROJECT_NAME` used when sharing compose stacks; suffixed with the worktree name when isolating |

---
To change this skill, do not edit this copy: use `/dev-tools:update-skill`, or see `docs/updating-skills.md` in `mzvonar/claude-skills-public`.
