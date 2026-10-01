#!/usr/bin/env python3
"""collect-plan.py — step 1 of /describe:plan: gather the plan's text and ground it against the tree.

Usage:
  collect-plan.py [--from FILE[#HEADING]]... [--grep-from FILE REGEX]... [--epic N] [--story KEY]
                  [--slug NAME] [--out DIR]
                  [--epics-file F] [--status-file F] [--stories-dir D] [--proposals-glob G]

Inputs are DOCUMENTS, never a planning tool's layout: a whole file, one heading's subtree of a file
(`docs/epics.md#Epic 15` — a case-insensitive substring of the heading text, or `#re:^Epic 15\\b`
for a regex), or the paragraphs of a file that match a regex. `--epic` and `--story` are sugar over
those, driven by `.claude/claude-skills.json` → `describe.plan.*` (SKILL.md → Configuration) or the
matching flags; without either they say so and exit 2.

Writes, under <root>/.describe-changes/plan/<slug>/ by default:
  sources/NN-<name>.md   each extracted input, verbatim
  plan.md                all of them, each under a `<!-- source: … -->` marker — what the analyst reads
  meta.json              repo, root, branch, head, the language census, the inputs, the slug
  structure.json         headings; the units (level-3 headings) with their acceptance-criteria lines; and
                         `verbatim` — the plan's own acceptance-criteria and open-questions sections, word
                         for word, each with the file and the lines it came from (the page shows them as written)
  citations.json         every repo path the plan names (exists / in range / missing), every backticked
                         identifier and how many tracked files contain it — the grounding pass
The last line printed is `OUT=<dir>`. Exit 2 when nothing was collected.
"""
import argparse, collections, datetime, glob, json, os, re, subprocess, sys

LANG_BY_EXT = {
    ".kt": "Kotlin", ".kts": "Kotlin", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
    ".mjs": "JavaScript", ".cjs": "JavaScript", ".jsx": "JavaScript", ".py": "Python", ".java": "Java",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".cs": "C#", ".swift": "Swift", ".php": "PHP", ".scala": "Scala",
    ".sql": "SQL", ".sh": "Shell", ".bash": "Shell", ".yaml": "YAML", ".yml": "YAML", ".css": "CSS", ".scss": "CSS",
    ".html": "HTML", ".c": "C", ".h": "C", ".cpp": "C++", ".hpp": "C++", ".m": "Objective-C", ".dart": "Dart",
    ".ex": "Elixir", ".exs": "Elixir", ".clj": "Clojure", ".proto": "Protobuf", ".tf": "Terraform",
    ".json": "JSON", ".toml": "TOML", ".graphql": "GraphQL", ".prisma": "Prisma", ".vue": "Vue", ".svelte": "Svelte",
}
HEAD_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
# A repo path: at least one directory segment and an extension, optionally `:a` or `:a-b`. Not
# preceded by a URL scheme or another path character, so `https://x/y.md` and `a/b/c.md` inside a
# longer token are not double-counted.
# The extension starts with a letter: `13.2/13.3` (two story numbers) is not a path.
PATH_RE = re.compile(r"(?<![\w/:.\-])((?:[A-Za-z0-9_@.\-]+/)+[A-Za-z0-9_@.\-]+\.[A-Za-z][A-Za-z0-9]{0,7})(?::(\d+)(?:-(\d+))?)?")
BARE_FILE_RE = re.compile(r"`([A-Za-z0-9_.\-]+\.[A-Za-z0-9]{1,8})`")
SYMBOL_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]{3,63})`")
URL_RE = re.compile(r"https?://\S+")
AC_RE = re.compile(r"^\s*(?:\*\*(Given|When|Then|And|But)\*\*|(?:Given|When|Then|And|But)\b|- \[[ xX]\]|AC-?\d+\b)")
MAX_SYMBOLS = 200
# The plan's own acceptance-criteria and open-questions sections, found by WHAT A SECTION IS CALLED —
# never by a planning tool's layout. A section is a heading (with its subtree) or a bold label alone on
# its line (`**Acceptance Criteria:**`, the shape an epic list uses inside each story). The name is
# matched from its start, case-insensitively, after emphasis, a leading number and a trailing colon are
# stripped; `acs?$` takes the whole name so a criterion's own heading (`AC-1 — …`) is not a section.
# Generic English on purpose: a repo adds its own names under describe.plan.verbatim (SKILL.md →
# Configuration), and they extend these, never replace them.
VERBATIM_DEFAULT = {
    "acceptance": [r"acceptance\s+criteria\b", r"acceptance\s+(?:tests?|scenarios?)\b", r"acs?$"],
    "questions": [r"open\s+(?:questions?|issues?|decisions?|points?)\b", r"unresolved\s+(?:questions?|issues?)\b",
                  r"outstanding\s+questions?\b", r"questions?\s+for\b", r"decisions?\s+(?:needed|required|pending)\b",
                  r"questions?$"],
}
LABEL_RE = re.compile(r"^\s*(?:\*\*|__)(?P<name>[^*_].*?)(?:\*\*|__)\s*:?\s*$")
RULE_RE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")

def run(args, cwd, check=True):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=check).stdout

def repo_root():
    try:
        return run(["git", "rev-parse", "--show-toplevel"], os.getcwd()).strip()
    except Exception:
        return os.getcwd()

def load_config(root):
    p = os.path.join(root, ".claude", "claude-skills.json")
    try:
        return (json.load(open(p, encoding="utf-8")).get("describe") or {}).get("plan") or {}
    except Exception:
        return {}

def read_text(path):
    return open(path, encoding="utf-8", errors="replace").read()

def headings(lines):
    """(line index, level, text) of every heading — fenced code blocks skipped, where a `#` is a comment."""
    out, fence = [], None
    for i, l in enumerate(lines):
        m = FENCE_RE.match(l)
        if m:
            fence = None if fence == m.group(1) else (fence or m.group(1)); continue
        if fence: continue
        h = HEAD_RE.match(l)
        if h: out.append((i, len(h.group(1)), h.group(2)))
    return out

def subtree(lines, idx, level):
    j = idx + 1
    fence = None
    while j < len(lines):
        m = FENCE_RE.match(lines[j])
        if m:
            fence = None if fence == m.group(1) else (fence or m.group(1))
        elif not fence:
            h = HEAD_RE.match(lines[j])
            if h and len(h.group(1)) <= level: break
        j += 1
    return lines[idx:j]

def extract_headings(text, spec):
    """Every heading matching `spec` (substring, or `re:` regex), each with its subtree and the index of
    its first line in `text` — what maps a verbatim section back to the file's own line numbers."""
    lines = text.splitlines()
    pat = re.compile(spec[3:], re.I) if spec.startswith("re:") else re.compile(re.escape(spec), re.I)
    return [(t, "\n".join(subtree(lines, i, lv)), i) for i, lv, t in headings(lines) if pat.search(t)]

def section_name(raw):
    """A heading or label reduced to the words that say what the section IS."""
    s = re.sub(r"[*_`]+", "", raw).strip()
    s = re.sub(r"^(?:§\s*)?\d+(?:\.\d+)*[.)]?\s+", "", s)
    return s.rstrip(":").strip().lower()

def verbatim_kind(raw, patterns):
    name = section_name(raw)
    for kind, pats in patterns.items():
        if any(re.match(p, name) for p in pats):
            return kind
    return None

def verbatim_sections(text, patterns):
    """(kind, title, context, first, last) for every acceptance-criteria or open-questions section of
    one source — 0-based line indexes into `text`, trailing blank lines and thematic breaks trimmed. A
    match inside a section already taken is part of it, not a section of its own; fenced code is never
    read, so a `## Acceptance Criteria` inside an example block is not one."""
    lines = text.splitlines()
    hs = headings(lines)
    fenced, fence = set(), None
    for i, l in enumerate(lines):
        m = FENCE_RE.match(l)
        if m:
            fenced.add(i); fence = None if fence == m.group(1) else (fence or m.group(1)); continue
        if fence: fenced.add(i)
    head_at = {i: (lv, t) for i, lv, t in hs}
    labels = {}
    for i, l in enumerate(lines):
        if i in fenced or i in head_at: continue
        m = LABEL_RE.match(l)
        if m and verbatim_kind(m.group("name"), patterns): labels[i] = m.group("name").strip().rstrip(":").strip()
    def context(i, level):
        for j, lv, t in reversed(hs):
            if j < i and lv < level: return t
        return None
    found, taken = [], -1
    for i in sorted(set(head_at) | set(labels)):
        if i <= taken: continue
        if i in head_at:
            lv, t = head_at[i]
            kind = verbatim_kind(t, patterns)
            if not kind: continue
            last = i + len(subtree(lines, i, lv)) - 1
            title, ctx = t, context(i, lv)
        else:
            title = labels[i]; kind = verbatim_kind(title, patterns)
            nxt = [j for j in list(head_at) + list(labels) if j > i]
            last = (min(nxt) if nxt else len(lines)) - 1
            ctx = context(i, 7)
        while last > i and (not lines[last].strip() or RULE_RE.match(lines[last])): last -= 1
        found.append((kind, title, ctx, i, last)); taken = last
    return found

def extract_paragraphs(text, regex):
    """The blank-line-separated blocks matching `regex` — a paragraph, a list, a status block."""
    pat = re.compile(regex, re.I | re.M)
    blocks, cur = [], []
    for l in text.splitlines():
        if l.strip(): cur.append(l)
        elif cur: blocks.append("\n".join(cur)); cur = []
    if cur: blocks.append("\n".join(cur))
    return [b for b in blocks if pat.search(b)]

def language_census(tracked):
    c = collections.Counter()
    for f in tracked:
        lang = LANG_BY_EXT.get(os.path.splitext(f)[1].lower())
        if lang: c[lang] += 1
    return dict(c.most_common())

def slugify(s, limit=40):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:limit].rstrip("-") or "plan"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="froms", action="append", default=[], metavar="FILE[#HEADING]")
    ap.add_argument("--grep-from", dest="greps", action="append", nargs=2, default=[], metavar=("FILE", "REGEX"))
    ap.add_argument("--epic"); ap.add_argument("--story")
    ap.add_argument("--slug"); ap.add_argument("--out")
    ap.add_argument("--epics-file"); ap.add_argument("--status-file"); ap.add_argument("--stories-dir"); ap.add_argument("--proposals-glob")
    a = ap.parse_args()

    root = repo_root()
    cfg = load_config(root)
    epics = a.epics_file or cfg.get("epics")
    status = a.status_file or cfg.get("status")
    stories = a.stories_dir or cfg.get("stories")
    proposals = a.proposals_glob or cfg.get("proposals")
    out_base = a.out or os.path.join(root, cfg.get("outDir") or ".describe-changes/plan")

    inputs = []   # (kind, file, spec)
    for f in a.froms:
        file, _, spec = f.partition("#")
        inputs.append(("heading" if spec else "file", file, spec or None))
    for file, rx in a.greps:
        inputs.append(("grep", file, rx))
    if a.epic:
        if not epics:
            print("--epic needs the epics file: set describe.plan.epics in .claude/claude-skills.json or pass --epics-file", file=sys.stderr); sys.exit(2)
        n = re.escape(a.epic)
        inputs.append(("heading", epics, rf"re:\bEpic {n}\b"))
        inputs.append(("grep", epics, rf"\bEpic {n} dependencies\b"))
        if status:
            inputs.append(("grep", status, rf"^\s*(#.*\bEPIC {n}\b|epic-{n}(-retrospective)?:|{n}-\d+[a-z]?-)"))
    if a.story:
        if not stories:
            print("--story needs the stories dir: set describe.plan.stories in .claude/claude-skills.json or pass --stories-dir", file=sys.stderr); sys.exit(2)
        hits = sorted(glob.glob(os.path.join(root, stories, f"{a.story}*.md"))) or sorted(glob.glob(os.path.join(root, stories, f"*{a.story}*.md")))
        if not hits:
            print(f"--story {a.story}: no file under {stories} matches", file=sys.stderr); sys.exit(2)
        for h in hits: inputs.append(("file", os.path.relpath(h, root), None))
    if not inputs:
        ap.print_usage(); print("nothing to collect: pass --from, --grep-from, --epic or --story", file=sys.stderr); sys.exit(2)

    sources = []   # (label, text)
    origins = []   # (file, index of the source's first line in that file) — parallel to `sources`; the
                   # index is None where the text is not one contiguous run of the file (a grep's blocks)
    def resolve(file):
        p = file if os.path.isabs(file) else os.path.join(root, file)
        if not os.path.isfile(p):
            print(f"no such file: {file}", file=sys.stderr); sys.exit(2)
        return p
    for kind, file, spec in inputs:
        text = read_text(resolve(file))
        rel = os.path.relpath(resolve(file), root)
        if kind == "file":
            sources.append((rel, text)); origins.append((rel, 0))
        elif kind == "heading":
            hits = extract_headings(text, spec)
            if not hits: print(f"warning: no heading in {rel} matches {spec!r}", file=sys.stderr)
            for t, body, at in hits:
                sources.append((f"{rel}#{t}", body)); origins.append((rel, at))
        else:
            hits = extract_paragraphs(text, spec)
            if not hits: print(f"warning: nothing in {rel} matches /{spec}/", file=sys.stderr)
            if hits:
                sources.append((f"{rel} ~ /{spec}/", "\n\n".join(hits))); origins.append((rel, None))
    # A proposal the extracted text names is part of the plan: include it whole, once.
    if proposals:
        known = {os.path.relpath(p, root) for p in glob.glob(os.path.join(root, proposals))}
        named = set()
        joined = "\n".join(t for _, t in sources)
        for p in known:
            if os.path.basename(p) in joined and p not in {lbl for lbl, _ in sources}:
                named.add(p)
        for p in sorted(named):
            sources.append((p, read_text(os.path.join(root, p)))); origins.append((p, 0))
    if not any(t.strip() for _, t in sources):
        print("nothing to describe: the inputs produced no text", file=sys.stderr); sys.exit(2)

    slug = a.slug or (f"epic-{a.epic}" if a.epic else None) or (slugify(a.story) if a.story else None)
    if not slug:
        first = next((h for _, lv, h in headings(sources[0][1].splitlines())), None) or os.path.basename(sources[0][0])
        slug = slugify(first)
    out = os.path.join(out_base, slug)
    os.makedirs(os.path.join(out, "sources"), exist_ok=True)
    for stale in glob.glob(os.path.join(out, "sources", "*.md")): os.remove(stale)
    plan_parts = []
    for i, (label, text) in enumerate(sources, 1):
        name = f"{i:02d}-{slugify(label.split('#')[-1].split(' ~ ')[0], 48)}.md"
        open(os.path.join(out, "sources", name), "w", encoding="utf-8").write(text.rstrip() + "\n")
        plan_parts.append(f"<!-- source: {label} -->\n\n{text.rstrip()}\n")
    plan = "\n\n".join(plan_parts)
    open(os.path.join(out, "plan.md"), "w", encoding="utf-8").write(plan)

    # ---- structure: headings and units -----------------------------------------------------------
    lines = plan.splitlines()
    hs = headings(lines)
    units = []
    for i, lv, t in hs:
        if lv != 3: continue
        body = subtree(lines, i, lv)
        acs = [l.strip() for l in body[1:] if AC_RE.match(l)]
        units.append({"heading": t, "line": i + 1, "acceptance_lines": len(acs), "acs": acs[:60]})
    # The plan's own acceptance criteria and open questions, word for word, per source: `start`/`end`
    # are the lines IN THE FILE, so a comment on the page lands on the line the author will edit.
    patterns = {k: list(v) for k, v in VERBATIM_DEFAULT.items()}
    for kind, extra in ((cfg.get("verbatim") or {}) if isinstance(cfg.get("verbatim"), dict) else {}).items():
        if kind in patterns and isinstance(extra, list):
            patterns[kind] += [p for p in extra if isinstance(p, str)]
    verbatim = []
    for (label, text), (file, offset) in zip(sources, origins):
        src_lines = text.splitlines()
        for kind, title, ctx, first, last in verbatim_sections(text, patterns):
            verbatim.append({"kind": kind, "title": title, "context": ctx, "source": label, "file": file,
                             "start": offset + first + 1 if offset is not None else None,
                             "end": offset + last + 1 if offset is not None else None,
                             "text": "\n".join(src_lines[first:last + 1])})
    structure = {"headings": [{"level": lv, "text": t, "line": i + 1} for i, lv, t in hs], "units": units,
                 "verbatim": verbatim}
    json.dump(structure, open(os.path.join(out, "structure.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    # ---- grounding: every path and symbol the plan names, checked against the tree ---------------
    try:
        tracked = set(run(["git", "ls-files", "-z"], root).split("\0")) - {""}
    except Exception:
        tracked = set()
    by_base = collections.defaultdict(list)
    for f in tracked: by_base[os.path.basename(f)].append(f)
    # The sources' text, not plan.md: the `<!-- source: … -->` markers name the plan's own files and
    # would count as citations of themselves.
    clean = URL_RE.sub(" ", "\n".join(t for _, t in sources))
    paths, mentions = {}, collections.Counter()
    for m in PATH_RE.finditer(clean):
        p, a1, b1 = m.group(1), m.group(2), m.group(3)
        p = p.rstrip(".,;:)")
        mentions[p] += 1
        entry = paths.setdefault(p, {"path": p, "exists": p in tracked or os.path.isfile(os.path.join(root, p)),
                                     "tracked": p in tracked, "ranges": [], "lines": None})
        if a1:
            entry["ranges"].append([int(a1), int(b1) if b1 else int(a1)])
    # A plan often cites a path RELATIVE to the thing a row is about (`mocks/handlers.ts:141-157` under
    # an "operator-ui" row). One tracked file ending in that path is what the author meant; say so
    # rather than reporting it missing, and keep the line range for the resolved file.
    suffix_index = collections.defaultdict(list)
    for f in tracked:
        parts = f.split("/")
        for i in range(1, len(parts)):
            suffix_index["/".join(parts[i:])].append(f)
    for p, e in paths.items():
        e["mentions"] = mentions[p]
        if not e["exists"]:
            cands = suffix_index.get(p, [])
            e["resolved_to"] = cands[0] if len(cands) == 1 else None
            e["candidates"] = cands[:6]
            if e["resolved_to"]:
                e["exists"] = True
                e["resolved"] = True
                p_real = e["resolved_to"]
            else:
                p_real = None
        else:
            p_real = p
        if e["exists"]:
            try:
                n = sum(1 for _ in open(os.path.join(root, p_real), encoding="utf-8", errors="replace"))
            except Exception:
                n = None
            e["lines"] = n
            e["out_of_range"] = [r for r in e["ranges"] if n is not None and (r[0] < 1 or r[1] > n)]
        else:
            e["out_of_range"] = []
    bare = {}
    for m in BARE_FILE_RE.finditer(clean):
        name = m.group(1)
        if "/" in name or name in paths: continue
        cands = by_base.get(name, [])
        bare[name] = {"name": name, "resolved": cands[0] if len(cands) == 1 else None,
                      "candidates": cands[:6], "mentions": bare.get(name, {}).get("mentions", 0) + 1}
    symbols = collections.Counter()
    for m in SYMBOL_RE.finditer(clean):
        tok = m.group(1)
        if tok in bare or tok in paths or "." in tok: continue
        symbols[tok] += 1
    # The plan's own documents are excluded from the search: a symbol that occurs only in the plan
    # is exactly the "nowhere in the tree" this pass exists to find, and the plan always mentions it.
    plan_files = {lbl.split("#")[0].split(" ~ ")[0] for lbl, _ in sources}
    excludes = [f":(exclude){p}" for p in sorted(plan_files)]
    sym_rows = []
    for tok, n in symbols.most_common(MAX_SYMBOLS):
        try:
            hits = run(["git", "grep", "-I", "-l", "-w", "-F", "-e", tok, "--", ".", *excludes], root, check=False)
            files = [x for x in hits.splitlines() if x]
        except Exception:
            files = []
        sym_rows.append({"symbol": tok, "mentions": n, "files": len(files), "sample": files[:4]})
    citations = {
        "paths": sorted(paths.values(), key=lambda e: (e["exists"], -e["mentions"], e["path"])),
        "bare_files": sorted(bare.values(), key=lambda e: e["name"]),
        "symbols": sym_rows,
        "summary": {
            "paths": len(paths), "paths_found": sum(1 for e in paths.values() if e["exists"]),
            "paths_out_of_range": sum(1 for e in paths.values() if e.get("out_of_range")),
            "bare_files": len(bare), "bare_resolved": sum(1 for e in bare.values() if e["resolved"]),
            "symbols": len(sym_rows), "symbols_found": sum(1 for s in sym_rows if s["files"]),
        },
    }
    json.dump(citations, open(os.path.join(out, "citations.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    try:
        branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root).strip()
        head = run(["git", "rev-parse", "--short", "HEAD"], root).strip()
    except Exception:
        branch, head = "", ""
    meta = {"repo": os.path.basename(root), "root": root, "branch": branch, "head": head,
            "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "languages": language_census(tracked), "slug": slug, "out": out,
            "inputs": [{"kind": k, "file": f, "spec": s} for k, f, s in inputs],
            "sources": [lbl for lbl, _ in sources], "plan_lines": len(lines)}
    json.dump(meta, open(os.path.join(out, "meta.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    s = citations["summary"]
    print(f"collected {len(sources)} source(s), {len(lines)} lines → {os.path.relpath(out, root)}/plan.md")
    print(f"structure: {len(hs)} headings, {len(units)} units (level-3), "
          f"{sum(u['acceptance_lines'] for u in units)} acceptance lines")
    va = sum(1 for v in verbatim if v["kind"] == "acceptance"); vq = len(verbatim) - va
    print(f"verbatim: {va} acceptance-criteria section{'' if va == 1 else 's'}, {vq} open-questions section{'' if vq == 1 else 's'}"
          + (" — shown on the page as written" if verbatim else ""))
    print(f"grounding: paths {s['paths_found']}/{s['paths']} found"
          + (f" ({s['paths_out_of_range']} with a line range past the file's end)" if s['paths_out_of_range'] else "")
          + f" · bare file names {s['bare_resolved']}/{s['bare_files']} resolved · symbols {s['symbols_found']}/{s['symbols']} present in the tree")
    langs = ", ".join(f"{k} {v}" for k, v in list(meta["languages"].items())[:6])
    print(f"languages: {langs}")
    print(f"OUT={out}")

if __name__ == "__main__":
    main()
