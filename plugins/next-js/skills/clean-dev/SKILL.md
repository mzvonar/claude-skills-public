---
name: clean-dev
description: Kill the Next.js dev server on the project's dev port and start a fresh one with `.next` (plus any configured extra caches) cleared. Detects the port (svc → `PORT` in `.env.local` / `.env` → `-p`/`--port` in the dev script → explicit argument → 3000) and the package manager, and uses the repo's own kill / clean scripts when they exist. Use whenever the user wants a clean dev-server restart — "clean dev", "restart the dev server", "kill and restart next", "blow away .next and restart", "fresh dev server", `/next-js:clean-dev [port]` — after regenerating a Prisma client, or when a newly added route hangs compiling forever.
---

# clean-dev

Kill the dev server on **the project's dev port**, clear the dist cache(s), start a fresh server.

## 1. Find the port

First hit wins; an explicit argument beats everything, `port` in config beats detection.

1. `svc` installed (`command -v svc` — the `/svc:dev-services` skill): `svc status --json` and read the port of this worktree's Next dev service.
2. `PORT=` in `.env.local`, then `.env`.
3. `-p` / `--port` in the `dev` script of `package.json` (or the script named by `devScript`).
4. Explicit argument: `/next-js:clean-dev 3100`.
5. `3000`.

```bash
PORT=$(grep -hE '^PORT=' .env.local .env 2>/dev/null | head -1 | cut -d= -f2 | tr -d '"')
PORT=${PORT:-$(node -p "(require('./package.json').scripts.dev||'').match(/(?:-p|--port)[ =](\d+)/)?.[1] ?? ''")}
PORT=${PORT:-3000}
```

## 2. Package manager

`pnpm-lock.yaml` → pnpm, `yarn.lock` → yarn, `package-lock.json` → npm, `bun.lockb` → bun. `<pm>` below stands for the result.

## 3. Restart

**Service managed by `svc`:** do not kill it by PID or background a replacement yourself — that desyncs `svc status` from what is actually running for every other session on the machine.

```bash
rm -rf .next          # plus every path in extraCaches
svc restart <service>
```

**Otherwise**, from the project root inside the current worktree. If `package.json` already has scripts for this (`dev:kill`, `dev:clean`, `clean` are common names), use them. Else:

```bash
pids=$(lsof -t -i :"$PORT" -sTCP:LISTEN); [ -n "$pids" ] && kill $pids   # SIGTERM; -9 only if it survives a few seconds
rm -rf .next                                                            # plus extraCaches
<pm> run dev                                                            # long-running — start with run_in_background: true
```

"Port already free" is fine — proceed. Run the dev script as it is written; don't add flags like `--turbopack` unless the script already has them.

## Scope the kill to the port — never `pkill next`

A second supervised Next server may exist on another port (the admin UI of a local backend stack, a storybook, an e2e server). Supervised ones respawn the moment they are killed, so chasing them is pointless and broadening the kill takes out things other sessions depend on. If you see another `next`/`next-server` process in `ps` or `lsof` output, ignore it — the port filter above already skips it.

## A newly added route that hangs compiling = suspect the dist cache first

Symptom: the server logs `○ Compiling /<new-route> ...` and never logs completion — minutes, across restarts — while existing routes on the same server compile in seconds.

**The decisive test costs one `cp` and one restart:** replace the page with a 3-line stub that imports nothing and request it. If the stub hangs identically, the problem is neither your import graph nor the route's layout, and the search space is partitioned in about 30 seconds. Do this before theorising about memory pressure or import cycles — both are plausible, both were wrong when this was first diagnosed. The tell: **existing routes are fine, only the route that does not exist in the cache yet hangs.**

The fix is the dist cache of *that* server: `.next` for the dev server, the matching entry in `extraCaches` for a second server (with `svc`: `svc stop <e2eService> && rm -rf <cache> && svc up <e2eService>`).

## Clear caches before any cross-branch build

Same family, different symptom. Building the base branch right after a feature branch can die with "Cannot find module .../<route-only-on-the-branch>/page.js". The cause is `.next/dev/types/validator.ts`, a stale typegen artifact still referencing the branch's route; nothing to do with the base branch's code, and it makes a cross-branch baseline look like a broken tree.

Any `git checkout` across branches that added or removed routes invalidates every dist cache. Clear `.next` and all `extraCaches` before the build, then regenerate route types if your Next version has typegen (`<pm> exec next typegen`).

## Configuration

Optional, in `.claude/claude-skills.json`:

```json
{
  "clean-dev": {
    "port": 3100,
    "extraCaches": [".next-e2e"],
    "e2eService": "dev-server-e2e",
    "devScript": "dev"
  }
}
```

| Key | Default | Meaning |
|---|---|---|
| `port` | detected (see §1) | Dev-server port to kill; an explicit argument still wins. |
| `extraCaches` | `[]` | Additional dist directories to clear alongside `.next` (e.g. a separate e2e build dir). |
| `e2eService` | unset | `svc` service name of a second (e2e) Next server, restarted when its cache is cleared. |
| `devScript` | `"dev"` | `package.json` script that starts the dev server; also where the `-p`/`--port` lookup reads. |

---
To change this skill, do not edit this copy: use `/dev-tools:update-skill`, or see `docs/updating-skills.md` in `mzvonar/claude-skills-public`.
