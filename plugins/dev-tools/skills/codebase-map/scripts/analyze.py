#!/usr/bin/env python3
"""
codebase-map / analyze.py  —  deterministic codebase scanner (no LLM).

Discovers modules, detects stacks, extracts endpoints, infers raw edges,
hashes each module for change detection. Writes <out>/model.json and,
when a previous model exists, <out>/changes.json {added,changed,removed}.

Usage:
  analyze.py --root PATH [--out .codemap] [--depth 4]
"""
import os, re, json, hashlib, argparse, time

BUILD_MARKERS = {
    "package.json": "node", "pom.xml": "maven-jvm",
    "build.gradle": "gradle-jvm", "build.gradle.kts": "gradle-jvm",
    "settings.gradle": "gradle-jvm", "settings.gradle.kts": "gradle-jvm",
    "go.mod": "go", "Cargo.toml": "rust",
    "pyproject.toml": "python", "requirements.txt": "python", "setup.py": "python",
    "Gemfile": "ruby", "composer.json": "php", "build.sbt": "scala",
}
SKIP_DIRS = {".git", "node_modules", "vendor", "build", "dist", "target", ".gradle",
             "__pycache__", ".venv", "venv", ".idea", ".next", "out", "coverage",
             "tmp", ".terraform", "bin", "obj", "generated", ".cache"}
SRC_EXT = {".kt", ".java", ".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rb", ".rs", ".php", ".scala"}
CFG_NAMES = re.compile(r"(application.*\.(yml|yaml|properties)|docker-compose.*\.ya?ml|Dockerfile.*|\.env.*|"
                       r"openapi.*\.(ya?ml|json)|routes\.rb|.*\.gradle(\.kts)?|pom\.xml|package\.json|go\.mod)$")
MAX_FILE = 500_000
MAX_FILES_PER_MODULE = 4000


def detect_stack(path, markers):
    exts = set()
    for _, _, fs in os.walk(path):
        for f in fs:
            e = os.path.splitext(f)[1]
            if e in SRC_EXT:
                exts.add(e)
        break  # top level sample is enough for a hint; refined below
    if "package.json" in markers:
        return "typescript" if any(p.endswith((".ts", ".tsx")) for p in _shallow(path)) else "node"
    if any(m in markers for m in ("pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle.kts")):
        return "kotlin" if _has_ext(path, ".kt") else "java"
    if "go.mod" in markers: return "go"
    if "Gemfile" in markers: return "ruby"
    if any(m in markers for m in ("pyproject.toml", "requirements.txt", "setup.py")): return "python"
    if "Cargo.toml" in markers: return "rust"
    return BUILD_MARKERS.get(next(iter(markers), ""), "unknown")


def _shallow(path, n=200):
    out = []
    for dp, dn, fs in os.walk(path):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fs:
            out.append(f)
            if len(out) > n: return out
    return out


def _has_ext(path, ext, cap=3000):
    i = 0
    for dp, dn, fs in os.walk(path):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fs:
            if f.endswith(ext): return True
            i += 1
            if i > cap: return False
    return False


def iter_files(path):
    n = 0
    for dp, dn, fs in os.walk(path):
        dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.startswith(".")]
        for f in fs:
            yield os.path.join(dp, f)
            n += 1
            if n > MAX_FILES_PER_MODULE: return


def read(fp):
    try:
        if os.path.getsize(fp) > MAX_FILE: return ""
        with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return ""


# ----------------------------- endpoint extractors -----------------------------
def ex_spring(txt):
    out = []
    cls = re.search(r'@RequestMapping\(\s*(?:value\s*=\s*)?["\']([^"\']+)', txt)
    base = cls.group(1) if cls else ""
    for m in re.finditer(r'@(Get|Post|Put|Delete|Patch|Request)Mapping\(\s*(?:value\s*=\s*)?(?:\{\s*)?["\']([^"\']*)', txt):
        verb = m.group(1).upper() if m.group(1) != "Request" else "ANY"
        out.append((verb, (base + m.group(2)) or "/"))
    return out


def ex_ts(txt):
    out = []
    for m in re.finditer(r'\b(?:app|router|fastify)\.(get|post|put|delete|patch|all)\(\s*[`"\']([^`"\']+)', txt):
        out.append((m.group(1).upper(), m.group(2)))
    for m in re.finditer(r'@(Get|Post|Put|Delete|Patch)\(\s*[`"\']?([^`"\')]*)', txt):  # Nest
        out.append((m.group(1).upper(), m.group(2) or "/"))
    return out


def ex_py(txt):
    out = []
    for m in re.finditer(r'@(?:app|router)\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)', txt):
        out.append((m.group(1).upper(), m.group(2)))
    for m in re.finditer(r'@(?:app|blueprint)\.route\(\s*["\']([^"\']+)["\'](?:[^)]*methods\s*=\s*\[([^\]]*)\])?', txt):
        verbs = re.findall(r'["\'](\w+)["\']', m.group(2) or "") or ["GET"]
        for v in verbs: out.append((v.upper(), m.group(1)))
    return out


def ex_go(txt):
    out = []
    for m in re.finditer(r'\.(GET|POST|PUT|DELETE|PATCH)\(\s*"([^"]+)"', txt):
        out.append((m.group(1), m.group(2)))
    for m in re.finditer(r'HandleFunc\(\s*"([^"]+)"', txt):
        out.append(("ANY", m.group(1)))
    return out


def ex_rails(txt):
    out = []
    for m in re.finditer(r'\b(get|post|put|patch|delete)\s+["\']([^"\']+)', txt):
        out.append((m.group(1).upper(), m.group(2)))
    for m in re.finditer(r'\bresources?\s+:(\w+)', txt):
        out.append(("REST", "/" + m.group(1)))
    return out


def ex_openapi(txt):
    out, cur = [], None
    for line in txt.splitlines():
        pm = re.match(r'^\s{0,6}(/[^\s:]*):\s*$', line)
        if pm:
            cur = pm.group(1); continue
        vm = re.match(r'^\s{2,12}(get|post|put|delete|patch):\s*$', line)
        if vm and cur:
            out.append((vm.group(1).upper(), cur))
    return out


EXTRACTORS = {
    ".kt": ex_spring, ".java": ex_spring,
    ".ts": ex_ts, ".tsx": ex_ts, ".js": ex_ts, ".jsx": ex_ts,
    ".py": ex_py, ".go": ex_go, ".rb": ex_rails,
}


def extract_endpoints(path):
    eps, files = [], []
    seen = set()
    for fp in iter_files(path):
        ext = os.path.splitext(fp)[1]
        base = os.path.basename(fp)
        rel = os.path.relpath(fp, path)
        if ext in SRC_EXT or CFG_NAMES.search(base):
            files.append(rel)
        fn = None
        if re.search(r'openapi.*\.(ya?ml|json)$', base, re.I):
            fn = ex_openapi
        elif base == "routes.rb":
            fn = ex_rails
        elif ext in EXTRACTORS:
            fn = EXTRACTORS[ext]
        if not fn:
            continue
        txt = read(fp)
        if not txt:
            continue
        for verb, p in fn(txt):
            key = (verb, p)
            if key in seen:
                continue
            seen.add(key)
            eps.append({"method": verb, "path": p, "file": rel})
            if len(eps) > 600:
                return eps, files
    return eps, files


def module_hash(path):
    h = hashlib.sha1()
    items = []
    for fp in iter_files(path):
        if os.path.splitext(fp)[1] in SRC_EXT or CFG_NAMES.search(os.path.basename(fp)):
            try:
                st = os.stat(fp)
                items.append((os.path.relpath(fp, path), int(st.st_mtime), st.st_size))
            except OSError:
                pass
    for it in sorted(items):
        h.update(repr(it).encode())
    return h.hexdigest()[:16]


def find_modules(root, depth):
    mods = []
    for dp, dn, fs in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.startswith(".")]
        rel = os.path.relpath(dp, root)
        d = 0 if rel == "." else rel.count(os.sep) + 1
        if d > depth:
            dn[:] = []; continue
        markers = [f for f in fs if f in BUILD_MARKERS]
        if markers:
            mods.append((dp, rel, markers))
    # de-dup ids
    return mods


GENERIC_IDS = {"common", "config", "types", "type", "hooks", "test", "tests", "mock",
               "mocks", "env", "enums", "enum", "helpers", "constants", "utils", "util",
               "i18n", "e2e", "core", "api", "model", "models", "shared", "lib", "libs",
               "dna", "modality", "assets", "styles", "components", "app", "apps", "web"}


def _distinctive(mid):
    """Only treat ids that look like real service/component names as name-match targets,
    so generic package names don't create a fully-connected mess."""
    base = mid.split("/")[-1].lower()
    if base in GENERIC_IDS:
        return False
    return ("-" in base or "_" in base) or len(base) >= 8


def infer_edges(modules):
    """Heuristic edges: a module references another (distinctive) module's id in its config/source."""
    ids = {m["id"] for m in modules}
    aliases = {}
    for m in modules:
        if not _distinctive(m["id"]):
            aliases[m["id"]] = set()
            continue
        a = {m["id"], m["id"].replace("-", "_"), m["id"].replace("_", "-"),
             "".join(w.capitalize() for w in re.split(r"[-_]", m["id"].split("/")[-1]))}
        aliases[m["id"]] = {x for x in a if len(x) >= 6}
    edges = []
    for m in modules:
        text = m.pop("_text", "")
        compose = m.pop("_compose", [])
        hits = set()
        for other in modules:
            if other["id"] == m["id"] or not aliases[other["id"]]:
                continue
            for al in aliases[other["id"]]:
                if re.search(r"\b" + re.escape(al) + r"\b", text):
                    hits.add(other["id"]); break
        for dep in compose:
            if dep in ids and dep != m["id"]:
                hits.add(dep)
        for tgt in hits:
            edges.append({"from": m["id"], "to": tgt, "label": "", "kind": "current"})
    return edges


def gather_edge_text(path):
    """Concatenate config-ish files (bounded) for cross-module reference scanning + compose depends_on."""
    buf, compose = [], []
    cnt = 0
    for fp in iter_files(path):
        base = os.path.basename(fp)
        if CFG_NAMES.search(base):
            t = read(fp)
            buf.append(t)
            if base.startswith("docker-compose"):
                compose += re.findall(r'^\s*-\s*([a-z0-9_-]+)\s*$', t, re.M)
                compose += re.findall(r'^\s{2,}([a-z0-9_-]+):\s*$', t, re.M)
            cnt += 1
            if cnt > 60:
                break
    return "\n".join(buf)[:200_000], compose


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default=".codemap")
    ap.add_argument("--depth", type=int, default=4)
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    os.makedirs(args.out, exist_ok=True)

    raw = find_modules(root, args.depth)
    modules = []
    used = set()
    for path, rel, markers in raw:
        mid = os.path.basename(path)
        if mid in used:
            mid = rel.replace(os.sep, "/")
        used.add(mid)
        stack = detect_stack(path, set(markers))
        eps, files = extract_endpoints(path)
        text, compose = gather_edge_text(path)
        modules.append({
            "id": mid, "path": os.path.relpath(path, root), "stack": stack,
            "markers": markers, "fileCount": len(files),
            "endpoints": eps, "endpointCount": len(eps),
            "hash": module_hash(path), "_text": text, "_compose": compose,
        })

    edges = infer_edges(modules)  # also strips _text/_compose
    model = {"root": root, "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "moduleCount": len(modules), "modules": modules, "edges": edges}

    # change detection vs previous model
    prev_path = os.path.join(args.out, "model.json")
    changes = {"added": [], "changed": [], "removed": []}
    if os.path.exists(prev_path):
        try:
            prev = json.load(open(prev_path))
            ph = {m["id"]: m["hash"] for m in prev.get("modules", [])}
            ch = {m["id"]: m["hash"] for m in modules}
            for mid, h in ch.items():
                if mid not in ph: changes["added"].append(mid)
                elif ph[mid] != h: changes["changed"].append(mid)
            changes["removed"] = [mid for mid in ph if mid not in ch]
        except (ValueError, KeyError):
            pass

    json.dump(model, open(prev_path, "w"), indent=1)
    json.dump(changes, open(os.path.join(args.out, "changes.json"), "w"), indent=1)
    print(f"modules: {len(modules)}  edges: {len(edges)}  "
          f"endpoints: {sum(m['endpointCount'] for m in modules)}")
    if any(changes.values()):
        print(f"changes  added={changes['added']} changed={changes['changed']} removed={changes['removed']}")
    print(f"wrote {prev_path}")


if __name__ == "__main__":
    main()
