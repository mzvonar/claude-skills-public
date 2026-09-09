# codebase-map

A project-agnostic Claude Code skill that builds an **interactive, zoomable map of any
codebase**: a directed graph of modules/services (who calls whom) where clicking a
module zooms into its endpoints and structure, with a description of what each does.

Invoke it conversationally — "map this codebase", "visualize the architecture",
"refresh the map" — or via the `codebase-map` skill.

## How it works (token-efficient by design)

```
analyze.py   →  .codemap/model.json   (scan: modules, stacks, endpoints, edges, hashes)   [script]
   (LLM)     →  .codemap/enrichment.json   (roles, edge labels, grouping)                  [tiny LLM pass]
build.py     →  codebase-map-site/{index.html,data.json}                                   [script]
serve.sh     →  http://<lan-ip>:8777/                                                      [script]
```

- Scripts do all scanning and HTML generation. The LLM never reads source to build
  the map — it only writes a small `enrichment.json` from the compact `model.json`.
- **Refresh** re-runs `analyze.py`, which diffs file hashes and lists changed modules;
  only those get re-enriched. Near-zero tokens.

## Manual use

```bash
python3 scripts/analyze.py --root /path/to/repo --out /path/to/repo/.codemap
# (optionally hand-write .codemap/enrichment.json)
python3 scripts/build.py  --in /path/to/repo/.codemap --out /path/to/repo/codebase-map-site
bash    scripts/serve.sh  /path/to/repo/codebase-map-site 8777
```

Works with zero enrichment (modules grouped by stack, endpoint drill-down auto-generated);
enrichment adds human descriptions and meaningful edge labels.

## Extending

- Add endpoint extractors for more frameworks in `scripts/analyze.py` (`EXTRACTORS`).
- The viewer (`assets/template.html`) is generic and reads `data.json`; restyle freely.

## Requirements

`python3` (stdlib only). The viewer loads vis-network + markmap from CDN, so the
viewing device needs internet.
