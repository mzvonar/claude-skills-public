# describe — the plan before the work, the change after it, for a human to judge

Two Claude Code skills for the person in the loop. Neither reviews code for you (CodeRabbit,
`/code-review` and friends do that); both allocate a human's attention instead of dumping a document
on them, and both render in chat and as a mobile-first HTML report that takes comments anywhere.

| | `/describe:plan` | `/describe:changes` |
|---|---|---|
| when | BEFORE anyone implements — an ad-hoc plan, a story or task spec, a change proposal, an epic | AFTER an agent implemented a task, before a human signs it off |
| the reader's question | "is this the right direction, and what would I change before we start?" | "is my signature on this honest?" |
| what it shows | plain words on what will be different for a person, a before/after map and data-model view, code sketches in the project's own languages (types, signatures, endpoints, ports, components), the acceptance criteria, what stays the same, assumptions with how each was checked, how you will try it, and the few **steering points** to settle first — each with the plan's answer, the alternative and its cost | intent + summary, phases, a call/data-flow map, the ~3 **findings** a human must verify, noise folded away, how to check, what moved since the last reading |
| grounded in | every path and symbol the plan names, checked against the repository; sketches quote the code as it is today | the diff, classified and folded |
| skill dir | `skills/plan/` | `skills/changes/` |

```
plan:     plan text in → ground it against the tree → plain words + map + sketches + steering points → Q&A → the plan is steered
changes:  diff in → fold the noise → phases + visual map → the ~3 things a human must verify → Q&A → feedback → sharper skill
```

Until 2.0.0 this plugin was `describe-changes` with one skill of the same name. The rename is the
only breaking change: reinstall as `describe` (below) and call `/describe:changes` where you called
`/describe-changes:describe-changes`. Output directories (`.describe-changes/`), the lessons store
(`~/.describe-changes/`) and the `DESCRIBE_CHANGES_HOME` variable keep their names, so nothing a
reader already has moves.

## What the changes report shows

- **What was done and why** — summary judged against the task's intent, plus the author's confession
  (the spots the agent was unsure about).
- **How it was built** — 2–6 phases in dependency order, not file order.
- **Map of the change** — mermaid graph: who calls whom, where data flows, what was moved / split /
  renamed (colour-coded by change kind). Views beside it: `screen`, `flow`, `adoption`, `datamodel`.
- **What a human must check** — critical (≤ 3, hard cap) / medium / low cards, each a *question the
  reviewer can answer* with the code snippet one tap away. Over-flagging is treated as the cardinal
  sin: credibility is the only currency.
- **Where the code parts company with the codebase** — a structural divergence from a written rule
  or from what every neighbouring file does ranks critical, because it propagates and only a human
  can call it direction or mistake. It must cite the rule (or two neighbours) it contradicts;
  `conventions.txt` collects the candidates and the validator rejects an uncited one as taste.
- **Folded as noise** — a **vendored subtree** proven to be the upstream it names (the review
  question is the pin, not the thousands of copied lines). A copy that differs from its pin is never
  folded and says so. When the pin arrives in the same diff, every value in it is the author's own
  word — hash and `origin` alike — so two things must hold before anything folds: the origin must be
  one the BASE ref already carries (an earlier review accepted it), and the bytes must re-derive
  from that origin at the pinned commit via a shallow fetch. A **first** vendoring has no accepted
  origin yet and is read in full, as is any change that repoints `origin` — deliberately, because
  adopting an upstream is a human decision. Also pure renames with their import rewrites nested
  under them, moves, splits, whitespace/format-only hunks, comment-only hunks, lockfiles, generated
  files, snapshots, prop threading (with a flow of the components the prop passes through), index
  rows for files the change adds, and working notes (plans, handoffs, journals — never an ADR, wiki
  page or changelog).
- **Everything else** — the honest list of substantive files that got no flag, each with a ⚑ gut-flag
  button ("something feels off here — dig in").
- **Since you last read this** — a report is read again after the fixes land, and the second reading
  asks a different question. Every render snapshots the report; the next one opens with what moved:
  findings resolved / added / re-rated, checks re-written (so un-ticked), the commits in between.
  The same delta is also a page of its own (`delta.html`, plus one per earlier snapshot): a real
  report over the code between the two readings — its own diff, map, folds — because each snapshot
  freezes the worktree on a private git ref. Pick any earlier reading to diff from.

The skill then stays in Q&A mode, and every question, ▲▼✕ vote, note and gut-flag is recorded so the
skill can be recalibrated — locally by default, team-wide via a pluggable backend.

Design source: a brainstorming session (2026-05-26) and `review-tool-elevator-pitch.md`
(ownership-transfer north star, attention budget, credibility constraint, human-points/AI-investigates,
divergence scoring).

## What the plan report shows

- **In plain words** — three to five sentences a person outside the team can read: what will be
  different for someone, and why. Every card on the page opens the same way, with the mechanism
  underneath it.
- **Views and map** — the same toolset as the changes report, where a colour means "will be": a
  before/after map of what goes where, and usually a `datamodel` view of the shapes that change.
- **Steering points** — the dual of findings, with the same budget (≤ 3 to settle first): a decision
  the plan made that a person could make differently, its current answer, the alternative and what
  changing it costs. Decisions already made render apart, dated, so nobody re-litigates one by accident.
- **How it will be built** — the plan's units (stories, tasks, steps) with their acceptance criteria,
  the files each touches (`new / changed / removed`, each opening the file as it is today), who
  reviews, what it depends on.
- **Sketches** — the planned shapes in the project's own languages: the lines as they are today,
  with real line numbers, and the planned lines beneath them. Types and signatures, not bodies.
- **What stays the same**, **Assumptions** (each `measured`, `read` or `assumed`), **How you'll try
  it**, **Who else is involved**, a **glossary**, and **Grounding** — every path and symbol the plan
  cites, found or not.
- **As written in the plan** — the plan's own acceptance criteria and open questions, word for word:
  any heading or bold label so named, whatever tool wrote the plan (`## Acceptance Criteria`,
  `**Acceptance Criteria:**`, `## Open questions for T2`, …; a repo adds its own names under
  `describe.plan.verbatim`). Every line keeps its number in the plan file and takes a comment there.
- Two levels, each fronted by a band: the **5-minute version** — the plain words, the pictures and
  the steering points — then **the detail**, whose band is also a fold: open by default, one tap
  shuts it (remembered per repo), and any link into it (the table of contents, a hash) unfolds it.
  There is no mode to switch. The plan's own words, when it has any, sit between the two in a band
  and fold of their own.

Verdicts on a steering point (▲ settle first · ▼ fine as is · ✕ not a decision · ✓ keep) and
comments on anything come back to the session, which drafts the amendments to the plan documents
and edits them only when told to.

## Layout

```
skills/changes/
  SKILL.md                  the procedure (what the model does, step by step)
  VERSION
  reference/analysis-guide.md   severity rules, credibility budget, tags, divergence lens
  reference/report-schema.md    report.json — the LLM ↔ renderer contract
  reference/visualizations.md   the view toolset: screen, flow, adoption, datamodel (shared with plan)
  reference/learning-loop.md    feedback channels, local/shared store, maintainer workflow
  scripts/collect-diff.sh       range resolution → raw.diff, numstat, commits, meta.json,
                                conventions.txt (rules + neighbours governing the changed paths), then ↓
  scripts/classify-diff.py      deterministic noise pass → diff-model.json + substantive.diff
  scripts/check-report.py       validates report.json (budget, ids, file refs, graph)
  scripts/render-report.py      report.json → index.html (mobile-first, mermaid map, snippets)
  scripts/views.py              the view renderers + the mermaid map builder — SHARED with plan
  scripts/serve.py              HTTP server (LAN + Tailscale URLs) + POST /feedback capture — SHARED
  scripts/feedback.py           lessons store: ingest / question / outcome / push / digest / export — SHARED
  scripts/snapshots.py          every version of a report + what changed between two of them
  scripts/report_keys.py        content hashes that keep a finding/check identifiable across re-renders — SHARED
  scripts/highlight.py          render-time syntax lexer — SHARED
  assets/template.html          CSS + JS shell (collapse, filter, feedback, comments, mermaid loader) — SHARED
skills/plan/
  SKILL.md                  the procedure for a plan
  VERSION
  reference/plan-schema.md      report.json for a plan — the LLM ↔ renderer contract
  reference/analysis-guide.md   steering points, plain words, sketches, grounding
  scripts/collect-plan.py       inputs (files, headings, an epic, a story) → plan.md, sources/, meta.json,
                                structure.json, citations.json (every cited path and symbol, checked)
  scripts/check-plan.py         validates the plan report (plain-first, budget, sketches against the tree)
  scripts/render-plan.py        report.json → index.html, through the changes skill's shell and views
  assets/plan.css               the plan page's own styles, injected into the shared shell
tests/run.sh                    smoke test of every script on a synthetic repo (no LLM); plan.sh is its plan half
```

"SHARED" means the plan skill imports it from `../changes/scripts/` — one copy, one plugin, so the two
skills cannot drift apart. Scripts are Python 3 stdlib + git only. The HTML needs internet for the
mermaid CDN; the map falls back to a text list without it.

## Install

```
/plugin marketplace add mzvonar/claude-skills-public
/plugin install describe@claude-skills-public
```

Then, once per consumer repo, add `.describe-changes/` to its `.gitignore` (report + feedback output
is written into every repo you run either skill on; the plan skill writes under `.describe-changes/plan/`).

Coming from `describe-changes`: `claude plugin uninstall describe-changes@claude-skills-public`, then
the install above, and replace `/describe-changes:describe-changes` with `/describe:changes` in any
repo instructions. Both installed at once would register the same skill twice under two names.

### Dev mode — iterate on the skills while using them on real repos

Work in a checkout of the marketplace and load the plugin from the working tree:

```bash
git clone git@github.com:mzvonar/claude-skills-public.git "$DC"
bash "$DC/plugins/describe/tests/run.sh"        # verify before trusting it on a real diff or plan
cd <consumer-repo> && claude --plugin-dir "$DC/plugins/describe"
```

Edits are live on the next invocation. Nothing about the skill is committed to the consumer; do not
copy it into a consumer's `.claude/skills/` (a project-level copy silently shadows the plugin).

It works because `scripts/collect-diff.sh` and `collect-plan.py` resolve the target repo from the
**cwd** (`git rev-parse --show-toplevel`), not from the script's own location. The lessons store is
machine-global (`~/.describe-changes/lessons.jsonl`), with every event tagged `repo`, so several
consumers feed one log and `feedback.py digest --repo <name>` still separates them.

Loop: edit `skills/changes/…` or `skills/plan/…` → `bash tests/run.sh` → run the skill in a consumer
repo → `feedback.py digest` → bump `VERSION` (both skills) + the plugin version → commit + push.

Caveat: `VERSION` is a static string, so lessons collected across an iteration session all carry the
same `skill_version` and the digest cannot attribute one to a specific edit. Bump `VERSION` when a
change is worth telling apart.

## Use

```
/describe:changes                      # branch vs default branch (+ working tree), or working tree on main
/describe:changes HEAD~3               # any git diff args
/describe:changes --staged --task "…"  # with explicit intent
/describe:changes main --story docs/stories/3-2-story.md
/describe:changes --chat-only          # no HTML (phone-only session)

/describe:plan --from docs/plans/search.md               # a plan document, whole
/describe:plan --from docs/epics.md#"Epic 15"            # one heading's subtree (regex: #re:…)
/describe:plan --epic 15                                  # the epic assembled from the configured planning files
/describe:plan --story 15-2                               # a story spec from the configured stories dir
/describe:plan                                            # the plan the conversation just made (written to a file first)
```

Both also trigger on their own: the changes skill after the agent implements a story/task ("walk me
through what you changed", "what should I review"), the plan skill before it ("walk me through the
plan", "what are we going to build", "review the plan").

Output lands in `<repo>/.describe-changes/<branch>/` for a change and
`<repo>/.describe-changes/plan/<slug>/` for a plan (`report.json`, `index.html`, `feedback.jsonl`, the
sources and grounding files). The server prints LAN and Tailscale URLs for the phone; it binds
`0.0.0.0` because a phone cannot reach a loopback bind, so every request is gated on a token minted
per run and printed inside those URLs (the first open sets a cookie for the rest of the session).
`--token T` pins it, `--no-token` serves openly for a trusted setup. A plan report serves on 8791 by
default, so it can sit beside a changes report on 8790.

## Learning loop

See `skills/changes/reference/learning-loop.md`. Short version:

```bash
python3 skills/changes/scripts/feedback.py digest     # what humans disagreed with, what they asked
```

→ edit `reference/analysis-guide.md` → bump `VERSION` → `bash tests/run.sh` → commit + push (dev mode
is live immediately). Configure `~/.describe-changes/config.json` with an HTTP backend to pool lessons
across a team. Plan reports feed the same store: a steering point's verdicts arrive as the same
`more / less / noise / checked` events a finding's do.

## Tests

```bash
bash tests/run.sh
```
