# report.json for a plan — the contract between the analysis (LLM) and the renderer (script)

Write it to `$OUT/report.json`. `check-plan.py` validates it; `render-plan.py` renders it. Keys
marked ● are required. Three keys keep the names the changes report uses — `findings`,
`how_to_check`, `views` — so the shared feedback tooling (`../changes/scripts/feedback.py`) reads a
plan's steering points, try-it cards and pictures without knowing which skill wrote them.

```jsonc
{
  "kind": "plan",                                                       // ● literally "plan"
  "title": "Codelists from the configuration component",                // ● the plan's name
  // The ask, ONE line, ≤ 260 chars: what this plan is for, or who asked for it.
  "intent": "Programme task PR-017: the register stops shipping its own code tables and reads them from the platform component.",
  // ● THE OPENING. 3–5 sentences a person outside the team can read: what will be different for
  // someone, and why. No code symbols at all in the first sentence (error), at most two anywhere
  // (warning). ≤ 800 chars.
  "plain": "Today the operator screen gets its dropdown lists — regions, professions, marital status — from a copy baked into the register. After this plan it asks the platform's configuration service for each list when a screen needs it, so a value an administrator adds or retires shows up without a release of the register. Labels stay the register's own translations; only the list of codes moves.",
  // ● FUNCTIONAL summary, ≤ 4 sentences / 700 chars: what a person can do afterwards and the rule
  // that decides it. May name up to three symbols. Never restates `intent`.
  "summary": "…",
  // Optional: what is explicitly in and out. Short phrases.
  "scope": { "in": ["the operator screens' code lists"], "out": ["the field document — stays in the register", "the register's own write-time validation (paused story)"] },

  // ● The plan's units in the plan's order — its stories, tasks or steps. 1–12.
  "units": [
    { "id": "15.1", "title": "A mock of the configuration component, on the laptop and in CI",
      "plain": "Developers and the test pipeline get a small fake of the platform service that answers exactly like it, from captured data, so nothing here needs the real cluster.",   // ● plain-first (error on a symbol in sentence 1)
      "detail": "…the mechanism, 1–3 sentences, symbols allowed…",     // optional
      "acs": [                                                          // the acceptance criteria AS WRITTEN, one entry each
        { "id": "AC1", "text": "Given the component's openapi.yaml at one pinned tag…", "plain": "optional: the same criterion in a sentence a stranger can read" }
      ],
      "touches": [                                                      // the files this unit will create / change / remove
        { "file": "dev/compose.yaml", "status": "changed", "note": "one more service" },   // status ∈ new | changed | removed | unchanged
        { "file": "dev/config-mock/server.mjs", "status": "new" }                           // a `new` file must NOT exist yet (warning if it does); every other status must exist (error)
      ],
      "depends_on": [],                                                 // unit ids
      "reviewers": "one reviewer; nothing in the protected categories",  // free text: who must review, and why
      "size": "S",                                                      // S | M | L
      "outside": ["read access to the platform repo for the drift job"]  // optional: what the unit needs from outside this repo
    }
  ],

  // Decisions the plan already carries — dated and attributed, so the page keeps them apart from
  // the open steering points. A decision with no `when` warns: an undated ruling is a claim.
  "decisions": [
    { "text": "The operator screen reads the component directly, through the edge — never the register as a middleman.", "by": "owner", "when": "2026-09-29", "source": "proposal §3" }
  ],

  // ● STEERING POINTS — the dual of findings. Ids S1, S2… (any severity). ≤ 3 critical (error),
  // ≤ 7 medium (warning). Each is a DECISION a person can make differently, not a doubt.
  "findings": [
    { "id": "S1", "severity": "critical",                              // critical = settle before work starts · medium = weigh · low = note
      "title": "Refresh is manual: an operator never sees a new code until they press refresh",
      "plain": "When an administrator adds a region, an operator with the screen already open keeps the old list until they refresh by hand. The plan chose that over polling.",   // ● plain-first
      "question": "Is a manual refresh acceptable on the record screen, or should a screen re-read its lists when it regains focus?",   // ● ONE question
      "current": "Manual refresh only; nothing polls (decision block, 'Versions')",           // ● what the plan says
      "alternative": "Re-read on window focus with If-None-Match — a 304 costs nothing when unchanged",   // ● the other answer
      "cost": "One query option and a test in the config package; no contract change.",       // what changing it costs (or not changing it)
      "why_human": "How stale a screen may be is a product call, not a technical one.",
      "file": "docs/planning/epics.md", "lines": "2467-2468",        // ● where the reader looks: a plan document or a code file; must exist
      "unit": "15.2",                                                  // optional
      "tags": ["product", "runtime"]                                   // free; become filter buttons
    }
  ],

  // Sketches of the planned shapes, in the project's own languages. Ids K1, K2…
  "sketches": [
    { "id": "K1", "unit": "15.2", "title": "A code value gains status, position, parents and aliases",
      "plain": "The register's idea of one code grows to match what the platform sends: whether it is retired, where it sorts, which parent it belongs to, and the other spellings other systems use for it.",  // ● plain-first
      "language": "TypeScript",                                        // one of meta.json → languages (warning otherwise)
      "file": "src/domain/schema.ts",                                  // ● the file the sketch is about
      "status": "changed",                                             // changed | new | removed
      "before": { "lines": "174-202" },                                // the real lines, checked against the file; or {"text": "…"} when quoting is not possible
      "after": "export const CodeValueSchema = v.object({\n  code: valueCode,\n  status: v.picklist([\"active\", \"retired\"]),\n  position: v.number(),\n  parents: v.array(ParentRefSchema),\n  aliases: v.array(ValueAliasSchema),\n});",   // the planned shape — types and signatures, never bodies
      "note": "optional: one sentence on what the sketch does NOT decide" }
  ],

  // Pictures — the shared toolset (../changes/reference/visualizations.md): screen | flow | adoption | datamodel.
  // `change` means "will be". A `datamodel` view whenever a stored or exchanged shape changes.
  "views": [
    { "kind": "datamodel", "title": "What one code holds — today and after", "narrative": "…",
      "entities": [ { "id": "CodeValue", "label": "CodeValue", "change": "modified", "file": "src/domain/schema.ts", "lines": "174-178",
                      "fields": [ { "name": "code", "type": "string", "change": "unchanged" },
                                  { "name": "active", "type": "boolean", "change": "removed", "note": "becomes status" },
                                  { "name": "status", "type": "'active' | 'retired'", "change": "added" } ] } ],
      "relations": [ { "from": "CodeValue", "to": "ParentRef", "kind": "has-many", "label": "parents", "change": "added" } ] }
  ],

  // ● The before/after map. Same shape as the changes report; `change` means "will be".
  // node.kind adds `service | system | external` (a hexagon) for the things outside this repo.
  "graph": { "narrative": "…", "nodes": [ { "id": "edge", "label": "Envoy edge", "kind": "service", "change": "modified", "file": "dev/envoy/envoy.yaml" } ], "edges": [] },

  "invariants": ["A record stores the code string and nothing else about a code list — nothing persisted changes."],   // what stays the same
  "assumptions": [                                                     // each with how it was checked
    { "text": "The component's contract is identical at tags 0.5.0 and 0.6.0.", "checked_by": "measured", "note": "byte-compared on 2026-09-29" }   // measured | read | assumed
  ],
  // How you will TRY it once each unit lands — future tense, one card per unit a person can drive.
  "how_to_check": [
    { "id": "V1", "unit": "15.2", "feature": "A retired code still shows on an old record", "surface": "ui", "where": "/persons/{id}",
      "steps": ["Retire a value on the component.", "Open a record that holds it."], "expect": "The label shows, marked retired; the filter no longer offers it for new data." }
  ],
  // ONE line of judgement over citations.json, shown at the top of the Grounding section: what the red
  // rows ARE — a typo in the plan, files in another repository, things the plan creates. The rows are
  // mechanical; this is the sentence a reader needs in order not to work it out from them.
  "grounding_note": "All 4 missing paths are in other repositories; the 9 unknown identifiers are platform names the plan introduces. No typo.",
  "people": [ { "who": "platform team", "role": "loads the eight missing tables; routes the path on the cluster", "needed_for": "15.3" } ],
  "glossary": [ { "term": "snapshot", "plain": "one whole code table as it is at one moment, with a version number" } ]
}
```

Rules the validator enforces: `kind == "plan"`; `plain` opens on no symbol (error) and runs 1–5
sentences; ≤ 3 critical steering points (error), ≤ 7 medium (warning); every steering point has
`title`, `plain`, `question`, `current`, `alternative`, `why_human`, `file`; ids unique, `S<n>` for
steering points, `K<n>` for sketches, `V<n>` for try-it cards; every `file` exists in the tree
except a `new` touch or sketch; a sketch's `before.lines` lies inside the real file; `assumptions[].checked_by`
∈ `measured | read | assumed`; view kinds from the shared toolset; every graph edge names a node.
Prose caps mirror the changes report: `title` ≤ 130 (error) / ≤ 80 (warning); a `plain` on a card
≤ 2 sentences and ≤ 300 chars (warning); `question` asks exactly one thing (warning).
