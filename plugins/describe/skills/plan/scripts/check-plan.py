#!/usr/bin/env python3
"""check-plan.py — deterministic guard on a plan's report.json before rendering.

Exit 0 when the report is well-formed; 1 with the problems listed otherwise. Enforces what
reference/plan-schema.md promises: plain-first prose (an error where a `plain` opens on a code
symbol), the steering budget (≤ 3 critical hard, ≤ 7 medium soft), the required parts of a
steering point, every cited file present in the tree (except what the plan will create), a
sketch's `before.lines` inside the real file, the view kinds of the shared toolset, and every
graph edge naming a node. The grounding summary from citations.json is printed as advice.
"""
import json, os, re, subprocess, sys

SEV = {"critical", "medium", "low"}
SEV_RANK = {"critical": 0, "medium": 1, "low": 2}
MAX_CRITICAL, MAX_MEDIUM = 3, 7
REQ_TOP = ["kind", "title", "plain", "summary", "units", "findings", "sketches", "views", "graph"]
TOUCH_STATUS = {"new", "changed", "removed", "unchanged"}
SKETCH_STATUS = {"changed", "new", "removed"}
VIEW_KINDS = {"screen", "flow", "adoption", "datamodel"}
NODE_CHANGE = {"added", "modified", "removed", "moved", "renamed", "split", "unchanged"}
CHECKED_BY = {"measured", "read", "assumed"}
SENTENCE_RE = re.compile(r"[.!?](?:\s|$)")
SYMBOL_RE = re.compile(r"`[^`]+`")

def n_sentences(s): return len(SENTENCE_RE.findall(s or ""))
def n_symbols(s): return len(SYMBOL_RE.findall(s or ""))
def first_sentence(s):
    m = SENTENCE_RE.search(s or "")
    return (s or "")[:m.end()] if m else (s or "")

def repo_root_of(report_path, meta):
    if meta.get("root") and os.path.isdir(meta["root"]): return meta["root"]
    d = os.path.dirname(os.path.abspath(report_path))
    try:
        r = subprocess.run(["git", "-C", d, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip(): return r.stdout.strip()
    except Exception:
        pass
    return None

def inside(root, path):
    if not root or os.path.isabs(path): return False
    full = os.path.realpath(os.path.join(root, path))
    return full.startswith(os.path.realpath(root) + os.sep)

def exists(root, path):
    return bool(root) and inside(root, path) and os.path.isfile(os.path.join(root, path))

def line_count(root, path):
    try:
        return sum(1 for _ in open(os.path.join(root, path), encoding="utf-8", errors="replace"))
    except Exception:
        return None

def check_plain(text, who, errs, warns, page=False):
    """Plain first — the one prose rule that is an error, because it is always fixable by reordering."""
    if not text:
        errs.append(f"{who}: missing 'plain'"); return
    if n_symbols(first_sentence(text)):
        errs.append(f"{who}: 'plain' opens on a code symbol — say what a PERSON meets first, name the symbol in the next sentence")
    ns, nc, nsym = n_sentences(text), len(text), n_symbols(text)
    if page:
        if nc > 900: errs.append(f"{who}: plain is {nc} chars; hard cap 900 (aim ≤ 800, 3–5 sentences)")
        elif nc > 800: warns.append(f"{who}: plain is {nc} chars — aim ≤ 800")
        if ns > 5: warns.append(f"{who}: plain runs to {ns} sentences — 3 to 5")
        if ns < 2: warns.append(f"{who}: plain is {ns} sentence — the opening earns three")
        if nsym > 2: warns.append(f"{who}: plain names {nsym} code symbols — two at most, and none in sentence one")
    else:
        if nc > 300: warns.append(f"{who}: plain is {nc} chars — aim ≤ 300, about two sentences")
        if ns > 2: warns.append(f"{who}: plain runs to {ns} sentences — two is the target")
        if nsym > 2: warns.append(f"{who}: plain names {nsym} code symbols — keep the one the reader must open")

def main():
    if len(sys.argv) < 2:
        print("usage: check-plan.py <report.json>"); sys.exit(2)
    rp = sys.argv[1]
    d = os.path.dirname(os.path.abspath(rp))
    r = json.load(open(rp, encoding="utf-8"))
    meta = {}
    if os.path.exists(os.path.join(d, "meta.json")):
        meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
    root = repo_root_of(rp, meta)
    errs, warns = [], []
    for k in REQ_TOP:
        if k not in r: errs.append(f"missing top-level key '{k}'")
    if errs: print("\n".join("ERROR: " + e for e in errs)); sys.exit(1)
    if r.get("kind") != "plan":
        errs.append(f"kind must be 'plan' (got {r.get('kind')!r})")

    # ---- the header ---------------------------------------------------------------------------
    check_plain(r.get("plain"), "page", errs, warns, page=True)
    n_sum = len(r["summary"])
    if n_sum > 700: errs.append(f"summary is {n_sum} chars; hard cap 700")
    elif n_sum > 420: warns.append(f"summary is {n_sum} chars — aim ≤ 420")
    if n_sentences(r["summary"]) > 4: warns.append("summary runs to more than 4 sentences")
    if n_symbols(r["summary"]) > 3: warns.append(f"summary names {n_symbols(r['summary'])} code symbols — say what a person can do")
    if r.get("intent") and len(r["intent"]) > 260: warns.append(f"intent is {len(r['intent'])} chars — one line")
    if len(r.get("title", "")) > 130: errs.append("title is over 130 chars")

    # ---- units --------------------------------------------------------------------------------
    unit_ids = set()
    if not r["units"]: errs.append("units is empty — a plan has at least one unit (story, task, step)")
    for i, u in enumerate(r["units"]):
        uid = u.get("id") or f"[{i}]"
        if not u.get("id") or not u.get("title"): errs.append(f"unit {uid}: needs 'id' and 'title'")
        if uid in unit_ids: errs.append(f"duplicate unit id {uid}")
        unit_ids.add(uid)
        check_plain(u.get("plain"), f"unit {uid}", errs, warns)
        for j, ac in enumerate(u.get("acs") or []):
            if not isinstance(ac, dict) or not ac.get("text"): errs.append(f"unit {uid}: acs[{j}] needs 'text'")
        for j, t in enumerate(u.get("touches") or []):
            if not isinstance(t, dict) or not t.get("file"): errs.append(f"unit {uid}: touches[{j}] needs 'file'"); continue
            st = t.get("status", "changed")
            if st not in TOUCH_STATUS: errs.append(f"unit {uid}: touches {t['file']} status must be one of {'|'.join(sorted(TOUCH_STATUS))} (got {st!r})"); continue
            if root and not inside(root, t["file"]): errs.append(f"unit {uid}: touches '{t['file']}' points outside the repo")
            elif st == "new" and exists(root, t["file"]): warns.append(f"unit {uid}: touches '{t['file']}' is 'new' but the file exists — 'changed'?")
            elif st != "new" and root and not exists(root, t["file"]): errs.append(f"unit {uid}: touches '{t['file']}' ({st}) — no such file in the repo; a file the plan creates is status 'new'")
        if u.get("size") and u["size"] not in ("S", "M", "L"): warns.append(f"unit {uid}: size is {u['size']!r} — S | M | L")
    for u in r["units"]:
        for dep in u.get("depends_on") or []:
            if dep not in unit_ids: warns.append(f"unit {u.get('id')}: depends_on {dep!r} is not a unit of this plan")

    # ---- decisions ----------------------------------------------------------------------------
    for i, dc in enumerate(r.get("decisions") or []):
        if not isinstance(dc, dict) or not dc.get("text"): errs.append(f"decisions[{i}]: needs 'text'"); continue
        if not dc.get("when"): warns.append(f"decisions[{i}]: no 'when' — an undated ruling reads as a claim")

    # ---- steering points ----------------------------------------------------------------------
    ids, counts = set(), {"critical": 0, "medium": 0, "low": 0}
    for f in r["findings"]:
        fid = f.get("id", "?")
        if fid in ids: errs.append(f"duplicate steering id {fid}")
        ids.add(fid)
        if not re.fullmatch(r"S\d+", str(fid)): errs.append(f"{fid}: id must be S<n>")
        sev = f.get("severity")
        if sev not in SEV: errs.append(f"{fid}: severity must be critical|medium|low (got {sev!r})"); continue
        counts[sev] += 1
        for key in ("title", "question", "current", "alternative", "why_human", "file"):
            if not f.get(key): errs.append(f"{fid}: missing '{key}'")
        check_plain(f.get("plain"), fid, errs, warns)
        t = f.get("title", "")
        if len(t) > 130: errs.append(f"{fid}: title is {len(t)} chars; hard cap 130")
        elif len(t) > 80: warns.append(f"{fid}: title is {len(t)} chars — aim ≤ 80")
        q = f.get("question", "")
        if q and q.count("?") != 1: warns.append(f"{fid}: question asks {q.count('?')} things — ONE question the reader can answer")
        if len(q) > 220: warns.append(f"{fid}: question is {len(q)} chars — it is a question, not its justification")
        if f.get("file") and root:
            if not inside(root, f["file"]): errs.append(f"{fid}: file '{f['file']}' points outside the repo")
            elif not exists(root, f["file"]): errs.append(f"{fid}: file '{f['file']}' — no such file in the repo (cite the plan document or the code the point is about)")
        if f.get("lines") and not re.fullmatch(r"\d+(-\d+)?", str(f["lines"])): errs.append(f"{fid}: lines must be 'N' or 'N-M'")
        if f.get("unit") and f["unit"] not in unit_ids: warns.append(f"{fid}: unit {f['unit']!r} is not a unit of this plan")
    if counts["critical"] > MAX_CRITICAL:
        errs.append(f"{counts['critical']} critical steering points > budget {MAX_CRITICAL}. If everything must be settled first, nothing is — demote by reversibility.")
    if counts["medium"] > MAX_MEDIUM: warns.append(f"{counts['medium']} medium steering points > soft budget {MAX_MEDIUM}")

    # ---- sketches -----------------------------------------------------------------------------
    langs = {k.lower() for k in (meta.get("languages") or {})}
    kids = set()
    for k in r["sketches"]:
        kid = k.get("id", "?")
        if kid in kids: errs.append(f"duplicate sketch id {kid}")
        kids.add(kid)
        if not re.fullmatch(r"K\d+", str(kid)): errs.append(f"{kid}: sketch id must be K<n>")
        for key in ("title", "file", "status"):
            if not k.get(key): errs.append(f"sketch {kid}: missing '{key}'")
        check_plain(k.get("plain"), f"sketch {kid}", errs, warns)
        st = k.get("status")
        if st not in SKETCH_STATUS: errs.append(f"sketch {kid}: status must be one of {'|'.join(sorted(SKETCH_STATUS))} (got {st!r})"); continue
        if k.get("unit") and k["unit"] not in unit_ids: warns.append(f"sketch {kid}: unit {k['unit']!r} is not a unit of this plan")
        if langs and k.get("language") and k["language"].lower() not in langs:
            warns.append(f"sketch {kid}: language {k['language']!r} is not in the tree's census ({', '.join(sorted(meta.get('languages') or {}))}) — sketches are written in the project's languages")
        if not k.get("language"): warns.append(f"sketch {kid}: no 'language'")
        path = k.get("file") or ""
        if root and path and not inside(root, path): errs.append(f"sketch {kid}: file '{path}' points outside the repo")
        before, after = k.get("before"), k.get("after")
        if st in ("changed", "removed"):
            if not isinstance(before, dict) or not (before.get("lines") or before.get("text")):
                errs.append(f"sketch {kid}: a {st} sketch needs before.lines (the real lines) or before.text")
            elif before.get("lines"):
                if not re.fullmatch(r"\d+(-\d+)?", str(before["lines"])): errs.append(f"sketch {kid}: before.lines must be 'N' or 'N-M'")
                elif root and not exists(root, path): errs.append(f"sketch {kid}: before.lines cites '{path}', which is not in the repo")
                else:
                    n = line_count(root, path) if root else None
                    a1, _, b1 = str(before["lines"]).partition("-")
                    a1, b1 = int(a1), int(b1 or a1)
                    if n is not None and (a1 < 1 or b1 > n or a1 > b1): errs.append(f"sketch {kid}: before.lines {before['lines']} is outside {path} ({n} lines)")
                    if b1 - a1 > 80: warns.append(f"sketch {kid}: before quotes {b1 - a1 + 1} lines — quote the definition that changes, 10 to 40")
        if st == "new" and root and exists(root, path): warns.append(f"sketch {kid}: status 'new' but '{path}' exists — 'changed'?")
        if st in ("changed", "new") and not (after or "").strip(): errs.append(f"sketch {kid}: a {st} sketch needs 'after' — the planned shape")
        if st == "removed" and (after or "").strip(): warns.append(f"sketch {kid}: a removed sketch carries an 'after' — is it a change?")
        if after and len(after.splitlines()) > 80: warns.append(f"sketch {kid}: after is {len(after.splitlines())} lines — shapes and signatures, not bodies")

    # ---- views + graph ------------------------------------------------------------------------
    for i, v in enumerate(r["views"]):
        kind = v.get("kind")
        if kind not in VIEW_KINDS: errs.append(f"views[{i}]: kind must be one of {'|'.join(sorted(VIEW_KINDS))} (got {kind!r})"); continue
        if kind == "datamodel":
            ents = v.get("entities") or []
            if not ents: errs.append(f"views[{i}] (datamodel): needs 'entities'")
            eids = set()
            for e in ents:
                if not isinstance(e, dict) or not e.get("id") or not e.get("label"): errs.append(f"views[{i}] (datamodel): every entity needs 'id' and 'label'"); continue
                eids.add(e["id"])
                if e.get("change", "unchanged") not in NODE_CHANGE: errs.append(f"views[{i}] (datamodel): entity {e['id']} bad change {e.get('change')!r}")
                for fld in e.get("fields") or []:
                    if not isinstance(fld, dict) or not fld.get("name"): errs.append(f"views[{i}] (datamodel): a field of {e['id']} has no 'name'")
                    elif fld.get("change", "unchanged") not in NODE_CHANGE: errs.append(f"views[{i}] (datamodel): field {e['id']}.{fld['name']} bad change {fld.get('change')!r}")
            for rel in v.get("relations") or []:
                if rel.get("from") not in eids or rel.get("to") not in eids:
                    errs.append(f"views[{i}] (datamodel): relation {rel.get('from')}→{rel.get('to')} names an entity that is not in the view")
        elif kind == "screen" and not v.get("screen"): errs.append(f"views[{i}] (screen): needs 'screen'")
        elif kind == "flow" and not v.get("steps"): errs.append(f"views[{i}] (flow): needs 'steps'")
        elif kind == "adoption" and not v.get("root"): errs.append(f"views[{i}] (adoption): needs 'root'")
    g = r["graph"]; node_ids = {n.get("id") for n in g.get("nodes", [])}
    for n in g.get("nodes", []):
        for key in ("id", "label", "kind", "change"):
            if not n.get(key): errs.append(f"graph node {n.get('id', '?')}: missing '{key}'")
        if n.get("change") not in NODE_CHANGE: errs.append(f"graph node {n.get('id')}: bad change '{n.get('change')}'")
    for e in g.get("edges", []):
        if e.get("from") not in node_ids or e.get("to") not in node_ids: errs.append(f"graph edge {e.get('from')}→{e.get('to')} references unknown node")
    if len(g.get("nodes", [])) > 40: warns.append(f"graph has {len(g['nodes'])} nodes — the map should fit a phone; map the riskiest unit and say so")

    # ---- the rest -----------------------------------------------------------------------------
    for i, x in enumerate(r.get("assumptions") or []):
        if not isinstance(x, dict) or not x.get("text"): errs.append(f"assumptions[{i}]: needs 'text'"); continue
        if x.get("checked_by") not in CHECKED_BY: errs.append(f"assumptions[{i}]: checked_by must be measured|read|assumed (got {x.get('checked_by')!r})")
    vids = set()
    for i, c in enumerate(r.get("how_to_check") or []):
        cid = c.get("id", f"#{i}")
        if cid in vids: errs.append(f"duplicate how_to_check id {cid}")
        vids.add(cid)
        if not re.fullmatch(r"V\d+", str(cid)): errs.append(f"how_to_check {cid}: id must be V<n>")
        if not c.get("feature"): errs.append(f"how_to_check {cid}: missing 'feature'")
        if not c.get("steps"): errs.append(f"how_to_check {cid}: needs at least one step")
        if not c.get("expect"): warns.append(f"how_to_check {cid}: no 'expect' — a step list with no stated outcome cannot be failed")
        if c.get("unit") and c["unit"] not in unit_ids: warns.append(f"how_to_check {cid}: unit {c['unit']!r} is not a unit of this plan")
    for i, p in enumerate(r.get("people") or []):
        if not isinstance(p, dict) or not p.get("who"): errs.append(f"people[{i}]: needs 'who'")
    for i, gl in enumerate(r.get("glossary") or []):
        if not isinstance(gl, dict) or not gl.get("term") or not gl.get("plain"): errs.append(f"glossary[{i}]: needs 'term' and 'plain'")
    for i, inv in enumerate(r.get("invariants") or []):
        if not isinstance(inv, str) or not inv.strip(): errs.append(f"invariants[{i}]: a sentence")
    if "grounding_note" in r and not (isinstance(r["grounding_note"], str) and r["grounding_note"].strip()):
        errs.append("grounding_note must be a non-empty sentence when present")

    # ---- grounding, as advice -----------------------------------------------------------------
    cp = os.path.join(d, "citations.json")
    if os.path.exists(cp):
        try:
            c = json.load(open(cp, encoding="utf-8")); s = c.get("summary") or {}
            missing = [p["path"] for p in c.get("paths") or [] if not p.get("exists")]
            oor = [p["path"] for p in c.get("paths") or [] if p.get("out_of_range")]
            print(f"grounding: paths {s.get('paths_found', 0)}/{s.get('paths', 0)} found · symbols {s.get('symbols_found', 0)}/{s.get('symbols', 0)} present")
            if missing: warns.append("plan cites paths not in the tree — a typo, or something the plan creates; either way say which: " + ", ".join(missing[:10]) + (" …" if len(missing) > 10 else ""))
            if oor: warns.append("plan cites line ranges past the file's end: " + ", ".join(oor[:10]))
        except Exception as ex:
            warns.append(f"citations.json unreadable: {ex}")

    for w in warns: print("WARN:", w)
    for e in errs: print("ERROR:", e)
    print(f"steering: {counts['critical']} settle-first / {counts['medium']} weigh / {counts['low']} note; "
          f"{len(r['units'])} units; {len(r['sketches'])} sketches; {len(r['views'])} views; "
          f"{len(g.get('nodes', []))} map nodes")
    sys.exit(1 if errs else 0)

if __name__ == "__main__":
    main()
