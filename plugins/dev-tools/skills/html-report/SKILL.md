---
name: html-report
description: Generates a polished dark-themed HTML code review report and opens it in the browser. Use this whenever producing or presenting a code review, security review, PR review, or any structured finding report — especially after /review, /security-review, or ultrareview, or when the user asks to "show results as HTML", "generate a report", or "present me the result". The report renders collapsible finding cards grouped by severity (Critical / Important / Suggestion), numbered reference codes (C1, C2, I1…) the user can cite back in conversation, copyable full-path file locations with line numbers for IDE navigation, and before/after code diffs.
user-invocable: true
allowed-tools: Bash(*), Write, Read
---

Produce a polished HTML report from a set of review findings and open it in the browser.

## Steps

**0. Is this session reading the CURRENT skill text?**

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-freshness.sh" "${CLAUDE_PLUGIN_ROOT}"
```

Local, no network, and **silent** unless something is wrong. Exit **3** — this session is serving
an older cached copy of THIS plugin than the one installed; a session pins its version at the first
call and never moves. Put it to the user (`AskUserQuestion`): reload (`/reload-plugins`) and re-run,
or carry on knowingly. Asks once per plugin per session. Exit **2** — could not determine, which is
not a pass. Exit **4** — this call is wired wrong and checked nothing; report it.

**1. Gather findings**

Collect all findings from the current review conversation. Group them into up to three severity buckets — Critical, Important, Suggestion — and number them within each bucket (C1, C2 …, I1, I2 …, S1, S2 …). Omit a section entirely if it has no findings.

**2. Write the body HTML to a temp file**

Write only the *inner content* (everything inside `<div class="page">`) to `<tmp>/<slug>-body.html`, where `<tmp>` is `$TMPDIR` if set, else `/tmp`.  
Choose `<slug>` as a short kebab-case label derived from the branch name, ticket, or topic (e.g. `auth-refactor`, `login-form`).

See **Body structure** and **Finding card** below for what to write.

**3. Combine with the template**

```bash
python3 - <<'PY'
import os, tempfile
template = "${CLAUDE_PLUGIN_ROOT}/skills/html-report/assets/template.html"
tmp = tempfile.gettempdir()
t = open(template).read()
b = open(f'{tmp}/<slug>-body.html').read()
title = '<Page Title Here>'
out = t.replace('__PAGE_TITLE__', title).replace('__BODY_CONTENT__', b)
open(f'{tmp}/<slug>-review.html', 'w').write(out)
print(f'{tmp}/<slug>-review.html')
PY
```

Replace `<slug>` and `<Page Title Here>` with actual values before running. The `${CLAUDE_PLUGIN_ROOT}` placeholder is expanded by Claude Code when the skill loads; if you see it unexpanded, substitute the plugin's install directory.

**4. Open and report**

```bash
open "<tmp>/<slug>-review.html"          # macOS
xdg-open "<tmp>/<slug>-review.html"      # Linux
```

Tell the user the report is open and give the file path so they can share or reopen it.

---

## Body structure

Write these elements in order inside the body file:

### Header
```html
<header>
  <h1>Code Review — [Topic]</h1>
  <div class="branch">[branch-name] &nbsp;·&nbsp; [ticket-id]</div>
</header>
```
Omit the `·` and ticket-id if not known.

### Summary bar
One badge per non-empty severity level, counts matching your actual finding totals:
```html
<div class="summary-bar">
  <div class="badge critical"><div class="dot"></div>2 Critical</div>
  <div class="badge important"><div class="dot"></div>3 Important</div>
  <div class="badge suggestion"><div class="dot"></div>4 Suggestions</div>
</div>
```

### Overview
2–4 sentences: what was reviewed, what's broadly good, and the main finding themes.
```html
<div class="overview">
  <strong>Overview.</strong> [Summary paragraph. Use <code>inline code</code> for identifiers.]
</div>
```

### Severity sections
One `<section>` per non-empty bucket:
```html
<section class="critical">
  <h2>Critical</h2>
  <!-- finding cards -->
</section>

<section class="important">
  <h2>Important</h2>
  <!-- finding cards -->
</section>

<section class="suggestion">
  <h2>Suggestions</h2>
  <!-- finding cards -->
</section>
```

### Footer
```html
<footer>
  Generated for <strong>[topic]</strong> &nbsp;·&nbsp; Claude Code review
</footer>
```

---

## Finding card

```html
<div class="finding open"><!-- use "finding open" for Critical; just "finding" for Important/Suggestion -->
  <div class="finding-header">
    <span class="severity-pill pill-critical">C1</span><!-- pill-critical / pill-important / pill-suggestion -->
    <span class="finding-title">[Title — may contain <code>inline code</code>]</span>
    <span class="chevron">▶</span>
  </div>
  <div class="finding-body">

    <!-- LOCATION (required) — single file -->
    <div class="location-row">
      <span class="location">path/from/project/root/file.ts:42</span>
      <span class="line-range">lines 42–58</span><!-- omit when single-line -->
    </div>

    <!-- LOCATION — multiple files (replace location-row with this) -->
    <div class="multi-location">
      <span class="location">src/foo.ts:10</span>
      <span class="location">src/bar.ts:25</span>
    </div>

    <!-- EXPLANATION (recommended) -->
    <p class="why">[Why this matters. Use <code>code</code> for identifiers, <strong>bold</strong> for key terms.]</p>

    <!-- BEFORE CODE (optional) -->
    <div class="label current">Current</div>
    <pre><code>[problematic code — escape &lt; &gt; &amp; inside pre/code]</code></pre>

    <!-- AFTER CODE (optional) -->
    <div class="label improved">Fix</div><!-- or "Better" for suggestions -->
    <pre><code>[improved code]</code></pre>

    <!-- EXTRA NOTE (optional) -->
    <div class="fix-note">[Additional context, caveats, or alternatives.]</div>

  </div>
</div>
```

### Label variants
| Class | Color | Use for |
|---|---|---|
| `label current` | orange | The problematic before-state |
| `label improved` | green | The fix or improved version |
| `label` (plain) | muted | Neutral labels ("Better", "Remove", "Example") |

### Marking a finding as fixed

Add `fixed` to the finding's class and insert a `<span class="fixed-badge">✓ Fixed</span>` between the title and the chevron. The card dims and gets a green border accent. Content stays visible for reference.

```html
<div class="finding fixed">
  <div class="finding-header">
    <span class="severity-pill pill-critical">C2</span>
    <span class="finding-title">[title]</span>
    <span class="fixed-badge">✓ Fixed</span>
    <span class="chevron">▶</span>
  </div>
  ...
</div>
```

### Code escaping
Inside `<pre><code>` blocks, always escape HTML special characters:
- `<` → `&lt;`
- `>` → `&gt;`
- `&` → `&amp;`

### Location path rules
- Use the **full path from the project root**, not just the filename — e.g. `apps/web/src/hooks/use-auth.ts:42`. This lets the user paste it directly into their IDE's "Open File" dialog to jump to the line.
- `:LINE` anchors to the **first affected line**.
- Put the line range (`lines X–Y`) in a separate `<span class="line-range">` *outside* the `.location` chip so it isn't included when the user copies the path.

---
To change this skill, do not edit this copy: use `/dev-tools:update-skill`, or see `docs/updating-skills.md` in `mzvonar/claude-skills-public`.
