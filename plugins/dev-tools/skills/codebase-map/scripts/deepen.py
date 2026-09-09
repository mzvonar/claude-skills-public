#!/usr/bin/env python3
"""
codebase-map / deepen.py  —  build a FOCUSED reading list for one module so the
LLM can author endpoint->code chains by reading only a handful of files (not the
whole module). No LLM here; this just gathers context.

Usage:
  deepen.py --module <id> [--in .codemap]
Writes <in>/deepen/<id>.context.md and prints the path + next step.
"""
import os, re, json, argparse

SKIP_DIRS = {".git", "node_modules", "vendor", "build", "dist", "target", ".gradle",
             "__pycache__", ".venv", "venv", ".idea", ".next", "out", "coverage", "tmp", "bin", "obj"}
SRC_EXT = {".kt", ".java", ".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rb", ".rs", ".php", ".scala"}
ROLE = re.compile(r"(Controller|Service|Repository|Repo|Gateway|Client|Mapper|Handler|Resolver|"
                  r"UseCase|Facade|Adapter|Store|Dao|Api|Consumer|Publisher|Producer)$")
DECL = {
    ".kt": [r"(?:class|interface|object)\s+(\w+)"],
    ".java": [r"(?:public\s+|final\s+|abstract\s+)*(?:class|interface|enum)\s+(\w+)"],
    ".scala": [r"(?:class|trait|object)\s+(\w+)"],
    ".ts": [r"(?:export\s+)?(?:class|interface)\s+(\w+)", r"(?:export\s+)?(?:const|function)\s+(\w+)\s*[=(]"],
    ".tsx": [r"(?:export\s+)?(?:class|interface)\s+(\w+)", r"(?:export\s+)?(?:const|function)\s+(\w+)\s*[=(]"],
    ".js": [r"(?:export\s+)?(?:class)\s+(\w+)", r"(?:export\s+)?(?:const|function)\s+(\w+)\s*[=(]"],
    ".py": [r"(?:class|def)\s+(\w+)"],
    ".go": [r"type\s+(\w+)\s+struct", r"func\s+(?:\([^)]*\)\s*)?(\w+)\s*\("],
    ".rb": [r"(?:class|module)\s+(\w+)", r"def\s+(\w+)"],
}
MAX_FILE = 400_000


def iter_files(path):
    for dp, dn, fs in os.walk(path):
        dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.startswith(".")]
        for f in fs:
            yield os.path.join(dp, f)


def read(fp):
    try:
        if os.path.getsize(fp) > MAX_FILE: return ""
        return open(fp, encoding="utf-8", errors="ignore").read()
    except OSError:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", required=True)
    ap.add_argument("--in", dest="indir", default=".codemap")
    args = ap.parse_args()

    model = json.load(open(os.path.join(args.indir, "model.json")))
    mod = next((m for m in model["modules"] if m["id"] == args.module), None)
    if not mod:
        raise SystemExit(f"module '{args.module}' not in model.json. Available: "
                         + ", ".join(m["id"] for m in model["modules"]))
    mpath = os.path.join(model["root"], mod["path"])

    # index declarations by role
    role_index = {}   # symbol -> relpath  (role-matching only)
    all_decls = {}    # symbol -> relpath
    for fp in iter_files(mpath):
        ext = os.path.splitext(fp)[1]
        pats = DECL.get(ext)
        if not pats:
            continue
        txt = read(fp)
        if not txt:
            continue
        rel = os.path.relpath(fp, mpath)
        for pat in pats:
            for m in re.finditer(pat, txt):
                sym = m.group(1)
                all_decls.setdefault(sym, rel)
                if ROLE.search(sym):
                    role_index.setdefault(sym, rel)

    handler_files = sorted({e.get("file") for e in mod.get("endpoints", []) if e.get("file")})

    out = [f"# Deepen context — {mod['id']}",
           f"_stack: {mod.get('stack')} · {mod.get('fileCount')} files · "
           f"{mod.get('endpointCount')} endpoints · path: {mod['path']}_", "",
           "## Goal",
           "Author an endpoint→code-chain outline for this module: for each endpoint, the call "
           "chain Controller → Service → Gateway/Repository/Client (+ Mapper, async/saga notes where present). "
           "**Read only the files listed below**, trace the calls, and write the outline to a plain .md file.",
           "", "## Endpoints and their handler files (read these controllers first)"]
    for e in mod.get("endpoints", [])[:200]:
        out.append(f"- `{e['method']} {e['path']}`  ·  `{e.get('file','?')}`")
    out += ["", "## Key classes by role (where services/repos/gateways live — read as needed)"]
    if role_index:
        for sym in sorted(role_index):
            out.append(f"- `{sym}`  ·  `{role_index[sym]}`")
    else:
        out.append("_(none matched role suffixes; inspect handler files and follow their imports)_")
    out += ["", f"## All declarations index ({len(all_decls)} symbols — sample)"]
    for sym in sorted(all_decls)[:120]:
        out.append(f"- `{sym}` · `{all_decls[sym]}`")
    out += ["", "## Next step",
            f"1. Read the handler files above (relative to `{mod['path']}/`), follow calls into the role classes.",
            "2. Write the outline to a .md file, e.g.:",
            "```",
            f"## {mod['id']}",
            "- **Role:** ...",
            "- **Endpoints**",
            "  - `METHOD /path` name",
            "    - Controller: `Class.method` → Service: `Class.method` → Repository/Client: `Class`",
            "```",
            f"3. Inject it:  `python3 set_markdown.py --module {mod['id']} --md-file <that-file> --in {args.indir}`",
            "4. Rebuild:    `python3 build.py --in {0} --out <site>`".format(args.indir)]

    ddir = os.path.join(args.indir, "deepen")
    os.makedirs(ddir, exist_ok=True)
    cpath = os.path.join(ddir, f"{mod['id'].replace('/', '_')}.context.md")
    open(cpath, "w").write("\n".join(out))
    print(f"wrote {cpath}")
    print(f"  {len(handler_files)} handler files, {len(role_index)} role classes, "
          f"{len(all_decls)} declarations indexed")
    print(f"next: read that context, author the outline, then run set_markdown.py --module {mod['id']}")


if __name__ == "__main__":
    main()
