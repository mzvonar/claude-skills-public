#!/usr/bin/env python3
"""check-report.py — deterministic guard on report.json before rendering.

Exit 0 when the report is well-formed; non-zero with a list of problems otherwise.
Enforces the credibility budget: ≤ 3 critical (hard), ≤ 7 medium (warn), every finding has
`why_human` + `verify`, every file referenced exists in diff-model.json, every graph edge
references a known node, ids are unique and follow C1/M1/L1 numbering.
"""
import json, sys, os, re, subprocess

SEV = {"critical": "C", "medium": "M", "low": "L"}
SEV_RANK = {"critical": 0, "medium": 1, "low": 2}
# The DB package (report-schema.md → db_package). Severity per reason kind is decided in ONE place —
# classify-diff.REASON_SEVERITY — and mirrored here so a report cannot re-rate a kind per call site.
DB_REASON_SEVERITY = {
    "destructive_ddl": "critical", "unrepresented_ddl": "critical", "data_mutation": "critical",
    "schema_migration_drift": "critical", "ordering": "medium", "structural_ddl": "medium", "additive_ddl": "low",
}
DB_DETECTED_BY = {"config", "heuristic", "no_schema_diff"}
DB_NOTE_MAX = 100
# Who raised a finding, on a two-pass run (SKILL.md §2b). "both" is the strongest signal the report
# can carry: two readers who could not see each other's work landed on the same spot.
PROVENANCE = {"fresh", "author", "both"}
MAX_CRITICAL, MAX_MEDIUM = 3, 7
REQ_TOP = ["title", "summary", "phases", "graph", "findings", "folded"]

def repo_root_of(report_path):
    d = os.path.dirname(os.path.abspath(report_path))
    try:
        meta = json.load(open(os.path.join(d, "meta.json")))
        if meta.get("root") and os.path.isdir(meta["root"]): return meta["root"]
    except Exception: pass
    # The report lives inside the repo it describes, so ask git rather than walking up looking for a
    # `.git` DIRECTORY — in a linked worktree `.git` is a file and the walk runs past the root to /.
    try:
        r = subprocess.run(["git", "-C", d, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None

def check_divergence(f, fid, root):
    """A `convention` finding must cite what it diverges FROM.

    This is the whole difference between a convention finding and a style opinion. "I would have
    written it the other way" is taste and costs credibility; "the rule says X and these two
    siblings do X" is checkable, and the reviewer can open both. So the citation is required, its
    paths must exist, and a claim resting on local precedent needs TWO neighbours — one sibling
    doing it differently is a coincidence, not a convention."""
    errs, warns = [], []
    refs = f.get("diverges_from") or []
    if isinstance(refs, (str, dict)): refs = [refs]
    if "convention" not in (f.get("tags") or []):
        if refs: warns.append(f"{fid}: has 'diverges_from' but is not tagged 'convention'")
        return errs, warns
    if not refs:
        errs.append(f"{fid}: a 'convention' finding must cite what it diverges from in 'diverges_from' "
                    f"(a rule like CLAUDE.md:161, or 2+ neighbours that do it the other way). "
                    f"Uncited, it is taste — drop it or cite it.")
        return errs, warns
    paths = []
    for ref in refs:
        s = ref.get("ref", "") if isinstance(ref, dict) else str(ref)
        if not s: errs.append(f"{fid}: empty entry in 'diverges_from'"); continue
        p = s.split(":")[0]
        paths.append(p)
        if root and not os.path.exists(os.path.join(root, p)):
            errs.append(f"{fid}: diverges_from '{s}' — no such file in the repo")
    rules = [p for p in paths if os.path.splitext(p)[1] in (".md", ".mdc", ".txt") or os.path.basename(p).startswith(".")]
    if not rules and len(set(paths)) < 2:
        errs.append(f"{fid}: 'diverges_from' cites one neighbour and no written rule — one sibling is a "
                    f"coincidence. Cite the rule, or a second file that does it the other way.")
    return errs, warns

def check_db_package(f, fid, model, known_files):
    """One finding owns the whole database change. Everything it claims is checked against the
    facts classify-diff.py recorded in diff-model.json → db: which file is the schema, which files
    are migrations and in what order, what the SQL does. A package whose headline severity
    disagrees with its reasons is unreadable, so that one is an error, not a warning."""
    errs, warns = [], []
    pk = f.get("db_package")
    if not isinstance(pk, dict):
        return [f"{fid}: db_package must be an object"], warns
    db = (model or {}).get("db") or {}
    kind = pk.get("headline_kind")
    migs = pk.get("migrations")
    reasons = pk.get("reasons")
    if kind not in ("schema", "migrations"):
        errs.append(f"{fid}: db_package.headline_kind must be schema|migrations (got {kind!r})")
    if not isinstance(migs, list):
        errs.append(f"{fid}: db_package.migrations must be a list (use [] for none)"); migs = []
    paths = []
    for i, mg in enumerate(migs):
        if not isinstance(mg, dict) or not mg.get("path"):
            errs.append(f"{fid}: db_package.migrations[{i}] needs a 'path'"); continue
        paths.append(mg["path"])
        if known_files is not None and mg["path"] not in known_files:
            errs.append(f"{fid}: db_package migration '{mg['path']}' is not in the diff")
        note = mg.get("note")
        if note is not None:
            if not isinstance(note, str):
                errs.append(f"{fid}: db_package.migrations[{i}].note must be a string")
            elif len(note) > DB_NOTE_MAX:
                warns.append(f"{fid}: note on {mg['path']} is {len(note)} chars (cap {DB_NOTE_MAX}; the renderer truncates)")
    if len(migs) == 1 and isinstance(migs[0], dict) and migs[0].get("note"):
        warns.append(f"{fid}: a single migration carries a note — the reason already names the only file; the renderer omits it")
    if kind == "schema":
        if db.get("schema_artifact") and f.get("file") != db["schema_artifact"]:
            errs.append(f"{fid}: headline_kind 'schema' requires file == the schema artifact ({db['schema_artifact']}), got {f.get('file')!r}")
        if db and not db.get("schema_changed"):
            errs.append(f"{fid}: headline_kind 'schema' but the schema artifact did not change in this diff — use 'migrations'")
    elif kind == "migrations":
        if not paths:
            errs.append(f"{fid}: headline_kind 'migrations' requires a non-empty migrations list")
        elif f.get("file") != paths[0]:
            errs.append(f"{fid}: headline_kind 'migrations' requires file == migrations[0].path ({paths[0]}), got {f.get('file')!r}")
        if db.get("schema_changed"):
            errs.append(f"{fid}: the schema artifact changed in this diff — headline_kind must be 'schema' with file {db['schema_artifact']}")
    # Every migration the classifier found must be in the package, or it leaks into "Everything
    # else" — the duplication this package exists to remove (the §7 exclusion is keyed on these).
    model_migs = [m["path"] for m in db.get("migrations") or []]
    for p in model_migs:
        if p not in paths:
            errs.append(f"{fid}: migration {p} is in the diff but not in db_package.migrations — it would render twice")
    for p in paths:
        if model_migs and p not in model_migs:
            warns.append(f"{fid}: db_package lists {p}, which the classifier does not consider a migration file")
    if model_migs and paths and [p for p in paths if p in model_migs] != [p for p in model_migs if p in paths]:
        errs.append(f"{fid}: db_package.migrations must keep the classifier's order (filename/timestamp): {model_migs}")
    # Notes come from the SQL parse, never from prose: an operation named in a note must literally be
    # in the file. The classifier's `summary` IS that line; a note that says something else is a claim
    # the validator cannot trace.
    by_path = {m["path"]: m for m in db.get("migrations") or []}
    for mg in migs:
        if not isinstance(mg, dict) or not mg.get("note"): continue
        fact = by_path.get(mg["path"])
        if fact is not None:
            if not fact.get("ops"):
                errs.append(f"{fid}: note on {mg['path']} but the parser found no SQL operation there — omit the note (nothing can be traced to a statement)")
            elif not fact.get("summary"):
                errs.append(f"{fid}: note on {mg['path']} but its operations are all low severity — omit the note; a bare filename says 'nothing to see'")
            elif mg["note"] != fact["summary"]:
                warns.append(f"{fid}: note on {mg['path']} differs from the parsed summary ({fact['summary']!r}) — every operation it names must appear in the file")
    if not isinstance(reasons, list) or not reasons:
        errs.append(f"{fid}: db_package.reasons must be a non-empty list"); reasons = []
    kinds, sevs = [], []
    for i, r in enumerate(reasons):
        if not isinstance(r, dict):
            errs.append(f"{fid}: db_package.reasons[{i}] must be an object"); continue
        k, s = r.get("kind"), r.get("severity")
        if k not in DB_REASON_SEVERITY:
            errs.append(f"{fid}: reasons[{i}].kind must be one of {'|'.join(DB_REASON_SEVERITY)} (got {k!r})"); continue
        kinds.append(k)
        if s not in SEV:
            errs.append(f"{fid}: reasons[{i}].severity must be critical|medium|low (got {s!r})"); continue
        sevs.append(s)
        if s != DB_REASON_SEVERITY[k]:
            errs.append(f"{fid}: reasons[{i}] ({k}) is rated {s}; the severity table says {DB_REASON_SEVERITY[k]} — change the table, not the report")
        if not r.get("question"): warns.append(f"{fid}: reasons[{i}] ({k}) has no 'question' — the renderer falls back to the default")
        if k == "unrepresented_ddl":
            if r.get("detected_by") not in DB_DETECTED_BY:
                errs.append(f"{fid}: reasons[{i}] (unrepresented_ddl) needs detected_by ∈ {'|'.join(sorted(DB_DETECTED_BY))} — the reader must know whether to discount a heuristic hit")
    if len(kinds) != len(set(kinds)):
        warns.append(f"{fid}: db_package repeats a reason kind — merge them")
    if sevs:
        top = min(sevs, key=lambda s: SEV_RANK[s])
        if f.get("severity") != top:
            errs.append(f"{fid}: severity is {f.get('severity')!r} but the max over db_package.reasons is {top!r} — they must agree")
    if kind == "schema" and not paths and "schema_migration_drift" not in kinds:
        errs.append(f"{fid}: a schema change with no migration must carry a schema_migration_drift reason")
    if "schema_migration_drift" in kinds and paths:
        errs.append(f"{fid}: schema_migration_drift is claimed but the package lists migrations")
    # What the SQL supports must be in the package. The classifier's reasons are facts about the
    # statements; the analyst may add (a non-SQL migration it read), never drop.
    for r in db.get("reasons") or []:
        if r["kind"] not in kinds:
            errs.append(f"{fid}: the migration SQL shows {r['kind']} ({r.get('detail','')[:90]}) but db_package has no such reason")
    return errs, warns

def main():
    if len(sys.argv) < 2:
        print("usage: check-report.py <report.json> [diff-model.json]"); sys.exit(2)
    rp = sys.argv[1]
    r = json.load(open(rp))
    model_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(rp), "diff-model.json")
    model = json.load(open(model_path)) if os.path.exists(model_path) else None
    repo_root = repo_root_of(rp)
    known_files = {f["path"] for f in model["files"]} | {f["old_path"] for f in model["files"] if f.get("old_path")} if model else None
    errs, warns = [], []
    for k in REQ_TOP:
        if k not in r: errs.append(f"missing top-level key '{k}'")
    if errs: print("\n".join("ERROR: " + e for e in errs)); sys.exit(1)
    # Brevity is a correctness property here, not taste: the failure this tool exists to prevent is a
    # rubber-stamped signature, and an over-long header is the cheapest way to cause one. Enforced
    # mechanically because "keep it short" as advice loses to the urge to explain your own work.
    n_sum = len(r["summary"])
    if n_sum < 20:
        warns.append(f"summary is too short to be useful ({n_sum} chars)")
    elif n_sum > 700:
        errs.append(f"summary is {n_sum} chars; hard cap 700. Cut to what a reviewer cannot infer from the intent line.")
    elif n_sum > 420:
        warns.append(f"summary is {n_sum} chars — aim for ≤ 420 (about 3 sentences)")
    if len(re.findall(r"[.!?](?:\s|$)", r["summary"])) > 4:
        warns.append("summary runs to more than 4 sentences — the header is skimmed, not read")
    # Mechanism-first tell. A functional summary names what a person can now do; a mechanical one
    # names the symbols that do it. Counting `backticked` identifiers is a crude proxy, but it fires
    # on exactly the shape that reads like a commit message — and that shape is the second-commonest
    # reason this section gets skipped, after length.
    n_sym = len(re.findall(r"`[^`]+`", r["summary"]))
    if n_sym > 3:
        warns.append(f"summary names {n_sym} code symbols — say what a PERSON can now do and which rule stops them; keep mechanism for where it IS the decision")
    if r.get("intent"):
        if len(r["intent"]) > 260:
            warns.append(f"intent is {len(r['intent'])} chars — it should be ONE line naming what was asked, not a retelling")
        # Duplicate detection: intent and summary answer different questions (asked vs done). When they
        # share most of their vocabulary the reader gets the same paragraph twice and starts skipping.
        sig = lambda s: {w for w in re.findall(r"[a-z]{5,}", s.lower())}
        a, c = sig(r["intent"]), sig(r["summary"])
        if a and c:
            overlap = len(a & c) / min(len(a), len(c))
            if overlap > 0.55:
                warns.append(f"intent and summary overlap {overlap:.0%} — intent is what was ASKED, summary is what CHANGED and why it is non-obvious; do not restate")
    conf = r.get("confession")
    if isinstance(conf, list):
        for i, item in enumerate(conf):
            if not isinstance(item, dict) or not item.get("point"):
                errs.append(f"confession[{i}]: each item needs a one-line 'point' (plus optional 'detail')")
            elif len(item["point"]) > 180:
                warns.append(f"confession[{i}]: point is {len(item['point'])} chars — it is a headline; move the rest into 'detail'")
            if isinstance(item, dict) and not isinstance(item.get("corroborated_by", []), list):
                errs.append(f"confession[{i}]: corroborated_by must be a list of finding ids — use [] for 'the cold pass looked and flagged nothing here'")
        if len(conf) > 6:
            warns.append(f"{len(conf)} confession items — if everything is doubtful nothing is; keep the ones that would change what a reviewer does")
    elif isinstance(conf, str) and len(conf) > 300:
        warns.append("confession is a long string — use the list form [{point, detail}] so a reviewer can skim it and expand only what matters")

    ids, counts = set(), {"critical": 0, "medium": 0, "low": 0}
    for f in r["findings"]:
        fid = f.get("id", "?")
        if fid in ids: errs.append(f"duplicate finding id {fid}")
        ids.add(fid)
        sev = f.get("severity")
        if sev not in SEV: errs.append(f"{fid}: severity must be critical|medium|low (got {sev!r})"); continue
        counts[sev] += 1
        if not re.fullmatch(SEV[sev] + r"\d+", fid): errs.append(f"{fid}: id must be {SEV[sev]}<n> for severity {sev}")
        for key in ("title", "why_human", "verify", "file"):
            if not f.get(key): errs.append(f"{fid}: missing '{key}'")
        if known_files is not None and f.get("file") and f["file"] not in known_files:
            errs.append(f"{fid}: file '{f['file']}' is not in the diff")
        if f.get("lines") and not re.fullmatch(r"\d+(-\d+)?", str(f["lines"])): errs.append(f"{fid}: lines must be 'N' or 'N-M'")
        if len(f.get("why_human", "")) > 400: warns.append(f"{fid}: why_human is long ({len(f['why_human'])} chars) — compress")
        if "provenance" in f and f["provenance"] not in PROVENANCE:
            errs.append(f"{fid}: provenance must be one of {'|'.join(sorted(PROVENANCE))} (got {f['provenance']!r})")
        e2, w2 = check_divergence(f, fid, repo_root)
        errs += e2; warns += w2
        if "db_package" in f:
            e3, w3 = check_db_package(f, fid, model, known_files)
            errs += e3; warns += w3

    # One package per report — decided: multiple unrelated DB changes still form one group. And the
    # package is not optional: when the diff carries a DB change the report must own it, or the
    # migrations scatter across "Everything else" as ordinary files.
    packages = [f.get("id", "?") for f in r["findings"] if "db_package" in f]
    if len(packages) > 1:
        errs.append(f"findings {', '.join(packages)} all carry db_package — at most one finding may (one package per report)")
    if model and model.get("db") and not packages:
        db = model["db"]
        errs.append(f"the diff carries a DB change ({db.get('headline_kind')} headline, {len(db.get('migrations') or [])} migration(s)) "
                    f"but no finding carries db_package — build it from diff-model.json → db (report-schema.md)")

    # Provenance is all-or-nothing. A report where some findings name their pass and others do not
    # cannot be read: an untagged finding is indistinguishable from one the cold pass missed, which
    # inverts the meaning of the section this field exists to feed.
    tagged = [f for f in r["findings"] if f.get("provenance")]
    if tagged and len(tagged) != len(r["findings"]):
        errs.append(
            f"{len(tagged)} of {len(r['findings'])} findings carry 'provenance' — set it on every "
            "finding or on none; a partly-tagged report reads as if the cold pass missed the rest"
        )
    # `corroborated_by` must point at findings that exist, or the "Two readings" section cites ids
    # the reader cannot find.
    if isinstance(conf, list):
        for i, item in enumerate(conf):
            for ref in (item.get("corroborated_by") or []) if isinstance(item, dict) else []:
                if ref not in ids:
                    errs.append(f"confession[{i}]: corroborated_by names {ref}, which is not a finding id")
    if counts["critical"] > MAX_CRITICAL:
        errs.append(f"{counts['critical']} critical findings > budget {MAX_CRITICAL}. If everything is critical, nothing is — demote.")
    if counts["medium"] > MAX_MEDIUM: warns.append(f"{counts['medium']} medium findings > soft budget {MAX_MEDIUM}")

    # How-to-check: the section exists so a reviewer can exercise the change instead of trusting the
    # report, so a step list that cannot be followed is worse than no card at all.
    check_ids = set()
    for i, c in enumerate(r.get("how_to_check") or []):
        cid = c.get("id", f"#{i}")
        if cid in check_ids: errs.append(f"duplicate how_to_check id {cid}")
        check_ids.add(cid)
        if not re.fullmatch(r"V\d+", str(cid)): errs.append(f"how_to_check {cid}: id must be V<n>")
        if not c.get("feature"): errs.append(f"how_to_check {cid}: missing 'feature'")
        if not c.get("steps"): errs.append(f"how_to_check {cid}: needs at least one step")
        if not c.get("expect"): warns.append(f"how_to_check {cid}: no 'expect' — a step list with no stated outcome cannot be failed")
        surface = c.get("surface", "ui")
        if surface not in ("ui", "api", "cli"): errs.append(f"how_to_check {cid}: surface must be ui|api|cli (got {surface!r})")
        req = c.get("request")
        if req:
            if surface != "api": warns.append(f"how_to_check {cid}: 'request' is only meaningful with surface:\"api\"")
            if not req.get("method") or not req.get("path"):
                errs.append(f"how_to_check {cid}: request needs 'method' and 'path'")
            elif not str(req["path"]).startswith("/"):
                errs.append(f"how_to_check {cid}: request.path must start with '/' (the base URL is chosen in the page)")
        elif surface == "api":
            warns.append(f"how_to_check {cid}: surface is api but there is no 'request' — no curl, Postman entry or inline send can be offered")

    g = r["graph"]; node_ids = {n.get("id") for n in g.get("nodes", [])}
    for n in g.get("nodes", []):
        for key in ("id", "label", "kind", "change"):
            if not n.get(key): errs.append(f"graph node {n.get('id','?')}: missing '{key}'")
        if n.get("change") not in {"added", "modified", "removed", "moved", "renamed", "split", "unchanged"}:
            errs.append(f"graph node {n.get('id')}: bad change '{n.get('change')}'")
    for e in g.get("edges", []):
        if e.get("from") not in node_ids or e.get("to") not in node_ids:
            errs.append(f"graph edge {e.get('from')}→{e.get('to')} references unknown node")
    if len(g.get("nodes", [])) > 40: warns.append(f"graph has {len(g['nodes'])} nodes — the map should fit a phone; prune to the change-relevant symbols")

    for i, p in enumerate(r["phases"]):
        for key in ("id", "title", "narrative"):
            if not p.get(key): errs.append(f"phase[{i}]: missing '{key}'")
        for fp in p.get("files", []):
            if known_files is not None and fp not in known_files: errs.append(f"phase {p.get('id')}: file '{fp}' not in diff")
    for fid in r.get("unreviewed", []):
        if known_files is not None and fid not in known_files: warns.append(f"unreviewed '{fid}' not in diff")

    for w in warns: print("WARN:", w)
    for e in errs: print("ERROR:", e)
    print(f"findings: {counts['critical']} critical / {counts['medium']} medium / {counts['low']} low; "
          f"{len(g.get('nodes', []))} nodes / {len(g.get('edges', []))} edges; {len(r['phases'])} phases")
    sys.exit(1 if errs else 0)

if __name__ == "__main__":
    main()
