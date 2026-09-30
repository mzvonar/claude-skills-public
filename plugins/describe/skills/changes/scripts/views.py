#!/usr/bin/env python3
"""views.py — the visualization toolset shared by /describe:changes and /describe:plan.

One renderer per view kind (`screen`, `flow`, `adoption`, `datamodel`), the mermaid map builder and
the text list that stands in for it when the CDN never answers. The two skills draw the same
pictures — a plan shows the shape it intends, a change shows the shape it produced — so the code
lives once, here. Each caller passes in the one thing that differs between them: how a file
reference opens (`fchip`), because only the change report has a diff to open it into; the plan
report opens the file as it is today.

Pure functions over report JSON → HTML strings. No I/O, nothing read from disk.
"""
import hashlib, html

E = html.escape

CHANGE_FILL = {"added": "#1f5a3a", "modified": "#6b4a12", "removed": "#6b1f1f", "moved": "#1f3f6b", "renamed": "#1f3f6b",
               "split": "#3b2a6b", "unchanged": "#2d3748"}
EDGE_STYLE = {"calls": "-->", "dataflow": "==>", "imports": "-.->", "renders": "-->", "extends": "-->", "moved_to": "-.->",
              "split_into": "-.->", "emits": "-->", "reads": "-.->", "writes": "==>"}
CH_LABEL = {"added": "new", "modified": "changed", "removed": "deleted", "moved": "moved", "renamed": "renamed", "split": "split", "unchanged": ""}

def mid(s): return "n" + hashlib.md5(s.encode()).hexdigest()[:8]

def short_path(p, budget=40):
    """A cluster title the box can actually hold.

    Mermaid sizes a cluster box from its CONTENTS, never from its title, so a title wider than the
    box overflows it and collides with whatever sits alongside. Measured on a real map before this
    changed: ten clusters titled with full repo paths produced SEVEN overlapping pairs.

    Keep the first segment and the last two, elide the middle. The last two are what disambiguate
    `.../en/translation.json` from `.../fr/translation.json` -- a bare basename does not, and two
    boxes titled `translation.json` are worse than one wide box.
    """
    p = p.replace('"', "")
    if len(p) <= budget: return p
    seg = [x for x in p.split("/") if x]
    if len(seg) > 3:
        cand = seg[0] + "/…/" + "/".join(seg[-2:])
        if len(cand) <= budget: return cand
    cand = "…/" + "/".join(seg[-2:])
    if len(cand) <= budget: return cand
    # Every path-shaped elision still overflows, so cut CHARACTERS. A long basename is the case no
    # segment elision can reach, and for an input with no `/` at all the segment form returned a
    # string LONGER than the one it was handed — the exact fault this function exists to prevent.
    tail = seg[-1] if seg else p
    return "…" + tail[-(budget - 1):]

def mermaid(graph):
    nodes, edges = graph.get("nodes", []), graph.get("edges", [])
    if not nodes: return ""
    out = ["flowchart TD"]
    by_file = {}
    for n in nodes: by_file.setdefault(n.get("file") or "", []).append(n)
    use_sub = 1 < len(by_file) <= 12
    def node_line(n):
        label = n["label"].replace('"', "'")
        kind = n.get("kind", "")
        if kind in ("component",): shape = f'(["{label}"])'
        elif kind in ("type", "interface", "schema"): shape = f'[/"{label}"/]'
        elif kind in ("module", "file"): shape = f'[["{label}"]]'
        elif kind in ("store", "db", "table"): shape = f'[("{label}")]'
        elif kind in ("service", "system", "external"): shape = f'{{{{"{label}"}}}}'
        else: shape = f'["{label}"]'
        return f'  {mid(n["id"])}{shape}'
    for f, ns in by_file.items():
        # A subgraph is a GROUPING. A box drawn around a single node groups nothing, and it costs
        # the map the full width of its title -- which is how ten one-node boxes collided above.
        if use_sub and f and len(ns) > 1:
            out.append(f'  subgraph {mid("f:"+f)}["{short_path(f)}"]')
            out += ["  " + node_line(n) for n in ns]
            out.append("  end")
        else:
            out += [node_line(n) for n in ns]
    for e in edges:
        arrow = EDGE_STYLE.get(e.get("kind", "calls"), "-->")
        lab = (e.get("label") or e.get("kind") or "").replace('"', "'").replace("|", "/")
        out.append(f'  {mid(e["from"])} {arrow}{"|" + chr(34) + lab + chr(34) + "|" if lab else ""} {mid(e["to"])}')
    for ch, fill in CHANGE_FILL.items():
        ids = [mid(n["id"]) for n in nodes if n.get("change") == ch]
        if ids:
            style = f"fill:{fill},stroke:#cbd5e0,color:#ffffff" + (",stroke-dasharray:4 3" if ch == "removed" else "")
            out.append(f"  classDef {ch} {style}")
            out.append(f"  class {','.join(ids)} {ch}")
    return "\n".join(out)

def map_list(graph):
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    rows = []
    for n in graph.get("nodes", []):
        rows.append(f'<div><span class="ch-{E(n["change"])}">{E(n["label"])}</span> <span style="color:var(--fg3)">{E(n.get("kind",""))} · {E(n["change"])}{(" · " + E(n["file"])) if n.get("file") else ""}</span></div>')
    for e in graph.get("edges", []):
        a, b = nodes.get(e["from"], {}).get("label", e["from"]), nodes.get(e["to"], {}).get("label", e["to"])
        rows.append(f'<div>{E(a)} —{E(e.get("label") or e.get("kind",""))}→ {E(b)}</div>')
    return "\n".join(rows)

def pill(change):
    return f'<span class="chg chg-{E(change)}">{E(CH_LABEL.get(change, change))}</span>' if change and change != "unchanged" else ""

def view_screen(v, fchip):
    def box(n, depth=0):
        slot = f'<span class="slot">{E(n["slot"])} ▸</span>' if n.get("slot") else ""
        kids = "".join(box(c, depth + 1) for c in n.get("children", []))
        note = f'<div class="scr-note">{E(n["note"])}</div>' if n.get("note") else ""
        cls = "scr scr-" + E(n.get("change", "unchanged")) + (" scr-slot" if n.get("slot") else "")
        return f'<div class="{cls}"><div class="scr-h">{slot}<span class="scr-l">{E(n["label"])}</span>{pill(n.get("change"))}{fchip(n)}</div>{note}{kids}</div>'
    return f'<div class="screen">{box(v["screen"])}</div>'

def view_flow(v, fchip):
    def step(st, i=None):
        kids = "".join(step(c) for c in st.get("then", []))
        note = f'<div class="st-note">{E(st["note"])}</div>' if st.get("note") else ""
        files = "".join(fchip({"file": f}) for f in st.get("files", []))
        return (f'<div class="step step-{E(st.get("change", "unchanged"))}"><div class="st-h">{("<span class=st-n>" + str(i) + "</span>") if i else ""}<span class="st-l">{E(st["label"])}</span>{pill(st.get("change"))}{fchip(st)}{files}</div>{note}'
                + (f'<div class="st-then">{kids}</div>' if kids else "") + '</div>')
    return '<div class="flow">' + "".join(step(st, i) for i, st in enumerate(v["steps"], 1)) + "</div>"

def view_adoption(v, fchip):
    root = v["root"]
    roots = root if isinstance(root, list) else [root]
    rh = "".join(f'<div class="ad-root ad-{E(r.get("change","added"))}"><div class="scr-h"><span class="scr-l">{E(r["label"])}</span>{pill(r.get("change"))}{fchip(r)}</div>' + (f'<div class="scr-note">{E(r["note"])}</div>' if r.get("note") else "") + '</div>' for r in roots)
    uses = "".join(f'<div class="ad-use ad-{E(u.get("change","modified"))}"><div class="scr-h"><span class="scr-l">{E(u["label"])}</span>{pill(u.get("change"))}{fchip(u)}</div>' + (f'<div class="scr-note">{E(u["note"])}</div>' if u.get("note") else "") + '</div>' for u in v.get("uses", []))
    repl = "".join(f'<div class="ad-use ad-removed"><div class="scr-h"><span class="scr-l">{E(u["label"])}</span>{pill("removed")}{fchip(u)}</div>' + (f'<div class="scr-note">{E(u["note"])}</div>' if u.get("note") else "") + '</div>' for u in v.get("replaces", []))
    return (f'<div class="adoption"><div class="ad-roots">{rh}</div><div class="ad-arrow">used in ↓</div><div class="ad-uses">{uses}</div>'
            + (f'<div class="ad-arrow">replaces ↓</div><div class="ad-uses">{repl}</div>' if repl else "") + '</div>')

# The glyph a field row carries beside its colour, for anyone who cannot tell the hues apart —
# the same four the file references use elsewhere on the page.
FIELD_GLYPH = {"added": "+", "removed": "−", "modified": "~", "unchanged": "·", "moved": "→", "renamed": "→"}
REL_GLYPH = {"has-many": "──▶ many", "has-one": "──▶ one", "refs": "──▶",
             "extends": "──▷ extends", "uses": "──▶ uses"}

def view_datamodel(v, fchip):
    """Entities as cards, their fields as rows, the relations as a strip beneath.

    A DATA MODEL is the picture a reader wants when the question is "what will we store, and how
    does it hang together" — a call graph answers neither. Each entity is a box coloured by its
    change, each field a row with its type and its own change glyph, so a type that gains two
    members and loses one reads as exactly that, not as "modified". Relations are drawn as text
    arrows rather than a second mermaid canvas: they survive a blocked CDN, they print, and an
    entity count that fits a phone never needs panning.

    Shape (reference/visualizations.md): `entities[]` with `id`, `label`, `change`, optional
    `file`/`lines`/`note`, and `fields[]` of `name`, `type`, `change`, optional `note`;
    `relations[]` of `from`, `to`, `kind` (has-many | has-one | refs | extends | uses), optional
    `label`, `change`.
    """
    ents = v.get("entities") or []
    cards = []
    for ent in ents:
        ch = ent.get("change", "unchanged")
        rows = []
        for f in ent.get("fields") or []:
            fch = f.get("change", "unchanged")
            note = f'<div class="dm-fn">{E(f["note"])}</div>' if f.get("note") else ""
            rows.append(f'<tr class="dm-{E(fch)}"><td class="dm-g">{E(FIELD_GLYPH.get(fch, "·"))}</td>'
                        f'<td class="dm-n">{E(f["name"])}{note}</td><td class="dm-t">{E(f.get("type", ""))}</td></tr>')
        note = f'<div class="scr-note">{E(ent["note"])}</div>' if ent.get("note") else ""
        loc = f' <span class="dm-loc">{E(ent["lines"])}</span>' if ent.get("lines") else ""
        cards.append(f'<div class="dm-ent dm-{E(ch)}" data-ent="{E(ent["id"])}">'
                     f'<div class="scr-h"><span class="scr-l">{E(ent["label"])}</span>{pill(ch)}{fchip(ent)}{loc}</div>'
                     + (f'<table class="dm-f">{"".join(rows)}</table>' if rows else "") + note + "</div>")
    labels = {ent["id"]: ent.get("label", ent["id"]) for ent in ents}
    rels = []
    for r in v.get("relations") or []:
        rch = r.get("change", "unchanged")
        arrow = REL_GLYPH.get(r.get("kind", "refs"), "──▶")
        lab = f' <span class="dm-rl">{E(r["label"])}</span>' if r.get("label") else ""
        rels.append(f'<div class="dm-rel dm-{E(rch)}"><span class="dm-re">{E(labels.get(r["from"], r["from"]))}</span>'
                    f' <span class="dm-ra">{E(arrow)}</span>{lab} <span class="dm-re">{E(labels.get(r["to"], r["to"]))}</span>{pill(rch)}</div>')
    return (f'<div class="datamodel"><div class="dm-grid">{"".join(cards)}</div>'
            + (f'<div class="dm-rels">{"".join(rels)}</div>' if rels else "") + "</div>")

VIEWS = {"screen": view_screen, "flow": view_flow, "adoption": view_adoption, "datamodel": view_datamodel}

def render_view(v, fchip):
    fn = VIEWS.get(v.get("kind"))
    return fn(v, fchip) if fn else ""
