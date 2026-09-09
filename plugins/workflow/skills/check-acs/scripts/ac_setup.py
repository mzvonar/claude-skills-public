#!/usr/bin/env python3
"""Build an AC-audit run directory from a spec and the change that implemented it.

  ac_setup.py --spec path/to/spec.md --range <base>..<head> [--out DIR] [--paths ...]
  ac_setup.py --spec path/to/spec.md --diff-file some.diff
  ac_setup.py --acs-dir path/to/acs --diff-file some.diff --spec path/to/spec.md

Works with any markdown spec that has a criteria section (a ticket, a story, an RFC).
Produces:
  <out>/spec.md         the criteria section plus whatever precedes it, minus implementation notes
  <out>/acs/<AC>.md     one file per criterion
  <out>/payload.diff    the diff the judge will see
  <out>/MANIFEST.txt    what was included, so a later reader can spot payload gaps

Payload completeness is the failure mode that produces false findings: a judge told "X is
missing" when X was merely outside the diff it was shown will say so, correctly and uselessly.
So --paths defaults to everything the range touched, and anything you exclude is recorded.
"""
import argparse, os, pathlib, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ac_config import cfg

# Headings that commonly introduce criteria, and sections that follow them. Both overridable —
# they are conventions, not rules, and every team names things differently.
SECTION_PATTERNS = [r'acceptance\s+criteria', r'^\s*criteria\s*$', r'requirements',
                    r'acceptance\s+tests', r'\bACs?\b']
STOP_PATTERNS = [r'tasks', r'subtasks', r'dev\s+notes', r'implementation', r'completion',
                 r'dev\s+agent', r'validation', r'testing\s+notes', r'file\s+list']

def sh(*a):
    return subprocess.run(a, capture_output=True, text=True, check=True).stdout

def find_section(text, patterns):
    """Return (start, end) of the first heading matching any pattern, through to the next
    same-or-higher-level heading."""
    for m in re.finditer(r'^(#{1,4})\s+(.+)$', text, re.M):
        title = m.group(2).strip()
        if any(re.search(p, title, re.I) for p in patterns):
            level = len(m.group(1))
            nxt = re.search(rf'^#{{1,{level}}}\s+', text[m.end():], re.M)
            return m.start(), (m.end() + nxt.start() if nxt else len(text))
    return None

def split_acs(section):
    """Split a criteria section into individual criteria.

    Handles the two shapes that cover most specs: a numbered/bulleted list, and one heading
    per criterion. Falls back to the whole section as a single criterion rather than guessing
    badly — a wrong split silently changes what is being judged.
    """
    # shape 1: headings like '### AC3 — ...'
    heads = list(re.finditer(r'^#{2,5}\s+.*?\b(AC[-\w.]*\d[\w.-]*)\b.*$', section, re.M | re.I))
    if len(heads) >= 2:
        out = []
        for i, h in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(section)
            out.append((h.group(1).upper(), section[h.start():end].strip()))
        return out
    # shape 2: a numbered or bulleted list. Split only at the list's OUTERMOST indent level —
    # criteria routinely carry indented sub-bullets, and splitting those out invents criteria
    # that nobody wrote and silently changes what is being judged.
    body = section[section.index('\n'):] if '\n' in section else section
    marker = re.compile(r'^([ \t]*)(?:\d+[.)]|[-*])\s+\S', re.M)
    indents = [len(m.group(1).expandtabs(4)) for m in marker.finditer(body)]
    if not indents:
        return [('AC1', section.strip())]
    top = min(indents)
    parts, cur = [], None
    for line in body.split('\n'):
        m = marker.match(line + ' ')
        if m and len(m.group(1).expandtabs(4)) == top:
            if cur is not None:
                parts.append('\n'.join(cur))
            cur = [line]
        elif cur is not None:
            cur.append(line)
    if cur is not None:
        parts.append('\n'.join(cur))
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return [('AC1', section.strip())]
    out, seen = [], {}
    for i, p in enumerate(parts, 1):
        m = re.match(r'\s*(?:\d+[.)]|[-*])\s+\**`?(AC[-\w.]*)`?', p, re.I)
        num = re.match(r'\s*(\d+)[.)]', p)
        name = (m.group(1).upper() if m else f'AC{num.group(1) if num else i}')
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            name = f'{name}-{seen[name]}'
        out.append((name, p))
    return out

ap = argparse.ArgumentParser()
ap.add_argument('--spec', required=True, help='markdown file containing the criteria')
ap.add_argument('--range', help='git range, e.g. abc^..abc or main..HEAD')
ap.add_argument('--diff-file', help='use an existing diff instead of a git range')
ap.add_argument('--acs-dir', help='use pre-split criteria files instead of splitting --spec')
ap.add_argument('--out', default=None,
                help='run directory (default: config outDir, else ac-audit/<key>; <key> = the spec file stem)')
ap.add_argument('--paths', nargs='*', default=None, help='limit the diff (default: everything)')
ap.add_argument('--section', nargs='*', default=None,
                help='override criteria-heading patterns (default: config sectionPatterns, else built-ins)')
a = ap.parse_args()
if not a.range and not a.diff_file:
    sys.exit('need --range or --diff-file')

spec_p = pathlib.Path(a.spec)
text = spec_p.read_text()
out = pathlib.Path(a.out or str(cfg('outDir', 'ac-audit/<key>')).replace('<key>', spec_p.stem))
(out / 'acs').mkdir(parents=True, exist_ok=True)

span = find_section(text, a.section or cfg('sectionPatterns') or SECTION_PATTERNS)
if not span and not a.acs_dir:
    sys.exit(f'no criteria section found in {a.spec}. Pass --section with a regex that matches '
             f'its heading, or --acs-dir with the criteria already split into files.')
# With --acs-dir the criteria come from disk, so an unrecognised heading is not fatal — that is
# the whole point of the flag. The judge then sees the spec up to the first implementation
# section, which is the best available context.
sec_start, sec_end = span if span else (len(text), len(text))

# The judge sees everything up to the end of the criteria, minus sections that carry the
# implementer's own account of what they did — those bias it toward agreeing.
head = text[:sec_start]
for pat in STOP_PATTERNS:
    m = re.search(rf'^#{{1,4}}\s+.*{pat}.*$', head, re.M | re.I)
    if m:
        head = head[:m.start()]
(out / 'spec.md').write_text((head.rstrip() + '\n\n' + text[sec_start:sec_end].rstrip() + '\n').lstrip())

if a.acs_dir:
    acs = [(p.stem, p.read_text()) for p in sorted(pathlib.Path(a.acs_dir).glob('*.md'))]
    for name, body in acs:
        (out / 'acs' / f'{name}.md').write_text(body)
else:
    acs = split_acs(text[sec_start:sec_end])
    for name, body in acs:
        (out / 'acs' / f'{name}.md').write_text(body + '\n')

if a.diff_file:
    diff = pathlib.Path(a.diff_file).read_text()
    included = omitted = []
else:
    cmd = ['git', 'diff', a.range] + (['--'] + a.paths if a.paths else [])
    diff = sh(*cmd)
    included = sh(*(['git', 'diff', '--name-only', a.range] + (['--'] + a.paths if a.paths else []))).split()
    omitted = sorted(set(sh('git', 'diff', '--name-only', a.range).split()) - set(included))
(out / 'payload.diff').write_text(diff)

(out / 'MANIFEST.txt').write_text(
    f'spec: {a.spec}\nsource: {a.range or a.diff_file}\npaths: {a.paths or "ALL"}\n'
    f'criteria ({len(acs)}): {", ".join(n for n, _ in acs)}\n'
    f'diff bytes: {len(diff)} (~{len(diff)//4} tokens)\n'
    + (f'files included ({len(included)}):\n' + ''.join(f'  {f}\n' for f in included) if included else '')
    + (f'\nFILES OMITTED FROM THE PAYLOAD ({len(omitted)}) — check any "X is missing" verdict\n'
       f'against these before believing it:\n' + ''.join(f'  {f}\n' for f in omitted) if omitted else ''))

print(f'{out}: {len(acs)} criteria, diff {len(diff)} bytes (~{len(diff)//4} tokens)')
if len(diff) < 2000 or len(diff) < len(text):
    print('  WARNING: the diff is small relative to the spec. A range that captured only the '
          'spec commit, or the wrong base, is the usual cause — check MANIFEST.txt file list '
          'before sweeping, or every criterion will read as unimplemented.')
print(f'  criteria: {", ".join(n for n, _ in acs)}')
if omitted:
    print(f'  WARNING: {len(omitted)} changed files omitted from the payload — see MANIFEST.txt')
