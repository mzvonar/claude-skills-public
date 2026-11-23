---
name: numbers
description: 'Discipline for every figure Claude states, computes, writes into code or checks in a document — money, prices, VAT, percentages, totals, counts, conversions. Arithmetic runs in a tool, never in prose; every figure carries its unit and scale (cents vs euros, net vs gross, per month vs per year, percent vs fraction); scale changes happen at one named boundary; rounding happens once, under a named rule; every figure that matters is computed a second, independent way; every figure states its origin (measured, computed, third-party, assumption) and, if it can change, its date. Also audits a document''s figures before it is shared. Use for pricing research, invoices, VAT, averages, growth rates, rounding, and whenever a figure looks off by 10x or 100x. Triggers on: "calculate", "total", "VAT", "price", "percent", "per month", "cents", "round", "convert", "is this number right", "check the numbers", "where does this number come from".'
---

# numbers

Figures go wrong the same few ways every time: a value is silently divided or multiplied by 10 or
100 because its scale was never written down, an intermediate result gets rounded "to keep it
readable", a percentage and a fraction get mixed up, or a sum is done in prose and is simply wrong.
None of these is a reasoning failure you can fix by trying harder. They come from doing arithmetic
**in your head** and carrying numbers **without labels**, so the fix is mechanical: stop doing
either.

A retail stocktake works the same way. Nobody trusts one person's count of a shelf. Two people
count it **blind**, without seeing each other's figure or the expected total, and any mismatch is
recounted before anyone writes it down. Every rule below is a version of that.

## The rules

### Arithmetic runs in a tool, never in prose

Any figure that is not copied verbatim from a source (adding, multiplying, a percentage, an
average, a unit or currency conversion, a growth rate) is **produced by a tool call** and quoted
from its output. This includes "trivial" arithmetic: the trivial cases are where the ×100 slips
happen, because nobody checks them.

Use exact decimal arithmetic for money, never binary floats:

```bash
python3 -c 'from decimal import Decimal as D, ROUND_HALF_UP
net = D("81.30"); rate = D("0.23")
gross = net * (1 + rate)
print(gross, gross.quantize(D("0.01"), ROUND_HALF_UP))'
# 99.9990 100.00
```

Floats are not money: in JavaScript `19.99 * 100` is `1998.9999999999998`, so truncating it to
cents gives 1998. In Python `round(2.675, 2)` is `2.67`. Write the inputs as strings
(`D("19.99")`), not as float literals.

If no tool is available, say the figure is unverified. Never present mental arithmetic as a
result.

### Every number carries its unit and scale

A bare `12345` is not a fact. Write it as one of:

| ambiguity | say it explicitly |
|---|---|
| minor vs major currency unit | `12345 cents` / `€123.45`, never `12345` alone |
| net vs gross | `€81.30 net`, `€100.00 incl. 23 % VAT` |
| period | `€9.90 / month`, `€99 / year`, `€2 / seat / month` |
| percent vs fraction vs points | `23 %` = `0.23`; "up 2 percentage points" (20 % → 22 %) is not "up 2 %" (20 % → 20.4 %) |
| count vs amount | `3 invoices`, `€3.00` |

In code the unit goes into the **name**: `totalAmountCents`, `priceEur`, `vatRatePercent` vs
`vatRateFraction`, `durationMs`. Before you convert or compare a value, find where it is declared
(the column, the type, the API field) and read its unit there. Never infer the unit from the
magnitude.

### Scale changes happen once, at a named boundary

The ÷100 / ×100 between minor and major units, and the ×100 between fraction and percent, each
happen in **one** place: a conversion function, the parser at the input edge, the formatter at the
output edge. Never insert a bare `/ 100` or `* 100` inline. Call the boundary function
(`conversionHelpers` in Configuration), or add one if the codebase has none. When you see a value
that "looks 100x too big", **do not fix it by dividing**. Trace it to the boundary it skipped or
crossed twice. The divide-to-fix move is how one bug becomes two.

### Round once, at the end, under a named rule

- Carry full precision through every intermediate step. Never round a subtotal "for readability".
- Round only the figure you present or store, and **name the rule**: half-up, half-even (banker's)
  or truncation, and **at which level**. Per-line and per-document rounding give different totals:
  VAT at 23 % on three €0.10 lines is €0.06 rounded per line but €0.07 rounded once on the €0.30
  total. Where the domain fixes the rule (tax law, an invoice standard, a payment scheme), use that
  rule and cite it (`roundingRules` in Configuration). Where nothing fixes it, ask.
- A rounded or estimated figure is written as one: `≈ €1,200 / month (rounded to the nearest
  €100)`. An exact-looking number must be exact.

### Compute every figure that matters a second, independent way

Before stating a computed figure that someone will act on, derive it again **by a different
route** and compare:

- reverse the operation: from gross, recompute net (`100.00 / 1.23` → `81.30…`) and compare it to
  the stated net;
- reconcile totals: the total equals the sum of its parts, and the parts are counted separately;
- cross-source: the same figure from a second document or query;
- magnitude anchor: is it within an order of magnitude of a known reference point (last month,
  list price, a competitor's plan)? A €9.90 plan reported as €990 fails this before anything else
  does.

The second route also checks what the formula silently assumes, because a correct calculation on
the wrong basis passes every arithmetic check:

- **the denominator:** which population it counts (all organisations or only active ones, all
  invoices or only paid ones);
- **the window:** which dates it covers, and whether the period boundaries are inclusive;
- **the averaging method:** mean or median, weighted or unweighted;
- **annualising:** a monthly figure ×12 assumes every month is alike. Say so when they are not.

If the two routes disagree, **stop and reconcile**: find which input or step differs. Never pick
the more plausible one, never average them, and never report one while dropping the other.

### Copy figures, never retype them

Numbers from a source (a document, a query result, a tool's output, a user's message) are copied
verbatim with where they came from, in their original form and unit: `12345 (cents, from
totalAmountCents)`, not a mentally converted `€123.45`. Do the conversion in the tool, so the raw
value and the converted one both appear.

### Know where every figure came from, and when

Every figure you state is one of five kinds, and the reader is owed which:

| origin | what it is | what it needs |
|---|---|---|
| **measured** | read from a system, file, query or measurement | the source and how it was read (the query, the report, the sheet and cell) |
| **computed** | derived from other figures | the formula and its inputs, each of them traced too |
| **third-party** | a report, study, statistic, regulation or a competitor's price list | the original source (not an article quoting it) and its publication date |
| **assumption** | an estimate or an input someone chose | the word "assumption", and who chose it if known |
| **unsourced** | nobody can say where it came from | a flag, never a quiet pass |

- **Date anything that can change:** prices, exchange rates, counts, balances, a competitor's
  plans. `€29 / month (their pricing page, 2026-11-23)`, not `€29 / month`.
- **Re-read a measured figure from its source** rather than trusting a copy of it made earlier. If
  the two differ, report both values and the likely reason (another date, scope or definition, or
  the data changed).
- **Check a third-party figure's scope** against how you use it: the country, sector, year and
  sample it covers, and its definition of the thing being counted.
- **Never fill a gap with a plausible number.** A missing input is reported as missing. A
  believable invented figure is worse than an obvious blank, because nobody goes looking for it.
- **Never silently correct someone else's figure.** When a document you are editing or checking
  carries a wrong number, report the wrong value, the right one and how you got it, and let its
  owner decide.

### Show the work

When a reply or report contains computed figures, give the inputs, the formula and the tool output
together (a small table is enough) so a reader can check any line without redoing all of it. For
a figure in a test, the fixture states the inputs and the expected value is computed in the
assertion's own terms, or the literal carries its unit in the variable name. Never a magic number
someone worked out off-screen.

## Self-check before sending

Scan your own reply and diff for numbers before you finish. For each computed figure:

- did a tool produce it, and is its unit, scale and period written next to it?
- was anything rounded before the last step, and is the rounding rule named?
- did a second route agree with it?
- does any `/ 100`, `* 100`, `/ 10` or `* 10` appear outside a named conversion boundary?
- is its origin clear (measured, computed, third-party, assumption), and is a figure that can
  change dated?
- does the same metric appear anywhere else in the reply or document with a different value?

If any answer is no, fix it or label the figure as unverified. Never send it as fact.

## Auditing a document before it is shared

The rules above are for figures you produce. When asked to check a document someone else wrote, or
one you wrote earlier ("check the numbers", "where does this figure come from", "is this safe to
send"), run the same rules over every figure it contains. Scale the effort to the document: a
three-line message gets a few lines back, a report gets the full table.

- **Inventory.** List every figure: counts, percentages, rates, money, measurements, dates used as
  data, ranks and ratios. Include tables, charts, footnotes, captions and speaker notes. For each,
  note the value as written with its unit, where it sits (section, slide, cell), what it claims to
  measure, and the source the document cites, if any.
- **Classify** each by origin, using the table in "Know where every figure came from".
- **Trace measured figures** back to their source and read them again. If the source is out of
  reach, ask the user where the figure came from before calling it unverifiable.
- **Recompute computed figures** in a tool from their inputs, with the checks in "Compute every
  figure that matters a second, independent way". Never accept a derived figure from the text.
- **Open third-party sources** and confirm the figure, its date, its scope and its definition.
- **Cross-check the document against itself:** one metric, one value everywhere, and no two figures
  that contradict each other.

Report the bottom line first: how many figures were checked, how many fall under each status below,
and whether the document is safe to share. Then one row per figure:

| # | Figure | Where | Origin | Source and method | As of | Status | Note |
|---|---|---|---|---|---|---|---|

Status is one of **Verified**, **Corrected** (old and new value), **Assumption** (with its owner if
known), **Unverifiable** or **Unsourced**. End with the fixes the document needs, most important
first. The document itself stays unchanged until its owner decides.

## Configuration

Zero config works: the rules apply as written, and the skill asks when a rounding rule or money
unit is not determined. Per-repo facts live in `.claude/claude-skills.json` under the `numbers`
key. Every key is optional and documents the repo; none changes the rules.

| key | default | meaning |
|---|---|---|
| `moneyUnit` | none (read each value's declaration) | How the codebase stores money, e.g. `"integer minor units (cents) in *Cents columns"`. |
| `conversionHelpers` | none | Functions that own the minor↔major and fraction↔percent scale changes. A bare `/ 100` elsewhere is a finding. |
| `roundingRules` | none (ask) | Domain rounding rules with their source, e.g. VAT rounding level and mode. |
| `calculator` | `python3` with `decimal` | Command used for arithmetic, if the machine lacks Python or the repo prefers another. |

```json
{
  "numbers": {
    "moneyUnit": "integer minor units (cents); columns end in Cents",
    "conversionHelpers": ["decimalToCents", "formatAmount"],
    "roundingRules": ["VAT: half-up to 0.01 per document total"],
    "calculator": "python3"
  }
}
```
