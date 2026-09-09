# Migration traps

Three defects that were live in this migrator, found against one real 3,622-line corpus. Each is a
silent corruption: the migration completes, the counts look plausible, and items are misfiled.

They are recorded because they are properties of *hand-written markdown ledgers in general*, not of
one repo's file. Anyone adopting this format will meet them.

**Catch them the same way they were caught: cross-check the migrator's status count against an
independent count of the source, and refuse a near-match.** The sequence on that corpus was
11 → 42 → 39 → 40, with 40 the independently verified answer. Every intermediate number looked
reasonable.

---

## 1. The status marker is written many ways

Expected `**DONE (2026-08-04)**`. Actually present, all in one file:

| form | note |
|---|---|
| `**DONE (2026-08-04)**` | the documented one |
| `**✅ DONE (2026-08-04, item-35)**` | emoji prefix, second field inside the parens |
| `**DONE upstream (2026-08-31, …)**` | a word between the marker and the paren |
| `**KILLED (2026-08-04, item-35 …)**` | |
| `- ~~struck through~~` | no marker at all |

And two shapes that must **not** match:

- `HALF DONE (2026-07-20)` — a progress note, not a status.
- ``mark it `**DONE (YYYY-MM-DD)**` `` — prose *documenting the convention*. A ledger that explains
  its own format contains its own format.

A strict pattern found 10 of 40. A loose one found 48, including both false positives.

## 2. A character window reaches into sub-bullets

Scoping the status search to "the first 200 characters of the item" pulls in nested bullets when the
headline is short — so an item whose **child** was marked killed inherits the child's status.
Misfiled 2 of 42.

Scope to the item's **own bullet line**. Sub-bullets are context for the parent, never a status.

## 3. The status parenthetical wraps onto the next line

Having scoped to line 1, this one appears:

```markdown
- **DONE (2026-08-31, chore/some-branch-abc1234 — a deliberate pipeline-shape change, which is this
  very thing) …
```

The closing `)` is two lines down. A pattern requiring it on line 1 silently drops the item —
line-spanning data under a per-line pattern. Make the closing paren optional and take the date.

---

## The general rule

All three are the same mistake at different scales: **anchoring on the layout the author imagined
rather than the layout the corpus contains.** A hand-maintained ledger accretes formatting over
years and nothing ever validated it, because until now nothing read it mechanically.

So: parse loosely, restrict scope deliberately, and **report what was inferred instead of deciding
silently**. `migrate.py` prints an ambiguous count for exactly this reason — those are the entries a
person should read before the migration is committed.
