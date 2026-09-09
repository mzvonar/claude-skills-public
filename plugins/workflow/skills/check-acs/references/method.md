# The evidence behind check-acs

Derived from a controlled study on two shipped changes in one repository (~1,900 judge calls,
model `claude-fable-5`, backend-heavy diffs of 1,400–2,500 lines). **Every number in this file
was measured on that one corpus with that one model.** None of them has been reproduced
elsewhere; read them as the shape of the behaviour, not as rates that transfer. Read this before
trusting or extending the skill: it records what was measured, what turned out to be false, and
what is still unknown.

## Why one-criterion-at-a-time works

Five properties, and they compound:

- **One criterion per call.** The unit of judgment is a single narrow written claim, not "does
  this 2,500-line diff look right". Attention is not spread across eleven criteria at once.
- **A fresh context every call.** No anchoring on earlier verdicts, no momentum from "the last
  six were fine", no conversation in which the author's rationale has already been accepted. A
  two-pass human review has all three of those working against it.
- **The criterion text is the oracle, not the code.** "Does this satisfy this written
  requirement" forces a literal reading. Reviewers read code and ask "is this reasonable?" — a
  different and far more forgiving question.
- **Repetition turns a coin-flip into a signal.** This is the single biggest lever. A defect the
  model spots 60% of the time is invisible to one review pass and obvious as a 6/10. Most real
  findings surfaced as *split* verdicts.
- **A forced binary verdict.** No "looks good, one small note". The model must commit, then
  justify the commitment.

## What it found

| finding | outcome |
|---|---|
| A criterion required a specific negative test case; the test file had none. Two-pass human review had recorded that criterion as "all present". | **Real.** Confirmed by grep at `main`. Surfaced on 26/30 runs. |
| A criterion required four reads to run inside one transaction; the code opened the transaction but issued the reads through the default connection, so they ran outside it. | **Real.** The shipped code's own comment admitted the deviation. 2/2. |
| A criterion's user-facing strings were reported absent. | **False positive.** The strings existed; the file holding them was outside the payload. |

One in three new leads was wrong, and the cause was payload incompleteness rather than model
error — the model reasoned correctly about what it had been shown. Hence the manifest, and the
rule that every "X is missing" is checked against the repo before it is recorded.

## Measured rates, and how much to trust them

All measured on one corpus, one model:

| measure | result |
|---|---|
| False rejections (criteria the change does satisfy) | 0/840 |
| Invented requirements | 0 |
| False passes on code defects | 0/110 |
| False passes on **test-coverage** criteria | **13/30 (43%)** |
| Correct locus attribution (defect one file away) | 0/90 misattributed |

**These rates are not measured against an independent oracle.** They are measured against labels
written by the same person who built the test mutations, and twice those labels were wrong — both
times in the model's favour, and both times revised after the model disagreed. Under the original
labels, one mutant alone would have scored 30/30 false passes and the "0/110 false passes" figure
would read about 21%. The revisions were correct on the merits, but a process where the label
author adjudicates every disagreement can only move the error rate toward zero. Read "0% false
rejections" as **"no rejection survived investigation as false"** — weaker, and honest.

Fixing this needs pre-registered labels written by someone other than whoever builds the test
cases, not more runs.

## The non-monotonicity result, and why the mechanical checker exists

An implementation was mutated to remove three *more* required test cases than the original was
already missing — strictly worse by construction. It was rejected **less** often: 17/30 versus
26/30 for the unmutated version (Fisher exact, two-tailed, p = 0.020).

The mechanism is visible in the rationales and is not hallucination. The model sees the gap and
argues it away: *"the null-account case lacks a direct assertion but is implicitly verified — the
existing tests' return-value assertions would fail if it regressed."* That reasoning was
**substantively correct**. It is a judgment about sufficiency of coverage, and sufficiency is
exactly where a verdict is a coin-flip.

A verdict that moves the wrong way as the artefact degrades cannot be an oracle. So for criteria
that name a concrete artifact, do not ask for a verdict — search for the string. That is what
`ac_artifacts.py` is: small, deterministic, no tolerances.

## Hypotheses that were tested and refuted

Recorded so they are not re-litigated:

- **Prompt style does not matter.** direct / explain / explain-and-fix were within noise of each
  other across 1,080 calls: identical on every clear-cut criterion (0/10 each where the code was
  right, 10/10 each on the unambiguous defects). Spend budget on repetitions, not style variants.

  The one criterion where they differed is worth recording precisely, because it is easy to
  misread. On a borderline criterion — a real but arguably minor omission — explain-and-fix
  rejected it 10/10 where the other two rejected it 8/10. Those rejections were **true**, so
  asking for a fix made the judge *more* accurate there, not less. There is no measured evidence
  that requesting a remedy degrades verdict quality; an earlier version of this document claimed
  otherwise on the strength of that single data point, which the data does not support.

- **The weakness is not "omission vs commission".** The natural theory — it spots wrong code but
  not missing code — is false. A deliberately omitted required event was caught 10/10, exactly as
  often as a present-but-wrong field (10/10), with zero false rejections on the control. The
  weakness is narrower: criteria whose satisfaction is a *coverage-sufficiency* judgment.
- **The mutations were not simply too obvious.** A deliberately subtle one — two arguments
  transposed in a call, with the test's expected values flipped to match so the suite stayed
  green and the change was internally consistent — was still caught 10/10, with rationales
  quoting the function signature against the call site.

## Known limits

- One repository, one model, two changes, backend-heavy diffs. Frontend and visual criteria were
  never exercised, and no cost or rate figure here has been reproduced on another corpus.
- Long context is untested past ~60K tokens. Published work reports sharp degradation in
  evidence-finding beyond 64K, so treat very large payloads with suspicion.
- The test mutations were written by the same person interpreting the results, so they test the
  defects that person thought to create.
- Nothing here measures **recall**: there is no labelled corpus, so how many real defects the
  method misses is simply unknown — and on coverage criteria it is known to be bad.
