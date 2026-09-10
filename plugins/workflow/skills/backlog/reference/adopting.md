# Adopting the format in a repo

Written after doing it once, on one 3,622-line / 251-item ledger; every number below is from that single corpus. Everything below that reads like
excessive caution is there because skipping it cost a round.

The shape of the job: **migrate into a scratch directory, prove nothing was lost, resolve by hand
what the migrator refuses to decide, then move it into place.** Never migrate in place — the source
is the only copy of the thing you are checking against.

---

## The order

```bash
LEDGER=path/to/old-ledger.md          # the monolith you are migrating away from
OUT=$(mktemp -d)

# 0. DERIVE YOUR LEDGER'S CLOSED VOCABULARY. Do not trust the ledger's own header — the first
#    corpus documented two words and used six, and the four it never mentioned cost seven items.
grep -oE '\*\*[^*]{0,4}[A-Z]{4,}' "$LEDGER" | grep -oE '[A-Z]{4,}' | sort | uniq -c | sort -rn

python3 scripts/migrate.py "$LEDGER" "$OUT"              # 1. migrate to scratch  (index.md + index/)
node scripts/verify-migration.mjs "$LEDGER" "$OUT"       # 2. nothing lost, extractions agree
node scripts/validate.mjs "$OUT/index.md"                # 3. structure, pointers, policy
```

If a generator appends to the ledger by its existing name, keep that name: pass
`--index-name <name>.md` to both `migrate.py` and `verify-migration.mjs` and validate that file.
The configured `indexPath` (see SKILL.md → Configuration) is where the result ends up.

Step 0 takes a second and is the one this page most wishes it had had. Read the list: anything that
retires an item and is not in `CLOSED_WORDS` (`migrate.py`) belongs there, and in the `CLOSED`
regex that `backlog.mjs`, `validate.mjs` and `verify-migration.mjs` each carry. Step 2 also prints
marker-shaped words it does not recognise, so it catches what step 0 missed — but only as a notice
a person reads, because no comparison can find a word both sides are missing.

Step 2 is the gate. It exits non-zero if any source content is unaccounted for or if a second
extractor disagrees about which items are closed, and **both of those happened on the first real
adoption** — see `migration-traps.md`. Do not move anything into place while it is red.

Then resolve what step 1 reported (below), move the output into place at `indexPath`, and repoint
whatever used to read the monolith.

---

## What `migrate.py` reports, and what to do about each

It prints counts rather than deciding. Each line is a task.

### `open with NO trigger: N`

Expected, and large on first adoption — **97 of 194** on the real corpus. The monolith hid them;
the `deferred-work` policy surfaces them because an item with no trigger cannot be classified into
any bucket. It is not "keep-deferred", it is **untriaged**.

**Do not invent triggers to clear the number.** A guessed trigger is worse than a missing one: it
reads as a decision someone made. Give them triggers incrementally, a few per grooming pass, when
the surrounding work makes the real trigger obvious. Adoption is not the moment to triage 97 items.

### `sections with NO bullet items: N`

A `## ` section holding prose but no top-level bullet — on the real corpus, a `### ` heading with
**Trigger / What / Why / Owner** paragraphs, which is an item by every meaning except this
migrator's. Its content is kept in the index so nothing is lost, but it is **invisible to
`backlog.mjs`**, which reads detail frontmatter.

Promote each one by hand into a proper detail file, then replace the section's prose in the index
with the item's entry. Notably the one found was the *newest* entry in the ledger — the shape a
ledger drifts toward is the shape the migrator is least likely to model.

### `open items under a RETIRED/DONE section heading: N`

The section heading carries a status its items do not. **The migrator reports these and never
applies them**, deliberately: a retired section usually means its items are done, but a DONE
section can hold one live item and only a person can tell which.

Read the section's banner and decide per item. On the real corpus there was one, under a heading
reading *"all five seams are closed … do not action"* — it had migrated as live work, which is
exactly what that banner existed to prevent. Write the `status` in the vocabulary the readers share
(`CLOSED` in `backlog.mjs` / `validate.mjs` / `verify-migration.mjs`) — a word outside it reads as
open however final it sounds, which is trap 8 in miniature.

### `status inferred/ambiguous: N`

Two shapes, both recorded as `<WORD> (date unknown)` and both worth a minute: a struck-through item,
and a closure whose parenthetical is not a date or is absent (`**SUPERSEDED the same day — FIXED
upstream at 2c8bf973.**`). Fix the ones you can date. Six on the real corpus.

---

## Two decisions to make explicitly

**Keep `policy: deferred-work`?** `migrate.py` writes it into the index frontmatter. Keeping it is
what makes an open item without a `trigger` a reported finding. Drop the line and you have a plain
backlog where items are actionable when picked and `trigger` is optional — which also silently
retires the untriaged count. Decide it, do not inherit it.

**What was in the preamble?** The migration replaces everything above the first `## ` heading with
the index's own header, on purpose: a preamble usually documents the old layout ("one bullet = one
item", "mark it `**DONE (YYYY-MM-DD)**`"), which is what stops being true. `verify-migration.mjs`
prints those lines as a NOTICE rather than a finding. Read them — that is also where a policy note,
an owner, or a link would have been.

---

## Known rough edges

**Some index summaries read as a status marker.** `summary` is derived from the item's first bold
span, so an item whose marker is written at the head of the bullet — `- **DONE (2026-08-04)** —
decided at the retro…` — yields `summary: DONE (2026-08-04)`, which names nothing. **43 of 247** on
the real corpus, all of them closed items, so they are rows you meet only when reading the index
directly or passing `--all`. Fixing it means skipping a leading marker and falling back to the
first sentence, and for some items no title survives outside a `~~strikethrough~~` further down.

---

## Retiring a predecessor grooming skill

If the repo already has something that reads the monolith, the format change is also its
retirement. One lesson generalises beyond any particular tool:

**A check that warns about a missing dependency, and names the fallback, does not verify the
fallback exists.** On the real adoption, two files checked for the predecessor skill and said
grooming would fall back to a customization hook. It was warn-only, so nothing broke — and the hook
had never been written. Deleting the skill would have dropped grooming entirely, with a warning
that reads like housekeeping as the only signal.

So: **wire the replacement first, prove it resolves, then delete.** And when you fix the check
afterwards, do not replace it with a presence check for the new skill — the gate is whether the
replacement is *wired*, not whether a file exists, and a second presence check repeats the defect
under a new filename.

**Write the replacement as a POINTER, not a copy** — SKILL.md's *Wiring grooming into a workflow*
has the shape. The predecessor skill carried the buckets and the rules in its own body, so the
obvious move when replacing it is to carry them across. Do not: they live in the skill now, and a
second copy drifts. On the first adoption the gate restated them in 51 lines and its copy of the
untriaged count was wrong twice before anyone noticed. The reviewer that caught it was not looking
at the count — a person asked why the gate did not simply point at the skill.

There is a tell for having got this wrong. If guarding the gate requires asserting the *content* of
the buckets, the gate is a copy; if it only has to assert that the gate points at the skill and
that the skill still defines them, it is a pointer.

---

## After adoption

The index is **hand-maintained from here on**. Do not re-run `migrate.py` over a ledger that has
been edited since: generators append to the index directly (see SKILL.md → *Coexisting with
generators*) and a regeneration eats those appends. If a migrator fix lands upstream later, apply
its effect as an edit to the affected rows, not by regenerating. That happened on the first
adoption — four fixes landed after the ledger was in place, and all four were applied as edits to
the seven, four and two affected files respectively.

`verify-migration.mjs` stays useful afterwards, but only its coverage half: once items are added by
hand the detail files outnumber the source ledger's, so items can no longer be lined up by position
and the status comparison is skipped with a notice. A `CONTENT_DROPPED` finding still means
something went missing and is still worth acting on.
