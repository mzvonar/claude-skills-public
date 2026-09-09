#!/usr/bin/env python3
"""Tally an AC-audit sweep.

  ac_tally.py <run-dir> [--diff payload] [--style explain] [--dump] [--only AC3 AC7]

Reports, per criterion, how many runs said satisfied. Two things deserve attention and both
are easy to miss in a single-pass review:

  REJECTED  every run said not_satisfied — a strong lead.
  SPLIT     the runs disagree. This is the most valuable state, not noise: a defect the model
            spots half the time is invisible to one review pass and obvious here. Most real
            findings in the study behind this skill (one corpus, one model) surfaced as splits,
            not unanimous verdicts.

The counts are a triage device. The rationales are the actual output — read them with --dump.
"""
import argparse, collections, json, pathlib, sys

ap = argparse.ArgumentParser()
ap.add_argument('run'); ap.add_argument('--diff', default='payload')
ap.add_argument('--style', default='explain'); ap.add_argument('--dump', action='store_true')
ap.add_argument('--only', nargs='*'); ap.add_argument('--json', action='store_true')
a = ap.parse_args()

root = pathlib.Path(a.run) / 'results' / a.diff
if not root.exists():
    sys.exit(f'no results at {root}')
acs = sorted([d.name for d in root.iterdir() if d.is_dir()],
             key=lambda s: (len(s), s))
if a.only:
    acs = [x for x in acs if x in a.only]

rows, bad = [], 0
for ac in acs:
    d = root / ac / a.style
    if not d.exists():
        continue
    for f in sorted(d.glob('*.json'), key=lambda p: int(p.stem) if p.stem.isdigit() else 0):
        try:
            j = json.load(open(f))
        except Exception:
            bad += 1; continue
        so = j.get('structured_output') or {}
        v = so.get('verdict')
        if v is None and j.get('result'):
            try: v = json.loads(j['result']).get('verdict')
            except Exception: pass
        if v not in ('satisfied', 'not_satisfied'):
            bad += 1
            # An API cap or refusal writes a result file with no verdict. Counting files instead
            # of verdicts is how a capped sweep silently looks complete.
            continue
        rows.append(dict(ac=ac, n=f.stem, verdict=v, cost=j.get('total_cost_usd', 0),
                         explanation=so.get('explanation') or '', fix=so.get('fix') or ''))

if a.json:
    print(json.dumps(rows, indent=1)); sys.exit()

print(f'\n{len(rows)} usable verdicts, {bad} unusable (cap/refusal/parse) — '
      f'${sum(r["cost"] for r in rows):.2f}\n')
print(f'| {"criterion":<12} | {"satisfied":>9} | state |')
print(f'|{"-"*14}|{"-"*11}|-------|')
flagged = []
for ac in acs:
    rs = [r for r in rows if r['ac'] == ac]
    if not rs: continue
    s = sum(r['verdict'] == 'satisfied' for r in rs)
    state = 'ok' if s == len(rs) else ('REJECTED' if s == 0 else 'SPLIT')
    if state != 'ok': flagged.append(ac)
    print(f'| {ac:<12} | {s:>4}/{len(rs):<4} | {state} |')

if bad:
    print(f'\n{bad} cells have no verdict. Re-run the sweep — it is idempotent and will fill '
          f'only the gaps. Do not report a sweep as complete on file count alone.')
if flagged:
    print(f'\nLeads to investigate: {", ".join(flagged)}')
    print('Read the rationale of each before believing it:  ac_tally.py <run> --dump --only ' +
          ' '.join(flagged))
    print('A "X is missing" verdict may mean X was outside the payload, not absent from the repo '
          '— check MANIFEST.txt and grep the tree before recording a finding.')
else:
    print('\nNo criterion came back rejected or split. That is weak evidence, not a pass: on '
          'criteria about test coverage this judge waved defects through about 43% of the time '
          '(measured on one corpus, one model).')

if a.dump:
    for r in rows:
        if a.only and r['ac'] not in a.only: continue
        if r['verdict'] == 'not_satisfied' or (a.only and r['ac'] in a.only):
            print(f'\n### {r["ac"]} #{r["n"]} -> {r["verdict"]}\n{r["explanation"]}')
            if r['fix']: print(f'FIX: {r["fix"]}')
