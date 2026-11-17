---
name: design-work
description: 'Work on how a UI looks and feels the way a design tool does: a fast edit → look → iterate loop with the user, a high design and UX bar, two or three labelled options when the direction is open, and a visual check after every change (screenshots at desktop and phone width, read by eye, plus an automatic layout lint for overflow, clipped or overlapping text, small tap targets, low contrast and console errors). Tests, mutation runs and full check suites run once, when the design is approved and about to be committed, pushed or released. Use this whenever the work will be judged by looking at it: "make it prettier", "polish", "fix the layout", "it looks off on mobile", "redesign the card", "make it unobtrusive", "use an icon instead", "match the design/mockup", spacing, colour, typography, alignment, icons, empty/loading states, a new UI control, responsive or dark-mode work, or a back-and-forth on look and feel. Use it even when the user does not say "design", and even for a one-line style change.'
---

# Design work

**Goal:** the user iterates on a UI with you the way they would in a design tool. Each round comes back in a minute
or two, looks right at a glance, and has been checked by eye before they see it. Taste, consistency and a working
layout are the product here, not a passing test suite.

Design work is any change to how a page looks or behaves under the user's hand: markup, styles, layout, copy on the
screen, icons, motion, the states of a control. A change to what is stored, sent or computed is not design work, even
when a design round asked for it (see "The gate").

## 0. Is this session reading the CURRENT skill text?

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-freshness.sh" "${CLAUDE_PLUGIN_ROOT}"
```

Local, no network, and **silent** unless something is wrong. Exit **3** — this session is serving
an older cached copy of THIS plugin than the one installed; a session pins its version at the first
call and never moves. Put it to the user (`AskUserQuestion`): reload (`/reload-plugins`) and re-run,
or carry on knowingly — and if you already put this question for this plugin in this session, just
note it and carry on; the check is stateless and will keep reporting. Exit **2** — could not
determine, which is not a pass. Exit **4**, or `No such file` / exit **127** — this call is wired
wrong and checked nothing; report it. Why: `docs/conventions.md` in `mzvonar/claude-skills-public`.

## 1. The round

Every round, small or large, is the same five steps. Do them yourself, in this session: a subagent turns one round
into several messages, and a message that lands late costs the user a whole round. Delegate only work that is not a
design round (a data migration, a test sweep at the end).

1. **Know what you are drawing.** For a tweak ("smaller", "an × instead of the word"), just do it. For a new surface
   or a direction that is genuinely open, ask two to four focused questions first, or show options (step 2 below)
   instead of asking. A question about taste is cheaper answered by two pictures than by prose.
2. **Read before drawing.** Open the neighbours of what you change and the design system the repo already has: tokens
   or theme variables, the component library, the closest existing control of the same kind (its size, colour, icon,
   spacing, hover). Your change should look like it was always there. When the user names a reference ("like the code
   comment's ×"), copy its actual values from the source, not your memory of them.
3. **Make the change.** Smallest edit that does it, in the design system's own terms: an existing component or
   token first, a new token second, a one-off value last and with a reason. Never escape the system to hit a pixel.
4. **Make it viewable.** Use the running dev server's hot reload, or the repo's build step for the page (a static
   build, a bundle the page serves). Know the exact URL the user will reload. Never restart a server the user is
   looking at without saying so, and never change its access token or port from under them: a page that silently
   stops working reads as your bug.
5. **Look at it — the visual check (§3)** — then report (§5).

## 2. When the direction is open: options, not a guess

A design tool shows variants side by side and lets the user pick. Do the same whenever two seniors could reasonably
choose differently (layout, emphasis, icon vs word, density):

- Build two or three **clearly different** options, labelled **A / B / C**, each with a one-line rationale. Not three
  shades of the same idea.
- Put them where the user can see them together: a scratch route or page, a story in the repo's component explorer,
  or one component behind a query parameter (`?variant=b`) — whatever the repo already has. Screenshot all of them in
  one visual-check run and show the screenshots.
- For a single value the user will want to dial (a size, a gap, a colour), show the value in two or three settings the
  same way rather than asking "how big?".
- When they pick, delete the losers and the scaffolding in the same round. A variant left behind is dead code.

## 3. The visual check — after EVERY change, before you report

This is the step a design tool ran for you after each edit and Claude Code does not, unless you do it. A round is not
done until **you have looked at it** — the check is your eye on the screenshots, judging them the way a designer
would. The script only does the mechanical half: it takes the screenshots at the right widths and points at the
problems geometry can prove, so your look starts with the likely suspects. A clean script run with screenshots nobody
read is not a check.

```bash
node "${CLAUDE_PLUGIN_ROOT}/skills/design-work/scripts/visual-check.mjs" <url> [<url> …] \
  --out <scratch dir>/shots [--selector '<css of the changed surface>'] [--label after]
```

Run it from the repo root (it uses the repo's own Playwright; `PLAYWRIGHT_MODULE` points elsewhere). By default it
shoots each URL at **1280 px and 390 px**, and lints the layout: sideways scrolling and the element that causes it,
clipped text, overlapping text, overlapping controls, tap targets under 24 px on a phone, text below WCAG contrast,
unnamed controls, images without alt, console and page errors, failed requests. Exit 1 lists what to look at; 0 means
the lint found nothing, which is **not** a pass by itself.

Then **read every screenshot yourself** (open each PNG with your file-reading tool; you see images) against the
checklist in
[references/visual-check.md](references/visual-check.md): alignment, spacing rhythm, a control pushed onto its own
line, a row that grew, an icon of the wrong size or weight, inconsistency with its neighbours, what happens with long
text and with no data. Fix what you find and run it again. Counting elements or "no console errors" is not a visual
check: a layout can be broken with every assertion green.

- Check every surface the change touches, not just the one you were asked about: a shared style reaches them all.
- Use a throwaway page, story or seeded data, never the user's real data, when the check would write anything.
- For a fix of something the user saw, shoot **before** the edit too (`--label before`) and compare the pair.
- Add 768 px when the layout has a tablet breakpoint, and `--color-scheme dark` when the app has a dark mode.
- If the page needs a login, pass `--storage-state` (a Playwright state file the repo's e2e setup writes) or a header.

## 4. The quality bar

[references/design-quality.md](references/design-quality.md) is the full checklist; read it before a new surface and
skim it before reporting. In one breath: hierarchy you can read in a squint; one spacing scale and one type scale;
edges that line up; the repo's own components, colours and icon set; every state designed (empty, loading, error,
long text, many items, disabled, hover, focus); targets at least 24 px and comfortable at 44 on a phone; text at WCAG
contrast; copy short, concrete and in the product's words; destructive actions confirm or undo; nothing that only
works on hover; motion small and purposeful; no generic "AI" decoration (gradients for their own sake, emoji as icons,
everything in a shadowed card, fake logos or photos instead of honest placeholders).

## 5. Reporting a round

Short, and in the user's words: what changed and where; the screenshots or their paths (show them inline when the
user is on a phone); which surfaces and widths you looked at; anything you found and fixed; the URL to reload. Say
plainly what you did not check (a width, a state, a browser). If something looks off and you are not sure it is
intended, ask with a picture rather than guessing.

## 6. The gate — once, at the end

While the design is still moving, do NOT run test suites, mutation sets, snapshot updates, full lint/type sweeps or
release checks: they pin behaviour and get redone every time the design moves, and they turn a two-minute round
into twenty. Run the whole gate **once**, when the user says the design is right and the change is about to be
committed, pushed or released:

1. Update the tests the design changed (prefer asserting meaning — `data-*` state, roles, text — over class strings or
   pixel values, so the next restyle does not break them), and run them.
2. Run the repo's full check (its CI entry point, `check-all`, `pnpm test` + lint + typecheck — whatever it has).
3. Do one last visual check of every touched surface on the final build.

Two exceptions run in the round itself: a change to what is **stored, sent or computed** gets its tests immediately (a
page that looks right and loses data is not a draft), and so does anything security-relevant.

## 7. Boundaries

- If the repo mirrors an external design source (a design-tool project, exported comps, Figma frames), that source
  belongs to the user. Edit the repo's copy as the repo's workflow says, but never write back to the external tool
  unless asked, each time.
- Never commit, push or release unless the user asks.
- A complaint about the process ("this used to take seconds", "why didn't you check it on a phone?") is feedback on
  how you work: change the loop, not just the pixel.

## Configuration

Optional, in the repo's `.claude/claude-skills.json` under `"design-work"`. Everything is detected first; set a key
only when detection is wrong.

| Key | Default | Meaning |
|---|---|---|
| `url` | the dev server: `svc` if installed, then `PORT` in `.env.local` / `.env`, then the `dev` script's `-p`/`--port`, then 3000 | Base URL the visual check opens. |
| `widths` | `[1280, 390]` | Widths every round is checked at. |
| `build` | none — hot reload is assumed | The command that makes a change viewable (a static build, a bundle step). Run after each edit. |
| `gate` | the repo's CI entry point, else its test + lint + typecheck scripts | The command(s) of §6, run once at the end. |
| `storageState` | none | A Playwright storage-state file for pages behind a login. |

## What a design tool did, and where it lives here

| In the design tool | Here |
|---|---|
| Live preview after each edit | §1 step 4: hot reload or the `build` step, and the exact URL to reload |
| A check of the result after each task (screenshots, console errors) | §3: `visual-check.mjs` + reading every screenshot |
| Options laid side by side on a canvas | §2: A / B / C on one page, screenshotted together |
| Tweaks (dialling a value) | §2: the value in two or three settings, shown together |
| Knowing the design system | §1 step 2: read tokens, components and the neighbours first |
| Comments pinned to an element | ask for a screenshot or the selector; read pasted images |
| A high bar for craft | §4 and references/design-quality.md |
| Fast rounds | §1 (no relay) and §6 (no gate until the end) |
