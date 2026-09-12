# Migration traps

Twelve defects that were live in this migrator: traps 1–10 found against one real 3,622-line
corpus, 11 and 12 against a 5,201-line one two adoptions later. Each is a silent corruption: the
migration completes, the counts look plausible, and content is misfiled or simply absent. Trap 12
is the limit case — it produces exactly the output a correct run produces.

They are recorded because they are properties of *hand-written markdown ledgers in general*, not of
one repo's file. Anyone adopting this format will meet them.

**Catch them the same way they were caught: cross-check the migrator's status count against an
independent count of the source, and refuse a near-match.** `scripts/verify-migration.mjs` now does
both halves of that automatically and is the gate in `adopting.md`; run against the migration that
shipped with traps 4–7 live it reports 85 dropped-content findings and exactly the four
status disagreements that were found by hand. Read on anyway — it is a differential check between
two implementations, so it cannot see a shape they both get wrong, and that is what a near-match is. The sequence on the real corpus was
11 → 42 → 39 → 40 → **44**, and every intermediate number looked reasonable.

That `40` is the point of this page. It shipped as "the independently verified answer" and was
wrong by four. It survived because the cross-check compared *counts*: two numbers four apart still
read as "roughly agreeing, close enough". **Compare the SETS.** The four missing items were named
in seconds once the two extractors' outputs were diffed as sets rather than sized, and each was then
confirmed by reading the item.

---

## 1. The status marker is written many ways

Expected `**DONE (2026-08-04)**`. Actually present, all in one file:

| form | note |
|---|---|
| `**DONE (2026-08-04)**` | the documented one |
| `**✅ DONE (2026-08-04, item-35)**` | emoji prefix, second field inside the parens |
| `**DONE upstream (2026-08-31, …)**` | a word between the marker and the paren |
| `**DONE in-story (2026-08-25, …)**` | another word, and it wraps — see trap 4 |
| `**KILLED (2026-08-04, item-35 …)**` | |
| `- ~~struck through~~` | no marker at all |

And two shapes that must **not** match:

- `HALF DONE (2026-07-20)` — a progress note, not a status.
- ``mark it `**DONE (YYYY-MM-DD)**` `` — prose *documenting the convention*. A ledger that explains
  its own format contains its own format.

A strict pattern found 10 of 44. A loose one found 48, including both false positives.

## 2. A character window reaches into sub-bullets

Scoping the status search to "the first 200 characters of the item" pulls in nested bullets when the
headline is short — so an item whose **child** was marked killed inherits the child's status.
Misfiled 2 of 42.

Scope to the item's **own text**, which ends at its first sub-bullet. Sub-bullets are context for
the parent, never a status.

> Not "the first line". An earlier revision of this page said "the item's own bullet line", the
> migrator read that as `block.split("\n")[0]`, and traps 4 and 5 are what that cost. An item's own
> text is its bullet line **plus the continuation lines under it** — markdown lets the author break
> a line anywhere, so where the text ends is a structural question, not a positional one.

## 3. The status parenthetical wraps onto the next line

```markdown
- **DONE (2026-08-31, chore/some-branch-abc1234 — a deliberate pipeline-shape change, which is this
  very thing) …
```

The closing `)` is two lines down. A pattern requiring it silently drops the item — line-spanning
data under a per-line pattern. Make the closing paren optional and take the date.

## 4. The marker is not at the head of the item

Two shapes, one cause. An item retired **in place** keeps its original text as the record and gets
its marker appended at the END of the body:

```markdown
- **`ShapeGuardTest.DOMAIN_ROOT` still scans only the legacy `domain/` directory** for the
  doc-comment half. Nothing is missed while every port lives there …
  **DONE (2026-09-07)** — follow-up run: `AuditPort` moved, and the root became `LayerDirectories…`.
```

And a marker that *starts* on the bullet line can have its parenthetical **open** on the next one:

```markdown
- **Sanitize `transactionId` at the MDC source (`TransactionIdMdcFilter`).** **DONE in-story
  (2026-08-25, review round 1):** `sanitizeForLog` now runs before `MDC.put` …
```

Trap 3 made the *closing* paren optional and stopped there — the class was named and one member of
it was closed. Four items on the real corpus migrated `open` while their own body said DONE, and
three were then reported as untriaged, i.e. as needing a trigger for work already finished.

The fixture set is why it survived: it contained the wraps its author had seen. **Normalise the
zone — flatten the item's own text — rather than adding a pattern per observed wrap.**

## 5. An item's block contains what follows it

An item runs to the next top-level bullet, so its block also holds anything sitting between them at
the **left margin** — typically a trailing `###` sub-heading and the paragraph under it, which
belong to the next group and carry a marker of their own:

```markdown
- **An open item.** …

### A following sub-heading — **DONE (2026-09-03)**

**✅ DONE (2026-09-03) — this retires the heading above, not the bullet before it.**
```

This one appeared *while fixing trap 4*: widening the zone from one line to the whole block retired
an open item with a DONE written eleven lines below it about something else. A continuation line of
a bullet is indented; anything at the left margin has left the item.

---

## 6. A section carries content that is not an item

An item-driven walk writes items. A hand-written ledger also holds, under its `## ` headings:

- **intro prose** — why this group was parked, who owns it, what supersedes it. On the real corpus,
  **23 of 85** sections had some, and all 23 were dropped.
- **a status on the heading itself** — `## Deferred from: code review of item-18 … — **RETIRED (2026-08-07)**`,
  with a blockquote reading *"all five seams are closed … do not action"*. Its one item carried no
  marker of its own, so it migrated `open`: presented as live work, which is precisely what that
  banner was written to stop. The banner even says so — *"the block was never marked on itself, so
  grooming kept re-reading it as open."*

Keep the headings and the prose in the index; readers match on `id:` / `detail:` lines, so neither
costs them anything. And **report** a section-level status onto its open items rather than applying
it: a retired section usually means its items are done, but a DONE section can hold one live item
and only a person can tell which.

## 7. A section with no bullets at all

The newest entry on the real corpus was a `### ` heading with **Trigger** / **What** / **Why** /
**Owner** paragraphs and not one bullet anywhere. It is an item by every meaning except the
migrator's, so an item-driven walk dropped the whole section — a live item with a stated trigger,
absent from a migration billed as lossless, with the item count unchanged and nothing to notice.

Walk **sections**, not items. Then a section with no items still reaches the index and gets
reported for promotion by hand. That was where the first fix stopped, and it was not enough:
see trap 11, where the same shape is half a ledger and "by hand" is not a remedy.

> Both of these were found by asking a question the item counts cannot answer: *did all of the
> source's content reach the output?* The item-level answer was a clean 251/251 while 23
> section intros and one whole item were on the floor. **A losslessness check whose unit is the
> thing the tool already understands cannot see what the tool does not model.**

---

## 8. The closed vocabulary is not the one the ledger documents

The first corpus's own header said: *"Strike a bullet through or mark it `**DONE (YYYY-MM-DD)**` /
`**KILLED (YYYY-MM-DD)**` to retire it."* Two words. Measured across the same file:

| word | uses |
|---|---|
| `DONE` | 40 |
| `KILLED` | 11 |
| **`CLOSED`** | **9** |
| **`SUPERSEDED`** | **4** |
| **`RETIRED`** | **4** |
| **`RESOLVED`** | **1** |

The four the header never mentions retired **seven items that migrated `open`** — and because they
were open with no `trigger`, they landed in the *untriaged* set, i.e. presented to every grooming
pass as live work needing a trigger. Two of them read *"Kept for provenance; do not action."*

Three things make this the worst trap on the page:

- **The differential gate cannot see it.** `verify-migration.mjs` shared the same `DONE|KILLED`
  vocabulary, so both sides agreed and the gate went green. This is precisely the "shape BOTH
  implementations get wrong" its own header warns it is blind to — written before anyone had found
  one, and then found.
- **The author half-knew.** `SECTION_MARK` already accepted `RETIRED`, because a *section* heading
  used it. Nobody asked whether an *item* could. Widening one scope and not its sibling is the same
  enumerate-instead-of-close failure as traps 3→4.
- **Widening the migrator is half a fix.** Every consumer that decides "is this open?" carries the
  list too — `backlog.mjs` and `validate.mjs` both filtered on `/^(DONE|KILLED)/`, so the newly
  closed items would still have read as open in the reader.

**Derive it from your ledger before migrating** (`adopting.md` has the command), and note what
`verify-migration.mjs` now prints: marker-shaped words on items that migrated OPEN which neither
side claims. That report is the only signal a vocabulary gap has, because a comparison between two
implementations that share the gap produces none.

A hedge in front of a closure is not a closure: `MOSTLY CLOSED`, `PARTIALLY LANDED`, `HALF DONE`,
`NOT done` stay open and are reported. And a closure need not carry a date — `**SUPERSEDED the same
day — FIXED upstream at 2c8bf973.**` retires an item with no parenthetical at all. Record it as
`(date unknown)` and report it; leaving it open is how two of the seven were lost.

## 9. `repr()` is not a YAML quoter

Frontmatter was emitted with Python's `repr()`. It looks right and is not:

- **backslashes double.** An item quoting the regex `` `^conformance/.*\.md$` `` was stored as
  `\\.md$` — the record no longer matches the source it claims to preserve.
- **an apostrophe becomes `\'`**, which is invalid inside a YAML single-quoted scalar. YAML doubles
  it (`''`). Two files shipped unparseable.

Nothing failed, because both readers here scan lines with a regex instead of parsing YAML — so the
format was sold as frontmatter while two files were not frontmatter. **If you emit a format, emit it
with that format's rules, and validate with that format's parser rather than the reader you shipped.**

---

## 10. A `### ` heading can be the ITEM, and its bullets its FIELDS

The walk reads top-level bullets as items. A hand-written ledger also carries records shaped as a
heading plus labelled fields:

```markdown
### Data-table integration traps for the search screen — **KILLED (2026-08-04)**

- **What:** three traps the first implementation hit …
- **Trigger:** scoping of item-28 — fold into its notes verbatim.
```

Read bullet-by-bullet that is **two items**, and on the real corpus four such records became eight.
Every consequence is bad in a different way:

- the summaries were `What` and `Trigger`, which name nothing;
- neither half carried a trigger, because the trigger was its *sibling* — so both were reported
  **untriaged**, asking for a trigger that was sitting one bullet away;
- the heading's own status was never read, so two records whose headings said `DONE` and `KILLED`
  shipped as `open` — the same harm as trap 8, by a different route.

Fold a `### ` run into one item **only when every bullet under it is a short bold label ending in a
colon**, and take the summary and the status from the heading. The guard matters: `### ` is an
ordinary grouping heading in plenty of ledgers, and folding those would merge unrelated items and
lose every summary but the heading's. Report the count of folded records so the choice is visible.

**Both halves of the toolchain segment, so both must fold.** `migrate.py` learned this and
`verify-migration.mjs` did not, so the two counted 247 items against 251 and every position after
the first fold was off by one — **67 spurious status disagreements on a correct migration**. A
differential check whose halves disagree about what an *item is* compares nothing, and it fails
loudly, which is worse than useless: it buries the real findings under its own noise. The same
shape had already appeared twice that day — a widened vocabulary that only one of four consumers
knew, and a YAML escape the writer emitted and no reader decoded. **When a definition changes, the
question is not "did I fix it" but "who else holds a copy of this definition".**

Note where this sits relative to trap 7: that was a heading with **no** bullets, this is a heading
whose bullets are not items. They are the same mistake — *the item is not always the bullet* — and
fixing the first did not reveal the second, because a heading with two bullets under it looks
exactly like a section that is working.

---

## 11. "Report it, a person will promote it" does not survive the second corpus

Traps 6 and 7 were both closed by *keeping the content in the index and printing a count*. On the
corpus that found them, one section had no bullets, so one line of output and one hand-promotion
closed it. On the next ledger — 5,201 lines, 610 KB — **108 of 219 sections had no bullet**, and
they carried **72 of the ledger's 154 cross-referenced ids**, including four of the six that its
sprint-status file pointed at. The migration passed its own gate with nothing dropped, and 47% of
the ledger reached the output as prose with no frontmatter: invisible to `backlog.mjs`, which is
the one thing the format exists to provide.

So the remedy was the trap. A count of 1 reads as a loose end; the same count at 108 reads as
"promote a hundred records by hand before you can use this", which nobody does — and the migration
still calls itself lossless, because the *content* is all there. **When the fix for a shape is
"report it and promote by hand", ask what that costs at ten times the count.** Below some
threshold a report is a remedy; above it, it is a way of not implementing the feature.

Fold it instead: a bulletless section is a record whose **heading is its own text**, exactly the
contract trap 10's field-records already use. One item per `### ` run, or the whole section as one
item where there are no sub-headings. Report the folded count so the inference stays visible.

Two boundaries opened the moment headings became records, and both were live immediately — the
"widening a scope opens a boundary" corollary, twice in one change:

- **A heading states its status UNBOLDED.** Every marker pattern needs a `**`, because a bullet's
  author must emphasise the marker to make it stand out. A heading is already emphasised, so they
  do not: `## RESOLVED in 8.3 (pre-existing test-rot) — …` migrated open. The same gap sat in the
  *section*-level check, where it hid twelve items whose closure was written on the heading above
  them — and that check is the only signal those items have. Anchor the pattern structurally (the
  heading's start, or after a separator) so a heading that merely mentions the word stays open.
- **The differential gate reads a different zone.** `migrate.py` takes a folded record's status
  from the heading; the verifier took it from the block, and `migrate.py` writes the body without
  the heading — so the two disagreed on every flat record, three of them real closures. This is
  trap 10's lesson arriving on schedule: *when a definition changes, the question is not "did I fix
  it" but "who else holds a copy".* The gate caught it, which is the only reason it is a footnote.

---

## 12. The gate exits 0 because it never ran

`validate.mjs` guarded its CLI block with `import.meta.url === pathToFileURL(process.argv[1]).href`.
`import.meta.url` is the **real** path; `process.argv[1]` is whatever the caller typed. Put one
symlink anywhere on the way in and they differ, the guard is false, and the script exits 0 having
validated nothing.

This is not exotic. The script's own install path routinely is a symlink — a plugin cache under
`~/.claude` pointing at another volume is the ordinary case, and that is exactly how it was found:
`node ~/.claude/plugins/.../validate.mjs <index>` printed nothing and exited 0, while the same file
invoked through `realpath` printed **633 findings**. It had been reporting clean for as long as
anyone had run it that way.

Resolve both sides before comparing. And note the shape, because it is worse than a wrong answer:
**a gate that cannot fail is indistinguishable from a gate that passed.** Every other trap here
corrupts data and leaves a plausible count; this one produces the output a correct run produces.
The only defence is a test that runs the CLI *through a symlink* and asserts it says the same thing
as the direct invocation — asserting on the exported function would have passed throughout, since
the exported function was never broken.

---

## The general rule

Traps 1–5 are the same mistake at different scales: **anchoring on the layout the author imagined
rather than the layout the corpus contains.** A hand-maintained ledger accretes formatting over
years and nothing ever validated it, because until now nothing read it mechanically.

Two corollaries, both bought the expensive way:

- **A fixture set demonstrates a closure; it does not achieve one.** Traps 4 and 5 each passed a
  suite that already had a row for "the marker wraps". Rows prove the scanner fires on the shapes
  someone thought of — normalising the input is what covers the ones nobody did.
- **Widening a scope opens a boundary.** Trap 4's fix made trap 5 reachable. Whenever a zone grows,
  ask what it now touches that it did not before, and add the fixture before believing the count.
- **Verify in the source's units, not the tool's.** Traps 6 and 7 are a different failure: not
  misread items but content the model has no slot for. Only a byte-level "is all of this somewhere
  in the output?" sweep finds those, and it must run before the migration is committed.
- **The item is not always the bullet.** Traps 7 and 10 are the same error at two extremes: a
  record with no bullets, and a record whose bullets are its fields. Whenever a walk assumes one
  syntactic form *is* the unit, ask what the ledger's other record shapes look like — the answer is
  in the file, and grepping its `### ` headings takes a second.
- **A vocabulary is data, and it is the one thing a differential check cannot test.** Trap 8 passed
  a green gate because both implementations shared the missing words. Where two checks must agree,
  ask what they agree *about*, and report the inputs neither of them claims.

So: parse loosely, normalise before matching, restrict scope structurally, and **report what was
inferred instead of deciding silently**. `migrate.py` prints an ambiguous count for exactly this
reason — those are the entries a person should read before the migration is committed.
