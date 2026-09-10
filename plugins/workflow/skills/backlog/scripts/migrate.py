#!/usr/bin/env python3
"""Split a monolithic backlog markdown file into an index + one detail file per item.

  migrate.py <source.md> <out-dir> [--index-name index.md]

Writes `<out-dir>/<index-name>` and `<out-dir>/<index stem>/` (one detail file per item). The
default index name is `index.md`; pass `--index-name` to keep the name the source already has
when a generator appends to it by that name.

Lossless for items by construction: every item's original block is written verbatim into its
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

# THE CLOSED VOCABULARY IS CORPUS DATA, NOT A CONSTANT. Assuming it is `DONE|KILLED` because that
# is what a ledger's own header documents costs items: the first real corpus documented two words
# and used SIX, and the four undocumented ones retired 7 items that then migrated `open` — into the
# untriaged set, i.e. presented to every grooming pass as live work needing a trigger, two of them
# saying "do not action" verbatim. Derive it from the ledger before migrating (adopting.md says how)
# and add what you find; `verify-migration.mjs` reports marker-shaped words it does not know.
CLOSED_WORDS = "DONE|KILLED|CLOSED|SUPERSEDED|RETIRED|RESOLVED"

# A hedge in front of a closure is not a closure. These are reported, never applied — "mostly
# closed" is a person's call, and the tool guessing either way is worse than the tool asking.
HEDGE = re.compile(r'(HALF|NOT|MOSTLY|PARTLY|PARTIALLY|NEARLY)\s*$', re.I)

# A section heading can carry a status of its own, and the prose under it can say things no item
# repeats — provenance, cross-references, "do not action". Both are content: neither is an item, so
# neither reaches a detail file, and dropping them is silent.
SECTION_MARK = re.compile(r'\*\*\s*(?:[^\w\s]\s*)?(' + CLOSED_WORDS + r')\b')

# A `### ` heading can be a RECORD, not a grouping: the heading names the item and the bullets under
# it are its FIELDS. On the first real corpus all five were this shape, and reading each field as a
# separate item split four records into eight — with a degenerate summary apiece (`What`, `Trigger`)
# and, for the two under a marked heading, `open` on work the heading said was KILLED.
#
# Guarded, because `### ` is a grouping heading in plenty of ledgers: the run is folded ONLY when
# every bullet under the heading is a short bold label ending in a colon. A single ordinary bullet
# in the run means the heading is a grouping and its bullets stay items. Grouping is reported.
FIELD_BULLET = re.compile(r'^- \*\*[A-Z][A-Za-z /]{0,24}:\*\*')


def yaml_single(s):
    r"""A YAML single-quoted scalar. The ONLY escape is a doubled quote; backslashes are literal.

    Not `repr()`, which was here and is Python's escaping, not YAML's: it doubled the backslash in
    a regex an item quoted (`\.md$` became `\\.md$`, so the stored record no longer matched its
    source) and wrote an apostrophe as \' , which YAML does not accept inside single quotes. Both
    shipped. The two readers here survived it only because they scan lines instead of parsing YAML.
    """
    return "'" + " ".join(str(s).split()).replace("'", "''") + "'"

items, no_trigger, closed_n, ambiguous, sections, section_open = [], 0, 0, [], [], []
records = 0
for a, b in zip(secs, secs[1:] + [len(lines)]):
    head = lines[a][3:].strip()
    body = lines[a+1:b]
    idx = [i for i, l in enumerate(body) if re.match(r'^- ', l)]
    intro = "\n".join(body[:idx[0]] if idx else body).strip()
    sections.append(dict(head=head, intro=intro, has_items=bool(idx)))
    sm = SECTION_MARK.search(head)

    # Fold each all-field `### ` run into ONE unit: (start, end, record_heading_or_None).
    subs = [i for i, l in enumerate(body) if l.startswith("### ")]
    folded = {}
    for si in subs:
        end = next((k for k in subs if k > si), len(body))
        run = [k for k in range(si + 1, end) if re.match(r'^- ', body[k])]
        if run and all(FIELD_BULLET.match(body[k]) for k in run):
            folded[run[0]] = (si, end, body[si][4:].strip())
            for k in run[1:]:
                folded[k] = None                       # absorbed into the record above
            records += 1

    units = []
    for j, s in enumerate(idx):
        if s in folded:
            if folded[s] is None:
                continue                               # a field of a record already emitted
            si, end, rec_head = folded[s]
            units.append((si, end, rec_head))
            continue
        units.append((s, idx[j+1] if j+1 < len(idx) else len(body), None))

    for s, e, rec_head in units:
        block = "\n".join(body[s:e]).rstrip()
        if not block.strip():
            continue
        # The status marker has many spellings and two lookalikes that must not match; the table in
        # reference/migration-traps.md is the authority. Detect loosely, scope deliberately, exclude
        # the literal placeholder, and REPORT anything inferred rather than deciding silently.
        #
        # The zone is the item's OWN TEXT, flattened — its bullet line plus the continuation lines
        # under it. Where it ENDS is structural, not positional, and both ends cost a real defect:
        #   a child bullet ends it, or a killed sub-bullet retires its parent (misread 2 of 42);
        #   the left margin ends it, or a trailing `### ` heading and the paragraph under it — which
        #   belong to the next group and carry their own marker — get read as this item's status.
        # Flattening is what makes the zone independent of where the author happened to wrap: at the
        # head, appended at the END when an item is retired in place, or with the parenthetical
        # opening on the next line are all one status, and line 1 saw only the first.
        #
        # Measured on one real ledger: scoping to line 1 migrated four DONE items as `open`, three
        # then reported as untriaged; widening to the whole block retired an open item with a DONE
        # written eleven lines below it about something else.
        own = []
        for k, ln in enumerate(block.split("\n")):
            if k and re.match(r'^\s+[-*] ', ln):
                break                                   # a child bullet: context, not status
            if k and ln.strip() and not ln[0].isspace():
                break                                   # left margin: no longer this item's text
            own.append(ln)
        head_zone = " ".join(" ".join(own).split())
        # The closing paren stays OPTIONAL: it can fall outside the zone when the parenthetical runs
        # past the item's own text. Take the date and stop.
        if rec_head:
            head_zone = rec_head                       # the heading is the record's own text
        zone = re.sub(r'`[^`]*`', ' ', head_zone)   # prose that QUOTES the convention is not a status
        m = re.search(r'\*\*[^*]{0,4}(' + CLOSED_WORDS + r')[^(*]{0,12}\((?P<d>[^)\n]*)\)?', zone)
        if m and (re.search(r'Y{4}|MM-DD', m.group('d')) or HEDGE.search(zone[:m.start(1)])):
            m = None
        # A closure need not carry a date: `**RESOLVED — the A2 five-seam block (:692-713).**` and
        # `**SUPERSEDED the same day …**` are both retirements whose parenthetical is not a date, or
        # is absent. Recognise the marker, say the date is unknown, and REPORT it rather than
        # leaving the item open — the failure this replaces was silence, not a wrong date.
        undated = None
        if not m:
            u = re.search(r'\*\*\s*(?:[^\w\s]\s*)?(' + CLOSED_WORDS + r')\b', zone)
            if u and not HEDGE.search(zone[:u.start(1)]):
                undated = u
        struck = block.lstrip().startswith("- ~~")
        if m:
            status = f"{m.group(1)} ({m.group('d').split(',')[0].strip()})"
        elif undated:
            status = f"{undated.group(1)} (date unknown)"
            ambiguous.append((block[:70], f"{undated.group(1)} with no date parenthetical"))
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
        if rec_head:
            # The heading names the record; its fields do not. Strip a trailing status marker so the
            # summary says what the item IS — `What` and `Trigger` as summaries name nothing.
            summary = " ".join(re.sub(r'\s*[—-]*\s*\*\*[^*]*\*\*\s*$', '', rec_head).split())[:180]
        else:
            hm = re.match(r'^- \*\*(.+?)\*\*', block, re.S) or re.match(r'^- (.+?)[.\n]', block, re.S)
            summary = " ".join((hm.group(1) if hm else block[2:60]).split())[:180]
        if sm and status == "open":
            # Reported, never applied: a retired SECTION usually means its items are done, but a
            # DONE section can still hold one live item and only a person can tell. The one this
            # found had a heading reading "do not action" — grooming would have re-read it as open,
            # which is the very thing that heading was written to stop.
            section_open.append((f"{head[:58]}…", block.split("\n")[0][:80]))
        items.append(dict(head=head, sec=len(sections)-1, block=block, status=status,
                          trigger=trigger, summary=summary))

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
# Grouped under the original headings, with each section's intro prose kept verbatim. The index
# is the whole file's reduction, not just its bullets — a heading that says "do not action" has to
# survive somewhere a reader looks. Readers of this file match on `id:`/`detail:` lines, so prose
# and headings between entries cost them nothing.
# Walked by SECTION, not by item, so a section carrying no bullets at all still reaches the index.
# One exists in the wild: the newest entry on the real corpus is a `### ` heading with Trigger /
# What / Why / Owner paragraphs and no bullet anywhere, which an item-driven walk drops whole —
# a live item with a stated trigger, silently absent from a migration billed as lossless.
n = 0
for si, sec in enumerate(sections):
    index += ["", f"## {sec['head']}", ""]
    if sec["intro"]:
        index += [sec["intro"], ""]
    for it in [i for i in items if i["sec"] == si]:
        n += 1
        iid = f"dw-{n:03d}"
        fn = f"{iid}-{slug(it['summary'])}.md"
        fm = ["---", f"id: {iid}", f"source_section: {yaml_single(it['head'])}",
              f"summary: {yaml_single(it['summary'])}", f"trigger: {yaml_single(it['trigger'])}",
              f"status: {it['status']}", "---", ""]
        (out / stem / fn).write_text("\n".join(fm) + it["block"] + "\n")
        index += [f"- id: {iid}", f"  summary: {it['summary']}", f"  detail: `{stem}/{fn}`"]
(out / index_name).write_text("\n".join(index) + "\n")
print(f"  index              : {out / index_name}  (details under {out / stem}/)")
print(f"  items written      : {len(items)}  ({closed_n} closed, {len(items)-closed_n} open)")
bulletless = [s["head"] for s in sections if not s["has_items"]]
if bulletless:
    print(f"  sections with NO bullet items: {len(bulletless)}  <- content kept in the index, promote by hand")
    for h in bulletless:
        print(f"      {h[:78]}")
if records:
    print(f"  `### ` records folded from their field bullets: {records}")
print(f"  status inferred/ambiguous: {len(ambiguous)}")
if section_open:
    print(f"  open items under a RETIRED/DONE section heading: {len(section_open)}  <- resolve by hand")
    for h, first in section_open:
        print(f"      {h}\n        {first}")
print(f"  open with NO trigger: {no_trigger}  <- migration must surface these, not invent them")
