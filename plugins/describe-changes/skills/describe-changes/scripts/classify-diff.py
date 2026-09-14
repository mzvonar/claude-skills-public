#!/usr/bin/env python3
"""classify-diff.py — deterministic noise pass for describe-changes (stdlib only).

Reads a unified diff (git diff -M -C) and emits:
  diff-model.json   per-file / per-hunk classification, folds, symbol moves, stats
  substantive.diff  a unified diff containing ONLY hunks a human may need to read

Hunk categories (exactly one per hunk):
  substantive      real behaviour change — goes to the LLM and the human
  whitespace       identical after whitespace normalisation (not in whitespace-sensitive langs)
  format           identical after whitespace + trailing comma/semicolon + quote normalisation
  import-rewrite   only import/require specifiers changed (typically follow a rename/move)
  comment-only     every changed line is a comment
File-level noise kinds (whole file folded): lockfile, generated, snapshot, vendored, binary, rename (pure).

The LLM never re-derives any of this — it reads diff-model.json + substantive.diff.
"""
import argparse, json, os, re, sys
from collections import defaultdict

WS_SENSITIVE = {".py", ".pyi", ".hs", ".lhs", ".yml", ".yaml", ".nim", ".coffee", ".pug", ".jade",
                ".slim", ".haml", ".sass", ".styl", ".md", ".mdx", ".rst", ".f90", ".cbl"}
WS_SENSITIVE_NAMES = {"Makefile", "makefile", "GNUmakefile"}
# Languages with Automatic Semicolon Insertion. A line break is SEMANTIC in these even though the
# language is not whitespace-sensitive in the indentation sense: `return\n  value` returns undefined
# where `return value` does not. So a block whose LINE STRUCTURE changed can never be folded as
# whitespace/format here, however identical the two sides look once the newlines are stripped.
# Cost, stated: a pure prettier-style reflow that changes line count stops folding in these
# languages. That is the intended trade — re-indentation (the common case) keeps folding because it
# preserves line count, and no fold is allowed to hide a behaviour change.
ASI_LANGS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".go"}
LOCKFILES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock", "Cargo.lock",
             "poetry.lock", "Pipfile.lock", "composer.lock", "Gemfile.lock", "go.sum", "flake.lock",
             "mix.lock", "pubspec.lock", "packages.lock.json", "uv.lock", "pdm.lock"}
GENERATED_RE = re.compile(r"(^|/)(dist|build|out|coverage|\.next|node_modules|vendor|__generated__|generated|"
                          r"\.gen|target)/|\.min\.(js|css)$|\.(map|pb\.go|pb2\.py|g\.cs|d\.ts)$|(^|/)_generated[./]", re.I)
SNAPSHOT_RE = re.compile(r"(^|/)__snapshots__/|\.snap$|\.snapshot$")
GENERATED_MARKERS = ("@generated", "DO NOT EDIT", "do not edit", "Code generated", "auto-generated", "AUTO-GENERATED")

IMPORT_RE = re.compile(r"""^\s*(
    import\s.*|                                  # js/ts/py/go/java/kotlin/swift/rust-ish
    from\s+\S+\s+import\s.*|                      # python
    export\s+(\*|\{[^}]*\})\s+from\s.*|           # js re-export
    (const|let|var)\s+.*=\s*require\(.*|          # cjs
    require\s*\(.*|                               # bare require / ruby
    use\s+[\w:]+.*|                               # rust/php
    using\s+[\w.]+\s*;|                           # c#
    #include\s.*                                  # c/c++
)\s*$""", re.X)
COMMENT_RE = re.compile(r"^\s*(//|#|/\*|\*|\*/|--|<!--|;;|%|'''|\"\"\"|///|\"\"\"\s*$)")
# A named specifier alone on a line inside a multi-line import block: `  Foo,` / `  type Bar,` /
# `  Foo as Baz,`. Counted as import noise ONLY when the hunk is demonstrably inside an import
# statement (see IMPORT_CONTEXT_RE) — on its own such a line is indistinguishable from an object
# literal entry, an enum member or an array element, and folding those would hide real changes.
# Without this, re-pointing an import at a barrel reads as substantive: the DELETED deep-path
# `import { X } from "…/x"` lines match IMPORT_RE, but the ADDED `X,` inside the existing braces
# does not, so the hunk is half import-rewrite and half "substantive" and never folds.
SPECIFIER_RE = re.compile(r"^\s*(type\s+)?[A-Za-z_$][\w$]*(\s+as\s+[A-Za-z_$][\w$]*)?\s*,?\s*$")
# Deliberately `import` ONLY, not `export {`. Both are brace-and-specifier blocks, but adding a
# specifier to an EXPORT widens a module's public API — in this codebase a barrel is rule-bound
# (`service/index.ts` may export only `AsUser` functions), so a new export line is exactly the kind
# of thing a reviewer must see. An import moving to a different path changes nothing it can observe.
IMPORT_CONTEXT_RE = re.compile(r"^\s*import\b")
SYMBOL_RE = re.compile(r"""^\s*(?:export\s+)?(?:default\s+)?(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:static\s+)?
    (?:function\*?|def|fn|func|class|interface|type|enum|struct|trait|impl|module|object|
       (?:const|let|var|val)|(?:public|private|protected|internal)\s+(?:static\s+)?(?:[\w<>\[\],.?]+\s+)?)
    \s+([A-Za-z_$][\w$]*)""", re.X)
SPEC_RE = re.compile(r"""(['"])([^'"]+)\1""")
UNRESOLVED_MODULE = "(module not named in the hunk)"

# Working notes: the prose a change PRODUCES rather than the change itself — plans, handoffs, a
# lessons inbox, an append-only journal, a deferred-work backlog. Markdown only, and a decision
# record (ADR), a wiki page, a README or a changelog is deliberately NOT here: those are the "why"
# a reviewer most needs. Override with DESCRIBE_CHANGES_NOTES_RE when a repo names them differently.
NOTES_RE = re.compile(os.environ.get("DESCRIBE_CHANGES_NOTES_RE") or
                      r"(^|/)_bmad-output/|(^|/)plans?/|(^|/)(deferred-work|lessons-inbox|scratch)\.md$"
                      r"|(^|/)[^/]*handoff[^/]*\.md$|(^|/)wiki/log\.md$", re.I)
MD_EXT = (".md", ".mdx")
LINK_RE = re.compile(r"\]\(([^)\s]+)")
JSX_OPEN_RE = re.compile(r"<([A-Z][\w.]*)")
# A TYPE annotation, not an object-literal entry: the value side must be a TS primitive, a
# capitalised type, or a function type. `foo: bar,` in a literal does not qualify, and JSON keys
# are quoted so they never reach here.
PROP_DECL_RE = re.compile(r"^\s*(?:readonly\s+)?([A-Za-z_$][\w$]*)\??\s*:\s*"
                          r"(?:boolean|string|number|bigint|symbol|\(|[A-Z][\w.<>\[\]|\s]*)")

def ext_of(path):
    base = os.path.basename(path)
    if base in WS_SENSITIVE_NAMES: return "Makefile"
    return os.path.splitext(base)[1].lower()

def language(path):
    e = ext_of(path)
    return {".ts": "typescript", ".tsx": "tsx", ".js": "javascript", ".jsx": "jsx", ".mjs": "javascript",
            ".cjs": "javascript", ".py": "python", ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
            ".swift": "swift", ".rb": "ruby", ".php": "php", ".cs": "csharp", ".c": "c", ".h": "c", ".cpp": "cpp",
            ".hs": "haskell", ".ex": "elixir", ".exs": "elixir", ".scala": "scala", ".clj": "clojure",
            ".css": "css", ".scss": "scss", ".html": "html", ".vue": "vue", ".svelte": "svelte", ".sql": "sql",
            ".sh": "shell", ".bash": "shell", ".zsh": "shell", ".yml": "yaml", ".yaml": "yaml", ".json": "json",
            ".md": "markdown", ".mdx": "markdown", ".toml": "toml", "Makefile": "make"}.get(e, e.lstrip(".") or "text")


# ---------------------------------------------------------------- area
# Which of FOUR reading registers a file belongs to, so the report's "Everything else" list can put
# code first and let the reader skim or skip the rest. The order of the checks IS the rule — a file
# lands in the first bucket that matches — and it is mandatory: without a fixed precedence a `.sql`
# fixture under tests/ or a CI YAML lands differently between runs and the grouping looks unstable.
#
#   1. tests    — a test dir segment in the path, a *.test.* / *.spec.* / *_test.* / conftest.py
#                 basename, or a fixture/snapshot under a test dir (covered by the segment rule)
#   2. tooling  — dotfiles and dot-dirs, CI configs, manifests, lockfiles, Dockerfile/Makefile,
#                 *.config.*, root-level *.yml/*.yaml, root-level scripts/
#   3. docs     — *.md/*.mdx/*.rst/*.txt, LICENSE-class names, anything under docs/
#   4. code     — everything else; the default, never empty by rule
#
# Tests come first because "did they test it?" is the commonest question asked of the remainder,
# and an EMPTY tests bucket must be visible at a glance — folding tests into code hides exactly
# that. Tooling is decided BEFORE docs so a skill's SKILL.md or a CLAUDE.md counts as tooling, not
# prose. The same table lives in reference/analysis-guide.md; this function is the implementation.
TEST_DIRS = {"tests", "test", "__tests__", "spec", "specs", "e2e", "__fixtures__", "fixtures", "__snapshots__", "__mocks__"}
# `*.test.*` names a TEST only for code; `docker-compose.test.yml` / `app.test.json` are configs
# named after an environment, so config extensions are excluded from the basename rule.
TEST_BASENAME_RE = re.compile(r"(^|[._-])(test|spec|tests|specs)\.(?!ya?ml$|json$|toml$|ini$|env$|cfg$)[^.]+$|^conftest\.py$|_test\.[^.]+$|^test_[^/]+\.py$", re.I)
TOOLING_DIRS = (".claude/", ".agents/", ".cursor/", ".codex/", ".github/", ".gitlab/", ".husky/", ".vscode/",
                ".idea/", ".devcontainer/", ".circleci/", ".buildkite/")
TOOLING_NAMES = {"CLAUDE.md", "AGENTS.md", ".gitlab-ci.yml", "Dockerfile", "Makefile", "Justfile", "justfile",
                 ".editorconfig", ".gitignore", ".gitattributes", ".gitmodules", ".nvmrc", ".node-version",
                 ".tool-versions", ".python-version", "package.json", "pnpm-workspace.yaml", "lerna.json",
                 "turbo.json", "nx.json", "pyproject.toml", "setup.cfg", "Cargo.toml", "go.mod", "build.gradle",
                 "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "pom.xml", "Gemfile", "renovate.json",
                 ".renovaterc", "dependabot.yml", "codecov.yml", "sonar-project.properties"}
DOC_DIRS = ("docs/", "doc/", "wiki/", "_bmad-output/", ".planning/", "adr/", "rfcs/")
DOC_EXT = {".md", ".mdx", ".rst", ".adoc", ".txt"}

AREAS = ("code", "tests", "tooling", "docs")

def area(path):
    p = path.replace("\\", "/"); base = p.rsplit("/", 1)[-1]; e = ext_of(p)
    segs = p.split("/")[:-1]
    if any(s in TEST_DIRS for s in segs) or TEST_BASENAME_RE.search(base): return "tests"
    if p.startswith(TOOLING_DIRS) or base in TOOLING_NAMES or base in LOCKFILES: return "tooling"
    if base.startswith(".") and "/" not in p: return "tooling"                       # a root dotfile
    if e in (".yml", ".yaml") and "/" not in p: return "tooling"                       # root-level CI/config YAML
    if p.startswith("scripts/"): return "tooling"                                      # repo-root scripts/
    if re.match(r"^(docker-compose[\w.-]*\.ya?ml|compose[\w.-]*\.ya?ml|tsconfig[\w.-]*\.json|\.[\w-]+rc(\.[\w]+)?|[\w.-]+\.config\.[cm]?[jt]s|lint-staged\.config\.[cm]?js)$", base):
        return "tooling"
    if base.split(".")[0].upper() in {"README", "CHANGELOG", "LICENSE", "CONTRIBUTING", "CODEOWNERS", "SECURITY", "NOTICE"}: return "docs"
    if e in DOC_EXT or p.startswith(DOC_DIRS): return "docs"
    return "code"


# ---------------------------------------------------------------- db schema package
# The database change is ONE thing to review, however many files carry it: the authored schema
# artifact is the headline, its migrations are a sidecar. Everything mechanical about it lives
# here — which files, in what order, what the SQL does, how severe that is — so the analyst copies
# facts rather than inventing them, and the validator can hold the report to them.
#
# Nothing here is Prisma-shaped. A project with no schema concept (raw SQL files, an ORM with
# migrations only) is the second branch of one rule: the migrations themselves become the headline.
SCHEMA_CONVENTIONS = ("prisma/schema.prisma", "db/schema.rb", "schema.sql", "db/schema.sql", "db/structure.sql")
SCHEMA_BASENAMES = {"schema.prisma", "schema.rb"}
MIGRATION_DIR_SEGS = {"migrations", "migrate", "migration"}
MIGRATION_LOCK_RE = re.compile(r"(^|/)migration_lock\.[\w]+$")
CONFIG_FILE = ".claude/claude-skills.json"

def load_skill_config(root):
    """The consuming repo's `.claude/claude-skills.json`, or {} — never an error."""
    if not root: return {}
    try:
        with open(os.path.join(root, CONFIG_FILE), encoding="utf-8") as fh:
            cfg = json.load(fh)
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}

def _norm_rel(p):
    return p.replace("\\", "/").strip("/") if p else p

def db_layout(root, paths, cfg):
    """(schema_artifact, is_configured, migration_dirs) for this repo.

    `schema_artifact` is a repo-relative path or None. Convention first (the file must EXIST on
    disk or arrive in this diff), then the override in `describe-changes.schemaArtifact`. A
    configured path wins even when it does not exist yet — a typo in the config should be visible
    as "no schema change" plus a migration package, not silently replaced by a convention."""
    dc = cfg.get("describe-changes") or {}
    paths = set(paths)
    def present(rel): return rel in paths or (root and os.path.isfile(os.path.join(root, rel)))
    schema = _norm_rel(dc.get("schemaArtifact")) if isinstance(dc.get("schemaArtifact"), str) else None
    if not schema:
        for cand in SCHEMA_CONVENTIONS:
            if present(cand): schema = cand; break
    if not schema:
        # `**/schema.prisma` — anywhere, from the index or the diff
        hits = sorted(p for p in paths if p.rsplit("/", 1)[-1] in SCHEMA_BASENAMES)
        if not hits and root:
            try:
                import subprocess
                out = subprocess.run(["git", "-C", root, "ls-files", "-z", "--", "*schema.prisma", "*schema.rb"],
                                     capture_output=True, text=True, timeout=10)
                hits = sorted(p for p in out.stdout.split("\0") if p and p.rsplit("/", 1)[-1] in SCHEMA_BASENAMES)
            except Exception:
                hits = []
        schema = hits[0] if hits else None
    mig = dc.get("migrationsDir")
    mig_dirs = [_norm_rel(m) for m in (mig if isinstance(mig, list) else [mig]) if isinstance(m, str) and m]
    return schema, bool(dc.get("schemaArtifact")), mig_dirs

def is_migration_path(path, mig_dirs):
    """Under a configured migrations dir, or under a conventional one (any depth), or a *.sql
    whose path carries a migration segment. Lock/metadata files inside the dir are not migrations."""
    p = path.replace("\\", "/")
    if MIGRATION_LOCK_RE.search(p): return False
    for d in mig_dirs:
        if p.startswith(d + "/"): return True
    if mig_dirs: return False                         # an override REPLACES the convention
    segs = p.split("/")[:-1]
    if any(s.lower() in MIGRATION_DIR_SEGS for s in segs): return True
    return False

def unmanaged_sql(cfg):
    """(names, source): objects the repo declares as outside the ORM's model, and which key said so."""
    for key in ("describe-changes", "prisma-migrate"):
        items = (cfg.get(key) or {}).get("unmanagedSql")
        if isinstance(items, list) and items:
            names = set()
            for it in items:
                if isinstance(it, dict) and it.get("name"): names.add(str(it["name"]).strip('"'))
                elif isinstance(it, str): names.add(it.strip('"'))
            if names: return names, key
    return set(), None

# --- SQL operations ------------------------------------------------------------------------------
# A small, honest parser: statements split on `;` with comments stripped, each matched against the
# handful of shapes that decide severity. It does not understand SQL; it recognises the verbs a
# reviewer is paid to notice. Every op it emits quotes the statement it came from, which is what
# lets the per-file summary line satisfy "every operation named must literally appear in the file".
SQL_COMMENT_RE = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
IDENT = r'"?([\w$.]+)"?'
def _ident(s): return (s or "").strip('"').split(".")[-1]

REASON_SEVERITY = {          # §4.2 — the ONE place a reason's severity is decided (§12 tunes here)
    "destructive_ddl": "critical", "unrepresented_ddl": "critical", "data_mutation": "critical",
    "schema_migration_drift": "critical", "ordering": "medium", "structural_ddl": "medium",
    "additive_ddl": "low",
}
REASON_QUESTION = {
    "destructive_ddl": "What data does this lose, and is it recoverable?",
    "unrepresented_ddl": "Will it survive the next generated migration?",
    "data_mutation": "Does the predicate match the intended rows, and is it idempotent?",
    "ordering": "Does the backfill run before or after the structural change?",
    "schema_migration_drift": "Why is there no migration?",
    "structural_ddl": "Is the new structure the intended shape, and does existing data satisfy it?",
    "additive_ddl": "Is anything here more than additive?",
}
SEV_RANK = {"critical": 0, "medium": 1, "low": 2}
UNREP_INDEX_RE = re.compile(r"\bUSING\s+(hnsw|ivfflat|gin|gist|spgist|brin)\b", re.I)

def split_sql(text):
    text = SQL_COMMENT_RE.sub(" ", text)
    return [s.strip() for s in text.split(";") if s.strip()]

def sql_ops(text, unmanaged=None, schema_aware=True):
    """Ops in one migration's SQL. Each: {kind, severity, phrase, statement, object?, unrep?}.

    `unmanaged` is the set of object names the repo declares outside its ORM (config), or None when
    no such config exists — the two modes of §4.3. `schema_aware` is False for a project with no
    schema artifact, where "not represented in the schema" is not a meaningful claim."""
    ops = []
    stmts = split_sql(text)
    created_tables = {_ident(m.group(1)).lower() for s in stmts
                      for m in [re.match(r"\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?" + IDENT, s, re.I)] if m}
    defaults = set()      # (table, column) that receive a DEFAULT somewhere in the file
    for s in stmts:
        for m in re.finditer(r"ALTER\s+TABLE\s+(?:ONLY\s+)?" + IDENT + r".*?ALTER\s+(?:COLUMN\s+)?" + IDENT + r"\s+SET\s+DEFAULT", s, re.I | re.S):
            defaults.add((_ident(m.group(1)).lower(), _ident(m.group(2)).lower()))
    created_objs = set()  # names CREATEd in this file (index/trigger/view/function/constraint)
    for s in stmts:
        m = re.match(r"\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:UNIQUE\s+)?(?:MATERIALIZED\s+)?(?:INDEX|TRIGGER|VIEW|FUNCTION|POLICY)\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?" + IDENT, s, re.I)
        if m: created_objs.add(_ident(m.group(1)))
        for m2 in re.finditer(r"ADD\s+CONSTRAINT\s+" + IDENT, s, re.I): created_objs.add(_ident(m2.group(1)))

    def add(kind, phrase, stmt, obj=None, **extra):
        ops.append(dict(kind=kind, severity=REASON_SEVERITY[kind], phrase=phrase, object=obj,
                        statement=re.sub(r"\s+", " ", stmt)[:160], **extra))

    for s in stmts:
        u = re.sub(r"\s+", " ", s)
        head = u[:40].upper()
        # ---- DML
        m = re.match(r"(UPDATE|INSERT INTO|DELETE FROM|MERGE INTO)\s+" + IDENT, u, re.I)
        if m:
            verb = m.group(1).split()[0].upper()
            add("data_mutation", f"runs {verb} on {_ident(m.group(2))}", s, _ident(m.group(2)), verb=verb); continue
        if head.startswith("TRUNCATE"):
            m = re.match(r"TRUNCATE\s+(?:TABLE\s+)?" + IDENT, u, re.I)
            add("destructive_ddl", f"truncates {_ident(m.group(1)) if m else 'a table'}", s); continue
        # ---- destructive DDL
        m = re.match(r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?" + IDENT, u, re.I)
        if m: add("destructive_ddl", f"drops table {_ident(m.group(1))}", s, _ident(m.group(1))); continue
        tm = re.match(r"ALTER\s+TABLE\s+(?:ONLY\s+)?(?:IF\s+EXISTS\s+)?" + IDENT, u, re.I)
        table = _ident(tm.group(1)) if tm else None
        if tm:
            n_before = len(ops)
            # `DROP col` is legal without the COLUMN keyword, so exclude the other DROP forms that
            # live inside an ALTER TABLE: `ALTER COLUMN x DROP NOT NULL|DEFAULT|IDENTITY|EXPRESSION`.
            for m in re.finditer(r"DROP\s+(?!NOT\b|DEFAULT\b|CONSTRAINT\b|IDENTITY\b|EXPRESSION\b)(?:COLUMN\s+)?(?:IF\s+EXISTS\s+)?" + IDENT, u, re.I):
                add("destructive_ddl", f"drops column {table}.{_ident(m.group(1))}", s, table)
            for m in re.finditer(r"DROP\s+CONSTRAINT\s+(?:IF\s+EXISTS\s+)?" + IDENT, u, re.I):
                name = _ident(m.group(1))
                if unmanaged is not None and name in unmanaged and name not in created_objs:
                    add("unrepresented_ddl", f"drops unmanaged constraint {name} without re-creating it", s, name, detected_by="config")
                elif re.search(r"_fkey$|_fk$|foreign", name, re.I):
                    add("destructive_ddl", f"drops FK constraint {name}", s, name)
                else:
                    add("additive_ddl", f"drops constraint {name}", s, name)
            for m in re.finditer(r"ALTER\s+(?:COLUMN\s+)?" + IDENT + r"\s+SET\s+NOT\s+NULL", u, re.I):
                col = _ident(m.group(1))
                if (table.lower(), col.lower()) in defaults:
                    add("additive_ddl", f"sets {table}.{col} NOT NULL (with a default)", s, table)
                else:
                    add("destructive_ddl", f"sets {table}.{col} NOT NULL without a default", s, table)
            for m in re.finditer(r"ALTER\s+(?:COLUMN\s+)?" + IDENT + r"\s+(?:SET\s+DATA\s+)?TYPE\s+([\w\s()\[\],]+?)(?:\s+USING|,|$)", u, re.I):
                add("destructive_ddl", f"changes type of {table}.{_ident(m.group(1))} to {m.group(2).strip()}", s, table)
            for m in re.finditer(r"ADD\s+(?:COLUMN\s+)?(?:IF\s+NOT\s+EXISTS\s+)?" + IDENT + r"\s+([^,]+?)(?:,\s*ADD|$)", u, re.I):
                if re.match(r"ADD\s+CONSTRAINT", m.group(0), re.I): continue
                col, rest = _ident(m.group(1)), m.group(2)
                if re.search(r"\bNOT\s+NULL\b", rest, re.I) and not re.search(r"\bDEFAULT\b", rest, re.I) and table.lower() not in created_tables:
                    add("destructive_ddl", f"adds NOT NULL column {table}.{col} without a default", s, table)
                else:
                    add("additive_ddl", f"adds column {table}.{col}", s, table)
            for m in re.finditer(r"ADD\s+CONSTRAINT\s+" + IDENT + r"\s+(.+?)(?=,\s*ADD\s+CONSTRAINT|$)", u, re.I):
                name, body = _ident(m.group(1)), m.group(2)
                if re.search(r"\bFOREIGN\s+KEY\b", body, re.I):
                    if re.search(r"ON\s+(DELETE|UPDATE)\s+(CASCADE|SET\s+NULL|SET\s+DEFAULT)", body, re.I):
                        add("destructive_ddl", f"adds FK {name} with cascade", s, name)
                    else:
                        add("structural_ddl", f"adds FK {name}", s, name)
                elif re.search(r"\bUNIQUE\b", body, re.I):
                    if table.lower() in created_tables: add("additive_ddl", f"unique constraint {name} on new table", s, name)
                    else: add("structural_ddl", f"unique constraint {name} on existing {table}", s, name)
                elif re.search(r"\bCHECK\s*\(", body, re.I):
                    if unmanaged is not None and name in unmanaged: add("additive_ddl", f"re-asserts unmanaged CHECK {name}", s, name)
                    elif schema_aware: add("unrepresented_ddl", f"adds CHECK constraint {name}", s, name, detected_by="config" if unmanaged is not None else "heuristic")
                    else: add("structural_ddl", f"adds CHECK constraint {name}", s, name)
                else:
                    add("structural_ddl", f"adds constraint {name}", s, name)
            for m in re.finditer(r"ALTER\s+(?:COLUMN\s+)?" + IDENT + r"\s+DROP\s+NOT\s+NULL", u, re.I):
                add("additive_ddl", f"drops NOT NULL on {table}.{_ident(m.group(1))}", s, table)
            if len(ops) == n_before:
                add("additive_ddl", f"alters table {table}", s, table)
            continue
        m = re.match(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?" + IDENT, u, re.I)
        if m:
            add("structural_ddl", f"creates table {_ident(m.group(1))}", s, _ident(m.group(1)))
            if schema_aware and re.search(r"\bCHECK\s*\(", u, re.I):
                add("unrepresented_ddl", f"CHECK constraint inside table {_ident(m.group(1))}", s, _ident(m.group(1)),
                    detected_by="config" if unmanaged is not None else "heuristic")
            continue
        m = re.match(r"CREATE\s+(UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?" + IDENT + r"\s+ON\s+(?:ONLY\s+)?" + IDENT, u, re.I)
        if m:
            uniq, name, on = bool(m.group(1)), _ident(m.group(2)), _ident(m.group(3))
            special = UNREP_INDEX_RE.search(u) or re.search(r"\)\s*WHERE\s+", u, re.I)
            if special and schema_aware:
                what = ("%s index" % UNREP_INDEX_RE.search(u).group(1).lower()) if UNREP_INDEX_RE.search(u) else "partial index"
                if unmanaged is not None and name in unmanaged:
                    add("additive_ddl", f"re-asserts unmanaged {what} {name}", s, name)
                else:
                    add("unrepresented_ddl", f"creates {what} {name}" + (" (not in unmanagedSql)" if unmanaged is not None else ""), s, name,
                        detected_by="config" if unmanaged is not None else "heuristic")
            elif uniq:
                if on.lower() in created_tables: add("additive_ddl", f"unique index {name} on new table", s, name)
                else: add("structural_ddl", f"unique index {name} on existing {on}", s, name)
            else:
                add("additive_ddl", f"creates index {name}", s, name)
            continue
        m = re.match(r"DROP\s+INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+EXISTS\s+)?" + IDENT, u, re.I)
        if m:
            name = _ident(m.group(1))
            if unmanaged is not None and name in unmanaged and name not in created_objs:
                add("unrepresented_ddl", f"drops unmanaged index {name} without re-creating it", s, name, detected_by="config")
            else:
                add("additive_ddl", f"drops index {name}", s, name)
            continue
        m = re.match(r"CREATE\s+(?:OR\s+REPLACE\s+)?(TRIGGER|FUNCTION|(?:MATERIALIZED\s+)?VIEW|POLICY)\s+(?:IF\s+NOT\s+EXISTS\s+)?" + IDENT, u, re.I)
        if m:
            kind, name = m.group(1).lower().replace("materialized ", "materialized "), _ident(m.group(2))
            if schema_aware and not (unmanaged is not None and name in unmanaged):
                add("unrepresented_ddl", f"creates {kind} {name}", s, name, detected_by="config" if unmanaged is not None else "heuristic")
            else:
                add("additive_ddl", f"creates {kind} {name}", s, name)
            continue
        m = re.match(r"DROP\s+(TRIGGER|FUNCTION|(?:MATERIALIZED\s+)?VIEW|POLICY)\s+(?:IF\s+EXISTS\s+)?" + IDENT, u, re.I)
        if m:
            name = _ident(m.group(2))
            if unmanaged is not None and name in unmanaged and name not in created_objs:
                add("unrepresented_ddl", f"drops unmanaged {m.group(1).lower()} {name} without re-creating it", s, name, detected_by="config")
            else:
                add("additive_ddl", f"drops {m.group(1).lower()} {name}", s, name)
            continue
        if re.match(r"(CREATE|ALTER|DROP)\s+(TYPE|SEQUENCE|SCHEMA|EXTENSION|ENUM|DOMAIN)\b", u, re.I):
            add("additive_ddl", u.split("(")[0][:50].lower(), s); continue
        # anything else: unknown statement, recorded so the reader can see it was not understood
        if re.match(r"(CREATE|ALTER|DROP|RENAME|COMMENT|GRANT|REVOKE|SET|BEGIN|COMMIT|DO)\b", u, re.I):
            add("additive_ddl", "statement not classified: " + u[:40].lower(), s)
    return ops

SUMMARY_GROUP_RE = re.compile(r"^(drops|adds|creates|sets|changes|runs|truncates)\s+"
                              r"(FK constraint|NOT NULL column|CHECK constraint|unique index|unique constraint|type of|"
                              r"column|table|index|constraint|UPDATE|INSERT|DELETE|MERGE)\b")
PLURAL = {"type of": "column types", "NOT NULL column": "NOT NULL columns", "unique index": "unique indexes",
          "unique constraint": "unique constraints", "FK constraint": "FK constraints",
          "CHECK constraint": "CHECK constraints", "index": "indexes", "UPDATE": "UPDATEs", "INSERT": "INSERTs",
          "DELETE": "DELETEs", "MERGE": "MERGEs"}

def ops_summary(ops, cap=100):
    """The per-file one-liner (§5): the operations, not the severity. Only ops at critical/medium
    are named — a low-only file gets no line, because a bare filename means nothing to see.
    `drops column a.x; drops column a.y` collapses to `drops 2 columns`; a lone op keeps its phrase,
    which quotes the object the statement names."""
    keep = [o for o in ops if SEV_RANK[o["severity"]] <= SEV_RANK["medium"]]
    if not keep: return None
    groups = {}
    for o in keep:
        m = SUMMARY_GROUP_RE.match(o["phrase"])
        key = (m.group(1), m.group(2)) if m else (o["phrase"], None)
        groups.setdefault(key, []).append(o["phrase"])
    parts = []
    for (verb, noun), phrases in groups.items():
        if len(phrases) == 1 or noun is None: parts.append(phrases[0])
        else: parts.append(f"{verb} {len(phrases)} {PLURAL.get(noun, noun + 's')}")
    line = "; ".join(parts)
    return line if len(line) <= cap else line[:cap - 1].rstrip() + "…"

def db_scan(files, root, cfg):
    """The DB package as facts: headline, ordered migrations with their ops, the reasons the SQL
    supports, and the package severity. None when the diff touches no DB file.

    `files` are parsed FileDiffs. Only the ADDED side of a migration is parsed — a migration is
    normally an added file, and for an edited one the added lines are what changed."""
    paths = [f.path for f in files]
    schema, schema_cfg, mig_dirs = db_layout(root, paths, cfg)
    unmanaged, unmanaged_src = unmanaged_sql(cfg)
    mig_files = sorted((f for f in files if is_migration_path(f.path, mig_dirs)), key=lambda f: f.path)
    schema_changed = bool(schema) and schema in paths
    if not mig_files and not schema_changed:
        return None
    schema_aware = bool(schema)
    migrations, all_ops = [], []
    for f in mig_files:
        text = "\n".join(l for h in f.hunks for l in h.added)
        ops = sql_ops(text, unmanaged if unmanaged else None, schema_aware) if ext_of(f.path) == ".sql" else []
        sev = min((o["severity"] for o in ops), key=lambda s: SEV_RANK[s], default=None)
        migrations.append({"path": f.path, "status": f.status, "language": language(f.path), "ops": ops,
                           "severity": sev, "summary": ops_summary(ops)})
        all_ops += [dict(o, path=f.path) for o in ops]
    reasons = []
    def reason(kind, detail, **extra):
        reasons.append(dict(kind=kind, severity=REASON_SEVERITY[kind], question=REASON_QUESTION[kind], detail=detail, **extra))
    by_kind = {}
    for o in all_ops: by_kind.setdefault(o["kind"], []).append(o)
    def listing(ops, n=6):
        seen = list(dict.fromkeys(o["phrase"] for o in ops))
        return "; ".join(seen[:n]) + (f"; +{len(seen) - n} more" if len(seen) > n else "")
    if "destructive_ddl" in by_kind:
        reason("destructive_ddl", listing(by_kind["destructive_ddl"]) + ".")
    # Case 2 (§6): migrations with DDL but NO schema diff, in a project that HAS a schema artifact.
    # That is genuine drift — the ORM does not know these objects exist and its next generated
    # migration can drop them. Distinct from a DML-only backfill, which correctly has no schema diff.
    ddl = [o for o in all_ops if o["kind"] != "data_mutation"]
    if schema_aware and mig_files and not schema_changed and ddl:
        reason("unrepresented_ddl", f"{schema} did not change in this diff, so the schema does not describe what these "
               f"migrations do: {listing(ddl)}. The next generated migration can silently undo it.", detected_by="no_schema_diff")
    elif "unrepresented_ddl" in by_kind:
        # `detected_by` carries the mechanism; the renderer spells it out under the reason, so the
        # detail stays the list of statements and does not say it twice.
        by = sorted({o.get("detected_by", "heuristic") for o in by_kind["unrepresented_ddl"]})
        reason("unrepresented_ddl", listing(by_kind["unrepresented_ddl"]) + ".", detected_by=by[0] if len(by) == 1 else "config")
    if "data_mutation" in by_kind:
        reason("data_mutation", listing(by_kind["data_mutation"]) + ".")
    dml_files = {o["path"] for o in by_kind.get("data_mutation", [])}
    ddl_files = {o["path"] for o in all_ops if o["kind"] in ("destructive_ddl", "structural_ddl")}
    if len(mig_files) >= 2 and dml_files and (ddl_files - dml_files):
        order = [m["path"].rsplit("/", 2)[-2] if "/" in m["path"] else m["path"] for m in migrations if m["path"] in dml_files | ddl_files]
        reason("ordering", "Data and structure change in different migrations; they run in this order: " + " → ".join(order) + ".")
    if schema_changed and not mig_files:
        reason("schema_migration_drift", f"{schema} changed but no migration is in this diff.")
    if "structural_ddl" in by_kind:
        reason("structural_ddl", listing(by_kind["structural_ddl"]) + ".")
    if "additive_ddl" in by_kind:
        reason("additive_ddl", listing(by_kind["additive_ddl"]) + ".")
    if not reasons:
        # A schema-less migration in a language the parser does not read (rb/ts/py), or a schema
        # change with a non-SQL migration: the package still exists; the analyst writes the reason.
        pass
    reasons.sort(key=lambda r: SEV_RANK[r["severity"]])
    severity = reasons[0]["severity"] if reasons else None
    headline_kind = "schema" if schema_changed else "migrations"
    return {"schema_artifact": schema, "schema_configured": schema_cfg, "schema_changed": schema_changed,
            "migrations_dir_configured": mig_dirs, "unmanaged_sql_source": unmanaged_src,
            "headline_kind": headline_kind, "headline": schema if schema_changed else (migrations[0]["path"] if migrations else None),
            "migrations": migrations, "reasons": reasons, "severity": severity}

# ---------------------------------------------------------------- parsing
class Hunk:
    def __init__(s, header, old_start, old_len, new_start, new_len, context):
        s.header, s.old_start, s.old_len, s.new_start, s.new_len, s.context = header, old_start, old_len, new_start, new_len, context
        s.lines = []  # raw lines incl. leading ' ', '-', '+'
    @property
    def removed(s): return [l[1:] for l in s.lines if l.startswith("-")]
    @property
    def added(s): return [l[1:] for l in s.lines if l.startswith("+")]

class FileDiff:
    def __init__(s):
        s.old_path = s.new_path = None; s.status = "modified"; s.similarity = None
        s.binary = False; s.hunks = []; s.header_lines = []
    @property
    def path(s): return s.new_path if s.new_path and s.new_path != "/dev/null" else s.old_path

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")

def strip_ab(p):
    if p.startswith("a/") or p.startswith("b/"): return p[2:]
    return p

def parse(text):
    files, cur, hunk = [], None, None
    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            cur = FileDiff(); files.append(cur); hunk = None
            m = re.match(r'^diff --git "?a/(.*?)"? "?b/(.*?)"?$', raw)
            if m: cur.old_path, cur.new_path = m.group(1), m.group(2)
            cur.header_lines.append(raw); continue
        if cur is None: continue
        if hunk is None or raw.startswith("@@"):
            m = HUNK_RE.match(raw)
            if m:
                hunk = Hunk(raw, int(m.group(1)), int(m.group(2) or 1), int(m.group(3)), int(m.group(4) or 1), m.group(5).strip())
                cur.hunks.append(hunk); continue
            cur.header_lines.append(raw)
            if raw.startswith("similarity index"): cur.similarity = int(raw.split()[-1].rstrip("%"))
            elif raw.startswith("rename from"): cur.old_path = raw[len("rename from "):]; cur.status = "renamed"
            elif raw.startswith("rename to"): cur.new_path = raw[len("rename to "):]
            elif raw.startswith("copy from"): cur.old_path = raw[len("copy from "):]; cur.status = "copied"
            elif raw.startswith("copy to"): cur.new_path = raw[len("copy to "):]
            elif raw.startswith("new file mode"): cur.status = "added"
            elif raw.startswith("deleted file mode"): cur.status = "deleted"
            elif raw.startswith("Binary files") or raw.startswith("GIT binary patch"): cur.binary = True
            elif raw.startswith("--- "):
                p = raw[4:].split("\t")[0]; cur.old_path = None if p == "/dev/null" else strip_ab(p)
            elif raw.startswith("+++ "):
                p = raw[4:].split("\t")[0]; cur.new_path = None if p == "/dev/null" else strip_ab(p)
            continue
        if raw.startswith("\\ No newline"): continue
        hunk.lines.append(raw if raw else " ")
    for f in files:
        if f.status == "modified" and f.old_path is None: f.status = "added"
        if f.status == "modified" and f.new_path is None: f.status = "deleted"
        if f.old_path is None: f.old_path = "/dev/null"
        if f.new_path is None: f.new_path = "/dev/null"
    return files

# ---------------------------------------------------------------- classification
def norm_ws(s): return re.sub(r"\s+", "", s)
def norm_fmt(s):
    s = norm_ws(s)
    s = re.sub(r"[;,]+(?=[)\]}]|$)", "", s)          # trailing commas / semicolons
    s = s.replace(";", ",")                            # separator style (type/object literals, statements)
    s = s.replace("'", '"').replace("`", '"')         # quote style
    return s

def blocks_of(h):
    """Split a hunk into change blocks: maximal runs of -/+ lines (a replace = one block).

    `start`/`end` index back into `h.lines` so a block of bare specifiers can find the `from "…"`
    on the CONTEXT line that closes its import statement — see `enclosing_module`."""
    blocks, cur = [], None
    for i, l in enumerate(h.lines):
        if l.startswith("-") or l.startswith("+"):
            if cur is None: cur = {"removed": [], "added": [], "start": i}
            cur["removed" if l.startswith("-") else "added"].append(l[1:])
        elif cur is not None:
            cur["end"] = i; blocks.append(cur); cur = None
    if cur is not None: cur["end"] = len(h.lines); blocks.append(cur)
    return blocks

def classify_block(rem, add, ws_sensitive, in_import=False, asi=False):
    changed = rem + add
    if not changed: return "substantive"
    # In an ASI language, a changed line COUNT means the line structure moved, and line structure
    # decides where statements end. Refuse both whitespace and format folding for such a block.
    reflowed = asi and len([l for l in rem if l.strip()]) != len([l for l in add if l.strip()])
    if all(not l.strip() for l in changed):
        return "substantive" if ws_sensitive else "whitespace"
    if norm_ws("".join(rem)) == norm_ws("".join(add)):
        if reflowed: return "substantive"
        return "substantive" if ws_sensitive else "whitespace"
    if rem and add and norm_fmt("".join(rem)) == norm_fmt("".join(add)):
        return "substantive" if reflowed else "format"
    nonblank = [l for l in changed if l.strip()]
    # Mixed noise is still noise: every changed line must be an import OR a comment. Inside an
    # import statement, a bare specifier counts too — that is what makes a barrel re-point fold.
    def import_ish(l):
        return bool(IMPORT_RE.match(l) or (in_import and SPECIFIER_RE.match(l)))

    if nonblank and all(import_ish(l) or COMMENT_RE.match(l) for l in nonblank):
        return "import-rewrite" if any(import_ish(l) for l in nonblank) else "comment-only"
    return "substantive"

def hunk_in_import(h):
    """Is this hunk inside an import statement? Used to let bare specifiers count as import noise.

    Two independent signals, either sufficient: git's own context suffix on the `@@` header (it
    names the enclosing construct — `@@ … @@ import {`), and an import-shaped line among the hunk's
    OWN lines (context, added or removed). The header alone is a heuristic git can get wrong, and a
    hunk that opens mid-block has no `import` line of its own, so neither is reliable by itself.
    """
    if IMPORT_CONTEXT_RE.search((getattr(h, "header", "") or "").split("@@")[-1]):
        return True
    return any(IMPORT_CONTEXT_RE.match(l[1:] if l[:1] in "+- " else l) for l in getattr(h, "lines", []))

NOISE_ORDER = ["import-rewrite", "format", "whitespace", "comment-only"]

def classify_hunk(h, ws_sensitive, asi=False):
    """Hunk category = substantive if ANY block is; else the most significant noise kind present.
    Also records h.blocks (per-block categories) so import rewrites inside a substantive hunk can
    still be attached to the rename they follow."""
    in_import = hunk_in_import(h)
    h.blocks = [dict(b, category=classify_block(b["removed"], b["added"], ws_sensitive, in_import, asi))
                for b in blocks_of(h)]
    cats = {b["category"] for b in h.blocks}
    if not cats or "substantive" in cats: return "substantive"
    return next(c for c in NOISE_ORDER if c in cats)

# ── vendored subtrees ────────────────────────────────────────────────────────────────────────
# A committed copy of an upstream project is the largest thing a reviewer is asked to read and the
# least worth reading: the review question is "is the PIN right", not "are these 4,549 lines right".
# But folding it is only honest while the copy provably IS the upstream it names — and editing a
# vendored copy in place is a supported workflow, so it WILL happen. Hence: fold on PROOF, never on
# a path guess. Three outcomes, all reported by vendor_notes():
#   hash present and matches  → fold as `vendored`, naming the origin and commit
#   hash present and differs  → fold NOTHING; the copy was edited and that is the change to read
#   no hash in the pin        → fold NOTHING; the pin proves nothing about the bytes on disk
# `vendor` / `node_modules` paths keep folding as `generated` via GENERATED_RE — unpinned and
# unverifiable, they were already noise by path and this does not touch them.
VENDOR_PINS = (".describe-changes-version", ".vendor-pin")

def _git_toplevel():
    try:
        import subprocess
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except Exception:
        return None

def _parse_pin(text):
    kv = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); kv[k.strip()] = v.strip()
    return kv or None

def _read_pin(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return _parse_pin(fh.read())
    except OSError:
        return None

def _read_pin_at(root, ref, rel):
    """The pin AS IT EXISTS AT `ref`. Both halves of the proof must come from the reported range.

    Reading the subtree at `ref` while reading its expected hash from the WORKING TREE leaves the
    hole open from the other side: commit an edit to a vendored subtree, then leave an uncommitted
    pin whose tree_sha256 is the edited subtree's hash, and the two agree — folding a committed
    edit that is inside the reported range."""
    try:
        import subprocess
        out = subprocess.run(["git", "-C", root, "show", f"{ref}:{rel}"],
                             capture_output=True, text=True, timeout=15)
        return _parse_pin(out.stdout) if out.returncode == 0 else None
    except Exception:
        return None

def _tree_hash_fn():
    """The hash used by the vendored-fold proof, imported — never exec'd from a path.

    It used to load `tree-hash.py` out of the same directory. That directory is the vendored
    subtree itself when this skill describes its own vendoring, so the function deciding whether a
    copy matches its pin could be replaced by one returning whatever the pin claims, and every
    other check would then agree. Importing `report_keys` keeps one implementation in the module
    the rest of the run already depends on.

    The residual is worth stating rather than papering over: a skill reviewing a diff that edits
    the skill runs code from the diff it reviews. No arrangement inside the vendored tree fixes
    that — it is why an origin that CHANGES in the reviewed diff is not trusted at all (below)."""
    try:
        import sys
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path: sys.path.insert(0, here)
        from report_keys import tree_hash
        return tree_hash
    except Exception:
        return None

def _find_pins(root):
    """Repo-relative paths of every provenance file, from git's index rather than a tree walk.

    `os.walk(root)` ran over the whole repository for every report — `build/`, caches and all —
    even when the diff touched nothing vendored. git already knows the tracked files, and an
    UNtracked pin should not authorise a fold anyway. Falls back to a pruned walk outside git."""
    try:
        import subprocess
        # --others --exclude-standard as well as the index: a report covers untracked files, so a
        # vendoring that is staged-but-uncommitted (or not yet added at all) must still be found.
        # Ignored paths stay out, which is what `--exclude-standard` buys.
        out = subprocess.run(["git", "-C", root, "ls-files", "-z", "--cached", "--others",
                              "--exclude-standard", "--"] + [f"*{n}" for n in VENDOR_PINS],
                             capture_output=True, text=True, timeout=15)
        if out.returncode == 0:
            return [p for p in out.stdout.split("\0")
                    if p and os.path.basename(p) in VENDOR_PINS]
    except Exception:
        pass
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "__pycache__", "build", "dist")]
        for n in VENDOR_PINS:
            if n in filenames:
                found.append(os.path.relpath(os.path.join(dirpath, n), root).replace(os.sep, "/"))
    return found

def _materialise(root, ref, rel):
    """`rel` as it exists AT `ref`, in a temp dir — or None. Caller removes it."""
    import subprocess, tempfile, tarfile, io
    try:
        out = subprocess.run(["git", "-C", root, "archive", ref, "--", rel],
                             capture_output=True, timeout=60)
        if out.returncode != 0 or not out.stdout: return None
        tmp = tempfile.mkdtemp(prefix="dc-vendor-")
        with tarfile.open(fileobj=io.BytesIO(out.stdout)) as tf:
            # filter="data" refuses absolute/parent paths and device nodes (CVE-2007-4559). The
            # tar comes from `git archive` on this repo, but "the input is trusted" is exactly the
            # reasoning that makes extraction bugs ship; keep the guard. Older runtimes have no
            # `filter=` and warn instead, so fall back rather than crash.
            try: tf.extractall(tmp, filter="data")
            except TypeError: tf.extractall(tmp)
        d = os.path.join(tmp, rel)
        return d if os.path.isdir(d) else None
    except Exception:
        return None

def _verify_against_upstream(origin, sha, upstream_path, want_hash, th, timeout=90):
    """Is `want_hash` really the content at `origin`@`sha`:`upstream_path`? (verdict, why).

    This is the ONLY check that establishes provenance. `tree_sha256` proves a copy matches the pin
    beside it, and when that pin arrives in the same diff, both halves are the author's — pointing
    `skills=` at any directory and hashing it satisfies every local check. So when the pin is part
    of the change under review, the bytes are re-derived from the real remote: shallow-fetch the
    pinned commit, read the subtree out of it, hash it the same way, compare.

    Fails CLOSED. No network, a remote that will not serve the sha, a missing upstream_path — none
    of those prove anything, so none of them fold."""
    import subprocess, tempfile, shutil
    if not (origin and sha and upstream_path and want_hash and th):
        return False, "pin lacks origin/sha/upstream_path — cannot re-derive it from the remote"
    tmp = tempfile.mkdtemp(prefix="dc-upstream-")
    try:
        r = lambda *a: subprocess.run(["git", "-C", tmp, *a], capture_output=True, text=True, timeout=timeout)
        if subprocess.run(["git", "init", "-q", tmp], capture_output=True, timeout=30).returncode != 0:
            return False, "could not create a scratch repo to verify the upstream"
        r("remote", "add", "origin", origin)
        f = r("fetch", "--depth", "1", "-q", "origin", sha)
        if f.returncode != 0:
            return False, f"could not fetch {sha[:7]} from {origin} — not verified (offline, or the remote will not serve it)"
        out = subprocess.run(["git", "-C", tmp, "archive", sha, "--", upstream_path],
                             capture_output=True, timeout=timeout)
        if out.returncode != 0 or not out.stdout:
            return False, f"{upstream_path} is not present at {sha[:7]} in {origin}"
        import tarfile, io
        with tarfile.open(fileobj=io.BytesIO(out.stdout)) as tf:
            try: tf.extractall(tmp, filter="data")
            except TypeError: tf.extractall(tmp)
        d = os.path.join(tmp, upstream_path)
        if not os.path.isdir(d):
            return False, f"{upstream_path} is not a directory at {sha[:7]} in {origin}"
        return (th(d) == want_hash,
                "content matches the upstream commit" if th(d) == want_hash
                else f"content does NOT match {origin} @ {sha[:7]} — the pin describes different bytes")
    except Exception as e:
        return False, f"upstream verification failed ({type(e).__name__}) — not verified"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def _trusted_upstream(root, base_ref, pin_rel):
    """(origin, upstream_path) as the pin read at `base_ref` — the last state a review accepted.

    Everything in a pin that arrives WITH its change is the author's word, `origin` included.
    Re-deriving the bytes from that origin proves only that they match a repository the author
    chose, which an attacker satisfies by pointing it at their own. The origin therefore has to
    come from somewhere the change under review cannot reach: the base the MR targets."""
    if not base_ref: return None, None
    prior = _read_pin_at(root, base_ref, pin_rel)
    if not prior: return None, None
    return prior.get("origin"), prior.get("upstream_path")

def vendor_scan(root, verify_ref=None, changed=(), base_ref=None):
    """(verified, notes) — repo-relative subtree paths that are provably their pinned upstream.

    `verify_ref` is the commit whose content the report describes; when set (a committed-only
    report) the proof is read from THAT ref, not from the working tree — otherwise re-vendoring a
    copy after committing an edit to it would make the worktree match the pin again and fold away
    an edit that is inside the reported range.

    `changed` is the set of paths this diff touches. A pin listed there authorises a fold using
    provenance the same change introduced, so the fold is kept (a vendoring MR is the case this
    feature exists for) but flagged: the reviewer's remaining job is to confirm the origin and
    commit are the ones they expect. The hash proves the copy is internally consistent with its
    pin; it proves nothing about where the bytes came from.

    `notes` records every pin that did NOT yield a fold and why, so an unverified copy is visible
    rather than silently substantive."""
    import shutil
    verified, notes = {}, []
    if not root or not os.path.isdir(root): return verified, notes
    th = _tree_hash_fn()
    changed = set(changed or ())
    for pin_rel in _find_pins(root):
        pin_abs = os.path.join(root, pin_rel)
        pin = _read_pin_at(root, verify_ref, pin_rel) if verify_ref else _read_pin(pin_abs)
        if not pin:
            if verify_ref and _read_pin(pin_abs):
                # the pin exists in the worktree but not at the reported commit, so it describes
                # nothing in this range
                notes.append({"path": pin_rel, "why": f"pin does not exist at {verify_ref[:7]} — nothing folded from it"})
            continue
        origin, sha = pin.get("origin", "?"), (pin.get("sha") or "")
        want = pin.get("tree_sha256")
        for sub in (pin.get("skills") or "").split():
            rel = os.path.normpath(os.path.join(os.path.dirname(pin_rel), sub)).replace(os.sep, "/")
            if not os.path.isdir(os.path.join(root, rel)): continue
            if not want:
                notes.append({"path": rel, "why": "pin carries no tree_sha256 — cannot verify"}); continue
            if not th:
                notes.append({"path": rel, "why": "tree-hash unavailable — cannot verify"}); continue
            probe, tmp_parent = os.path.join(root, rel), None
            if verify_ref:
                probe = _materialise(root, verify_ref, rel)
                if probe is None:
                    notes.append({"path": rel, "why": f"cannot read the subtree at {verify_ref[:7]} — not verified"}); continue
                tmp_parent = probe[:-len(rel)] if rel and probe.endswith(rel) else None
            try:
                got = th(probe)
            finally:
                if tmp_parent: shutil.rmtree(tmp_parent, ignore_errors=True)
            if got != want:
                notes.append({"path": rel, "why": "copy differs from its pin — edited in place, shown in full"})
                continue
            detail_src = f"from {origin} @ {sha[:7]}, content verified against the pin"
            if pin_rel in changed:
                # The pin arrives with the change it authorises, so every LOCAL check — the hash
                # included — is the author's own word. Two things must hold before folding:
                # (1) the ORIGIN is one an earlier review already accepted, read from the base ref,
                #     because re-deriving from an origin the same diff chose proves only that the
                #     bytes match a repo the author picked;
                # (2) the bytes really are that origin's, at the pinned commit.
                t_origin, t_path = _trusted_upstream(root, base_ref, pin_rel)
                up_path = pin.get("upstream_path")
                if not t_origin:
                    notes.append({"path": rel, "why": "pin introduced by this same change and no accepted origin "
                                                      "exists at the base — a first vendoring is read in full"})
                    continue
                # BOTH halves must match the base, and a base that carries no `upstream_path` counts
                # as a mismatch rather than a free pass. The `t_path and …` spelling this replaces
                # let a pin predating `upstream_path` be extended with one — same trusted origin,
                # but a subtree path nobody had accepted, chosen by the change under review. The
                # compatibility it bought is one re-vendor wide and self-healing; the hole was not.
                if t_origin != origin or t_path != up_path:
                    moved = (f"{t_origin} → {origin}" if t_origin != origin
                             else f"upstream_path {t_path or '(absent at the base)'} → {up_path}")
                    notes.append({"path": rel, "why": f"pin introduced by this same change CHANGES the upstream "
                                                      f"({moved}) — a new upstream is a human decision, shown in full"})
                    continue
                ok, why = _verify_against_upstream(origin, sha, up_path, want, th)
                if not ok:
                    notes.append({"path": rel, "why": f"pin introduced by this same change and {why} — shown in full"})
                    continue
                detail_src = f"re-derived from {origin} @ {sha[:7]} itself — an origin the base already carries"
            verified[rel] = {"origin": origin, "sha": sha[:7] or "?", "pin": pin_rel,
                             "pin_in_diff": pin_rel in changed, "detail_src": detail_src}
    return verified, notes

def vendored_of(path, verified):
    """The verified vendored root governing `path`, or None."""
    for rel, prov in verified.items():
        if path == rel or path.startswith(rel + "/"): return prov
    return None

def file_noise_kind(f, added_text, verified=None):
    base = os.path.basename(f.path)
    if f.binary: return "binary"
    if verified and vendored_of(f.path, verified): return "vendored"
    if base in LOCKFILES: return "lockfile"
    if SNAPSHOT_RE.search(f.path): return "snapshot"
    if GENERATED_RE.search(f.path): return "generated"
    if ext_of(f.path) in MD_EXT and NOTES_RE.search(f.path): return "notes"
    head = "\n".join(added_text[:8])
    if f.status == "added" and any(m in head for m in GENERATED_MARKERS): return "generated"
    return None

def kebab(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name.split(".")[-1]).lower()

def registry_row(path, block, added_paths):
    """A one-line index/table row pointing at a file ADDED in this same change.

    `| [ADR-0051](0051-….md) | … |` restates a file the reviewer is already reading in full; it is
    bookkeeping the change owes its index, not a change. Folds ONLY when the link target is one of
    this diff's new files — a row pointing anywhere else is an edit to a live document."""
    if ext_of(path) not in MD_EXT or block["removed"] or len(block["added"]) != 1: return None
    line = block["added"][0].strip()
    if not (line.startswith("|") or line.startswith("- ") or line.startswith("* ")): return None
    here = os.path.dirname(path)
    for target in LINK_RE.findall(line):
        p = os.path.normpath(os.path.join(here, target.split("#")[0]))
        if p in added_paths: return p
    return None

def prop_uses_re(name):
    return re.compile(r"\b" + re.escape(name) + r"\b\s*(?:=\s*\{[^{}]*\}|=\s*\"[^\"]*\")?\s*,?")

def thread_block(block, name):
    """Is this block a pure pass-site for `name` — the prop added (or removed) and nothing else?

    Exactly one side may mention the prop, and after deleting its occurrences the two sides must be
    textually identical. `items={ACCOUNTANT_MORE_ITEMS}` → `items={moreItems}` therefore does NOT
    fold: the prop is absent from both sides, and were it present on both, the remainders differ."""
    rem = [l for l in block["removed"] if l.strip()]; add = [l for l in block["added"] if l.strip()]
    has_r, has_a = any(name in l for l in rem), any(name in l for l in add)
    if has_r == has_a: return None
    sub = prop_uses_re(name)
    norm = lambda ls: re.sub(r"[\s,]+", "", "".join(sub.sub("", l) for l in ls))
    if norm(rem) != norm(add): return None
    return "removed" if has_r else "added"

def target_component(hunk, block, lines, prev=None):
    """The component a pass-site hands the prop to: the tag on the changed line, else the nearest
    opening tag above it (a multi-line JSX element puts each prop on its own line).

    A long element can push its `<Tag` past the hunk's three context lines and into the PREVIOUS
    hunk — that is how `<AccountantTopSidebar` went missing while the prop line was right there. The
    scan continues into that hunk only when the two are contiguous, so a tag 200 lines up is never
    claimed as the target."""
    for l in lines:
        m = JSX_OPEN_RE.search(l)
        if m: return m.group(1)
    def scan(h, upto):
        for i in range(upto - 1, -1, -1):
            raw = h.lines[i]; m = JSX_OPEN_RE.search(raw[1:] if raw[:1] in "+- " else raw)
            if m: return m.group(1)
        return None
    found = scan(hunk, block.get("start", 0))
    if found or prev is None: return found
    if prev.new_start + prev.new_len >= hunk.new_start - 3:
        return scan(prev, len(prev.lines))
    return None

TOPLEVEL_ONLY = ("const", "let", "var", "val")

def symbols_in(lines):
    """Declared symbol names. Variable declarations count only at top level (column 0) so local
    `const env = …` in five test files does not masquerade as a moved symbol."""
    out = []
    for l in lines:
        m = SYMBOL_RE.match(l)
        if not m: continue
        if l[:1].isspace() and re.match(r"\s*(?:export\s+)?(?:%s)\b" % "|".join(TOPLEVEL_ONLY), l): continue
        out.append(m.group(1))
    return out

def import_specs(lines):
    specs = []
    for l in lines:
        for m in SPEC_RE.finditer(l): specs.append(m.group(2))
    return specs

FROM_RE = re.compile(r"""\bfrom\s+(['"])([^'"]+)\1""")

def enclosing_module(h, block):
    """The module a block of BARE specifiers belongs to.

    `import_specs` reads quoted module paths off the changed lines. A block that only adds
    `  Foo,` inside an existing `import { … } from "@/x"` has none — the path sits on the context
    line that closes the statement — so such a block used to look like "no module", which the fold
    then read as "an import was removed". It is the opposite: an import was ADDED. Scan forward to
    the first `from "…"`, stopping if a new `import` statement starts first (then the block was not
    inside one after all)."""
    lines = getattr(h, "lines", [])
    for i in range(block.get("end", 0), len(lines)):
        raw = lines[i]; l = raw[1:] if raw[:1] in "+- " else raw
        if IMPORT_CONTEXT_RE.match(l): break
        m = FROM_RE.search(l)
        if m: return m.group(2)
    return None

def block_modules(h, block, side):
    """Module paths the block imports FROM on `side` ("added"/"removed"), bare specifiers included."""
    mods = list(dict.fromkeys(import_specs(block[side])))
    if not mods and any(SPECIFIER_RE.match(l) for l in block[side] if l.strip()):
        enc = enclosing_module(h, block)
        if enc: mods = [enc]
    return mods

def content_lines(lines):
    return {l.strip() for l in lines if len(l.strip()) > 12 and not COMMENT_RE.match(l)}

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diff", required=True); ap.add_argument("--numstat"); ap.add_argument("--out", required=True)
    ap.add_argument("--root", default=None, help="repo root; where vendored-subtree pins are read from")
    ap.add_argument("--base-ref", default=None,
                    help="the ref this change targets; the ONLY source of a trusted vendored origin")
    ap.add_argument("--verify-ref", default=None,
                    help="prove vendored subtrees against this commit instead of the working tree "
                         "(set for a committed-only report, whose range is not the working tree)")
    a = ap.parse_args()
    text = open(a.diff, encoding="utf-8", errors="replace").read()
    files = parse(text)
    os.makedirs(a.out, exist_ok=True)
    root = a.root or _git_toplevel()
    verified, vendor_notes = vendor_scan(root, a.verify_ref, {f.path for f in files}, a.base_ref)
    cfg = load_skill_config(root)
    db = db_scan(files, root, cfg)
    db_role = {}
    if db:
        if db["schema_artifact"]: db_role[db["schema_artifact"]] = "schema"
        for mg in db["migrations"]: db_role[mg["path"]] = "migration"

    model_files, folds = [], defaultdict(list)
    lines_changed = lines_sub = 0
    deleted_content, added_files = {}, []
    sym_removed, sym_added = defaultdict(set), defaultdict(set)
    renames = {}  # new_path -> old_path
    rename_targets = {}  # old_path -> {path, overlap} for low-similarity renames (split sources)

    for fi, f in enumerate(files, 1):
        all_added = [l for h in f.hunks for l in h.added]
        ws = ext_of(f.path) in WS_SENSITIVE or ext_of(f.path) == "Makefile"
        asi = ext_of(f.path) in ASI_LANGS
        noise = file_noise_kind(f, all_added, verified)
        hunks = []
        for hi, h in enumerate(f.hunks, 1):
            cat = classify_hunk(h, ws, asi) if noise is None else noise
            hunks.append({"id": f"F{fi}H{hi}", "header": h.header, "symbol": h.context or None,
                          "old_start": h.old_start, "old_lines": h.old_len, "new_start": h.new_start,
                          "new_lines": h.new_len, "category": cat, "added": len(h.added), "removed": len(h.removed),
                          "blocks": [{"category": b["category"], "removed": len(b["removed"]), "added": len(b["added"])}
                                     for b in getattr(h, "blocks", [])]})
            h.category = cat; h.id = f"F{fi}H{hi}"
            if cat in ("whitespace", "format", "comment-only"):
                folds[cat].append({"file": f.path, "hunk_ids": [h.id], "detail": h.context or h.header})
            sym_removed[f.path].update(symbols_in(h.removed)); sym_added[f.path].update(symbols_in(h.added))
        if f.status == "renamed" and not f.hunks: cat_file = "rename"
        elif f.status == "renamed": cat_file = "rename+modified"
        else: cat_file = f.status
        if f.status in ("renamed", "copied"): renames[f.new_path] = f.old_path
        if f.status == "deleted": deleted_content[f.path] = content_lines(l for h in f.hunks for l in h.removed)
        elif f.status == "renamed" and f.hunks and (f.similarity or 100) < 80:
            deleted_content[f.old_path] = content_lines(l for h in f.hunks for l in h.removed)
            rename_targets[f.old_path] = {"path": f.new_path, "overlap": (f.similarity or 0) / 100}
        if f.status == "added" and noise is None: added_files.append(f)
        entry = {"id": f"F{fi}", "path": f.path, "old_path": f.old_path if f.old_path != f.path else None,
                 "status": cat_file, "similarity": f.similarity, "language": language(f.path), "area": area(f.path),
                 "db": db_role.get(f.path), "whitespace_sensitive": ws, "noise_kind": noise, "hunks": hunks,
                 "substantive_hunks": sum(1 for h in hunks if h["category"] == "substantive"),
                 "symbols_added": sorted(sym_added[f.path]), "symbols_removed": sorted(sym_removed[f.path])}
        model_files.append(entry)
        if noise:
            prov = vendored_of(f.path, verified) if noise == "vendored" else None
            detail = (f"{f.status}, {prov['detail_src']}" if prov
                      else f"{f.status}, {len(hunks)} hunks")
            folds[noise].append({"file": f.path, "hunk_ids": [h["id"] for h in hunks], "detail": detail})
        if cat_file == "rename": folds["rename"].append({"file": f.path, "old_path": f.old_path, "hunk_ids": [], "detail": f"{f.old_path} → {f.path} (pure rename, {f.similarity}%)", "followers": []})

    # Import-rewrite hunks: attach as followers of the rename/move they reference, else stand-alone fold.
    rename_bases = {os.path.splitext(os.path.basename(n))[0]: n for n in renames}
    by_path = {e["path"]: e for e in model_files}
    for f in files:
        for h in f.hunks:
            for b in getattr(h, "blocks", []):
                if b["category"] != "import-rewrite": continue
                specs = import_specs(b["added"]) + import_specs(b["removed"])
                targets = [rename_bases[k] for k in rename_bases if any(k in sp for sp in specs)]
                partial = h.category == "substantive"
                added_specs = block_modules(h, b, "added"); removed_specs = block_modules(h, b, "removed")
                specs = specs or added_specs + removed_specs
                targets = targets or [rename_bases[k] for k in rename_bases if any(k in sp for sp in specs)]
                what = " / ".join(added_specs) or (("dropped: " + " / ".join(removed_specs)) if removed_specs else "")
                # Direction is known even when the module is not: a hunk can add a specifier whose
                # `} from "…"` sits past the last context line, and "which way" still matters more
                # to a reviewer than "from where".
                item = {"file": f.path, "hunk_ids": [h.id], "partial": partial, "added": added_specs, "removed": removed_specs,
                        "dir_added": any(l.strip() for l in b["added"]), "dir_removed": any(l.strip() for l in b["removed"]),
                        "detail": (what or h.header) + (" (inside a substantive hunk)" if partial else "")}
                parents = [r for r in folds["rename"] if r["file"] in targets]
                for r in parents: r["followers"].append(item)
                if not parents and not partial: folds["import-rewrite"].append(item)

    # Move / split detection: added files whose content largely came from a deleted file.
    moves = []
    for af in added_files:
        mine = content_lines(l for h in af.hunks for l in h.added)
        if len(mine) < 3: continue
        best, best_frac = None, 0.0
        for dp, dl in deleted_content.items():
            if not dl: continue
            frac = len(mine & dl) / len(mine)
            if frac > best_frac: best, best_frac = dp, frac
        if best and best_frac >= 0.5:
            moves.append({"from": best, "to": af.path, "overlap": round(best_frac, 2)})
    split_groups = defaultdict(list)
    for m in moves: split_groups[m["from"]].append(m)
    for src, rt in rename_targets.items():
        if src in split_groups:  # the renamed remainder counts as one more split target
            split_groups[src].insert(0, {"from": src, "to": rt["path"], "overlap": rt["overlap"]})
    for src, ms in split_groups.items():
        kind = "split" if len(ms) > 1 else "move"
        folds[kind].append({"file": src, "hunk_ids": [], "detail": f"{src} → " + ", ".join(m['to'] for m in ms),
                            "targets": [{"path": m["to"], "overlap": m["overlap"]} for m in ms]})
        for m in ms:
            if m["to"] in by_path:
                by_path[m["to"]]["moved_from"] = src; by_path[m["to"]]["overlap"] = m["overlap"]

    # Blocks whose lines merely travelled between a split/move source and its targets are 'moved'.
    target_content = defaultdict(set)   # source path -> union of content lines of its targets
    for m in moves:
        target_content[m["from"]] |= content_lines(l for h in next(x for x in files if x.path == m["to"]).hunks for l in h.added)
    for src, rt in rename_targets.items():
        tf = next((x for x in files if x.path == rt["path"]), None)
        if tf: target_content[src] |= content_lines(l for h in tf.hunks for l in h.added) | content_lines(
            l[1:] for h in tf.hunks for l in h.lines if l.startswith(" "))
    source_of = {m["to"]: m["from"] for m in moves}
    for f in files:
        src_for_removed = f.path if f.path in target_content else (f.old_path if f.old_path in target_content else None)
        src_for_added = source_of.get(f.path)
        for h in f.hunks:
            for b in getattr(h, "blocks", []):
                if b["category"] != "substantive": continue
                rem = {l.strip() for l in b["removed"] if len(l.strip()) > 12}; add = {l.strip() for l in b["added"] if len(l.strip()) > 12}
                if src_for_removed and rem and not add and rem <= target_content[src_for_removed]: b["category"] = "moved"
                elif src_for_added and add and not rem and add <= deleted_content.get(src_for_added, set()): b["category"] = "moved"
            if getattr(h, "blocks", None) and all(b["category"] == "moved" for b in h.blocks): h.category = "moved"

    # Registry rows + prop threading. Both are mechanical restatement the block classifier cannot
    # see, because both are ordinary code/prose lines — what makes them noise is a relationship to
    # something ELSE in the same diff (a file it adds, a prop it declares).
    added_paths = {e["path"] for e in model_files if e["status"] == "added"}
    declared = defaultdict(lambda: {"added": [], "removed": []})   # prop -> where its type was declared
    for f in files:
        if ext_of(f.path) not in (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts"): continue
        for h in f.hunks:
            for side in ("added", "removed"):
                for l in getattr(h, side):
                    m = PROP_DECL_RE.match(l)
                    if m and f.path not in declared[m.group(1)][side]: declared[m.group(1)][side].append(f.path)
    threads = defaultdict(lambda: {"files": [], "hunk_ids": [], "flow": [], "kind": None})
    for f in files:
        for hi, h in enumerate(f.hunks):
            for b in getattr(h, "blocks", []):
                if b["category"] != "substantive": continue
                target = registry_row(f.path, b, added_paths)
                if target:
                    b["category"] = "registry"
                    folds["registry"].append({"file": f.path, "hunk_ids": [h.id], "target": target,
                                              "detail": f"index row for {target}"})
                    continue
                declares = {m.group(1) for l in b["added"] + b["removed"] for m in [PROP_DECL_RE.match(l)] if m}
                for name, where in declared.items():
                    if not (where["added"] or where["removed"]): continue
                    if name in declares: continue     # the declaration itself stays visible; only pass-sites fold
                    kind = thread_block(b, name)
                    if not kind: continue
                    b["category"] = "prop-thread"
                    t = threads[name]; t["kind"] = kind if t["kind"] in (None, kind) else "changed"
                    if f.path not in t["files"]: t["files"].append(f.path)
                    t["hunk_ids"].append(h.id)
                    side = b["added"] if kind == "added" else b["removed"]
                    # A `prop,` line RECEIVES the value (a destructured parameter); only a JSX
                    # attribute PASSES it on. Without the distinction every receiving component
                    # emitted an edge to an unknown child and the flow filled with "not named".
                    if all(re.match(r"^\s*" + re.escape(name) + r"\s*,\s*$", l) for l in side if l.strip()):
                        continue
                    passes = re.compile(r"^\s*" + re.escape(name) + r"(?:\s*=\s*\{[^{}]*\}|\s*=\s*\"[^\"]*\")?\s*/?>?\s*$")
                    if not any(passes.match(l) or (JSX_OPEN_RE.search(l) and name in l) for l in side):
                        continue      # a parameter list or type member: the file RECEIVES, it does not pass on
                    comp = target_component(h, b, side, f.hunks[hi - 1] if hi else None)
                    # An unresolved target is still an edge: the pass-site file is a fact, and
                    # dropping it would silently shrink the flow to the tags that happened to be
                    # inside a hunk. The renderer says "component not named in the hunk".
                    if not any(x["from"] == f.path and x["to"] == comp for x in t["flow"]):
                        t["flow"].append({"from": f.path, "to": comp})
                    break
    for f in files:
        for h in f.hunks:
            if getattr(h, "blocks", None) and all(b["category"] in ("registry", "prop-thread") for b in h.blocks):
                h.category = h.blocks[0]["category"]

    # A prop threaded inside ONE file is a local rename, not drilling: require a pass-site outside
    # the file that declares it, or the item says nothing a reviewer could not see in one hunk.
    base_to_path = {kebab(os.path.splitext(os.path.basename(e["path"]))[0]): e["path"] for e in model_files}
    for name, t in list(threads.items()):
        decl = declared[name]["added"] + declared[name]["removed"]
        if len(set(t["files"]) | set(decl)) < 2: del threads[name]; continue
        for edge in t["flow"]: edge["to_file"] = base_to_path.get(kebab(edge["to"] or ""))
        n = len(t["files"])       # files is exact; component names are only known where a tag was in reach
        where = f"{n} file{'s' if n != 1 else ''}"
        t["verb"] = (f"new prop threaded through {where}" if t["kind"] == "added"
                     else f"prop removed from {where}" if t["kind"] == "removed"
                     else f"prop re-threaded through {where}")
        folds["prop-thread"].append({"file": name, "prop": name, "kind": t["kind"], "verb": t["verb"],
                                     "files": sorted(t["files"]), "hunk_ids": list(dict.fromkeys(t["hunk_ids"])),
                                     "declared_in": sorted(set(decl)), "flow": t["flow"],
                                     "detail": f"{name} — {t['verb']}: " + ", ".join(sorted(t["files"]))})
    folds["prop-thread"].sort(key=lambda it: -len(it["files"]))

    for f in files:
        # refresh the model entry for this file
        e = by_path.get(f.path)
        if e:
            for mh, h in zip(e["hunks"], f.hunks):
                mh["category"] = h.category
                mh["blocks"] = [{"category": b["category"], "removed": len(b["removed"]), "added": len(b["added"])} for b in getattr(h, "blocks", [])]
            e["substantive_hunks"] = sum(1 for h in e["hunks"] if h["category"] == "substantive")
    for e in model_files:
        for h in e["hunks"]:
            if e["noise_kind"]:
                lines_changed += h["added"] + h["removed"]; continue
            for b in h["blocks"]:
                n = b["added"] + b["removed"]; lines_changed += n
                if b["category"] == "substantive": lines_sub += n

    # Symbol moves: same symbol removed in one file and added in another.
    # A true move: the symbol left `src` (removed, not re-added there) and landed in `dst` (added, not removed there).
    symbol_moves = []
    for src, removed in sym_removed.items():
        left = removed - sym_added[src]
        for dst, added in sym_added.items():
            if src == dst: continue
            for name in sorted(left & (added - sym_removed[dst])):
                symbol_moves.append({"name": name, "from": src, "to": dst})

    if folds.get("import-rewrite"):
        # Group by module, and keep the DIRECTION per file: a group that only added the import must
        # not be described as a removal (it was, for every barrel re-point — the added lines carry
        # no quoted path, so the module was unknown and the item fell into an "imports removed"
        # bucket while the diff showed additions only).
        by_mod = defaultdict(lambda: {"files": [], "hunk_ids": [], "added_in": [], "removed_in": []})
        for it in folds["import-rewrite"]:
            add, rem = it.get("added") or [], it.get("removed") or []
            named = list(dict.fromkeys(add + rem))
            # Unnamed modules still split by direction — one "added and dropped" bucket would hide
            # which files did which, and the module name is the only thing missing, not the fact.
            unnamed_key = UNRESOLVED_MODULE + ("+" if it.get("dir_added") else "") + ("-" if it.get("dir_removed") else "")
            for mod in named or [unnamed_key]:
                g = by_mod[mod]
                hits = (("files", True), ("added_in", mod in add if named else it.get("dir_added")),
                        ("removed_in", mod in rem if named else it.get("dir_removed")))
                for key, hit in hits:
                    if hit and it["file"] not in g[key]: g[key].append(it["file"])
                g["hunk_ids"] += it["hunk_ids"]
        def verb(mod, v):
            n = len(v["files"]); files = f"{n} file{'s' if n != 1 else ''}"
            add, rem = bool(v["added_in"]), bool(v["removed_in"])
            if mod.startswith(UNRESOLVED_MODULE):               # direction known, module named outside the hunk
                what = "imports added" if add and not rem else "imports dropped" if rem and not add else "imports added and dropped"
                return f"{what} in {files} (the module is named outside the hunk)"
            if add and not rem: return f"now imported in {files}"
            if rem and not add: return f"no longer imported in {files}"
            return f"imports changed in {files} (added in {len(v['added_in'])}, dropped in {len(v['removed_in'])})"
        folds["import-rewrite"] = [{"file": mod, "module": "" if mod.startswith(UNRESOLVED_MODULE) else mod, "files": sorted(v["files"]),
                                    "hunk_ids": list(dict.fromkeys(v["hunk_ids"])), "verb": verb(mod, v),
                                    "added_in": sorted(v["added_in"]), "removed_in": sorted(v["removed_in"]),
                                    "detail": (f"{mod} ← " if not mod.startswith(UNRESOLVED_MODULE) else "") + verb(mod, v) + ": " + ", ".join(sorted(v["files"]))}
                                   for mod, v in sorted(by_mod.items(), key=lambda kv: -len(kv[1]["files"]))]
    fold_titles = {"rename": "Renamed files (imports updated to match)", "move": "Moved files", "split": "Files split",
                   "import-rewrite": "Import-only changes (module ← the files whose imports of it changed)",
                   "prop-thread": "Props threaded through components (prop ← where it flows)",
                   "whitespace": "Whitespace-only hunks",
                   "format": "Formatting-only hunks", "comment-only": "Comment-only hunks",
                   "registry": "Index / registry rows for files added here", "notes": "Working notes (plans, handoffs, journals)",
                   "lockfile": "Lockfiles", "generated": "Generated / build output", "snapshot": "Test snapshots",
                   "vendored": "Vendored code", "binary": "Binary files"}
    ORDER = ["rename", "move", "split", "import-rewrite", "prop-thread", "format", "whitespace", "comment-only",
             "registry", "notes", "lockfile", "generated", "snapshot", "vendored", "binary"]
    fold_list = [{"kind": k, "title": fold_titles.get(k, k), "count": len(v), "items": v}
                 for k, v in folds.items() if v]
    fold_list.sort(key=lambda x: ORDER.index(x["kind"]) if x["kind"] in ORDER else 99)

    files_sub = [e for e in model_files if e["substantive_hunks"] > 0]
    model = {
        "stats": {"files": len(model_files), "files_substantive": len(files_sub), "lines_changed": lines_changed,
                  "lines_substantive": lines_sub,
                  "noise_pct": round(100 * (1 - lines_sub / lines_changed)) if lines_changed else 0,
                  "hunks_by_category": dict(sorted(defaultdict(int, {
                      c: sum(1 for e in model_files for h in e["hunks"] if h["category"] == c)
                      for c in {h["category"] for e in model_files for h in e["hunks"]}}).items()))},
        "files": model_files, "folds": fold_list, "symbol_moves": symbol_moves,
        # The DB package as facts (schema artifact, ordered migrations, what the SQL does, the
        # reasons it supports). None when no DB file changed. report.json's db_package is built
        # FROM this and validated AGAINST it.
        "db": db,
        "notes": [f"{e['path']}: whitespace-sensitive language — whitespace hunks kept as substantive"
                  for e in model_files if e["whitespace_sensitive"] and any(
                      h["category"] == "substantive" and not h["symbol"] for h in e["hunks"])][:20]
                 # A vendored copy that could NOT be proven identical to its pin is shown in full,
                 # and says so. Without this line the reader cannot tell "no vendored copy here"
                 # from "a vendored copy was edited and I am reading all of it".
                 + [f"{n['path']}: vendored copy not folded — {n['why']}"
                    for n in vendor_notes if any(e["path"] == n["path"] or e["path"].startswith(n["path"] + "/")
                                                 for e in model_files)][:20],
    }
    json.dump(model, open(os.path.join(a.out, "diff-model.json"), "w"), indent=2)

    # substantive.diff — only substantive hunks, with the file headers git produced.
    out = []
    for f in files:
        keep = [h for h in f.hunks if getattr(h, "category", None) == "substantive"]
        if not keep: continue
        out.extend(f.header_lines)
        for h in keep:
            mix = ",".join(b["category"] for b in getattr(h, "blocks", []))
            out.append(f"{h.header}  [{h.id}]" + (f"  blocks: {mix}" if mix and mix != "substantive" else ""))
            out.extend(h.lines)
    open(os.path.join(a.out, "substantive.diff"), "w").write("\n".join(out) + ("\n" if out else ""))

    s = model["stats"]
    print(f"classified {s['files']} files / {lines_changed} changed lines → {s['lines_substantive']} substantive "
          f"({s['noise_pct']}% folded as noise); {len(fold_list)} fold groups; {len(symbol_moves)} symbol moves"
          + (f"; DB package: {db['headline_kind']} headline, {len(db['migrations'])} migration(s), "
             f"{db['severity'] or 'severity undecided'}" if db else ""))

if __name__ == "__main__":
    main()
