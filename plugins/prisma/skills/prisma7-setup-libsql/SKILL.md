---
name: prisma7-setup-libsql
disable-model-invocation: true
user-invocable: true
description: Bootstrap a new Next.js / Node.js project with Prisma v7 on libSQL / Turso (SQLite-compatible) using the `@prisma/adapter-libsql` driver adapter — packages, `schema.prisma` without `url`, `prisma.config.ts`, the client module, env vars, first migration, and the errors a fresh install hits. Invoke ONLY when explicitly bootstrapping or setting up Prisma from scratch — not for general Prisma edits in an existing project. Trigger phrases: "bootstrap a new project with Prisma and libSQL", "bootstrap a new project with Prisma and Turso", "set up Prisma 7 with libSQL/Turso from scratch", "new Next.js project needs Prisma 7 + libSQL", or when a fresh install hits P1012 / "datasource.url is required" / "Cannot find module @prisma/adapter-libsql". If Prisma is already configured and working, DO NOT fire — that is ordinary schema / migrate / client work (`/prisma:prisma-migrate`).
---

# Prisma 7 Setup — libSQL / Turso Driver Adapter

Prisma 7 removes the connection string from `schema.prisma` and moves connection
config into a dedicated `prisma.config.ts` at the **project root**. The
`@prisma/adapter-libsql` package handles both local SQLite files and remote Turso.

`<pm>` below is the project's package manager: `pnpm-lock.yaml` → pnpm, `yarn.lock` → yarn,
`package-lock.json` → npm, `bun.lockb` → bun; in a fresh project with no lockfile, use the
`packageManager` field of `package.json` or ask. (`<pm> add` is `npm install` for npm.)

---

## 0. Is this session reading the CURRENT skill text?

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-freshness.sh" "${CLAUDE_PLUGIN_ROOT}"
```

Local, no network, and **silent** unless something is wrong. Exit **3** — this session is serving
an older cached copy of THIS plugin than the one installed; a session pins its version at the first
call and never moves. Put it to the user (`AskUserQuestion`): reload (`/reload-plugins`) and re-run,
or carry on knowingly. Asks once per plugin per session. Exit **2** — could not determine, which is
not a pass. Exit **4** — this call is wired wrong and checked nothing; report it.

## 1. Install packages

```bash
<pm> add @prisma/client@^7 @prisma/adapter-libsql@^7
<pm> add -D prisma@^7 dotenv
```

`@libsql/client` is **not** needed — `@prisma/adapter-libsql` bundles it.

---

## 2. `prisma/schema.prisma` — remove the `url` field

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "sqlite"
  // do NOT add url here — it belongs in prisma.config.ts
}
```

Also remove `previewFeatures = ["driverAdapters"]` if present — driver adapters are GA in v7.

---

## 3. `prisma.config.ts` — at the project root (NOT inside `prisma/`)

Prisma CLI only looks for it at the root.

```ts
import path from "node:path"
import { config } from "dotenv"
import { defineConfig } from "prisma/config"

// Prisma CLI runs outside your framework and does not load .env.local by itself.
// override: false keeps a real env var (CI, production) ahead of the file.
config({ path: ".env.local", override: false })

export default defineConfig({
  schema: path.join(__dirname, "prisma", "schema.prisma"),
  datasource: {
    url: process.env.DATABASE_URL!,
  },
})
```

`datasource.url` is read by the Prisma CLI (`migrate dev`, `studio`, …). The runtime
adapter is wired separately in the client module — no `migrate.adapter` factory is needed.

---

## 4. Client module (e.g. `src/lib/db.ts`) — instantiate PrismaClient with the adapter

`PrismaLibSql` accepts the connection options directly — no `createClient` call needed.

```ts
import "server-only"
import { PrismaClient } from "@prisma/client"
import { PrismaLibSql } from "@prisma/adapter-libsql"

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient | undefined }

function createPrismaClient(): PrismaClient {
  const adapter = new PrismaLibSql({
    url: process.env.DATABASE_URL ?? "file:./dev.db",
    authToken: process.env.DATABASE_AUTH_TOKEN,
  })

  return new PrismaClient({
    adapter,
    log: process.env.LOG_LEVEL === "debug" ? ["query", "error", "warn"] : ["error"],
  })
}

export const db = globalForPrisma.prisma ?? createPrismaClient()

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = db
}
```

(`server-only` is a Next.js package; drop the import in a plain Node project.)

---

## 5. Environment variables

`DATABASE_URL` / `DATABASE_AUTH_TOKEN` are conventions, not requirements — keep whatever names
`prisma.config.ts` and the client module agree on.

```env
# Local dev (SQLite file)
DATABASE_URL="file:./dev.db"
DATABASE_AUTH_TOKEN=""          # leave empty for local SQLite

# Production (Turso)
# DATABASE_URL="libsql://<db>-<org>.turso.io"
# DATABASE_AUTH_TOKEN="eyJ..."
```

`DATABASE_AUTH_TOKEN` must be an empty string (not omitted) for local SQLite.

---

## 6. Run migrations

```bash
<pm> exec prisma migrate dev    # creates dev.db + applies migrations + regenerates the client
<pm> exec prisma generate       # regenerate the client after a schema-only change
```

From here on, `/prisma:prisma-migrate` covers day-to-day migration work.

---

## Common errors and fixes

| Error | Cause | Fix |
|---|---|---|
| `P1012: datasource.url is not allowed` | `url = env("DATABASE_URL")` still in `schema.prisma` | Remove `url` from the datasource block |
| `The datasource.url property is required` | `prisma.config.ts` missing, inside `prisma/`, or `DATABASE_URL` unset | Move it to the project root; make sure dotenv loads your env file |
| `Cannot find module '@prisma/adapter-libsql'` | Package not installed | `<pm> add @prisma/adapter-libsql@^7` |
| `driverAdapters is not a valid preview feature` | Old `previewFeatures = ["driverAdapters"]` in schema | Remove it — GA in Prisma 7 |

---

## Integrating with libraries that expect a Prisma client

Prisma 7's driver-adapter client is shaped differently from v5/v6 clients. Libraries that
auto-detect the adapter kind by inspecting the object may fall through to the wrong path
(BetterAuth, for instance, ends up in its Kysely path and throws `Failed to initialize
database adapter` at startup). Default to the library's explicit Prisma adapter when it
offers one — e.g. `prismaAdapter(db, { provider: "sqlite" })` from `better-auth/adapters/prisma`.

## Configuration

This skill reads no keys from `.claude/claude-skills.json`; the package manager is detected from the lockfile.

---
To change this skill, do not edit this copy: use `/dev-tools:update-skill`, or see `docs/updating-skills.md` in `mzvonar/claude-skills-public`.
