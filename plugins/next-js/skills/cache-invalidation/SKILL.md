---
name: cache-invalidation
description: Next.js cache invalidation discipline for `"use cache"` reads — `cacheTag` / `cacheLife` on the read side; `updateTag` (Server Actions), `revalidateTag(tag, { expire: 0 })` (Route Handlers) and `revalidateTag(tag, "max")` (stale-while-revalidate, background workers) on the write side; the Data Cache vs Router Cache split and when to call `refresh()` from `next/cache`. Use whenever writing a cached repository read, a mutation that must invalidate cache, a Server Action that returns to the same page instead of redirecting, or when debugging "I saved but the page didn't update" and flaky e2e tests that see stale data. Triggers on "cache", "use cache", "cacheTag", "cacheLife", "updateTag", "revalidateTag", "revalidatePath", "refresh from next/cache", "stale after save", "cache tags", "cache invalidation".
---

# Cache invalidation

## Requires

- Next.js 16, or a 15 canary with `dynamicIO` enabled (renamed `cacheComponents` in 16) in `next.config.*`.
- The `"use cache"` directive and `cacheTag`, `cacheLife`, `updateTag`, `revalidateTag`, `refresh` from `next/cache`. Older versions only have `revalidateTag(tag)` / `revalidatePath` — this skill does not apply to them.

One-line check:

```bash
node -p "require('next/package.json').version"; grep -nE 'cacheComponents|dynamicIO' next.config.*
```

## The pattern in one sentence

Cached reads tag themselves. Mutations return the tags they dirtied. The boundary that ran the mutation — Server Action, Route Handler or background worker — picks one of three invalidation calls based on its execution context. Nobody else touches cache.

## Layering

- **Tag definitions** live next to the queries they describe, as pure functions, one module per entity. Reads, mutations and boundaries import the same functions — never hand-write a tag string.
- **Reads** carry `"use cache"` + `cacheTag(...)` + `cacheLife(...)`.
- **Mutations** (services / use cases) return `{ data, cacheTags: string[] }` and never call `updateTag` / `revalidateTag` / `revalidatePath` themselves.
- **Boundaries** — Server Actions, Route Handlers, workers — are the only place invalidation happens, through three thin wrappers (below).

```ts
// tags for the `post` entity — one module, imported by reads and writes alike
export const postTags = {
  all: "posts",
  byTeam: (teamId: string) => `posts:team:${teamId}`,
  byId: (postId: string) => `post:${postId}`,
}
```

**Tag-shape changes are breaking changes — grep tests, not just production code.** When the shape of a tag function changes (`` `post:${id}` `` → `` `post:by-id:${id}` ``), production code follows transparently, but every test that asserts on the literal string — `expect(cacheTags).toEqual(expect.arrayContaining([stringContaining("post:")]))`, hardcoded comments documenting the old format — silently misses the new prefix. Before merging: `rg -l "post:"` across the feature (tests included) and update every assertion and comment in the same change. A tag refactor that compiles can still be broken at the test layer.

## Reads — tag them, or the writer is a silent no-op

**Cache invalidation is a closed loop — the writer side does nothing without a matching tagged read.** Tag definitions + returning `cacheTags` + calling a wrapper is dead infrastructure unless the corresponding read carries `"use cache"` + `cacheTag(<sameTag>)`. An untagged read is never in the cache keyed by that tag, so the invalidation matches nothing — a silent no-op that looks complete because all the write-side ceremony is present. When you add invalidation for a tag, grep for the read that produces the data and confirm it is `"use cache"`-tagged with the same tag; if no such read exists, either the invalidation is pointless or the read needs tagging.

Tag every cached read with all applicable tags (scoped and general), so invalidating either one clears it:

```ts
export async function findPostsByTeam(teamId: string) {
  "use cache"
  cacheTag(postTags.all, postTags.byTeam(teamId))
  cacheLife("minutes")

  const rows = await db.post.findMany({ where: { teamId } })
  return rows.map(toDomain)
}
```

### Choosing `cacheLife` — by mutation cadence, not by invalidation worry

With correct invalidation in the boundary, `cacheLife` is a pure performance/freshness knob, not a workaround for stale-after-write. Pick the longest profile that is safe given how often the data actually changes:

| Profile | Use when |
|---|---|
| `cacheLife("seconds")` | Token-based / write-adjacent reads where the next read is moments after a mutation and the boundary's invalidation must already have landed (an invite-token lookup inside an accept flow). |
| `cacheLife("minutes")` | Mutation-heavy entities — a `post` while it is being edited, list reads users navigate to right after saving. |
| `cacheLife("hours")` | Layout-level reads — team name, membership, role lookups. Rarely change; many requests reuse them. **Default for repository reads.** |
| `cacheLife("days")` / longer | Static-ish reference data with an externally imposed update cadence. Justify in a comment. |

**Don't reach for `"seconds"` defensively.** If a freshly mutated entity is not visible after a Server Action, the bug is almost certainly the boundary using the stale-while-revalidate wrapper instead of the blocking one — not `cacheLife`. `"seconds"` masks that bug by making the cache a near-bypass, paying steady-state DB load on every render to compensate for a one-line invalidation fix.

### Tag granularity must match query selectivity

Choose the tag at the same time as the query shape, not afterwards:

- **Selective query → selective tag.** A `findCommentsByPostIds(teamId, postIds)` read subscribes to `commentTags.byTeam(teamId)` — not the broad `postTags.byTeam(teamId)` that every unrelated post mutation busts.
- **In-service filtering means the tag is already too broad.** If the service pulls all rows and filters to a subset, the repository should pull only the subset, with a tag that matches.

Pair "new query" with "tag granularity decision" in the same change.

### Time-dependent reads are uncacheable

A read whose filter references the current time (`snoozedUntil <= now()`, `expiresAt > now()`, "due today") must not be cached: time advances without any mutation firing, so a cached result keeps serving stale rows (an expired snooze stays hidden) until an unrelated invalidation happens to bust the tag. Leave that read uncached; mutations on the table still return their tags as usual because other reads on the same table may be cached.

## Mutations — return tags, never invalidate

```ts
return {
  data: post,
  cacheTags: [postTags.byId(post.id), postTags.byTeam(post.teamId), postTags.all],
}
```

Return every tag that could match a cached read — over-invalidate rather than leave stale data.

## Boundaries — two modes, three APIs, three wrappers

Next.js has **two** invalidation modes and exposes them through different APIs depending on the caller:

| API | Caller context | Semantics |
|---|---|---|
| `updateTag(tag)` | Server Actions only | **Blocking** — entry expires immediately; the next read is a cache miss + fresh fetch (read-your-own-writes). |
| `revalidateTag(tag, { expire: 0 })` | Route Handlers | **Blocking** equivalent where `updateTag` is not allowed. |
| `revalidateTag(tag, "max")` | Anywhere | **Stale-while-revalidate** — the next read serves the stale value; the refresh runs in the background. |

**`revalidateTag(tag, "max")` is not eager invalidation.** The name suggests "invalidate now"; the documented behaviour is SWR. Used where read-your-own-writes is expected, it produces a one-render staleness gap that surfaces as flaky e2e tests and "I saved but it didn't update" reports.

Keep the three modes behind three thin wrappers in one module (`wrappersPath` in config, default `lib/cache.ts`). Names are yours; what matters is that each wrapper is bound to exactly one mode:

```ts
import { revalidateTag, updateTag } from "next/cache"

/** Server Actions — blocking, read-your-own-writes. */
export function updateCacheTags(tags: string[]) {
  for (const tag of tags) updateTag(tag)
}

/** Route Handlers — blocking; `updateTag` is not allowed there. */
export function expireCacheTags(tags: string[]) {
  for (const tag of tags) revalidateTag(tag, { expire: 0 })
}

/** Background workers — stale-while-revalidate. */
export function revalidateCacheTags(tags: string[]) {
  for (const tag of tags) revalidateTag(tag, "max")
}
```

### Which wrapper — by caller context

| Caller | Wrapper | Why |
|---|---|---|
| Server Action (`"use server"` file) | blocking, `updateTag` | The user is about to read what they just wrote. |
| Route Handler whose mutation the next render must see | blocking, `revalidateTag(tag, { expire: 0 })` | Same effect; `updateTag` is Server-Action-only. |
| Background worker (queue / cron / Inngest) or post-job cleanup | SWR, `revalidateTag(tag, "max")` | Nobody is waiting on the read; eventual consistency is correct and does not block the next render. |
| Test-seed endpoint, if you have one | blocking | Tests navigate immediately after seeding. |

### Server Action example

```ts
"use server"
import { refresh } from "next/cache"
import { updateCacheTags } from "@/lib/cache" // wrappersPath

export async function renamePost(input: RenamePostInput) {
  const result = await renamePostAsUser(await currentUserId(), input)

  updateCacheTags(result.cacheTags)
  refresh()

  return { postId: result.data.id }
}
```

### Background worker example

```ts
import { revalidateCacheTags } from "@/lib/cache" // wrappersPath

const result = await classifyPost(...)

if (result.cacheTags.length > 0) {
  revalidateCacheTags(result.cacheTags)
}
```

### A state transition and its inverse must both revalidate

When you ship a transition and its reverse (archive/unarchive, pin/unpin, resolve/reopen), the read-your-own-writes invalidation must be present on both paths. The two halves are typically built in different components or at different times and drift; the gap is invisible until someone exercises the neglected direction in place without a reload — and an e2e test that reloads before asserting will not catch it. Before hand-off, grep the sibling action/component for the invalidation call.

## Data Cache vs Router Cache — `refresh()` when the user stays on the page

The wrappers above touch the **Data Cache** (server-side). They do not invalidate the **Router Cache** (the browser's RSC payload for the current route). If the user stays on the same page after a mutation, the browser keeps rendering the stale payload — the page looks frozen even though the server data is fresh.

| Function | Data Cache | Router Cache |
|---|---|---|
| the three wrappers | invalidated | untouched |
| `revalidatePath` | invalidated | invalidated |
| `refresh()` from `next/cache` | untouched | refreshed |

**Decision rule:**
- Action ends with `redirect(...)` → no `refresh()` — the destination fetches its own fresh data on navigation.
- Action `return`s and the caller stays on the page (inline success message, button that stays put) → call `refresh()` right after the blocking wrapper.

Don't reach for `router.replace(pathname)` or `router.refresh()` from the Client Component as a workaround: it splits the invalidation logic across server and client, and `refresh()` from `next/cache` is the native Server Action primitive for exactly this case.

## Why three wrappers instead of one

A common failure mode is a single helper that calls `revalidateTag(tag, "max")` everywhere. Every Server Action's "saved!" toast is then followed by one render of stale data. In production the refetch is usually faster than the user, so it hides; in e2e tests, which navigate immediately, it shows up as flaky failures. The fix maps the two real modes (blocking, SWR) onto three wrappers because blocking has different APIs in Server Actions and Route Handlers, and background workers legitimately want SWR.

## Configuration

Optional, in `.claude/claude-skills.json`:

```json
{ "cache-invalidation": { "wrappersPath": "lib/cache.ts" } }
```

| Key | Default | Meaning |
|---|---|---|
| `wrappersPath` | `lib/cache.ts` (a suggestion — if absent, grep for `updateTag(` to find the real module) | Module holding the three wrappers around `updateTag` / `revalidateTag(expire: 0)` / `revalidateTag("max")`. |

---
To change this skill, do not edit this copy: use `/dev-tools:update-skill`, or see `docs/updating-skills.md` in `mzvonar/claude-skills-public`.
