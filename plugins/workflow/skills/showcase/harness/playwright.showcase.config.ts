import { defineConfig } from "@playwright/test";

import { slowMoForSpeed, speedFromEnv } from "./showcase/helpers/speed";

/**
 * Showcase config — a slow-mo, video-recording layer on top of the SAME stack,
 * auth setup, and storage-state the e2e suite uses.
 *
 * Differences from the e2e config:
 *  - `slowMo` so human-paced actions read on camera (scaled by SHOWCASE_SPEED).
 *  - `video: 'on'` — every run records.
 *  - Dedicated `showcase/specs` test dir + `*.showcase.ts` specs.
 *  - A narrower project set (auth setup + one showcase project), not the e2e matrix.
 *
 * `ADAPT:` markers are this file's configuration mechanism — each one is a seam
 * where the harness meets YOUR e2e suite. Resolve them once when bootstrapping;
 * everything not marked is generic and needs no change:
 *  1. Layer over the e2e base config (`import { baseConfig } from './playwright.config'`
 *     or wherever the shared base lives) and spread it into defineConfig / `use`
 *     below. Never fork the base config.
 *  2. `baseURL`: the runner passes `SHOWCASE_FRONTEND_URL` (config `ports.frontend`,
 *     else the detected dev port); `FRONTEND_BASE_URL` overrides it per run, e.g.
 *     to point at a deployed frontend. Change the last fallback if neither applies.
 *  3. Wire the e2e auth setup project into `dependencies:` and its storage-state
 *     file into `use.storageState` — reuse the e2e login, do not hand-roll it here.
 *  4. `webServer`: in `backendMode: local` (the default) Playwright boots your
 *     frontend dev server against whatever backend the e2e suite uses; in `remote`
 *     nothing is booted and the browser opens the deployed frontend at baseURL.
 */

// ADAPT: frontend URL fallback (see header, item 2).
const baseURL =
  process.env.FRONTEND_BASE_URL ||
  process.env.SHOWCASE_FRONTEND_URL ||
  "http://localhost:3000";

// `local` boots the frontend below; `remote` records a deployed one. Set via
// config `backendMode` (runner exports SHOWCASE_BACKEND_MODE).
const backendMode = process.env.SHOWCASE_BACKEND_MODE || "local";

// Clamp + slowMo derivation shared with the showcase fixture — the single
// implementation lives in showcase/helpers/speed.ts.
const slowMo = slowMoForSpeed(speedFromEnv(process.env.SHOWCASE_SPEED));

export default defineConfig({
  // Keep artifacts out of the e2e report/test-results trees.
  outputDir: "showcase/.pw-artifacts",
  projects: [
    // ADAPT: add the e2e auth setup project here and depend on it, e.g.
    // { name: 'auth-setup', testDir: '…', testMatch: /auth\.setup\.ts/ },
    {
      name: "showcase",
      testDir: "showcase/specs",
      // ADAPT: dependencies: ['auth-setup'],
    },
  ],
  // Narration-only reporter; the HTML report is produced by scripts/run-showcase.mjs.
  reporter: [["list"]],
  testDir: "showcase/specs",
  testMatch: /.*\.showcase\.ts/u,
  // Slow-mo walkthroughs plus warmup/poll blow past the default timeout — give real headroom.
  timeout: 240_000,

  // ADAPT: local frontend boot (see header, item 4). `WEBSERVER_COMMAND` (env or
  // config `serverEnv`) pins the command; the runner defaults it to `<pm> run dev`.
  // An already-running server on the URL is reused, so starting it yourself is fine.
  // Add a second entry here for any sidecar the feature needs (a job runner, a
  // mail catcher) — a feature that silently needs one records a degraded version
  // of itself without it.
  webServer:
    backendMode === "local"
      ? {
          command: process.env.WEBSERVER_COMMAND || "npm run dev",
          reuseExistingServer: true,
          timeout: 120_000,
          url: baseURL,
        }
      : undefined,

  use: {
    baseURL,
    launchOptions: { slowMo },
    // Video size pinned to the viewport: Playwright otherwise shrinks the
    // recording to fit 800×800, which blurs tutorial footage AND desyncs the
    // caption burner's rect-based subtitle placement (step rects are measured
    // in viewport pixels).
    video: { mode: "on", size: { height: 720, width: 1280 } },
    viewport: { height: 720, width: 1280 },
    // ADAPT: storageState from the e2e auth setup project (see header).
  },
});
