# report.json — the contract between the analysis (LLM) and the renderer (script)

Write this file to `$OUT/report.json`. `check-report.py` validates it; `render-report.py` renders it.
Keys marked ● are required.

```jsonc
{
  "title": "Per-step execution config for type:claude steps",          // ● short, the change's name
  // The ASK, ONE line, ≤ 260 chars. Rendered as a small lede above the summary.
  "intent": "Story 3.2: let workflow.yml set model/effort per step.",
  // ● What CHANGED, plus the one thing that is not obvious from it. ≤ 3 sentences / 420 chars
  // (hard cap 700). It must NOT restate the intent — the validator warns when they overlap > 55%.
  // Test: "what does the reviewer still not know after reading the intent line?" Answer only that.
  //
  // FUNCTIONAL, not mechanical: what a person can now do, what they can no longer do, and the rule
  // that decides which — in the product's own words. Mechanism earns a place only when it IS a
  // decision or a risk. Compare:
  //   ✗ "Guarded by one invariant re-asserted inside the write transaction over a row lock."
  //   ✓ "The last admin can't remove or demote themselves — the controls disappear rather than fail."
  // Same fact; the second is the one a reviewer can act on. The validator warns when a summary
  // carries more than three `backticked` identifiers, which is the usual tell for the first shape.
  "summary": "A step can now pick its own model and effort instead of taking the workflow's. Steps that say nothing keep today's behaviour — except for permission mode, where an unset value now means `default` rather than inheriting the daemon's.",
  // Author doubt, as a LIST — one scannable line each, the longer explanation folded behind it.
  // 2–4 items is the useful range; > 6 warns (if everything is doubtful, nothing is).
  // This is TESTIMONY, not analysis: only the author can say what they guessed at or could not test,
  // and on a two-pass run it is the ONLY thing the author contributes (findings come from the cold
  // pass — see SKILL.md §2a/§2b).
  "confession": [
    { "point": "The retry-path e2e never ran — I could not reproduce the fixture locally.",
      "detail": "Optional; shown only when the reader expands the point. Mechanism, what you tried, what would settle it.",
      // Two-pass runs only: the finding ids the INDEPENDENT pass raised over the same code. An
      // explicit `[]` means the cold reader looked there and flagged nothing — which is information,
      // not silence, and renders as an open question. Omit the key entirely on a single-pass run.
      "corroborated_by": ["C1"] },
    { "point": "`resolveModel`'s fallback is a guess; no test pins it.", "corroborated_by": [] }
  ],
  "range": "main..feat/3.2 (+ working tree)",                          // optional; meta.json has it

  // ● dependency order, 2–6. The narrative is the first prose anyone meets, before a line of code:
  // say what the phase DOES in a stranger's words, then name the files. Opening on a symbol warns.
  //   ✗ "`resolveModel` moves into `shared/workflow.ts` and gains an `effort` field."
  //   ✓ "A step can now carry its own model and effort. The types that describe it move to the
  //      shared module so the daemon and the UI read one definition."
  "phases": [
    { "id": "p1", "title": "Schema + types", "narrative": "…1–3 sentences, ≤ 320 chars…", "files": ["src/shared/workflow.ts"] }
  ],

  "graph": {                                                          // ●
    "narrative": "optional one-liner about what the map shows / omits",
    "nodes": [                                                        // ≤ ~25
      { "id": "runStep", "label": "runStep()", "kind": "function", "change": "modified", "file": "src/daemon/executor.ts" },
      { "id": "ExecCfg", "label": "ExecutionConfig", "kind": "type", "change": "added", "file": "src/shared/workflow.ts" },
      { "id": "oldHelper", "label": "buildArgs()", "kind": "function", "change": "moved", "file": "src/daemon/args.ts" }
    ],
    "edges": [
      { "from": "runStep", "to": "ExecCfg", "kind": "reads", "label": "model, effort" },
      { "from": "runStep", "to": "oldHelper", "kind": "calls" }
    ]
  },
  // node.kind: function | method | component | hook | type | interface | schema | module | file | store | db | table | endpoint | job | config
  // node.change: added | modified | removed | moved | renamed | split | unchanged
  // edge.kind: calls | dataflow | imports | renders | extends | moved_to | split_into | reads | writes | emits

  "views": [ /* optional, 0–3 — see visualizations.md: screen | flow | adoption */ ],

  "findings": [                                                       // ● important first; ids C1.. M1.. L1..
    {
      // THE DB SCHEMA PACKAGE — one finding that owns the ENTIRE database change: the authored
      // schema artifact as the headline, its migrations as a muted sidecar beneath it. Presence of
      // `db_package` is what marks it. Build it FROM `diff-model.json → db` (the classifier already
      // found the schema artifact, the migrations in run order, what each SQL file does and the
      // reasons it supports): copy `headline_kind`, the migration paths in the given order, each
      // file's `summary` as its `note` (or no note), and the `reasons`. Write the title toward RISK
      // ("drops 9 cascade edges; verify the backfill predicate") — the phase already says the shape.
      // At most ONE finding may carry it. It is required whenever `diff-model.json → db` is set.
      "id": "C1", "severity": "critical",           // = the max over reasons[].severity — enforced
      "title": "Organization becomes the tenant root; firmId leaves 8 models",
      "verify": "…", "why_human": "…",
      "file": "prisma/schema.prisma",               // the headline: db.headline (schema artifact, or the first migration)
      "db_package": {
        "headline_kind": "schema",                  // "schema" | "migrations"  — copy db.headline_kind
        "migrations": [                             // db.migrations, SAME order (filename/timestamp); [] allowed
          { "path": "prisma/migrations/20260913120000_x/migration.sql",
            "note": "drops 9 FK constraints; runs 1 UPDATE" },   // = that file's `summary`, verbatim; ≤ 100 chars;
          { "path": "prisma/migrations/20260913130000_y/migration.sql" }  // no `summary` → NO note (bare = nothing to see)
        ],
        "reasons": [                                // 1..n, from db.reasons; render flat when exactly 1
          { "kind": "destructive_ddl", "severity": "critical",
            "question": "What data does this lose, and is it recoverable?",
            "detail": "Drops the firm cascade edge on 9 child tables." },
          { "kind": "unrepresented_ddl", "severity": "critical",
            "detected_by": "config",                // "config" | "heuristic" | "no_schema_diff" — shown to the reader
            "question": "Will it survive the next generated migration?",
            "detail": "…" }
        ]
      }
    },
    {
      "id": "C2", "severity": "critical",
      // PLAIN FIRST — the reader has not opened the code and decides from the first line. `what`
      // says what a PERSON meets in sentence one, and may name the symbol in sentence two; never
      // the reverse. ≤ 2 sentences, ≤ 300 chars, ≤ 2 backticked symbols, and check-report.py
      // REJECTS a `what` whose first sentence names a symbol — the one prose rule that is an error,
      // because it is the commonest and always fixable by reordering. Full rules: analysis-guide §7.
      //   ✗ "`resolveMode()`'s fallback branch returns 'bypass' where it previously returned
      //      'default', so `spawnClaude` receives `--dangerously-skip-permissions`."
      //   ✓ "A step that does not name a permission mode now runs with every prompt skipped, where
      //      it used to ask. `resolveMode()` is where the fallback changed."
      "title": "`spawnClaude` passes `--dangerously-skip-permissions` whenever `execution.mode` is unset",
      "verify": "Is bypass the intended default for steps that do not declare a mode?",
      "why_human": "Default policy for unattended sessions is a judgement call with security consequences; no test encodes the intent.",
      "what": "A step that does not name a permission mode now runs with every prompt skipped, where it used to ask. `resolveMode()` is where the fallback changed.",
      "file": "src/daemon/executor.ts", "lines": "118-131", "hunks": ["F4H2"],
      "tags": ["divergence", "auth", "blast-radius"],
      // WHO raised it. Optional; set it only on a two-pass run (SKILL.md §2b), and set it on EVERY
      // finding when you set it on any — a mixed report cannot be read.
      //   "fresh"  — the cold pass, which had no access to the author's reasoning
      //   "author" — the author, from knowledge the diff does not carry
      //   "both"   — raised independently by both, which is the strongest signal in the report
      // Absent everywhere = single-pass run, and the "Two readings" section does not render.
      "provenance": "fresh"
      // optional instead of hunks: "before": "…code…", "after": "…code…"
    },
    {
      "id": "C3", "severity": "critical",
      "title": "`removeMemberAsUser` reads Prisma directly instead of going through the repository",
      "verify": "Is this deliberately outside the layer rule, or should it call `membershipRepository`?",
      "why_human": "The rule exists to keep tenant scoping in one place; whether this is a new direction is the author's call.",
      "file": "src/features/org/service/member-service.ts", "lines": "44-58", "hunks": ["F9H1"],
      "tags": ["convention", "blast-radius"],
      // REQUIRED on a `convention` finding: what it contradicts. A written rule, or ≥ 2 neighbours
      // that do it the other way. Uncited = taste, and check-report.py rejects it.
      "diverges_from": [
        { "ref": "CLAUDE.md:161", "why": "service layer never touches Prisma directly" },
        { "ref": "src/features/org/service/invitation-service.ts:22" }
      ]
    }
  ],

  // Optional. One entry per SHIPPED user-facing capability, so a reviewer can exercise it for real
  // instead of trusting the report. Omit for a change nobody can drive (pure refactor, infra, docs).
  "how_to_check": [
    {
      "id": "V1",                                   // V<n>, unique
      "feature": "Remove a member from an organization",
      "surface": "ui",                              // ui | api | cli   (default ui)
      "where": "/app/org/{slug}/settings/members",  // route, screen or command
      "setup": "Sign in as an owner of an org that has two owners.",   // optional preconditions
      "steps": ["Open Nastavenia → Členovia.", "Press Odstrániť on the other owner's row.", "Confirm."],
      "expect": "The row disappears without a page reload and a success toast shows.",
      "covered_by": "tests/e2e/specs/organization/member-removal.spec.ts"  // optional
    },
    {
      "id": "V2", "feature": "Bulk import endpoint", "surface": "api",
      "steps": ["Send the request below.", "Re-open the list — the rows are there."],
      "expect": "201 with {imported: 3}.",
      // `request` turns the card into a runnable one: copy-as-curl, a Postman collection for the
      // whole report, and an inline send. Only for surface:"api".
      "request": { "method": "POST", "path": "/api/v1/import",
                   "headers": {"content-type": "application/json"},
                   "body": {"rows": []},
                   "note": "Needs a signed-in session cookie." }
    }
  ],

  "folded": [ /* copy diff-model.json → folds verbatim; the HTML renders the MODEL's copy */ ],  // ●
  // "Everything else that changed" is the COMPLEMENT of every path shown above — a finding's `file`,
  // a DB package's migrations, a phase's `files`, a view's file chips. Each of those already opens
  // the file's diff, so a file listed there is never offered again here. Notes therefore only make
  // sense for files that actually land in that list; a note on a path shown above renders NOWHERE,
  // and the validator warns. Say it in the phase narrative instead.
  "unreviewed_notes": {                                              // files in NO section above: why they need none
    "src/pwa/components/StepCard.tsx": "prop pass-through only; typed end to end"
  }
}
```

Rules the validator enforces: ≤ 3 critical (error), ≤ 7 medium (warn); each finding has `title`,
`verify`, `why_human`, `file`; finding ids are unique and match severity (`C`/`M`/`L`); every file path
exists in the diff; every edge references a node; graph ≤ 40 nodes (warn).

On a finding's prose (analysis-guide §7). **Errors:** a `what` whose FIRST SENTENCE names a
backticked symbol, `what` > 500 chars, `what` > 3 sentences, `title` > 130 chars. **Warnings:**
`title` > 80 chars or naming > 2 symbols, `what` > 300 chars or > 2 sentences or naming > 2 symbols,
`verify` asking more than one question or running > 200 chars, `why_human` > 240 chars. A phase
narrative warns when it opens on a symbol, runs past 3 sentences, or exceeds 320 chars. These mirror
the header caps below onto the sections a reviewer actually spends time in — for the same reason,
measured on the same failure: on a real report the capped `summary` came in at 431 chars with no
code names while the uncapped `what` fields averaged four sentences, one of them reaching seven
sentences and thirteen symbols. Same author, same run. The difference was the check.

On `db_package` (all errors unless marked): at most one finding carries it, and one MUST when
`diff-model.json → db` is set; `headline_kind: "schema"` requires `file` to be the schema artifact
and the artifact to have changed, `"migrations"` requires a non-empty list with `file ==
migrations[0].path`; every migration the classifier found is listed, in its order (a missing one
would render twice in "Everything else"); every path is in the diff; `reasons` is non-empty, each
`kind` from `destructive_ddl | unrepresented_ddl | data_mutation | ordering | schema_migration_drift |
structural_ddl | additive_ddl`, each `severity` equal to the table in analysis-guide.md §8, and
`finding.severity` equal to the max of them; every reason kind the SQL supports (`db.reasons`) is
present — add reasons, never drop them; `unrepresented_ddl` carries `detected_by`; a schema
headline with `migrations: []` carries `schema_migration_drift`; a `note` on a file whose parsed
`summary` is empty is an error (nothing to trace it to), a note that differs from the summary or
exceeds 100 chars warns (the renderer truncates), and a note on a lone migration warns (the
renderer omits it).

On the header specifically: `summary` > 700 chars is an **error**, > 420 a warning, > 4 sentences a
warning; `intent` > 260 chars warns; `intent`/`summary` vocabulary overlap > 55% warns; a `confession`
item needs a `point` (its `detail` is optional), a `point` > 180 chars warns, and > 6 items warns.
These are caps on the reviewer's attention, not on your prose — an over-long header is the cheapest
way to produce the rubber-stamped signature this tool exists to prevent.

`confession` also accepts a plain string (the pre-1.1 form) and still renders, but the list is what
gets read: a reviewer skims four one-liners and opens the one that worries them, where the same
content as a paragraph is skipped whole and the doubt may as well not have been declared.
