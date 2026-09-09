# Prisma migrations on Supabase

Read this when `supabase/config.toml` exists. Everything here is Supabase-specific; the general procedure stays in `SKILL.md`.

## Connection URLs

| Env var (convention) | Used by | Purpose |
|---|---|---|
| `DATABASE_URL` | app runtime | Pooled connection through Supavisor/PgBouncer, port **6543**, `?pgbouncer=true&connection_limit=1` |
| `DIRECT_URL` | Prisma CLI (`prisma.config.ts`) | Direct connection, port **5432** — migrations and introspection; DDL does not work through the transaction-mode pooler |

Locally with the Supabase CLI both point at the same database on `127.0.0.1:54322` (no pooler). Production migrations:

```bash
DIRECT_URL="postgresql://postgres.<project-ref>:<password>@<pooler-host>:5432/postgres" <pm> exec prisma migrate deploy
```

Supabase Studio runs its own Next.js server on another local port (54323 by default) and is supervised — never kill it when restarting your dev server.

## RLS migrations must guard `auth.*` behind an `auth`-schema check

`prisma migrate dev` replays the migration history into a temporary shadow DB — a fresh database with **no Supabase `auth` schema**. Any migration that references `auth.jwt()` / `auth.uid()` directly fails the shadow replay with `schema "auth" does not exist`.

The fix is a guard, not a workaround. Wrap every `auth.*`-referencing block in a `DO $$ … $$` guard that checks the **`auth` schema**. The `authenticated` / `anon` roles are cluster-wide and exist even in the shadow DB, so a role-only guard is not enough:

```sql
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated')
     AND EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'auth') THEN
    -- ALTER TABLE … ENABLE ROW LEVEL SECURITY;
    -- CREATE POLICY … USING (auth.uid() = "userId") …
  END IF;
END $$;
```

PL/pgSQL plans the inner statements lazily, so when the guard is false `auth.jwt()` is never resolved: the shadow replay and bare-Postgres test DBs skip the block cleanly, while on real Supabase the policy applies normally. With every `auth.*` block guarded, `migrate dev` works without any shadow-DB workaround.

The same conditional-execute pattern covers `GRANT SELECT … TO authenticated, anon` (guard on `pg_roles`).

## Realtime publication membership

Tables that Supabase Realtime should broadcast need `ALTER PUBLICATION supabase_realtime ADD TABLE …`. Bare-Postgres test DBs have no such publication, so guard it:

```sql
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE "posts";
  END IF;
END $$;
```

Your realtime layer, if any, may have its own template for this; keep the two in sync.

## Legacy fallback — an un-guarded `auth.*` reference already blocks `migrate dev`

Prefer adding the guard in a new forward migration. If you must land a change before that:

```bash
<pm> exec prisma db push                                  # 1. sync the dev schema without the shadow-DB step
# 2. hand-author prisma/migrations/<timestamp>_<name>/migration.sql with the DDL db push just applied
<pm> exec prisma migrate resolve --applied <timestamp>_<name>   # 3. register it, skipping the shadow diff
<pm> exec prisma generate                                 # 4. regenerate the client (see SKILL.md), then restart the dev server
```

`migrate resolve --applied` on the broken migration itself, followed by `migrate deploy` for the new one, is the other shape of the same bypass — with the same obligation to regenerate the client and restart the dev server with its cache cleared.
