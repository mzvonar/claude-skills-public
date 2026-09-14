#!/usr/bin/env bash
# tests/db-package.sh — the DB schema package (one finding owning the whole database change) and
# the four-bucket remainder. One throwaway git repo per case; no LLM involved: the report.json is
# built the way the analyst is told to build it — from diff-model.json → db — then validated,
# rendered, and asserted on. Run by tests/run.sh; runnable alone.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$HERE/../skills/describe-changes/scripts"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export DESCRIBE_CHANGES_HOME="$T/home"
fail() { echo "FAIL: $*" >&2; exit 1; }
[ -n "$T" ] && [ -d "$T" ] || { echo "FATAL: no scratch dir" >&2; exit 1; }

# repo <name>: a fresh git repo at $T/<name>, cwd moved into it.
repo() { mkdir -p "$T/$1"; cd "$T/$1"; git init -q -b main . ; git config user.email t@t; git config user.name t; printf '.describe-changes/\nhome/\n' > .gitignore; }
commit() { git add -A && git commit -qm "$1"; }
# collect: stage everything, run step 1 in explicit mode, echo the OUT dir.
collect() { git add -A; bash "$S/collect-diff.sh" --staged | tail -1 | sed 's/^OUT=//'; }

# build_report <out> [extra-findings-json]: the analyst's job, mechanically — a report whose DB
# package is copied from diff-model.json → db, plus whatever code findings the case supplies.
build_report() {
python3 - "$1" "${2:-[]}" <<'PY'
import json, os, sys
d, extra = sys.argv[1], json.loads(sys.argv[2])
m = json.load(open(os.path.join(d, "diff-model.json")))
db = m.get("db")
files = [f["path"] for f in m["files"]]
findings = list(extra)
if db:
    sev = db["severity"] or "low"
    reasons = db["reasons"] or [{"kind": "additive_ddl", "severity": "low", "question": "Is anything here more than additive?", "detail": "non-SQL migration; read by hand"}]
    findings.append({
        "id": None, "severity": sev,
        "title": "Database change: " + (db["schema_artifact"] if db["headline_kind"] == "schema" else "migrations only"),
        "verify": reasons[0].get("question") or "?", "why_human": "Irreversible on a real database.",
        "file": db["headline"],
        "db_package": {"headline_kind": db["headline_kind"],
                       "migrations": [({"path": mg["path"], "note": mg["summary"]} if mg["summary"] else {"path": mg["path"]}) for mg in db["migrations"]],
                       "reasons": reasons}})
# ids follow severity order: C1.. M1.. L1..
counters = {"critical": 0, "medium": 0, "low": 0}
for f in sorted(findings, key=lambda f: {"critical": 0, "medium": 1, "low": 2}[f["severity"]]):
    counters[f["severity"]] += 1
    f["id"] = {"critical": "C", "medium": "M", "low": "L"}[f["severity"]] + str(counters[f["severity"]])
r = {"title": "db case", "intent": "exercise the db package", "summary": "A fixture change touching the database and some code, used to prove the package renders as specified.",
     "phases": [{"id": "p1", "title": "All of it", "narrative": "One phase.", "files": files[:3]}],
     "graph": {"nodes": [], "edges": []}, "findings": findings, "folded": m["folds"], "unreviewed_notes": {}}
json.dump(r, open(os.path.join(d, "report.json"), "w"), indent=1)
print("report built:", [(f["id"], f["severity"], f["file"]) for f in findings])
PY
}
# section <html> <id>: the inner HTML of one <section>.
section() { python3 -c "import re,sys; h=open(sys.argv[1]).read(); print(re.search(r'<section id=\"%s\"[^>]*>(.*?)</section>' % sys.argv[2], h, re.S).group(1))" "$1" "$2"; }

SCHEMA_BASE='datasource db { provider = "postgresql" }
model Post {
  id     String @id
  firmId String
  title  String
}
'
CODE_FINDING='[{"severity":"critical","title":"`save` now deletes on conflict","verify":"Intended?","why_human":"Data loss is a judgement call.","file":"src/save.ts","tags":["data"]}]'

# ── A. schema diff + THREE migrations, one risky, two routine; every bucket touched ─────────────
repo a
mkdir -p prisma/migrations/20260101000000_init src tests docs
printf '%s' "$SCHEMA_BASE" > prisma/schema.prisma
printf 'CREATE TABLE "Post" ("id" TEXT NOT NULL, "firmId" TEXT NOT NULL, "title" TEXT NOT NULL, CONSTRAINT "Post_pkey" PRIMARY KEY ("id"));\n' > prisma/migrations/20260101000000_init/migration.sql
printf 'provider = "postgresql"\n' > prisma/migrations/migration_lock.toml
printf 'export function save(x: string) { return x; }\n' > src/save.ts
printf 'export function other() { return 1; }\n' > src/other.ts
printf 'test("save", () => {});\n' > tests/save.test.ts
printf '# Docs\n' > docs/guide.md
printf 'name: ci\n' > ci.yml
commit base
# the change
printf '%s' "$SCHEMA_BASE" | sed 's/firmId String/organizationId String?\n  nick   String?/' > prisma/schema.prisma
mkdir -p prisma/migrations/20260102000000_add_nick prisma/migrations/20260103000000_org prisma/migrations/20260104000000_idx
printf 'ALTER TABLE "Post" ADD COLUMN "nick" TEXT;\n' > prisma/migrations/20260102000000_add_nick/migration.sql
printf -- '-- move tenancy to organization\nALTER TABLE "Post" ADD COLUMN "organizationId" TEXT;\nUPDATE "Post" SET "organizationId" = "firmId";\nALTER TABLE "Post" DROP COLUMN "firmId";\n' > prisma/migrations/20260103000000_org/migration.sql
printf 'CREATE INDEX "Post_organizationId_idx" ON "Post"("organizationId");\n' > prisma/migrations/20260104000000_idx/migration.sql
printf 'export function save(x: string) { db.deleteOnConflict(x); return x; }\n' > src/save.ts
printf 'export function other() { return 2; }\n' > src/other.ts
printf 'test("save", () => { expect(1).toBe(1); });\n' > tests/save.test.ts
printf '# Docs\n\nmore\n' > docs/guide.md
printf 'name: ci\non: push\n' > ci.yml
OUT="$(collect)"
python3 - "$OUT" <<'PY' || fail "A: model.db"
import json, sys, os
m = json.load(open(os.path.join(sys.argv[1], "diff-model.json"))); db = m["db"]
assert db and db["headline_kind"] == "schema" and db["headline"] == "prisma/schema.prisma", db
paths = [x["path"] for x in db["migrations"]]
assert paths == ["prisma/migrations/20260102000000_add_nick/migration.sql", "prisma/migrations/20260103000000_org/migration.sql",
                 "prisma/migrations/20260104000000_idx/migration.sql"], paths   # filename/timestamp order, lock file excluded
sums = [x["summary"] for x in db["migrations"]]
assert sums[0] is None and sums[2] is None, sums                 # routine files: NO line at all
assert sums[1] and "drops column Post.firmId" in sums[1] and "UPDATE" in sums[1], sums
kinds = [r["kind"] for r in db["reasons"]]
assert kinds[:2] == ["destructive_ddl", "data_mutation"] and "additive_ddl" in kinds, kinds
assert "unrepresented_ddl" not in kinds, "a schema-side change with a matching diff is not drift"
assert db["severity"] == "critical", db["severity"]
byp = {f["path"]: f for f in m["files"]}
assert byp["prisma/schema.prisma"]["db"] == "schema" and byp[paths[1]]["db"] == "migration", "files must carry their db role"
print("A model OK")
PY
build_report "$OUT" "$CODE_FINDING"
python3 "$S/check-report.py" "$OUT/report.json" || fail "A: a well-formed package must validate"
python3 "$S/render-report.py" --dir "$OUT" --no-snapshot --no-delta-pages >/dev/null
python3 - "$OUT/index.html" <<'PY' || fail "A: render"
import re, sys
h = open(sys.argv[1]).read()
fin = re.search(r'<section id="findings">(.*?)</section>', h, re.S).group(1)
card = fin.split('data-id="C2"', 1)[1].split('<div class="fb">', 1)[0]
assert 'class="dbtag">DB schema change' in card, "package card is not labelled"
assert '<ul class="dbp-rs">' in card, "≥2 reasons must render as a list"
for sev in ("critical", "low"):
    assert f'<span class="pill {sev}">{sev}</span>' in card, f"reason chip must carry its severity as TEXT ({sev})"
assert "What data does this lose" in card and "Does the predicate match" in card, "each reason carries its own question"
side = card.split('<details class="sidecar">', 1)[1]
assert "<summary>3 migrations · in run order</summary>" in side, side[:120]
files = re.findall(r'data-open="(prisma/migrations/[^"]+)"', side)
assert files == ["prisma/migrations/20260102000000_add_nick/migration.sql", "prisma/migrations/20260103000000_org/migration.sql",
                 "prisma/migrations/20260104000000_idx/migration.sql"], files   # semantic order, clickable to the diff
notes = re.findall(r'<div class="sc-note">([^<]*)</div>', side)
assert len(notes) == 1 and "drops column Post.firmId" in notes[0], notes      # ONLY the risky file has a line
assert "no findings" not in side.lower() and "nothing to see" not in side.lower(), "routine files must be bare filenames"
assert 'class="ann"' in side and side.count("<li") == 3, "annotated file is a shade less muted; no per-file severity badge"
assert not re.search(r'<li[^>]*>\s*<span class="pill', side), "no per-file severity badge in the sidecar"
# §7 — the exclusion trap: sidecar files must NOT reappear in "Everything else".
unrev = re.search(r'<section id="unreviewed">(.*?)</section>', h, re.S).group(1)
leaked = [p for p in files + ["prisma/schema.prisma"] if f'data-file="{p}"' in unrev]
assert not leaked, f"package files leaked into Everything else: {leaked}"
# four buckets, all present, in order
groups = re.findall(r'<h3 class="area" data-area="(\w+)">', unrev)
assert groups == ["code", "tests", "tooling", "docs"], groups
def group_of(p):
    i = unrev.index(f'data-file="{p}"'); return re.findall(r'data-area="(\w+)"', unrev[:i])[-1]
assert group_of("src/other.ts") == "code" and group_of("tests/save.test.ts") == "tests"
assert group_of("ci.yml") == "tooling" and group_of("docs/guide.md") == "docs"
assert 'data-file="src/save.ts"' not in unrev, "a flagged code file must not be listed again"
# the package sits where its severity puts it — here critical, alongside C1, not pinned first
order = re.findall(r'data-id="([CML]\d+)"', fin)
assert order == ["C1", "C2"], order
print("A render OK")
PY
# The §7 regression in its purest form: strip the sidecar from the exclusion and the leak returns.
# (Guards the renderer line, not the test fixture.)
grep -q 'for mg in ((f.get("db_package") or {}).get("migrations") or \[\])' "$S/render-report.py" || fail "renderer no longer excludes sidecar files from the remainder"

# ── B. a SINGLE migration: no per-file note, whatever the file carries ─────────────────────────
repo b
mkdir -p prisma/migrations/1_init src
printf '%s' "$SCHEMA_BASE" > prisma/schema.prisma
printf 'CREATE TABLE "Post" ("id" TEXT NOT NULL);\n' > prisma/migrations/1_init/migration.sql
commit base
printf '%s' "$SCHEMA_BASE" | sed 's/firmId String/firmId String?/' > prisma/schema.prisma
mkdir -p prisma/migrations/2_drop
printf 'ALTER TABLE "Post" DROP COLUMN "title";\n' > prisma/migrations/2_drop/migration.sql
OUT="$(collect)"
build_report "$OUT"
python3 - "$OUT" <<'PY'
import json, os, sys
d = sys.argv[1]; r = json.load(open(os.path.join(d, "report.json")))
pk = next(f for f in r["findings"] if "db_package" in f)["db_package"]
assert len(pk["migrations"]) == 1
pk["migrations"][0]["note"] = "drops column Post.title"       # the analyst wrote one anyway
json.dump(r, open(os.path.join(d, "report.json"), "w"))
PY
MSG="$(python3 "$S/check-report.py" "$OUT/report.json" 2>&1)" || fail "B: a note on a single migration is a warning, not an error: $MSG"
case "$MSG" in *"single migration carries a note"*) ;; *) fail "B: validator must warn about the redundant note: $MSG" ;; esac
python3 "$S/render-report.py" --dir "$OUT" --no-snapshot --no-delta-pages >/dev/null
grep -q 'class="sc-note"' "$OUT/index.html" && fail "B: a single migration must render without a per-file note"
grep -q '<summary>1 migration</summary>' "$OUT/index.html" || fail "B: sidecar summary for one migration"
echo "B single migration OK"

# ── C. hand-written migration, NO schema diff, DDL → drift, critical, named as drift ────────────
repo c
mkdir -p prisma/migrations/1_init
printf '%s' "$SCHEMA_BASE" > prisma/schema.prisma
printf 'CREATE TABLE "Post" ("id" TEXT NOT NULL);\n' > prisma/migrations/1_init/migration.sql
commit base
mkdir -p prisma/migrations/2_vec
printf 'CREATE INDEX "Post_embedding_idx" ON "Post" USING hnsw (embedding vector_cosine_ops);\n' > prisma/migrations/2_vec/migration.sql
OUT="$(collect)"
python3 - "$OUT" <<'PY' || fail "C: model"
import json, sys, os
db = json.load(open(os.path.join(sys.argv[1], "diff-model.json")))["db"]
assert db["headline_kind"] == "migrations" and db["headline"] == "prisma/migrations/2_vec/migration.sql", db
assert not db["schema_changed"] and db["schema_artifact"] == "prisma/schema.prisma"
r = {x["kind"]: x for x in db["reasons"]}
assert "unrepresented_ddl" in r and r["unrepresented_ddl"]["severity"] == "critical", r
assert r["unrepresented_ddl"]["detected_by"] == "no_schema_diff", r["unrepresented_ddl"]
assert "did not change" in r["unrepresented_ddl"]["detail"] and "hnsw" in r["unrepresented_ddl"]["detail"], r["unrepresented_ddl"]
assert "data_mutation" not in r
assert db["severity"] == "critical"
print("C model OK")
PY
build_report "$OUT"
python3 "$S/check-report.py" "$OUT/report.json" || fail "C: validate"
python3 "$S/render-report.py" --dir "$OUT" --no-snapshot --no-delta-pages >/dev/null
CARD="$(section "$OUT/index.html" findings)"
case "$CARD" in *"DDL the schema does not describe"*) ;; *) fail "C: the reason must name drift" ;; esac
case "$CARD" in *"schema artifact did not change"*) ;; *) fail "C: detected_by must be surfaced" ;; esac
case "$CARD" in *andwritten*) fail "C: 'handwritten' tells the reader to look without saying what for" ;; esac
grep -q 'data-open="prisma/migrations/2_vec/migration.sql"' "$OUT/index.html" || fail "C: headline migration not clickable"
echo "C drift OK"

# ── D. hand-written migration, NO schema diff, DML only → data_mutation, NOT drift ─────────────
repo d
mkdir -p prisma/migrations/1_init
printf '%s' "$SCHEMA_BASE" > prisma/schema.prisma
printf 'CREATE TABLE "Post" ("id" TEXT NOT NULL);\n' > prisma/migrations/1_init/migration.sql
commit base
mkdir -p prisma/migrations/2_backfill
printf 'UPDATE "Post" SET "title" = '"'"'untitled'"'"' WHERE "title" IS NULL;\n' > prisma/migrations/2_backfill/migration.sql
OUT="$(collect)"
python3 - "$OUT" <<'PY' || fail "D: model"
import json, sys, os
db = json.load(open(os.path.join(sys.argv[1], "diff-model.json")))["db"]
kinds = [r["kind"] for r in db["reasons"]]
assert kinds == ["data_mutation"], kinds
assert db["headline_kind"] == "migrations" and db["severity"] == "critical"
print("D model OK")
PY
build_report "$OUT"; python3 "$S/check-report.py" "$OUT/report.json" || fail "D: validate"
echo "D backfill OK"

# ── E. schema diff, NO migration → schema_migration_drift, empty sidecar rendered as a finding ──
repo e
mkdir -p prisma/migrations/1_init
printf '%s' "$SCHEMA_BASE" > prisma/schema.prisma
printf 'CREATE TABLE "Post" ("id" TEXT NOT NULL);\n' > prisma/migrations/1_init/migration.sql
commit base
printf '%s' "$SCHEMA_BASE" | sed 's/title  String/title  String\n  body   String?/' > prisma/schema.prisma
OUT="$(collect)"
python3 - "$OUT" <<'PY' || fail "E: model"
import json, sys, os
db = json.load(open(os.path.join(sys.argv[1], "diff-model.json")))["db"]
assert db["headline_kind"] == "schema" and db["migrations"] == [] and [r["kind"] for r in db["reasons"]] == ["schema_migration_drift"], db
assert db["severity"] == "critical"
print("E model OK")
PY
build_report "$OUT"; python3 "$S/check-report.py" "$OUT/report.json" || fail "E: validate"
python3 "$S/render-report.py" --dir "$OUT" --no-snapshot --no-delta-pages >/dev/null
grep -q 'sidecar sidecar-empty">No migration accompanies this schema change' "$OUT/index.html" || fail "E: empty sidecar must be a stated finding, not a blank"
grep -q 'Why is there no migration' "$OUT/index.html" || fail "E: drift question"
echo "E drift OK"

# ── F. a project with NO schema artifact: same group, headline = migrations, no ORM wording ─────
repo f
mkdir -p migrations src
printf 'CREATE TABLE users (id serial primary key);\n' > migrations/001_init.sql
printf 'x\n' > src/a.txt
commit base
printf 'ALTER TABLE users ADD COLUMN email text;\n' > migrations/002_email.sql
printf 'UPDATE users SET email = lower(email);\n' > migrations/003_lower.sql
OUT="$(collect)"
python3 - "$OUT" <<'PY' || fail "F: model"
import json, sys, os
db = json.load(open(os.path.join(sys.argv[1], "diff-model.json")))["db"]
assert db["schema_artifact"] is None and db["headline_kind"] == "migrations" and db["headline"] == "migrations/002_email.sql", db
kinds = [r["kind"] for r in db["reasons"]]
assert "data_mutation" in kinds and "unrepresented_ddl" not in kinds, kinds   # nothing to be "represented" in
print("F model OK")
PY
build_report "$OUT"; python3 "$S/check-report.py" "$OUT/report.json" || fail "F: validate"
python3 "$S/render-report.py" --dir "$OUT" --no-snapshot --no-delta-pages >/dev/null
grep -q 'class="dbtag">DB schema change' "$OUT/index.html" || fail "F: the same group must render"
grep -qi 'prisma' "$OUT/index.html" && fail "F: ORM-shaped wording leaked into a schema-less project's report"
grep -q '<summary>2 migrations · in run order</summary>' "$OUT/index.html" || fail "F: sidecar"
echo "F schema-less OK"

# ── G. config override resolves the schema artifact and migrations dir, NOT the convention ──────
repo g
mkdir -p .claude prisma db/migrate migrations
printf '{"describe-changes": {"schemaArtifact": "db/model.prisma", "migrationsDir": "db/migrate"}}\n' > .claude/claude-skills.json
printf '%s' "$SCHEMA_BASE" > prisma/schema.prisma      # the CONVENTION file exists and is untouched
printf '%s' "$SCHEMA_BASE" > db/model.prisma
printf 'CREATE TABLE "Post" ("id" TEXT NOT NULL);\n' > db/migrate/001.sql
printf 'select 1;\n' > migrations/stray.sql             # conventional dir, must be IGNORED under the override
commit base
printf '%s' "$SCHEMA_BASE" | sed 's/title  String/title  String?/' > db/model.prisma
printf 'ALTER TABLE "Post" ALTER COLUMN "title" DROP NOT NULL;\n' > db/migrate/002.sql
printf 'select 2;\n' > migrations/stray.sql
OUT="$(collect)"
python3 - "$OUT" <<'PY' || fail "G: override"
import json, sys, os
db = json.load(open(os.path.join(sys.argv[1], "diff-model.json")))["db"]
assert db["schema_artifact"] == "db/model.prisma" and db["schema_configured"] and db["schema_changed"], db
assert [m["path"] for m in db["migrations"]] == ["db/migrate/002.sql"], db["migrations"]
assert db["migrations_dir_configured"] == ["db/migrate"]
assert db["severity"] == "low", db["reasons"]
print("G override OK")
PY

# ── H. additive-only migration → LOW, and it sorts BELOW a critical code finding ───────────────
repo h
mkdir -p prisma/migrations/1_init src
printf '%s' "$SCHEMA_BASE" > prisma/schema.prisma
printf 'CREATE TABLE "Post" ("id" TEXT NOT NULL);\n' > prisma/migrations/1_init/migration.sql
printf 'export function save(x: string) { return x; }\n' > src/save.ts
commit base
printf '%s' "$SCHEMA_BASE" | sed 's/title  String/title  String\n  nick   String?/' > prisma/schema.prisma
mkdir -p prisma/migrations/2_nick
printf 'ALTER TABLE "Post" ADD COLUMN "nick" TEXT;\n' > prisma/migrations/2_nick/migration.sql
printf 'export function save(x: string) { db.deleteOnConflict(x); return x; }\n' > src/save.ts
OUT="$(collect)"
build_report "$OUT" "$CODE_FINDING"
python3 "$S/check-report.py" "$OUT/report.json" || fail "H: validate"
python3 "$S/render-report.py" --dir "$OUT" --no-snapshot --no-delta-pages >/dev/null
python3 - "$OUT" <<'PY' || fail "H: order"
import json, re, sys, os
d = sys.argv[1]
r = json.load(open(os.path.join(d, "report.json")))
pk = next(f for f in r["findings"] if "db_package" in f)
assert pk["severity"] == "low" and pk["id"] == "L1", (pk["id"], pk["severity"])
h = open(os.path.join(d, "index.html")).read()
fin = re.search(r'<section id="findings">(.*?)</section>', h, re.S).group(1)
order = re.findall(r'data-id="([CML]\d+)"', fin)
assert order == ["C1", "L1"], order                       # not pinned to the top
assert '<div class="dbp-r">' in fin and '<ul class="dbp-rs">' not in fin, "one reason renders flat, no nesting"
print("H additive OK")
PY

# ── I. the validator rejects each malformed package — one case per rule ────────────────────────
cd "$T/a"; OUT="$T/a/.describe-changes/main"
build_report "$OUT" "$CODE_FINDING" >/dev/null
python3 - "$OUT" <<'PY'
import json, os, sys, copy
d = sys.argv[1]; r = json.load(open(os.path.join(d, "report.json")))
pk_i = next(i for i, f in enumerate(r["findings"]) if "db_package" in f)
def case(name, mutate, expect):
    x = copy.deepcopy(r); mutate(x); x["_expect"] = expect
    json.dump(x, open(os.path.join(d, f"bad-{name}.json"), "w"))
def pk(x): return x["findings"][pk_i]["db_package"]
def add_second_package(x):
    x["findings"][0]["db_package"] = copy.deepcopy(pk(x))
case("two-packages", add_second_package, "at most one finding may")
case("kind", lambda x: pk(x).__setitem__("headline_kind", "prisma"), "headline_kind must be")
case("schema-wrong-file", lambda x: x["findings"][pk_i].__setitem__("file", "src/other.ts"), "requires file == the schema artifact")
def mig_kind_empty(x): pk(x)["headline_kind"] = "migrations"; pk(x)["migrations"] = []
case("migrations-empty", mig_kind_empty, "non-empty migrations list")
def mig_kind_wrong_file(x): pk(x)["headline_kind"] = "migrations"
case("migrations-wrong-file", mig_kind_wrong_file, "requires file == migrations[0].path")
case("reasons-empty", lambda x: pk(x).__setitem__("reasons", []), "non-empty list")
case("reason-kind", lambda x: pk(x)["reasons"][0].__setitem__("kind", "scary_sql"), "reasons[0].kind must be one of")
case("reason-sev-value", lambda x: pk(x)["reasons"][0].__setitem__("severity", "high"), "severity must be critical|medium|low")
case("reason-sev-table", lambda x: pk(x)["reasons"][0].__setitem__("severity", "medium"), "the severity table says critical")
case("sev-not-max", lambda x: x["findings"][pk_i].update(severity="low", id="L9"), "max over db_package.reasons")
def schema_no_drift(x): pk(x)["migrations"] = []
case("schema-empty-no-drift", schema_no_drift, "must carry a schema_migration_drift reason")
case("path-not-in-diff", lambda x: pk(x)["migrations"].append({"path": "prisma/migrations/ghost/migration.sql"}), "is not in the diff")
case("migration-leak", lambda x: pk(x)["migrations"].pop(), "would render twice")
def unrep_no_by(x): pk(x)["reasons"].append({"kind": "unrepresented_ddl", "severity": "critical", "question": "?", "detail": "x"})
case("unrep-no-detected-by", unrep_no_by, "needs detected_by")
def drop_package(x): del x["findings"][pk_i]["db_package"]
case("no-package", drop_package, "no finding carries db_package")
case("note-no-ops", lambda x: pk(x)["migrations"][0].__setitem__("note", "adds index on organizationId"), "omit the note")
def drop_reason(x): pk(x)["reasons"] = [q for q in pk(x)["reasons"] if q["kind"] != "data_mutation"]
case("reason-dropped", drop_reason, "migration SQL shows data_mutation")
def reorder(x): pk(x)["migrations"].reverse()
case("order", reorder, "keep the classifier's order")
# warnings, not errors
w = copy.deepcopy(r); pk(w)["migrations"][1]["note"] = "x" * 140; json.dump(w, open(os.path.join(d, "warn-note-long.json"), "w"))
w2 = copy.deepcopy(r); pk(w2)["migrations"][1]["note"] = "drops everything and backfills the moon"; json.dump(w2, open(os.path.join(d, "warn-note-untraced.json"), "w"))
PY
for f in "$OUT"/bad-*.json; do
  EXP="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['_expect'])" "$f")"
  if python3 "$S/check-report.py" "$f" >/dev/null 2>&1; then fail "I: check-report accepted $(basename "$f")"; fi
  MSG="$(python3 "$S/check-report.py" "$f" 2>&1 || true)"
  case "$MSG" in *"$EXP"*) ;; *) fail "I: $(basename "$f") rejected for the wrong reason (want '$EXP'):
$MSG" ;; esac
done
MSG="$(python3 "$S/check-report.py" "$OUT/warn-note-long.json" 2>&1)" || fail "I: an over-long note is a warning: $MSG"
case "$MSG" in *"WARN"*"140 chars"*) ;; *) fail "I: long note must warn: $MSG" ;; esac
MSG="$(python3 "$S/check-report.py" "$OUT/warn-note-untraced.json" 2>&1)" || fail "I: a reworded note is a warning: $MSG"
case "$MSG" in *"differs from the parsed summary"*) ;; *) fail "I: untraceable note must warn: $MSG" ;; esac
# …and the renderer truncates the long note at the cap
cp "$OUT/warn-note-long.json" "$OUT/report.json"
python3 "$S/render-report.py" --dir "$OUT" --no-snapshot --no-delta-pages >/dev/null
python3 - "$OUT/index.html" <<'PY' || fail "I: note not truncated"
import re, sys
n = re.findall(r'<div class="sc-note">([^<]*)</div>', open(sys.argv[1]).read())
assert n and len(n[0]) <= 100 and n[0].endswith("…"), n
print("I validator OK")
PY
rm -f "$OUT"/bad-*.json "$OUT"/warn-*.json

# ── J. unit: ordering, and the two modes of unrepresented-DDL detection ─────────────────────────
python3 - "$S" <<'PY' || fail "J: units"
import importlib.util, sys
spec = importlib.util.spec_from_file_location("cd", sys.argv[1] + "/classify-diff.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
class H:
    def __init__(s, added): s.added = added
class F:
    def __init__(s, path, sql): s.path, s.status, s.hunks = path, "added", [H(sql.splitlines())]
files = [F("prisma/schema.prisma", "model X {}"),
         F("prisma/migrations/1_backfill/migration.sql", 'UPDATE "Post" SET a = 1;'),
         F("prisma/migrations/2_table/migration.sql", 'CREATE TABLE "Org" ("id" TEXT NOT NULL);')]
db = m.db_scan(files, None, {})
kinds = [r["kind"] for r in db["reasons"]]
assert "ordering" in kinds, kinds
o = next(r for r in db["reasons"] if r["kind"] == "ordering")
assert o["severity"] == "medium" and "1_backfill → 2_table" in o["detail"], o
# same file carrying both: sequence inside one file is visible in the file — no ordering reason
db1 = m.db_scan([files[0], F("prisma/migrations/1_both/migration.sql", 'UPDATE "Post" SET a = 1; CREATE TABLE "Org" ("id" TEXT);')], None, {})
assert "ordering" not in [r["kind"] for r in db1["reasons"]]
# config mode: an unmanaged index dropped and NOT re-created is drift, detected by config;
# dropped and re-created is the documented workflow and is NOT flagged.
cfg = {"prisma-migrate": {"unmanagedSql": [{"name": "posts_embedding_idx", "sql": "CREATE INDEX ..."}]}}
drop_only = 'DROP INDEX "posts_embedding_idx";'
drop_recreate = drop_only + ' CREATE INDEX "posts_embedding_idx" ON "posts" USING hnsw (embedding vector_cosine_ops);'
a = m.sql_ops(drop_only, {"posts_embedding_idx"}, True)
assert [x["kind"] for x in a] == ["unrepresented_ddl"] and a[0]["detected_by"] == "config", a
b = m.sql_ops(drop_recreate, {"posts_embedding_idx"}, True)
assert "unrepresented_ddl" not in [x["kind"] for x in b], b
# heuristic mode: the same hnsw index with no config is flagged, and says it is a heuristic
c = m.sql_ops(drop_recreate, None, True)
u = [x for x in c if x["kind"] == "unrepresented_ddl"]
assert u and u[0]["detected_by"] == "heuristic", c
# the reason text names the mechanism
dbc = m.db_scan([files[0], F("prisma/migrations/1_x/migration.sql", drop_recreate)], None, cfg)
r = next(x for x in dbc["reasons"] if x["kind"] == "unrepresented_ddl") if any(x["kind"] == "unrepresented_ddl" for x in dbc["reasons"]) else None
assert r is None, "an unmanaged object re-asserted per config must not be drift"
dbh = m.db_scan([files[0], F("prisma/migrations/1_x/migration.sql", drop_recreate)], None, {})
r = next(x for x in dbh["reasons"] if x["kind"] == "unrepresented_ddl")
assert r["detected_by"] == "heuristic" and "hnsw" in r["detail"], r
assert not m.is_migration_path("prisma/migrations/migration_lock.toml", []), "lock/metadata files are not migrations"
assert m.is_migration_path("prisma/migrations/1_x/migration.sql", []) and m.is_migration_path("db/migrate/20260101_x.rb", [])
# severity table: one place, and the validator mirrors it
import json, re
chk = open(sys.argv[1] + "/check-report.py").read()
mirror = json.loads(re.search(r"DB_REASON_SEVERITY = (\{.*?\})", chk, re.S).group(1).replace("\n", "").replace("'", '"').rstrip("}").rstrip(",") + "}")
assert mirror == m.REASON_SEVERITY, (mirror, m.REASON_SEVERITY)
print("J units OK")
PY

echo "DB PACKAGE TESTS PASSED"
