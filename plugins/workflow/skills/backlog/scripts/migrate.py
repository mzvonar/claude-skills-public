#!/usr/bin/env python3
"""Split a monolithic backlog markdown file into an index + one detail file per item.

  migrate.py <source.md> <out-dir> [--index-name index.md]

Writes `<out-dir>/<index-name>` and `<out-dir>/<index stem>/` (one detail file per item). The
default index name is `index.md`; pass `--index-name` to keep the name the source already has
when a generator appends to it by that name.

Lossless by construction: every item's original block is written verbatim into its
detail file's body. The frontmatter is DERIVED from that block, never invented — a
field the source does not state is emitted empty and reported, not guessed.
"""
import argparse, re, pathlib

ap = argparse.ArgumentParser()
ap.add_argument('source', help='the monolithic backlog markdown file')
ap.add_argument('out', help='directory to write the index and detail files into')
ap.add_argument('--index-name', default='index.md',
                help='file name of the index inside <out> (default: index.md); the detail '
                     'directory is named after its stem')
args = ap.parse_args()

src, out = pathlib.Path(args.source), pathlib.Path(args.out)
index_name = args.index_name
stem = pathlib.Path(index_name).stem
(out / stem).mkdir(parents=True, exist_ok=True)
lines = src.read_text().split("\n")
secs = [i for i, l in enumerate(lines) if l.startswith("## ")]

def slug(s):
    s = re.sub(r'`[^`]*`', '', s)
    s = re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()
    return (s[:52].rstrip('-')) or "item"

items, no_trigger, closed_n, ambiguous = [], 0, 0, []
for a, b in zip(secs, secs[1:] + [len(lines)]):
    head = lines[a][3:].strip()
    body = lines[a+1:b]
    idx = [i for i, l in enumerate(body) if re.match(r'^- ', l)]
    for j, s in enumerate(idx):
        e = idx[j+1] if j+1 < len(idx) else len(body)
        block = "\n".join(body[s:e]).rstrip()
        if not block.strip():
            continue
        # Status is written many ways in a hand-maintained ledger: `**DONE (d)**`, `**✅ DONE (d, ref)**`
        # with an emoji, `**DONE upstream (d)**`, `**KILLED (d, ...)**`, and struck-through. Two
        # traps: `HALF DONE (d)` is not a status, and prose quoting `**DONE (YYYY-MM-DD)**` as the
        # convention is not one either. Detect loosely, restrict to the item's HEAD, exclude the
        # literal placeholder, and REPORT anything inferred rather than silently deciding.
        # The item's OWN bullet line, not the first N characters: a 200-char window reaches into
        # nested sub-bullets, and an item whose CHILD was killed would inherit the child's status.
        # Measured on one corpus: that misread 2 of 42 items before this was scoped to line 1.
        head_zone = block.split("\n")[0]
        # The closing paren is OPTIONAL: a status parenthetical can wrap onto the next line
        # (`- **DONE (2026-08-31, chore/... ` closes two lines later), so requiring `)` on
        # line 1 silently drops it. Line-spanning data, per-line pattern — take the date and stop.
        m = re.search(r'\*\*[^*]{0,4}(?<!HALF )(DONE|KILLED)[^(*]{0,12}\((?P<d>[^)\n]*)\)?', head_zone)
        if m and re.search(r'Y{4}|MM-DD', m.group('d')):
            m = None
        struck = block.lstrip().startswith("- ~~")
        if m:
            status = f"{m.group(1)} ({m.group('d').split(',')[0].strip()})"
        elif struck:
            status = "KILLED (date unknown)"
            ambiguous.append((block[:70], "struck through, no date"))
        else:
            status = "open"
        if status != "open":
            closed_n += 1
        tm = re.search(r'\*\*Trigger:?\*\*:?\s*(.+?)(?:\n\s*\n|\Z)', block, re.S)
        trigger = " ".join(tm.group(1).split())[:200] if tm else ""
        if not trigger and status == "open":
            no_trigger += 1
        hm = re.match(r'^- \*\*(.+?)\*\*', block, re.S) or re.match(r'^- (.+?)[.\n]', block, re.S)
        summary = " ".join((hm.group(1) if hm else block[2:60]).split())[:180]
        items.append(dict(head=head, block=block, status=status, trigger=trigger, summary=summary))

index = ["---",
         "# The migrated ledger is deferred work: an open item must say when it becomes",
         "# actionable. Drop this line to run a plain backlog, where items are actionable",
         "# when picked and `trigger` is optional.",
         "policy: deferred-work",
         "---",
         "",
         "# Backlog — index",
         "",
         "One entry per item. `detail:` points at the file holding the full record; that file's",
         "frontmatter is the source of truth for `trigger` and `status`. Entries appended here by a",
         "tool with no `detail:` are untriaged — grooming promotes them.",
         ""]
for n, it in enumerate(items, 1):
    iid = f"dw-{n:03d}"
    fn = f"{iid}-{slug(it['summary'])}.md"
    fm = ["---", f"id: {iid}", f"source_section: {it['head']!r}",
          f"summary: {it['summary']!r}", f"trigger: {it['trigger']!r}",
          f"status: {it['status']}", "---", ""]
    (out / stem / fn).write_text("\n".join(fm) + it["block"] + "\n")
    index += [f"- id: {iid}", f"  summary: {it['summary']}", f"  detail: `{stem}/{fn}`"]
(out / index_name).write_text("\n".join(index) + "\n")
print(f"  index              : {out / index_name}  (details under {out / stem}/)")
print(f"  items written      : {len(items)}  ({closed_n} closed, {len(items)-closed_n} open)")
print(f"  status inferred/ambiguous: {len(ambiguous)}")
print(f"  open with NO trigger: {no_trigger}  <- migration must surface these, not invent them")
