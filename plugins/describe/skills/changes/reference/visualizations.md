# Visualization toolset — pick per change, or none

A picture earns its place only when it answers a question the prose can't. `report.views` is a
list; each item is one view. Choose 0–3. The mermaid `graph` is optional now — leave `nodes: []` to
hide the map (for React UI work it is usually the wrong lens; keep it for data/call flow in
services, daemons, pipelines).

| kind | Use when | Shape |
|---|---|---|
| **screen** | UI work: a component renders inside a screen, has slots, something fills them | Nested boxes: screen → region → slot → what fills it. Dashed box = a slot. Colour = new/changed/deleted. A deleted box with strike-through shows what the new thing replaced. |
| **flow** | The change is a *story*: X created → Y deleted → callers re-pointed → restyled → patched | Numbered step chain with ↓; `then` nests sub-steps under a step. |
| **adoption** | A shared thing was created/extracted and N places now use it; old things it replaces | Root box(es) → "used in" grid → "replaces" grid (struck-through). |
| **datamodel** | What is STORED or EXCHANGED changes shape: a type gains or loses members, an entity appears or goes, a relation moves. The reader's question is "what will we hold, and how does it hang together" — a call graph answers neither. | Entity cards, one row per field (`name · type` with the field's OWN `+ − ~` glyph), and a strip of relations beneath (`has-many`, `has-one`, `refs`, `extends`, `uses`). Colour = the entity's change; a field carries its own, so a type that gains two members and loses one reads as exactly that. |

Every block with a `file` renders a ⟨/⟩ chip that opens that file's changed code in a sheet —
the same hunks that appear under "Everything else". Prefer the file the reader would open.

The same four kinds draw a PLAN (`/describe:plan`), where `change` means "will be": there the chip
opens the file as it is today, and a `datamodel` view is the usual centrepiece.

```jsonc
"views": [
  { "kind": "screen", "title": "Accountant page — any firm or client route", "narrative": "…",
    "screen": { "label": "Accountant page", "change": "modified", "file": "src/app/[locale]/app/firm/(app)/layout.tsx",
      "children": [
        { "label": "AccountantPage shell", "change": "added", "file": "…/page-shell/accountant-page.tsx", "children": [
          { "label": "AccountantPageHeader", "change": "added", "file": "…/accountant-page-header.tsx", "children": [
            { "slot": "title", "label": "page title", "change": "unchanged" },
            { "slot": "meta", "label": "ClientDetailMeta", "change": "added", "file": "…", "note": "client-detail routes only" },
            { "slot": "bell", "label": "FirmHeaderBell", "change": "added", "file": "…" } ] },
          { "label": "page body", "change": "unchanged" } ] },
        { "label": "layout sticky header bar", "change": "removed", "file": "…/layout.tsx", "note": "replaced by the header above" } ] } },
  { "kind": "flow", "title": "How the header landed", "steps": [
      { "label": "AccountantPageHeader + AccountantPage created", "change": "added", "files": ["…"] },
      { "label": "five firm-level pages wired", "change": "modified", "then": [ { "label": "portfolio", "file": "…", "change": "modified" } ] },
      { "label": "layout header + HideOnClientDetailRoute deleted", "change": "removed", "file": "…" } ] },
  { "kind": "adoption", "title": "TransactionPickerShell", 
    "root": [ { "label": "TransactionPickerShell", "change": "added", "file": "…" }, { "label": "TransactionRow", "change": "added", "file": "…" } ],
    "uses": [ { "label": "TransactionPickerDialog", "change": "modified", "file": "…", "note": "owner manual pairing" } ],
    "replaces": [ { "label": "TransactionPickerDetail overlay", "file": "…" } ] },
  { "kind": "datamodel", "title": "What a code value holds", "narrative": "…",
    "entities": [
      { "id": "CodeValue", "label": "CodeValue", "change": "modified", "file": "src/domain/schema.ts", "lines": "174-178",
        "fields": [ { "name": "code", "type": "string", "change": "unchanged" },
                    { "name": "active", "type": "boolean", "change": "removed", "note": "becomes `status`" },
                    { "name": "status", "type": "'active' | 'retired'", "change": "added" },
                    { "name": "parents", "type": "ParentRef[]", "change": "added" } ] },
      { "id": "ParentRef", "label": "ParentRef", "change": "added",
        "fields": [ { "name": "tableCode", "type": "string", "change": "added" }, { "name": "code", "type": "string", "change": "added" } ] },
      { "id": "CodelistRelation", "label": "CodelistRelation", "change": "removed", "note": "parents replace it" } ],
    "relations": [ { "from": "CodeValue", "to": "ParentRef", "kind": "has-many", "label": "parents", "change": "added" } ] }
]
```

`change` ∈ added | modified | removed | moved | renamed | split | unchanged. Labels are what a user or
a reader would call the thing, not the export name, unless the export name *is* the thing.

Rules of thumb: a **screen** view for any change that adds/moves UI chrome; a **flow** view when the
commit list tells a story with a deletion in the middle; an **adoption** view for every extracted
shared component/hook/helper with ≥ 3 consumers; a **datamodel** view whenever a persisted or wire
shape changes — one entity with one changed field is a sentence, not a view. If a view would have
one box, don't make it.
