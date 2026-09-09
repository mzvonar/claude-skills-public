---
name: showcase
description: >-
  Record and view a human-paced video + captioned screenshot walkthrough of a working feature,
  layered on the repo's existing Playwright e2e harness (same auth, page objects and seed helpers).
  Produces a self-contained `docs/showcases/<feature>/index.html` with the video and a captioned
  screenshot grid, verified frame by frame for error overlays and silent console errors, and served
  on the LAN for reviewers. Use when the user says "record a showcase for <feature>", "make me a
  feature showcase video", "show me <feature> working end to end", "generate the showcase page",
  "prove the feature works", or invokes `/workflow:showcase`. Bootstraps the vendored harness into the e2e
  package on first use. Optional tutorial mode turns retained specs into subtitled help videos.
  Never a regression suite, never in CI.
---

## Purpose & scope

- Records a slow-mo, narrated screenshot + video walkthrough of a working feature. Output:
  `<outDir>/<feature>/index.html` (default `docs/showcases/<feature>/index.html`). Disposable —
  safe to delete after viewing; the spec file is what gets committed.
- Layers on the **existing** Playwright e2e harness — same stack wiring, same auth setup, same
  page objects and seed helpers. It is NOT a parallel test stack.
- Separate from CI and the e2e projects; **never gates a pipeline**. Regression detection stays in
  the e2e suite (your repo's e2e authoring skill, if any). Rendered artifacts are gitignored; the
  spec FILE is committed.
- Do NOT use for regression testing; do NOT modify the e2e Playwright config or any e2e project for
  showcase purposes.

## Zero-config defaults

Everything below works with no configuration:

- **package manager** — from the lockfile in the repo root (`pnpm-lock.yaml`, `yarn.lock`,
  `bun.lockb`, `package-lock.json`), else npm.
- **e2e directory** — the first of `e2e/`, `test/`, `tests/e2e/` that holds a Playwright config;
  the harness is bootstrapped there.
- **frontend URL** — `FRONTEND_BASE_URL` if set; else `http://localhost:<port>` where the port is
  `ports.frontend`, then `PORT` in `.env.local` / `.env`, then `-p`/`--port` in the `dev` script,
  then 3000.
- **run command** — `<pm> showcase <feature>` when the e2e package has a `showcase` script, else
  `node <e2eDir>/scripts/run-showcase.mjs <feature>` (equivalently
  `<pm> exec playwright test --config <e2eDir>/playwright.showcase.config.ts` without the report).
- **output** — `docs/showcases/<feature>/`, served on port 8899.

## Configuration

Per-repo overrides live in `.claude/claude-skills.json` under the `showcase` key. Every key is
optional. The runner reads them; the harness files receive them as `SHOWCASE_*` env vars.

| key | default | meaning |
|---|---|---|
| `outDir` | `docs/showcases` | Root for rendered reports; the feature folder goes inside (`<outDir>/<artifactNaming>/index.html`). Relative to the repo root. Gitignore it. |
| `command` | auto-detect (see above) | The command the skill runs to record; set when the repo wraps the runner differently. |
| `e2eDir` | auto-detect `e2e/`, `test/`, `tests/e2e/` | Where the harness lives / is bootstrapped. |
| `ports` | `{}` | Named ports: `frontend` (local dev server the browser opens) and `report` (LAN report server). `SHOWCASE_PORT` env overrides `report`. |
| `serverEnv` | `{}` | Env passed to the Playwright process and its `webServer` — your app's env for a hermetic run (test mode flag, auth URL pinned to the showcase host, test DB routing, `WEBSERVER_COMMAND`). Explicit env on the command line wins. |
| `backendMode` | `local` | `local`: Playwright boots the local frontend against the backend the e2e suite uses. `remote`: nothing is booted; the browser opens the deployed frontend at `FRONTEND_BASE_URL`. |
| `artifactNaming` | `<feature>` | Per-feature folder name; `<feature>` and `<date>` are substituted. |
| `tutorialMode` | `false` | Treat specs as retained tutorial recorders (see **Two kinds of spec**). |

```json
{
  "showcase": {
    "e2eDir": "tests/e2e",
    "ports": { "frontend": 3100, "report": 8899 },
    "serverEnv": { "APP_MODE": "test", "AUTH_URL": "http://localhost:3100" },
    "backendMode": "local"
  }
}
```

## The harness ships with this skill — bootstrap on first use

The showcase layer (fixture, config, runner, report renderer) is **vendored under this skill's
`harness/` directory** — a working implementation, not a spec to build from scratch. The live copy
runs from the e2e package; the skill copy is the bootstrap template.

If the e2e directory has no showcase harness yet when this skill is invoked, bootstrap it:

1. Copy the harness into the e2e package, preserving layout (`<skill>` is this skill's directory,
   `<e2eDir>` the detected or configured e2e directory):
   ```bash
   cp -R <skill>/harness/showcase <e2eDir>/showcase
   cp -R <skill>/harness/scripts  <e2eDir>/scripts
   cp    <skill>/harness/playwright.showcase.config.ts <e2eDir>/
   ```
2. Add the runner script to the e2e package's `package.json`:
   `"showcase": "node scripts/run-showcase.mjs"`.
3. Add `<outDir>/` (default `docs/showcases/`) to the root `.gitignore` — rendered artifacts are
   never committed; spec files are.
4. **Resolve every `ADAPT:` marker in the copied files.** The markers are the harness's
   configuration mechanism: each is a seam where the generic harness meets *your* e2e suite. They
   live only in `playwright.showcase.config.ts` and `showcase/helpers/entry.ts`:
   (a) layer over the e2e base Playwright config once it exists (never fork it);
   (b) the frontend URL fallback, if the detected one is wrong;
   (c) wire the e2e auth setup project into `dependencies:` and its storage state into
   `use.storageState` — reuse the e2e login, never hand-roll one;
   (d) the `webServer` entry — the local frontend boot command, plus any sidecar the feature
   needs (a job runner, a mail catcher);
   (e) merge the e2e suite's extended `test` (page objects, seed helpers) into `entry.ts`.
5. The fixture, `paths.ts`, `speed.ts`, `report.mjs` and `run-showcase.mjs` need no changes —
   they resolve paths from their own location and the enclosing git repo, so cwd does not matter.

If the harness already exists in the e2e directory, use it as-is — do not re-copy over local
adaptations.

### Divergence policy: the e2e copy is authoritative, sync e2e → harness

Once bootstrapped, the **copy under the e2e directory is the authoritative one**: it is the copy
under the repo's lint/format gates; the skill's `harness/` tree is outside their scope. Sync
direction is **e2e → harness**, never the reverse. After changing a shared file in the e2e copy —
`showcase/helpers/showcase.ts`, `speed.ts`, `paths.ts`, `showcase/report.mjs`,
`scripts/run-showcase.mjs`, `showcase/specs/example.showcase.ts` — copy it over the matching
`harness/` file if the repo keeps a local copy of the skill. The two ADAPT templates
(`playwright.showcase.config.ts`, `showcase/helpers/entry.ts`) differ from their e2e counterparts
by design: port mechanical lint/format fixes to them while keeping their ADAPT seams.

## How the app runs during a recording

Two run modes, chosen per feature with `backendMode` (or per run by setting `FRONTEND_BASE_URL`):

### Mode `local` (default) — local frontend + real backend

Playwright boots the frontend dev server via the config's `webServer` entry (command from
`WEBSERVER_COMMAND`, default `<pm> run dev`; an already-running server on that URL is reused) and
points it at the backend the e2e suite uses — a compose stack, a shared dev backend, a mocked API,
whatever the e2e config already does. This records **un-deployed frontend code against real
services**. Boot only what the feature needs: if the repo is several apps, start the one app that
owns the feature.

```bash
FRONTEND_BASE_URL=http://localhost:3101 WEBSERVER_COMMAND="<pm> --filter admin dev" <pm> showcase roles
```

### Mode `remote` — deployed frontend

Nothing is booted. The browser opens the deployed frontend at `FRONTEND_BASE_URL`; the e2e auth
setup logs in against it. Right when the feature is already deployed and you just want to prove it.

### Hermetic runs

Showcases must be hermetic — every recording starts from a known state, same as e2e. Reusing data
across runs accumulates fixtures, contaminates screenshots and produces non-reproducible
recordings. Two levers, both borrowed from the e2e suite:

- **Reset the same way e2e does.** Wire a `globalSetup` that calls the e2e suite's reset routine
  against the database the showcase server actually reads (which may differ from the e2e test DB
  — pass the connection explicitly rather than trusting an env default). Truncate every test-data
  table in dependency order; do not scope the wipe to a naming prefix, which leaves strays.
- **Seed through the e2e helpers**, or through a test-only seed/session endpoint if your app has
  one. If such an endpoint enforces a test-account naming pattern, honour it in specs. Read the
  feature's e2e spec for the exact seed shape rather than guessing.

Pin **every** required server env var in `serverEnv` / the config's `webServer.env` — a fresh
checkout's `.env` ships secrets empty, and a dev `.env` often points auth at a remote host. Session
validation must match the showcase host: pin the auth URL to `http://localhost:<port>` for the
hermetic server, or protected routes redirect to sign-in mid-recording. Leave optional vars absent
rather than empty. When a feature adds a required var, add it to the showcase env in the same
change.

**Sidecars**: if the feature fires a background job, sends mail, or pushes events, the showcase
must run that sidecar too (a second `webServer` entry). Forgetting it is the #1 cause of "the
showcase looks fine but the feature is broken" — the action returns success and the toast fires,
but nothing was listening.

Auth: reuse the e2e harness's auth/storage-state setup. If a run redirects to login, refresh the
stored auth state via the e2e setup project and retry.

## Commands

| Command | Effect |
|---|---|
| `<pm> showcase <feature>` | Record `<feature>.showcase.ts`; write `<outDir>/<feature>/index.html` |
| `<pm> showcase <feature> +50%` | 1.5× pace (less slowMo, shorter pauses) |
| `<pm> showcase <feature> -30%` | 0.7× pace |
| `<pm> showcase <feature> --speed=2` | explicit 2× pace |
| `<pm> showcase <feature> --no-cursor` | disable the DOM pseudo-cursor overlay |
| `<pm> showcase <feature> --headed` | watch the run live (extra flags are forwarded to `playwright test`) |

- `<feature>` is matched by **basename substring** against `showcase/specs/**/*.showcase.ts`.
- Speed is clamped to `[0.1, 3.0]`; both `slowMo` and `showcase.pause()` scale off it.
- After the run the report path, an `open "…"` command and the LAN URL(s) are printed.

## Two kinds of spec: feature showcase vs tutorial recorder

Everything in this skill is written for the **feature showcase**: a disposable, reviewer-facing
walkthrough named `<feature>.showcase.ts`, recorded against the dev server. With `tutorialMode:
true` the same harness also serves a **tutorial recorder** that produces published help videos.
The fixture always writes a `captions.json` v2 timing manifest (per-step `startMs`/`endMs`,
`rect`, `voiceover`, subtitle position) next to the video; in tutorial mode a caption burner of
your own turns it into a subtitled MP4 + `.vtt`. The differences that bite:

| | Feature showcase | Tutorial recorder (`tutorialMode`) |
|---|---|---|
| Filename | `<feature>.showcase.ts` | named for the help bundle it feeds |
| Build | dev server (fast) | production bundle **mandatory** — no dev badge, no cold-compile frames |
| Steps | as many as the feature needs | 3–6, matching the tutorial script 1:1 |
| Captions | English, reviewer-facing | telemetry; published subtitles come from the tutorial script at burn time |
| Fixture names | anything | role names only — it is published material |
| Output | `<outDir>` (gitignored) | burned MP4 + VTT + poster, wherever your help content lives |

In tutorial mode return the acted-on `Locator` from a step so its bounding box lands in
`captions.json` (subtitle placement), and pass `{ voiceover, subtitlePosition: 'top' }` when the
step's payoff sits in the bottom band. The `_raw/` folder is the only place `captions.json` exists,
so burn before the next recording of the same feature overwrites it.

## Creating a spec

1. **Name it** `<feature>.showcase.ts` under `showcase/specs/` — `<feature>` is the id passed to
   the runner. Copy `showcase/specs/example.showcase.ts` as the starting point.
2. **Pick the variant**: authenticated (the common case — inherits the e2e storage state) or
   unauthenticated (a sign-in flow — compose the showcase fixture with whatever mail/OTP fixture
   the e2e suite has via `mergeTests`).
3. **Import the showcase entry point** (`../helpers/entry`) so the spec gets both the `showcase`
   fixture AND the e2e page objects.
4. **Set up + tear down data via the e2e helpers.** Every showcase cleans up after itself
   (`afterAll`), same as e2e. Unique IDs; read the feature's e2e spec for the exact seed shape.
5. **Write each `showcase.step(caption, fn)` as one narrative beat.** Captions are English (they
   are for reviewers), even when the app UI is in another language. Use existing page-object
   methods and selectors — don't inline raw locators. Add 400–1000 ms `showcase.pause()` between
   scenes.
6. **Warm up routes**, then record.

### Skeleton — authenticated

```ts
import { expect, test } from "../helpers/entry";

test.describe("<Feature> — <title>", () => {
  test("happy path", async ({ page, showcase }) => {
    showcase.describe("1–3 sentences stating what the video proves.");
    // Pre-compile every route the spec visits so the video doesn't open on a blank frame.
    await showcase.warmup("/app", "/app/items");

    await showcase.step("Open the dashboard", async () => {
      await page.goto("/app");
      await expect(page.getByRole("heading", { name: /overview/i })).toBeVisible();
    });
    await showcase.pause(600);
    await showcase.step("Create an item", async () => {
      await showcase.click(page.getByRole("button", { name: /new item/i }));
      await showcase.type(page.getByLabel(/name/i), "Quarterly report");
      await showcase.click(page.getByRole("button", { name: /save/i }));
      await expect(page.getByText(/saved/i)).toBeVisible();
    });
    await showcase.step("See it in the list", async () => {
      const row = page.getByRole("row").filter({ hasText: "Quarterly report" });
      await showcase.scrollTo(row); // below the fold → scroll before the screenshot
      await expect(row).toBeVisible();
    });
  });
});
```

### Skeleton — unauthenticated (sign-in flow, needs a mail fixture)

```ts
import { mergeTests } from "@playwright/test";
import { expect, test as showcaseTest } from "../helpers/showcase";
import { test as mailTest } from "<e2e fixtures>/mail"; // whatever the e2e suite provides

const test = mergeTests(showcaseTest, mailTest);

test.describe("Sign-in", () => {
  test("happy path", async ({ page, showcase, mail }) => {
    showcase.describe("Passwordless sign-in: visitor types email, follows the link, lands authenticated.");
    const email = `showcase-${Date.now()}@example.com`; // honour your test-account pattern
    await showcase.warmup("/sign-in");
    await showcase.step("Open the sign-in page", async () => {
      await page.goto("/sign-in");
      await expect(page.getByLabel(/e-?mail/i)).toBeVisible();
    });
    await showcase.step("Request a link", async () => {
      await showcase.type(page.getByLabel(/e-?mail/i), email);
      await showcase.click(page.getByRole("button", { name: /send/i }));
      await expect(page.getByText(/check your inbox/i)).toBeVisible();
    });
    await showcase.step("Follow the link and land authenticated", async () => {
      await page.goto(await mail.waitForMagicLink(email));
      await page.waitForURL(/\/app(\/|$)/);
      await expect(page.locator("h1").first()).toBeVisible();
    });
  });
});
```

### Gotchas

- **Multi-actor walkthroughs = swap the page session mid-spec.** The fixture records a single
  `page`. To show actor A → actor B end-to-end, mint the next actor's session, clear cookies, add
  the new ones for the showcase host, and navigate — the same recorded page continues as the new
  actor. Warm routes once up front; compilation is per-route, not per-session.
- **Responsive dual layouts → strict-mode violations.** A table that renders both a desktop
  `<table>` and a mobile card layout makes `getByRole(..., { name })` resolve to two elements.
  Scope to the row first (`getByRole("row").filter({ hasText })…`), mirroring the e2e selectors.
- **Plural forms.** An e2e selector that asserts a count-interpolated string for *one* item will
  not match when the showcase seeds three. Match the plural-agnostic stem.
- **Stale build cache after a branch switch** can hang a route's on-demand compile indefinitely
  while the console sidecar stays empty (a pending request is silent). Clear the dev build cache
  or treat the first recording as a throwaway warm-up.
- **Seed helpers may require the target user to exist** before attaching roles; mint the session
  first, then attach.

## Warm up routes before recording (avoid the first-load blank screen)

A dev server compiles a route on first navigation, and a cold app fetches its chunks — either way
the first `goto` inside a recorded step can open on a blank/compiling frame for many seconds.
Pre-compile every route the spec visits BEFORE the recorded steps via `showcase.warmup(...)`: it
navigates each path with `waitUntil: 'networkidle'`, swallows per-path errors (an auth redirect
still triggers the compile), then resets to `about:blank`. Call it once, after `describe()`. Routes
reached only by in-app clicks compile on click; warm those too if their first appearance is blank.

## Human-look pointer motion (glide, dwell, type)

The fixture injects a DOM pseudo-cursor overlay — a dot that tracks the mouse plus a click-ripple
ring scaled to the recording pace. To make the pointer *watchable*, use the fixture's motion helpers
instead of raw locator actions wherever the viewer should be able to follow the mouse:

- `await showcase.click(locator)` — glides the cursor from its last position along a curved, eased
  path, dwells briefly, then performs the real Playwright click (which fires the ripple).
- `await showcase.hover(locator)` — same glide + dwell, without the click.
- `await showcase.type(locator, 'text')` — motion-clicks the field, then types character by
  character at a natural cadence instead of `fill()`'s instant paste. NOT for native date/color
  inputs — their segmented editing needs `fill()`.

The glide is cosmetic and self-bounding: a missing or detaching target falls through to the real
action (which then fails with a proper timeout) instead of stalling the recording. Raw
`locator.click()` / page-object methods still work everywhere — reserve the motion helpers for the
beats the video is about.

### Cursor overlay

- Injected via `context.addInitScript`: a dot tracking `mousemove`, a pulse on `mousedown`;
  `pointer-events: none`, max z-index.
- Visible after `click/hover/dragTo/page.mouse.*`; NOT after `fill()/focus()` (no `mousemove`).
- Resets on navigation; re-arms on the next pointer action.
- Toggle: `--no-cursor` or `SHOWCASE_CURSOR=off`.

## Writing reliable steps (avoid blank screenshots)

- The fixture screenshots the instant `fn` returns — **no auto-wait**. `fn` must leave the page in
  the captioned state.
- `goto` + `waitForURL` resolves before paint → blank screenshot. Every screen-changing step needs
  one of: `expect(...).toBeVisible()`, `waitForLoadState('networkidle')`, or `waitForResponse(...)`.
  URL-only assertions also pass on an error overlay at the same URL.
- **Scrolling:** if the target is below the fold, `await showcase.scrollTo(locator)` inside the
  step before returning — scroll into view, then wait a frame so the screenshot settles.

### Async-pipeline results — poll, don't seed, and poll out of frame

When the payoff arrives via a background job (a notification, a state push, a digest), the showcase
stack runs the real pipeline (see **Sidecars**), so show the real result — don't fake it by
inserting the row directly; in a fast environment the real pipeline often wins the race and a
direct insert then doubles the row. The result is eventually consistent, so:

- **Do the readiness poll in a NON-RECORDED pre-step**, not inside a recorded `step()`: a
  `.toPass()` reload-poll inside a recorded step captures every blank reloading frame and half the
  video is white. Poll out of frame (an API count, a DB query, or
  `expect(async () => { await page.reload(); await expect(x).toBeVisible() }).toPass()`), then
  warm the routes, then record steps that run on an already-populated app.
- **Give the per-test timeout real headroom.** A slow-mo multi-actor walkthrough plus a poll
  blows past Playwright's default 30 s; the failure reads "Test timeout exceeded", not your
  `.toPass` timeout. The harness config sets `timeout: 240_000` for this reason.

## Post-run verification (MANDATORY)

A green Playwright run ≠ the feature works. After the recording:

1. **Read every PNG** in `<outDir>/<feature>/_raw/<run>/shots/*.png` with the `Read` tool.
2. Scan for: framework error overlays or stack traces; HTTP error pages (500/404); missing UI
   elements; untranslated i18n keys / raw `{variable}` placeholders; wrong auth state.
3. Cross-check each caption against the pixels, and against the feature's acceptance criteria.
4. **Inspect the console-errors sidecar** (`_raw/<run>/console-errors.jsonl` — one JSONL line per
   browser-side `console.error` / `console.warn` / uncaught `pageerror` / non-aborted
   `requestfailed`, anchored to the most recent screenshot via `afterStep`). Empty file = clean
   run. This catches *silent* runtime errors and failed XHRs that never surfaced a banner.

```bash
jq -c '.kind' <outDir>/<feature>/_raw/*/console-errors.jsonl | sort | uniq -c
jq 'select(.kind=="pageerror")' <outDir>/<feature>/_raw/*/console-errors.jsonl
```

## Reporting format

- If clean: "All N screenshots verified clean — no error overlays, captions match UI state."
- If issues found, report before declaring done, e.g.:
  ```
  ⚠ Showcase captured but has issues:
  Screenshot 04 (Open the item list):
    Problem: error overlay — "Cannot read properties of undefined (reading 'id')"
    Not a showcase bug — the feature is broken; the step's networkidle wait didn't catch it.
  ```
- Do NOT fix the underlying product bug from this skill — that's a separate task.
- **Every reply ends with the two printed lines**, copied verbatim from the runner's stdout (the
  report path and the `open "…"` command), plus the LAN URL. Do not paraphrase or relativize.

## Delivering the report

- **Auto-served on the LAN after every run.** The runner starts a static HTTP server over
  `<outDir>` on `ports.report` (default 8899; `SHOWCASE_PORT` overrides), detached so the one-shot
  command still exits, and prints `http://<lan-ip>:<port>/<feature>/index.html`. The port is
  reused across runs (a second bind harmlessly fails). Needs `python3`; if absent the runner
  prints the manual command. The server is best-effort and unmanaged — kill it with
  `pkill -f "http.server <port>"`.
- The report is a folder (`index.html` + `_raw/`), self-contained and openable directly.
- **Mobile / iOS:** iOS can't play the VP8 `.webm` Playwright records. `report.mjs` transcodes to
  H.264 MP4 when `ffmpeg` is on PATH and adds it as the first `<source>`, so in-page playback
  works on a phone; or send the `.mp4` directly. If the reviewer reaches the dev box over a VPN
  and Safari times out while the server answers locally, the VPN route on the phone is usually
  inactive — toggle it and check for the VPN badge before touching the server.
- Off-network reviewers: put a tunnelling tool (ngrok, a tailnet, …) in front of the same local
  server.
- **Stale video after re-recording** is the browser caching the `<video>` URL; the report appends
  `?v=<mtime>` to the source so the URL changes every re-record — check it did.

## Playwright truncates output-directory names

Playwright shortens long test-output directory names (`specs-my-long-feature-na-09cff-…`), so
any tool that locates a run by `basename.includes(fullKey)` fails on long spec names. Match on
progressively shorter prefixes and accept only a unique hit — truncation then resolves while
genuine ambiguity still errors. Prefer short feature ids.

## After viewing

1. `rm -rf <outDir>/<feature>` — discard the rendered report (artifacts stay gitignored).
2. **Keep the spec** if it documents a shipped feature or feeds tutorial mode; delete it if it was
   a genuine throwaway. Regression detection still lives in the e2e suite.

## Hard rules

- Showcase specs stay under `showcase/specs/` — never touch the e2e spec dirs.
- Never modify the e2e Playwright config or any e2e spec for showcase purposes; the showcase config
  is a layer over the base config.
- Never add showcase to CI.
- Never commit rendered artifacts under `<outDir>` (keep it gitignored).
- Every spec cleans up the data it creates (`afterAll`), same as e2e.
- Never skip post-run verification; never omit the final printed lines.
- Do NOT commit or push — the user does that.

## Troubleshooting

| Symptom | Fix |
|---|---|
| No spec found matching `<feature>` | The basename substring didn't match any `*.showcase.ts` — check `showcase/specs/`. |
| Run redirects to the login page | Stale auth state — re-run the e2e auth setup project and retry; in local mode also check the auth URL is pinned to the showcase host. |
| Local app has no data / API errors | The local frontend still needs a backend — point it at the one the e2e suite uses (mode `local`), or record the deployed app (mode `remote`). |
| App crashes at boot on missing env | A required server var is unset for the hermetic server — pin it in `serverEnv` / `webServer.env`. |
| Video blank / 0 bytes | The web server wasn't up before the first `step()` — raise `webServer.timeout` or start it manually first (a running server is reused). |
| First recorded frame is blank/compiling | Add the route to `showcase.warmup(...)` before the recorded steps. |
| Screenshot blank | `fn` returned before paint — end the step with `expect(...).toBeVisible()` or `waitForLoadState('networkidle')`. |
| Half the video is blank reloads | A reload-poll ran inside a recorded step — move it to a non-recorded pre-step. |
| Feature "works" on video but not in production | A sidecar (job runner, mailer) wasn't running — add it as a second `webServer` entry. |
| Wrong runs in the report | Delete `<outDir>/<feature>/_raw/` and re-record. |
| No mp4 / won't play on iOS | `ffmpeg` isn't installed — install it, then re-render with `node showcase/report.mjs <feature>`. |
| Route compile hangs after a branch switch | Stale dev build cache — clear it and re-record. |

---
To change this skill, do not edit this copy: use `/dev-tools:update-skill`, or see `docs/updating-skills.md` in `mzvonar/claude-skills-public`.
