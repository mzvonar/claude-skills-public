#!/usr/bin/env python3
"""Mechanical existence check for the concrete artifacts a criterion names.

  ac_artifacts.py <run-dir> <AC> [--repo .] [--expect extra_terms.txt] [--ignore RE]

Why this exists as a separate, dumber tool: the LLM judge is strong on semantics but measurably
weak on criteria of the form "a test / an event / a column / a file named X exists". Measured on
one corpus with one model, it waved such defects through 43% of the time, and its verdict was NOT
monotone —
deleting three more required test cases made it *less* likely to reject (17/30 vs 26/30,
p=0.02). Existence, unlike semantics, needs no judgment: search for the string.

So this tool never decides anything. It extracts the literal artifact names a criterion mentions
and reports, for each, whether it appears in the diff, elsewhere in the repo, or nowhere. The
three states matter and are different:

  IN DIFF   the change introduces or touches it.
  REPO ONLY it exists but this change did not touch it — fine for something pre-existing,
            a real finding if the criterion said this change must add it.
  MISSING   the string appears nowhere. The strongest mechanical signal available.

Extraction is heuristic and will pick up prose. That is deliberate: a noisy list you skim beats
a clean list that silently dropped the one artifact that mattered. Prune with --ignore, and add
anything the criterion states in prose rather than in backticks via --expect (one term per
line) — extraction may be fuzzy, but verification stays a literal string search.
"""
import argparse, pathlib, re, subprocess, sys

ap = argparse.ArgumentParser()
ap.add_argument('run'); ap.add_argument('ac')
ap.add_argument('--repo', default='.'); ap.add_argument('--diff', default='payload')
ap.add_argument('--expect'); ap.add_argument('--ignore', default=None)
ap.add_argument('--min-len', type=int, default=3)
a = ap.parse_args()

run = pathlib.Path(a.run)
ac_file = run / 'acs' / f'{a.ac}.md'
if not ac_file.exists():
    sys.exit(f'no such criterion: {ac_file}')
text = ac_file.read_text()
diff = (run / f'{a.diff}.diff').read_text() if (run / f'{a.diff}.diff').exists() else ''

# --- extraction ------------------------------------------------------------------------------
terms = set()
terms |= set(re.findall(r'`([^`\n]+)`', text))                     # backticked
terms |= set(re.findall(r'"([^"\n]{3,60})"', text))                # double-quoted
terms |= set(re.findall(r'\b([\w./-]+\.(?:[a-z]{1,5}))\b', text))  # file-ish paths
if a.expect:
    terms |= {l.strip() for l in open(a.expect) if l.strip() and not l.startswith('#')}

STOP = re.compile(r'^(?:[0-9.,%]+|true|false|null|and|or|not|the|a|an|is|are|no|yes|e\.g\.)$', re.I)
clean = set()
for t in terms:
    t = t.strip().strip('.,;:')
    if len(t) < a.min_len or STOP.match(t):
        continue
    if a.ignore and re.search(a.ignore, t):
        continue
    clean.add(t)

# --- verification: literal search, no interpretation ------------------------------------------
def repo_hits(term):
    for cmd in (['git', 'grep', '-I', '-F', '-c', '--', term],
                ['grep', '-rIF', '-c', '--', term, '.']):
        try:
            p = subprocess.run(cmd, cwd=a.repo, capture_output=True, text=True, timeout=60)
        except Exception:
            continue
        if p.returncode in (0, 1):
            return sum(int(l.rsplit(':', 1)[1]) for l in p.stdout.splitlines()
                       if ':' in l and l.rsplit(':', 1)[1].isdigit())
    return 0

rows = []
for t in sorted(clean, key=lambda s: (-len(s), s)):
    in_diff = t in diff
    n = repo_hits(t)
    rows.append((t, in_diff, n, 'IN DIFF' if in_diff else ('REPO ONLY' if n else 'MISSING')))

w = min(60, max([len(r[0]) for r in rows] + [9]))
print(f'\n{a.ac}: {len(rows)} artifact names extracted\n')
print(f'| {"artifact":<{w}} | repo hits | state |')
print(f'|{"-"*(w+2)}|-----------|-------|')
for t, _, n, state in rows:
    print(f'| {t[:w]:<{w}} | {n:>9} | {state} |')

missing = [r[0] for r in rows if r[3] == 'MISSING']
repo_only = [r[0] for r in rows if r[3] == 'REPO ONLY']
print(f'\nMISSING ({len(missing)}): {", ".join(missing) if missing else "none"}')
print(f'REPO ONLY ({len(repo_only)}): {", ".join(repo_only[:12])}'
      f'{" ..." if len(repo_only) > 12 else ""}')
print('\nThis is a presence report, not a verdict. Extraction is heuristic, so read the list '
      'before acting:\n'
      '  - MISSING on something the criterion requires this change to add  -> a finding.\n'
      '  - MISSING on prose the extractor mistook for an identifier        -> ignore it.\n'
      '  - REPO ONLY on something the criterion says this change must add  -> a finding.\n'
      '  - REPO ONLY on something described as pre-existing                -> expected.')
