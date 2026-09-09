#!/usr/bin/env python3
"""
codebase-map / build.py  —  merge model.json (+ optional enrichment.json) into a
self-contained interactive site (index.html + data.json). No LLM.

Auto-generates per-module drill-down markdown from extracted endpoints when the
enrichment does not supply richer markdown, so the explorer works with zero LLM.

Usage:
  build.py [--in .codemap] [--out codebase-map-site]
"""
import os, re, json, argparse, shutil

PALETTE = {"kotlin": "#9b59b6", "java": "#e67e22", "typescript": "#4a90e2",
           "node": "#3fb950", "python": "#f0a500", "go": "#2bb6a8", "ruby": "#e5534b",
           "rust": "#c1666b", "php": "#8a8fd0", "scala": "#d36c6c", "unknown": "#6e7681"}
CYCLE = ["#4a90e2", "#3fb950", "#f0a500", "#9b59b6", "#2bb6a8", "#e5534b", "#e67e22", "#8a8fd0"]


def auto_markdown(m, role):
    lines = [f"## {m['id']}",
             f"- **Stack:** {m.get('stack','?')}  ·  {m.get('fileCount',0)} source/config files",
             f"- **Role:** {role or '_(no description yet — run enrichment)_'}"]
    eps = m.get("endpoints", [])
    if eps:
        lines.append(f"- **Endpoints ({len(eps)})**")
        groups = {}
        for e in eps:
            seg = "/" + (e["path"].lstrip("/").split("/", 1)[0] or "")
            groups.setdefault(seg, []).append(e)
        for seg in sorted(groups):
            if len(groups) > 1:
                lines.append(f"  - {seg}")
                ind = "    "
            else:
                ind = "  "
            for e in groups[seg][:80]:
                lines.append(f"{ind}- `{e['method']} {e['path']}`  ·  {e.get('file','')}")
    else:
        lines.append("- _no endpoints detected (library / infra / docs module)_")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="indir", default=".codemap")
    ap.add_argument("--out", default="codebase-map-site")
    args = ap.parse_args()

    model = json.load(open(os.path.join(args.indir, "model.json")))
    enr_path = os.path.join(args.indir, "enrichment.json")
    enr = json.load(open(enr_path)) if os.path.exists(enr_path) else {}
    e_mods = enr.get("modules", {})
    e_groups = enr.get("groups", {})

    title = enr.get("title") or (os.path.basename(model["root"].rstrip("/")) + " — Codebase Map")

    nodes, modules, used_groups = [], {}, {}
    ci = 0
    for m in model["modules"]:
        em = e_mods.get(m["id"], {})
        group = em.get("group") or m.get("stack", "unknown")
        role = em.get("role") or em.get("description") or ""
        desc = em.get("description") or role or ""
        if group not in e_groups and group not in used_groups:
            color = PALETTE.get(group) or CYCLE[ci % len(CYCLE)]; ci += 1
            used_groups[group] = {"color": color, "shape": "box"}
        nodes.append({"id": m["id"], "label": m["id"], "group": group, "description": desc})
        modules[m["id"]] = {"markdown": em.get("markdown") or auto_markdown(m, role)}

    for n in enr.get("extraNodes", []):
        nodes.append(n)
        g = n.get("group", "infra")
        if g not in e_groups and g not in used_groups:
            used_groups[g] = {"color": "#6e7681", "shape": "dot"}

    groups = {}
    groups.update(used_groups)
    groups.update(e_groups)  # enrichment wins
    edges = enr.get("edges") or model.get("edges", [])

    data = {"title": title, "generatedAt": model.get("generatedAt"),
            "nodes": nodes, "edges": edges, "groups": groups, "modules": modules}

    os.makedirs(args.out, exist_ok=True)
    json.dump(data, open(os.path.join(args.out, "data.json"), "w"), indent=1)
    tpl = os.path.join(os.path.dirname(__file__), "..", "assets", "template.html")
    shutil.copyfile(tpl, os.path.join(args.out, "index.html"))

    print(f"built {args.out}/index.html  ·  {len(nodes)} nodes  {len(edges)} edges  "
          f"{len(modules)} drillable modules")
    enriched = sum(1 for m in model["modules"] if m["id"] in e_mods)
    print(f"enrichment: {enriched}/{len(model['modules'])} modules have descriptions"
          f"{' (none yet — run the LLM enrichment step)' if not enriched else ''}")


if __name__ == "__main__":
    main()
