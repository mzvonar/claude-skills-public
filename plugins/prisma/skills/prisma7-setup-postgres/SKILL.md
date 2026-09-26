---
name: prisma7-setup-postgres
disable-model-invocation: true
user-invocable: true
description: Bootstrap a new Next.js / Node.js project with Prisma v7 on PostgreSQL using the `@prisma/adapter-pg` driver adapter — packages, `schema.prisma` without `url`, `prisma.config.ts` at the root, the client module, per-provider env vars (`/prisma:prisma7-setup-postgres supabase|neon|rds|local`), first migration, and the errors a fresh install hits. Invoke ONLY when explicitly bootstrapping or setting up Prisma from scratch — not for general Prisma edits in an existing project. Trigger phrases: "bootstrap a new project with Prisma and Postgres", "set up Prisma 7 with Postgres from scratch", "new Next.js project needs Prisma 7 + pg", "Prisma 7 on Supabase/Neon/RDS", or when a fresh install hits P1012 / "datasource.url is required" / "Cannot find module @prisma/adapter-pg". If Prisma is already configured and working, DO NOT fire — that is ordinary schema / migrate / client work (`/prisma:prisma-migrate`).
---

# Prisma 7 Setup — PostgreSQL with the pg Driver Adapter

Prisma 7 removes the connection string from `schema.prisma` and moves connection
config into a dedicated `prisma.config.ts` at the **project root** (not inside
`prisma/`). `@prisma/adapter-pg` connects through the `pg` driver.

**Provider argument:** `/prisma:prisma7-setup-postgres supabase|neon|rds|local`. Without one,
pick `supabase` if `supabase/config.toml` exists, otherwise ask. It only changes §5 (env vars).

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
<pm> add @prisma/client@^7 @prisma/adapter-pg@^7 pg
<pm> add -D prisma@^7 @types/pg dotenv
```

---

## 2. `prisma/schema.prisma` — remove the `url` field

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  // do NOT add url here — it belongs in prisma.config.ts
}
```

Also remove `previewFeatures = ["driverAdapters"]` if present — driver adapters are GA in v7.

---

## 3. `prisma.config.ts` — at the project root (NOT inside `prisma/`)

**CRITICAL:** Prisma CLI only looks for this file at the project root.

```ts
import path from "node:path"
import { config } from "dotenv"
import { defineConfig } from "prisma/config"

// Prisma CLI runs outside your framework and does not load .env.local by itself.
// .env.local does not exist in CI/production — loading it is a safe no-op there.
// override: false keeps a real env var (CI, production) ahead of the file.
config({ path: ".env.local", override: false })

export default defineConfig({
  schema: path.join(__dirname, "prisma", "schema.prisma"),
  datasource: {
    url: process.env.DIRECT_URL!,
  },
})
```

### Two URLs: pooled for the app, direct for the CLI

`DATABASE_URL` and `DIRECT_URL` are **conventions**, not names Prisma requires — keep whatever
`prisma.config.ts` and the client module agree on. The split matters whenever the provider
fronts the database with a transaction-mode pooler (PgBouncer / Supavisor / Neon's pooler):

| Env var | Used by | Purpose |
|---|---|---|
| `DATABASE_URL` | client module (runtime) | App queries, through the pooler |
| `DIRECT_URL` | `prisma.config.ts` (CLI) | Migrations and introspection — DDL and prepared statements do not work through a transaction-mode pooler |

With no pooler (`local`, plain RDS) both are the same URL; keep both names anyway so adding a
pooler later is an env change, not a code change.

---

## 4. Client module (e.g. `src/lib/prisma.ts`) — instantiate PrismaClient with the adapter

```ts
import "server-only"

import { PrismaPg } from "@prisma/adapter-pg"
import { PrismaClient } from "@prisma/client"
import { Pool } from "pg"

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient | undefined }

function createPrismaClient() {
  const pool = new Pool({ connectionString: process.env.DATABASE_URL })
  const adapter = new PrismaPg(pool)
  return new PrismaClient({ adapter })
}

export const prisma = globalForPrisma.prisma ?? createPrismaClient()

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = prisma
}
```

(`server-only` is a Next.js package; drop the import in a plain Node project. If the repo has a
validated env module, read `DATABASE_URL` from it instead of `process.env`.)

---

## 5. Environment variables — by provider

### `supabase`

```env
# Local dev (Supabase CLI — one database, no pooler)
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
DIRECT_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres

# Cloud — pooled (6543) for the app, direct (5432) for the CLI
# DATABASE_URL=postgresql://postgres.<project-ref>:<password>@<pooler-host>:6543/postgres?pgbouncer=true&connection_limit=1
# DIRECT_URL=postgresql://postgres.<project-ref>:<password>@<pooler-host>:5432/postgres
```

Both hosts are shown in the Supabase dashboard under Connect. Migrations on Supabase have extra
rules (shadow DB vs `auth.*`, realtime publication) — `/prisma:prisma-migrate` covers them.

### `neon`

```env
# Pooled endpoint has a "-pooler" suffix in the host; the direct endpoint does not
DATABASE_URL=postgresql://<user>:<password>@<endpoint>-pooler.<region>.aws.neon.tech/<db>?sslmode=require
DIRECT_URL=postgresql://<user>:<password>@<endpoint>.<region>.aws.neon.tech/<db>?sslmode=require
```

Branch databases get their own endpoint pair; keep the pair together per environment.

### `rds`

```env
# No pooler: same URL twice. With RDS Proxy, point DATABASE_URL at the proxy and DIRECT_URL at the instance.
DATABASE_URL=postgresql://<user>:<password>@<instance>.<region>.rds.amazonaws.com:5432/<db>?sslmode=require
DIRECT_URL=postgresql://<user>:<password>@<instance>.<region>.rds.amazonaws.com:5432/<db>?sslmode=require
```

### `local`

```env
# Docker / Homebrew Postgres — same URL twice
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/<db>
DIRECT_URL=postgresql://postgres:postgres@localhost:5432/<db>
```

---

## 6. Run migrations

```bash
<pm> exec prisma migrate dev --name init   # creates + applies the first migration, regenerates the client
<pm> exec prisma generate                  # regenerate the client after a schema-only change
```

From here on, `/prisma:prisma-migrate` covers day-to-day migration work.

---

## Common errors and fixes

| Error | Cause | Fix |
|---|---|---|
| `The datasource.url property is required` | `prisma.config.ts` missing, inside `prisma/`, or `DIRECT_URL` unset | Move it to the project root; create the env file; make sure dotenv loads it |
| `P1012: datasource.url is not allowed` | `url = env("...")` still in `schema.prisma` | Remove `url` from the datasource block |
| `Cannot find module '@prisma/adapter-pg'` | Package not installed | `<pm> add @prisma/adapter-pg@^7` |
| `driverAdapters is not a valid preview feature` | Old `previewFeatures` in schema | Remove it — GA in Prisma 7 |
| `prepared statement already exists` | Pooled URL used for migrations | Point `prisma.config.ts` at the direct URL |
| `BetterAuthError: Failed to initialize database adapter` | Raw `prisma` client passed to `betterAuth({ database })` — auto-detection falls through to Kysely on Prisma 7's driver-adapter shape | `database: prismaAdapter(prisma, { provider: "postgresql" })` from `better-auth/adapters/prisma` |

---

## Integrating with libraries that expect a Prisma client

Prisma 7's driver-adapter client (`new PrismaClient({ adapter })`) is shaped differently from
v5/v6 clients. Libraries that auto-detect the adapter kind by inspecting the object may fall
through to the wrong path. BetterAuth is the canonical example — `database: prisma` appears to
work until startup, then throws from its Kysely code path:

```ts
import { betterAuth } from "better-auth"
import { prismaAdapter } from "better-auth/adapters/prisma"
import { prisma } from "./prisma"

export const auth = betterAuth({
  database: prismaAdapter(prisma, { provider: "postgresql" }),
  // ...
})
```

For any other library, default to its explicit Prisma adapter when it offers one rather than
relying on auto-detection.

## Configuration

This skill reads no keys from `.claude/claude-skills.json`; the provider comes from the argument (or `supabase/config.toml` detection) and the package manager from the lockfile.

---
To change this skill, do not edit this copy: use `/dev-tools:update-skill`, or see `docs/updating-skills.md` in `mzvonar/claude-skills-public`.
