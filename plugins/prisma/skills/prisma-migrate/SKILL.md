---
name: prisma-migrate
description: Run Prisma migrations and regenerate the Prisma client safely — preflight (env file, schema location, package manager), `migrate dev` / `migrate deploy` / `generate`, and the recovery procedures for the ways `migrate dev` refuses to run (drift, edited-after-apply checksum drift, shared dev DBs, raw-SQL objects Prisma cannot model, Prisma 7's agent reset guard). Use whenever the user asks to run or create a migration, apply schema changes, regenerate the Prisma client, "update the DB", "apply the schema", "run db:migrate", or when `prisma migrate dev` complains about drift, demands a reset, hangs on a prompt, or a new enum value / model is "undefined" at runtime after a migration.
---

# Prisma Migrate

## Preflight

0. **Is this session reading the CURRENT skill text?**
   ```bash
   bash "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/marketplaces/claude-skills-public/scripts/plugin-freshness.sh"
   ```
   Local, no network, silent when current. **Exit 3** = this session is serving an older cached
   version than the one installed — a session pins its version at the first call to a skill and
   never moves, and nothing else reports it. Put it to the user with `AskUserQuestion`: reload
   (`/reload-plugins`) and re-run, or carry on knowingly. Exit 2 or no such script = undetermined,
   carry on. Why: `docs/conventions.md`.
1. **Package manager** — `pnpm-lock.yaml` → pnpm, `yarn.lock` → yarn, `package-lock.json` → npm, `bun.lockb` → bun. `<pm> exec prisma …` below; prefer the repo's own scripts (`db:migrate`, `db:generate`, …) when `package.json` has them, because they carry the repo's flags and env wiring.
2. **Schema location** — `prisma.config.ts` at the project root if it exists (Prisma 7: connection URL lives there, not in the schema), else `prisma/schema.prisma`. Override with `schemaPath`.
3. **Env file** — `prisma.config.ts` typically loads `envFile` (default `.env.local`) via dotenv before reading the connection URL, so commands need no `DATABASE_URL=…` prefix. Check it exists before any Prisma command:

   ```bash
   ls .env.local
   ```

   If missing, stop and tell the user: "`.env.local` not found. Prisma needs the direct database URL to connect. Create it from `.env.example` (`cp .env.example .env.local`), fill in the values, and retry." In CI and production the file will not exist — that is expected; the URL is injected via the environment (a CI secret, a platform env var). `prisma.config.ts` should load the file with `override: false` so a real env var always wins over the file.
4. **Supabase** — if `supabase/config.toml` exists, read `references/supabase.md` in this skill before touching migrations (shadow-DB guard for `auth.*`, realtime publication guard, pooled vs direct URLs).
5. **Connection URL** — migrations need a **direct** connection. If your provider fronts the DB with a transaction-mode pooler (PgBouncer and the like), DDL does not work through it; the CLI must use the direct URL (commonly `DIRECT_URL`) while the app uses the pooled one (commonly `DATABASE_URL`). Locally the two are usually the same.

## Commands

```bash
<pm> exec prisma migrate dev --name describe-your-change   # dev: generate + apply + regenerate client
<pm> exec prisma generate                                  # regenerate the client after a schema change
<pm> exec prisma migrate deploy                            # CI / production / test DBs: apply pending, never prompts
<pm> exec prisma migrate status                            # applied vs pending (does NOT detect checksum drift)
```

After any `migrate dev` inspect the generated SQL for destructive operations before committing:

```bash
grep -nE 'DROP INDEX|DROP TABLE|DROP COLUMN|DROP CONSTRAINT|ALTER TABLE .* DROP' prisma/migrations/<timestamp>_<name>/migration.sql
```

## Migrations are immutable once applied or committed

Never edit a migration file after it has been applied — not even to add an idempotent index re-assert or a comment. The edit changes the file's checksum, which desyncs every long-lived dev DB's `_prisma_migrations` row and makes the next `migrate dev` demand a destructive reset. `migrate status` does not catch this; only `migrate dev`'s checksum check does, so the drift is invisible until someone is blocked. Corrections go in a **new** forward migration.

## `migrate reset` is off by default for agents

`prisma migrate reset` wipes the dev database. Prisma 7 already gates it for AI agents behind `PRISMA_USER_CONSENT_FOR_DANGEROUS_AI_ACTION`; this skill keeps it off unless `allowReset` is true, because a dev DB is often shared with other sessions or carries seed state that took time to build, and every situation that makes `migrate dev` ask for a reset has a non-destructive path below. A reset it demands is a question for the user, never a default.

## Drift recovery when `migrate dev` refuses to run

**Stop signals — switch to the procedure, do not loop:**

- `prisma migrate dev` exits with code **130** (SIGINT — the CLI is waiting on an interactive prompt a non-TTY shell cannot answer).
- The CLI prints "Drift detected" / "We need to reset" / "Are you sure you want to create and apply…" and hangs.
- `--skip-seed` returns "unknown or unexpected option" (you are guessing flags).
- Piping `echo y` / `printf "y\n"` into it still exits 130.

The prompt is destructive (it offers to reset), so retrying with more pipe variants only burns round-trips. `migrate dev` validates the **entire** history before applying, so unrelated historical drift blocks a brand-new change.

**Shared dev DB — probe `migrate deploy` first.** `migrate dev` can demand a reset over an *unrelated* migration's checksum drift while `migrate deploy` applies the actually-pending migration non-destructively. On any DB other sessions share: run `migrate deploy`, then `generate`. Reach for `migrate dev` only when you truly need a *new* migration generated.

**When you need a new migration and `migrate dev` is blocked:**

1. `<pm> exec prisma db push` — sync the dev DB to the schema without touching migration history.
2. Hand-author `prisma/migrations/<timestamp>_<name>/migration.sql` with the full statement set (including any raw-SQL objects from `unmanagedSql`, see below).
3. `<pm> exec prisma migrate resolve --applied <timestamp>_<name>` — register it as applied without running it.
4. `<pm> exec prisma migrate deploy` against the test DB, which has no drift and applies it cleanly.

For a **purely additive** change (`ADD COLUMN`, `ALTER TYPE … ADD VALUE`) skip `db push`: hand-write the SQL, apply it with `<pm> exec prisma db execute --file <migration.sql>` (use the env file: `<pm> exec dotenv -e .env.local -- prisma db execute …` or equivalent), then `migrate resolve --applied`.

Verify both stacks afterwards: `<pm> exec prisma db pull --print` against each DB, diff against the schema, fix every difference before continuing.

**Checksum drift that is permanent** (a file was edited after apply, and you will not rewrite history): hand-write the migration folder and apply with `migrate deploy`, which does not run the modified-checksum check. Then run `generate` **and** re-provision the test DB, or integration tests never learn the new shape.

Two traps when probing which DB a command hits:

- `dotenv -e .env.test -- prisma migrate deploy` can still hit the **dev** database when another env file wins the injection. **Read the datasource line the command prints** before believing which DB you are on.
- A probe migration leaves a `_prisma_migrations` row whose folder no longer exists; every later `prisma migrate` then reports drift. Clean up both the folder and the row.

`CREATE INDEX CONCURRENTLY` does apply under `migrate deploy` on Postgres (Prisma does not wrap migrations in a transaction there). Reach for it on the first index added after a table is large and live; skip it pre-launch, because it can leave an `INVALID` index behind.

## After `migrate resolve --applied`: regenerate the client and restart the dev server

`resolve --applied` and `migrate deploy` do **not** regenerate the client. The DB is updated but `@prisma/client` still reflects the schema before the new model/column; runtime throws `Cannot read properties of undefined (reading 'findFirst')` (or `.create`, `.update`) at the first call site. In the same commit:

```bash
<pm> exec prisma generate
```

then restart the dev server with its build cache cleared (`/next-js:clean-dev` if you use Next.js). Without the cache clear the dev server hot-reloads the new client into new chunks while chunks that already imported the old client keep the stale module instance: typecheck passes, runtime still throws "undefined".

## Enum-adding migrations (`ALTER TYPE … ADD VALUE`) need a dev-server restart

The new value is baked into the generated client's enum validation, not just the DB. A dev server that was already running keeps the old client in memory (a `node_modules` import loaded once at process start; app code hot-reloads, the client does not) and rejects the value client-side:

```
PrismaClientValidationError: Invalid value for argument `type`. Expected <Enum>.
```

even though the schema, the regenerated client on disk and the DB all have it (`grep -rl NEWVALUE node_modules/.prisma/client/`, `SELECT … FROM pg_enum`). Fix: `generate`, then a clean dev-server restart. CI and production build fresh, so only long-running local dev servers hit this.

## Raw-SQL objects Prisma cannot model get a generated `DROP` — delete it, never re-create after it

Vector indexes (HNSW/IVFFlat — `@@index(type:)` supports only BTree/Hash/Gin/Gist/SpGist/Brin, no storage parameters, no operator classes), extensions, triggers, views and functions live in raw SQL because the schema language cannot express them. Prisma's diff treats them as drift and emits `DROP INDEX` / `DROP …` in the migration it generates. The drop is silent — tests still pass, since a missing vector index is a perf regression and not a correctness failure — so it reaches review unless caught at the SQL-inspection step. Customizing the migration IS Prisma's documented answer for unsupported features; the question is only *how* you customize it.

**It is not every migration — only the ones that touch the owning table.** Measured on one repo with two unmanaged hnsw indexes across 108 migrations: **6** carried the generated `DROP`, while **36** carried a re-assert block someone had added defensively, and four of the six real drops carried no re-assert at all. The ritual was being applied roughly six times more often than needed, and was absent where it actually mattered. Inspect the generated SQL; do not pre-emptively decorate every migration.

**Two things are NOT in this category, and treating them as if they were is the common error:**

- **Partial indexes are DECLARATIVE now.** Prisma 7 supports `where:` on `@@index`, `@@unique` and `@unique` (`partialIndexes` preview), and the docs say it outright: *"You no longer need to customize migrations for partial indexes."* An `unmanagedSql` entry for one the schema now declares is stale — remove it, or every migration re-asserts an index Prisma already owns.
- **CHECK constraints are the opposite case.** PSL cannot express them at all, so Prisma's differ does not model them and never proposes dropping one. Add via a customized migration and then leave it alone: no `unmanagedSql` entry, no re-assert, no verification-gate line. Same repo, same 108 migrations: 3 CHECK constraints added by hand, **0** ever dropped, all 3 still live.

List the genuinely unmanaged ones in `unmanagedSql` (name + `CREATE … IF NOT EXISTS` statement) and treat them as one set:

1. After `migrate dev`, grep the generated SQL for `DROP INDEX` **generally** — not only for your index names.
2. **DELETE the generated `DROP` lines. Never let a drop stand and re-create the object after it.** Both end with the index present, so the difference is invisible in review and decisive in production: re-creating is a full, non-concurrent index build holding a write lock on the table for the length of the deploy, and vector indexes sit on the biggest tables you have. Deleting the statement costs nothing. Keeping the `unmanagedSql` re-assert as replay protection is fine — with the drops gone it is an `IF NOT EXISTS` no-op — but it is the deletion that does the work.
3. If `migrate dev` already executed the drop on the dev DB, re-create the objects by hand.
4. If it also half-applied the migration (so its `_prisma_migrations` checksum is now stale against your hand-edited SQL): delete that migration's `_prisma_migrations` row, drop whatever the migration created, then `migrate deploy` to re-apply the corrected file from scratch with a matching checksum.

Verification gate for every new migration on a branch:

```bash
base=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|origin/||'); base=${base:-main}
for m in $(git diff "$base"...HEAD --name-only --diff-filter=A | grep '^prisma/migrations/.*/migration\.sql$'); do
  for name in <each unmanagedSql.name>; do
    grep -q "DROP INDEX.*\"$name\"" "$m" && { echo "generated DROP for unmanaged $name left in $m — delete the line"; exit 1; }
  done
  # Any OTHER index drop may well be intentional; surface it for a human rather than failing.
  grep -q 'DROP INDEX' "$m" && echo "note: $m drops an index — confirm it is deliberate"
done
```

The gate asserts the **absence of the drop**, not the presence of a re-assert. An earlier version required every `unmanagedSql` name to appear in every new migration, and that is precisely what produced 36 no-op re-assert blocks against 6 real drops in the repo this was measured on: a gate that cannot be satisfied except by decorating, so everyone decorated. The object surviving is the invariant; a re-assert is one way to get there and the expensive one.

Back it with an integration test that queries `pg_indexes` / `pg_extension` after `migrate deploy` and asserts each object exists — the structural fix that survives author oversight. The test DB self-heals on the next re-provision; the dev DB needs manual repair after a drop.

## Adding a Postgres extension — audit both stacks

The dev stack and the test stack usually run different Postgres images. The dev image may ship the extension out of the box while the test image does not: the migration applies cleanly on dev and fails on test with "extension X is not available" during container boot. Before merging an `enable_<extension>` migration, check both:

```bash
docker compose ps --format '{{.Name}}'      # find the dev and test DB container names
docker exec <db-container> psql -U postgres -c "SELECT name FROM pg_available_extensions WHERE name = '<ext>';"
```

If the test image lacks it, switch to a variant that includes it (e.g. `pgvector/pgvector:pg17`) and pin the tag — do not float to `<major>-latest`. Note the image choice in the commit message so the dev/test pairing is greppable.

## Reverting a migration — audit the schema afterwards

When a migration is undone by a follow-up migration (rather than deleted before commit), the schema file and the live DB can silently diverge: the revert drops indexes/constraints from the DB, but the schema may still lack the declarations the original assumed. Reconcile by hand — `<pm> exec prisma db pull --print > /tmp/from-db.prisma; diff prisma/schema.prisma /tmp/from-db.prisma` — and resolve every difference now; by the time `migrate dev` notices, the drift is on the base branch.

## A migration a later change will read must update the validation schema in the same change

When a migration adds a column or changes nullability that a *future* feature will read, update the domain validation schema (Zod or equivalent) and extend the DB↔schema parity test to cover field presence and nullability — not only enum membership — in the same change. A DB-only migration with no consumer leaves the domain type lagging silently: the row-to-domain mapper throws the first time a later feature surfaces such a row, and that feature inherits it as a blocking prerequisite. If the domain update truly cannot land now, file an explicit catch-up task.

## Configuration

Optional, in `.claude/claude-skills.json`:

```json
{
  "prisma-migrate": {
    "allowReset": false,
    "envFile": ".env.local",
    "schemaPath": "prisma/schema.prisma",
    "unmanagedSql": [
      { "name": "posts_embedding_idx", "sql": "CREATE INDEX IF NOT EXISTS \"posts_embedding_idx\" ON \"posts\" USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);" },
      { "name": "posts_slug_not_deleted_key", "sql": "CREATE UNIQUE INDEX IF NOT EXISTS \"posts_slug_not_deleted_key\" ON \"posts\"(\"slug\") WHERE \"deletedAt\" IS NULL;" }
    ]
  }
}
```

| Key | Default | Meaning |
|---|---|---|
| `allowReset` | `false` | Whether the agent may run `prisma migrate reset`. Off because it wipes a DB that is often shared or hand-seeded, and every blocker has a non-destructive path above. |
| `unmanagedSql` | `[]` | Raw-SQL objects Prisma cannot model, as `{ name, sql }`. The verification gate fails a migration that still carries a generated `DROP` for one. Do NOT list partial indexes (declarative since Prisma 7) or CHECK constraints (never dropped). |
| `envFile` | `.env.local` | File the preflight checks for and that `prisma.config.ts` loads. |
| `schemaPath` | auto: `prisma.config.ts`, else `prisma/schema.prisma` | Where the schema lives when detection is wrong. |

---
To change this skill, do not edit this copy: use `/dev-tools:update-skill`, or see `docs/updating-skills.md` in `mzvonar/claude-skills-public`.
