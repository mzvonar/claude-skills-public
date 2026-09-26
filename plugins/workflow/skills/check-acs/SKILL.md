---
name: check-acs
description: 'Audit an implementation against its acceptance criteria, one criterion at a time, to find AC-misimplementations that code review misses. Use whenever the user wants to check, verify, or audit acceptance criteria — "does this actually satisfy the ACs", "check the ACs for this story", "did we really implement AC4", "audit this story before merge", "the review passed but I want a second opinion", or when reviewing a PR/MR against a spec or ticket. Also use when a story was marked done and the user suspects something slipped, or when they want to know which criteria a change fails. Combines a repeated fresh-context judge sweep with a deterministic existence check for criteria that name concrete artifacts.'
---

# check-acs

Find criteria an implementation does not actually satisfy.

This works because of *how* it asks, not because the model is clever. A reviewer — human or AI —
reads a whole diff against a whole spec and asks "does this look right?". This asks a much
narrower question, many times, with no memory between asks: **does this one diff satisfy this one
criterion?** Narrow questions get checked; broad ones get skimmed.

It has found real defects in shipped, merged, multi-pass-reviewed code. It has also produced a
confident false finding. Both behaviours come from the same property, so read
`references/method.md` before trusting any output — the evidence, the measured failure rates, and
the reasoning behind every rule here live there.

## The one rule that matters

**Use this to find, never to certify.** A rejection is a lead worth investigating. A pass is
close to meaningless: on criteria about test coverage this judge waved defects through 43% of
the time, and its verdict was *not monotone* — a strictly worse implementation was rejected
*less* often than the correct one (17/30 vs 26/30, p=0.02). Those figures were measured on one
corpus with one model; treat them as the shape of the risk, not a rate you can plan on. "All criteria passed" is not a
result you can report. "These three criteria came back split, and here is what I found when I
checked them" is.

## Workflow

### 0. Is this session reading the CURRENT skill text?

```bash
bash "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/marketplaces/claude-skills-public/scripts/plugin-freshness.sh"
```

Local, no network, silent when current. **Exit 3** = this session is serving an older cached
version than the one installed — a session pins its version at the first call to a skill and never
moves, and nothing else reports it. Put it to the user with `AskUserQuestion`: reload
(`/reload-plugins`) and re-run, or carry on knowingly. Exit 2 or no such script = undetermined,
carry on. Why: `docs/conventions.md`.

### 1. Build the run directory

```bash
scripts/ac_setup.py --spec <spec.md> --range <base>..<head>
```

The run directory defaults to `ac-audit/<key>` (`<key>` = the spec file's stem) or the configured
`outDir`; pass `--out` to override. Reads the spec's criteria section, splits it into one file per criterion, and captures the diff.
Then **read `MANIFEST.txt`**. It lists any changed file left out of the payload, because the most
likely false finding is a judge correctly reporting that something is absent from a diff that
never contained it. Include everything the criteria could reach — translations, migrations,
config, generated contracts — not just application source.

If the splitter mis-parses an unusual spec, pass `--section` with a regex for its heading (or set
`sectionPatterns` once in the config so every run in the repo gets it), or split the criteria by
hand and pass `--acs-dir`. A wrong split silently changes the question.

### 2. Screen wide and shallow

```bash
N=3 scripts/ac_sweep.sh ac-audit/<key>
```

Three runs over every criterion. The sweep is idempotent, so if an API cap interrupts it, run it
again and it fills only the gaps. The tally prints one of three states per criterion:

- **REJECTED** — every run said not satisfied. Strong lead.
- **SPLIT** — the runs disagree. **This is the most valuable state.** A defect the model catches
  half the time is a coin-flip in a single review pass and plainly visible here. Most real
  findings surface as splits, not as unanimous verdicts. Never average a split away.
- **ok** — no signal. Not evidence of correctness.

### 3. Deepen only where there is signal

```bash
N=10 scripts/ac_sweep.sh ac-audit/<key> AC4 AC8
scripts/ac_tally.py ac-audit/<key> --dump --only AC4 AC8
```

Spend runs where the screen flagged something. The counts triage; **the rationales are the
actual output**. A 6/10 with one precise rationale beats a 10/10 with vague ones.

### 4. Check named artifacts mechanically

For any criterion that names a concrete thing — a test case, an event, a column, a file, a
scope, a constant — do not ask for a verdict. Search for it:

```bash
scripts/ac_artifacts.py ac-audit/<key> AC8 --repo .
```

This is the band where the judge measurably fails, and where judgment is not needed: existence
is a string search. The tool extracts the names a criterion mentions and reports each as **IN
DIFF**, **REPO ONLY**, or **MISSING**. It decides nothing — extraction is heuristic and picks up
prose, so skim the list. `REPO ONLY` on something the criterion said this change must add is a
finding; `REPO ONLY` on something described as pre-existing is expected.

When a criterion states requirements in prose rather than in backticks — "covers the empty case,
the unknown-id case, and the cross-tenant case" — turn those into search terms yourself and pass
them with `--expect`. Extraction can be fuzzy; verification stays a literal search.

### 5. Verify every lead before reporting it

No finding leaves this skill unverified. For each one, open the code and confirm it. In
particular, before recording any "X is missing":

- Check `MANIFEST.txt` — was X simply outside the payload?
- Grep the repo — **missing from the diff is not missing from the codebase.**

This is not ceremony. In the study behind this skill, one of three new leads was a false
positive of exactly this kind, and the model's reasoning about it was impeccable — it was the
payload that was wrong.

### 6. Present findings, propose fixes, and ask

Only verified findings reach this step. For each one, write the fix yourself — you have the
repository, the conventions, and the surrounding tests. The judge saw a diff and nothing else,
so its idea of a fix routinely misses call sites and the tests that must change alongside; you
are better placed than it is.

Then put the decision to the user rather than acting on it. Present the findings as a numbered
list, each with its severity, its evidence, and the fix you propose, and ask which to fix — with
AskUserQuestion where available, offering the obvious groupings (all of them, only the confirmed
defects, a specific one, none for now). The user may already know that a finding is intentional,
or out of scope for this change, or someone else's story.

Do not apply fixes before asking, and do not fold "and I fixed it" into the report. An audit that
silently edits what it audits destroys the thing that makes it useful: you can no longer tell
whether the criterion passes because the code was right or because the tool rewrote it. It also
gets expensive when a lead turns out to be a false positive — one in three did in the study —
because now there is a change to undo as well as a claim to retract.

## Reporting

Report leads, what verifying them showed, and a proposed fix for each confirmed defect —
never a pass rate:

```
AC4  SPLIT 6/10 satisfied — VERIFIED DEFECT
     The criterion requires the four reads to run inside one transaction; the code opens the
     transaction but issues the reads through the default connection, so they run outside it.
     <file:line>
     Proposed fix: pass the transaction handle through to the four repository calls. Needs the
     repository helpers to accept a handle — check before adopting.

AC8  MISSING artifact — VERIFIED DEFECT
     Criterion names a "rejects an expired token" case; no such test exists (grep, whole repo).
     Proposed fix: add that case to <existing test file>, alongside the invalid-token case it
     already covers, asserting 401 and the documented error code.

AC2  REJECTED 0/3 — NOT A DEFECT
     Judge reported the translation keys absent; they are present in the locale file, which
     was outside the payload. Harness gap, not a code gap.

AC1, AC3, AC5-AC7  no signal. Not evidence of correctness.

Two confirmed defects. Which should I fix — both, AC4 only, AC8 only, or neither for now?
```

Keep the "not a defect" and "no signal" lines in the report. They are what stops the reader from
reading two findings as the whole story: the first says a lead was chased and dismissed, the
second says most criteria were never really tested by this run.

## Cost

Measured on one corpus with one model (`claude-fable-5`): about $0.29 per call once the prompt
cache is warm, on a ~60K-token payload; the first call of a run costs more because it creates the
cache. Other models and payload sizes will differ — read these as proportions, not prices. An N=3 screen of ten criteria is ~30 calls. Deepen
selectively rather than running N=10 everywhere — that is 3x the cost for signal you have
already located.

**Most of that price is the cached prompt, so do not let the N repeats race for it.** The sweep
runs sequentially (`P=1`) by design. On one ~226K-token payload a cell cost ~$4.9 cold and $0.65
warm — 7.6x — but measure before you extrapolate: the cache key covers the **whole** prompt, the
criterion included, so only the 2nd and 3rd run of the *same* criterion hit it. The first call of
every new criterion pays full price however you schedule it. That is why the sweep emits all `N`
runs of one criterion consecutively; keep that order. The saving is therefore `(N-1)/N` of the
calls: at N=3 sequential averages ~$2.1/cell against ~$4.9 at `P=6` (2.4x), at N=10 ~$1.1 (4.6x).
Under `P=6` every call is cold, because they all start before any has finished writing. Calls run
~45–60s, so ten criteria at N=3 is roughly twenty minutes — that wall-clock is what the multiple
costs. Raise `P` only to buy speed knowingly.

Caching does not blunt the method. It replays a computation; each verdict is still sampled fresh,
in a context that cannot see the other runs. That is what a SPLIT measures, and the measurements
behind this skill were themselves made on cached sweeps.

Two things not worth spending on, because they were measured (same corpus, same model) and made
no difference: **prompt style** (direct / explain / explain-and-fix were within noise across
1,080 calls — spend on N instead), and separate runs to catch *missing* code as opposed to *wrong* code (an omitted
required event was caught exactly as reliably as a wrong value, 10/10 each).

## Interpreting a disagreement

When the judge contradicts your reading of a criterion, treat your own labelling as the more
likely error. In the study, every apparent false rejection that was investigated turned out to
be correct, and twice the criterion was genuinely violated in a way the human labeller had
missed. Re-read the criterion's exact wording before dismissing a verdict — but equally, do not
let that become deference: verify, then decide.

## Configuration

Zero config works: the scripts find the repo by walking up from the current directory. Per-repo
overrides live in `.claude/claude-skills.json` under the `check-acs` key; every key is optional.

| key | default | meaning |
|---|---|---|
| `model` | `claude-fable-5` | Model passed to `claude -p` by `ac_judge.sh`. Precedence: `AC_MODEL` env var, then this key, then the default. |
| `outDir` | `ac-audit/<key>` | Run directory template for `ac_setup.py`; `<key>` is replaced by the spec file's stem. `--out` overrides per run. |
| `sectionPatterns` | built-in list (`acceptance criteria`, `criteria`, `requirements`, `acceptance tests`, `AC`/`ACs`) | Regexes matched against headings to find the criteria section. `--section` overrides per run. |

```json
{
  "check-acs": {
    "model": "claude-fable-5",
    "outDir": ".audits/<key>",
    "sectionPatterns": ["^done when", "acceptance\\s+criteria"]
  }
}
```

Environment knobs the scripts honour regardless of config: `AC_MODEL` (model), `AC_SCRATCH`
(scratch cwd for the judge), and `N` / `P` / `STYLE` / `DIFF` on `ac_sweep.sh`.

`references/method.md` — the measurements behind every claim here, and the known limits.

---
To change this skill, do not edit this copy: use `/dev-tools:update-skill`, or see `docs/updating-skills.md` in `mzvonar/claude-skills-public`.
