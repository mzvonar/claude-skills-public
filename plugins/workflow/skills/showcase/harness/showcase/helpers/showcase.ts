import fs from "node:fs";
import path from "node:path";

import type { Locator, Page, TestInfo, Video } from "@playwright/test";
import { test as base } from "@playwright/test";

import { featureFromSpecFile, showcaseRawDir } from "./paths";
import { speedFromEnv } from "./speed";

export { expect } from "@playwright/test";

/**
 * Playback speed multiplier. 1.0 = default pace, 2.0 = twice as fast (half the
 * slowMo/pause), 0.5 = half speed. Set by the runner from `--speed` / `+N%` flags.
 * The clamp and the matching `slowMo` derivation used by
 * `playwright.showcase.config.ts` live in `./speed` — one implementation, two
 * importers.
 */
const SPEED = speedFromEnv(process.env.SHOWCASE_SPEED);
const CURSOR_ENABLED = process.env.SHOWCASE_CURSOR !== "off";
const UNSAFE_SLUG_CHARS = /[^a-zA-Z0-9._-]/gu;

/**
 * The click ripple's CSS animation runs in real time while everything else in a
 * recording is stretched by 1/SPEED — an unscaled 450 ms pulse is proportionally
 * more fleeting at slow-mo pace and reads as "no click mark" to viewers. Scale it
 * with the recording pace.
 */
const RIPPLE_PULSE_MS = Math.round(450 / SPEED);

/** Dwell on the glide target before the real action fires (scaled by SPEED). */
const HOVER_DWELL_MS = 250;

export interface StepRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface StepRecord {
  order: number;
  caption: string;
  /** Relative path under the run dir. */
  shot: string;
  /**
   * Per-step timing relative to the recording epoch (captured at fixture start,
   * which coincides with the video start — Playwright begins recording when the
   * page is created, moments before the fixture body runs). A caption burner
   * (optional tutorial mode — see the skill) uses these to place subtitles at the
   * real step boundaries instead of splitting the video duration evenly.
   */
  startMs: number;
  endMs: number;
  /** Spoken-narration text (future TTS source) when it differs from the caption. */
  voiceover?: string;
  /**
   * Bounding box (VIEWPORT pixels) of the Locator the step fn returned — input
   * for subtitle placement (bottom-band avoidance) and future auto-zoom.
   * Best-effort: absent when the element detached before measurement.
   */
  rect?: StepRect;
  /** Force the burned subtitle band to the top/bottom of the frame for this step. */
  position?: "top" | "bottom";
}

interface ConsoleEvent {
  kind: "console.error" | "console.warn" | "pageerror" | "requestfailed";
  tsIso: string;
  afterStep: number;
  text: string;
}

/** Viewport the step rects were measured against. */
export interface CaptionsViewport {
  width: number;
  height: number;
}

/**
 * The captions.json v2 manifest — the producer/consumer contract between this
 * fixture and an optional tutorial caption burner (a tool of your own that turns
 * the recording into a subtitled MP4). `steps` is the canonical timed timeline;
 * `captions` is the same list under the v1 name for older consumers. `rect` is
 * captured in VIEWPORT pixels, but the encoded video frame can differ from the
 * viewport — a consumer deciding "is this in the bottom fifth?" needs the
 * frame the rects were measured against, hence `viewport`. This interface is the
 * producer-side contract; a consumer should pin the field names against a
 * fixture of its own (that check is repo-bound and deliberately not part of the
 * vendored harness).
 */
export interface CaptionsManifestV2 {
  version: 2;
  title: string;
  project: string;
  file: string;
  description: string;
  recordingStartedAt: string;
  finalizedMs: number;
  viewport: CaptionsViewport | null;
  video?: string;
  captions: StepRecord[];
  steps: StepRecord[];
}

/**
 * Build the captions.json v2 manifest. Pure and exported so the produced shape
 * is a compile-checked `CaptionsManifestV2` (pinned against the consumer
 * fixture — see the interface doc) instead of an untyped literal inside
 * `finalize()`.
 */
export const buildCaptionsManifest = (args: {
  description: string;
  file: string;
  finalizedMs: number;
  project: string;
  recordingStartedAt: string;
  steps: StepRecord[];
  title: string;
  video: string | undefined;
  viewport: CaptionsViewport | null;
}): CaptionsManifestV2 => ({
  captions: [...args.steps],
  description: args.description,
  file: args.file,
  finalizedMs: args.finalizedMs,
  project: args.project,
  recordingStartedAt: args.recordingStartedAt,
  steps: [...args.steps],
  title: args.title,
  version: 2,
  video: args.video,
  viewport: args.viewport,
});

/**
 * The `showcase` fixture: records a human-paced, captioned screenshot + video
 * walkthrough of a feature. One recorded `step()` == one narrative beat == one
 * screenshot with a caption in the final HTML report.
 *
 * Use the human-look motion helpers (`click`, `hover`, `type`) instead of raw
 * locator actions wherever the pointer should be watchable on camera.
 *
 * Reuse the e2e suite's real page objects by importing `test` from
 * `helpers/entry.ts` (which merges this fixture with the e2e fixtures), not from
 * here directly.
 */
export class Showcase {
  private readonly steps: StepRecord[] = [];
  private readonly consoleEvents: ConsoleEvent[] = [];
  private descriptionText = "";
  private order = 0;
  private readonly runDir: string;
  private readonly shotsDir: string;
  private readonly page: Page;
  private readonly testInfo: TestInfo;
  /** Last known pseudo-cursor position; seeds each glide. Lazily initialized. */
  private cursorPos: { x: number; y: number } | null = null;
  /**
   * Recording epoch for step telemetry. Playwright's video starts when the page
   * is created (in the `page` fixture, moments before this constructor runs), so
   * step times relative to this epoch map ~1:1 onto the video timeline. The
   * probed video DURATION overshoots the last step's endMs by seconds of
   * teardown tail; that surplus is not a start offset.
   */
  private readonly recordingEpochMs = Date.now();

  /**
   * Snapshotted at construction: `finalize()` runs after the page is closed
   * (video.saveAs only completes once the page closes), when
   * `page.viewportSize()` is no longer trustworthy.
   */
  private readonly viewport: CaptionsViewport | null;

  constructor(page: Page, testInfo: TestInfo) {
    this.page = page;
    this.testInfo = testInfo;
    this.viewport = page.viewportSize();
    const feature = featureFromSpecFile(testInfo.file);
    // One run dir per test title so re-records overwrite cleanly.
    const runSlug = testInfo.title.replace(UNSAFE_SLUG_CHARS, "-").slice(0, 80);
    this.runDir = path.join(showcaseRawDir(feature), runSlug);
    this.shotsDir = path.join(this.runDir, "shots");
    fs.mkdirSync(this.shotsDir, { recursive: true });
  }

  /** 1–3 sentence description of what the video proves. Shown at the top of the report. */
  describe(text: string): void {
    this.descriptionText = text;
  }

  /**
   * Record one narrative beat. `fn` must leave the page in the captioned state —
   * the screenshot is taken the instant `fn` returns, with NO auto-wait. End `fn`
   * with an `expect(...).toBeVisible()` or `waitForLoadState('networkidle')`.
   *
   * Timing telemetry (startMs/endMs relative to the recording epoch) is captured
   * around `fn` and written into `captions.json` (v2) so an optional caption
   * burner can place subtitles at the real step boundaries.
   *
   * Optionally return the acted-on Locator from `fn` — its bounding box is
   * recorded as the step's `rect` (subtitle placement + future auto-zoom;
   * best-effort, skipped if the element detached). Pass `voiceover` when the
   * spoken narration differs from the on-screen caption (fed to the future TTS
   * pipeline via captions.json). Pass `subtitlePosition: 'top'` when the step's
   * UI of interest (a CTA, a toast) sits in the bottom band where the burned
   * subtitle would cover it — the burner also infers this from `rect` when the
   * returned locator lands in the bottom fifth of the viewport.
   */
  async step(
    caption: string,
    fn: () => Promise<Locator | undefined> | Promise<void>,
    opts?: { voiceover?: string; subtitlePosition?: "top" | "bottom" }
  ): Promise<void> {
    this.order += 1;
    const { order } = this;
    const startMs = Date.now() - this.recordingEpochMs;
    const acted = await fn();

    // Close the caption window BEFORE the rect probe and the screenshot. Taking
    // endMs after either folds their cost into the recorded step length, so
    // subtitles run systematically long and the telemetry overstates every step
    // for any later consumer of endMs (e.g. the planned TTS pacing).
    const endMs = Date.now() - this.recordingEpochMs;

    let rect: StepRect | undefined;
    if (acted && typeof acted.boundingBox === "function") {
      // Bounded and SHORT: this runs right after actions that routinely unmount
      // their target (a dialog that closed, a toast the step just asserted
      // away). At the instant `fn` resolves the element is either attached now
      // or gone for good — there is no "attaches later" case worth waiting for,
      // and every ms spent waiting here is dead, actionless footage burned into
      // the published tutorial (the NEXT step's startMs closes this step's cue
      // window, so a 5s wait used to stretch both the video and its subtitle).
      rect =
        (await acted.boundingBox({ timeout: 500 }).catch(() => null)) ??
        undefined;
    }

    const shot = `shots/${String(order).padStart(2, "0")}.png`;
    await this.page.screenshot({ path: path.join(this.runDir, shot) });
    const entry: StepRecord = { caption, endMs, order, shot, startMs };
    if (opts?.voiceover) {
      entry.voiceover = opts.voiceover;
    }
    if (rect) {
      entry.rect = rect;
    }
    if (opts?.subtitlePosition) {
      entry.position = opts.subtitlePosition;
    }
    this.steps.push(entry);
  }

  /** Breathing room between scenes. Scaled by SHOWCASE_SPEED. */
  async pause(ms = 600): Promise<void> {
    await this.page.waitForTimeout(Math.round(ms / SPEED));
  }

  /**
   * Human-look click: glides the cursor from its last position to the target
   * along a curved, eased path (the DOM cursor dot follows), dwells briefly,
   * then performs a real Playwright click (which fires the click ripple).
   * Use inside `step` fns instead of `locator.click()` wherever the pointer
   * should be watchable.
   */
  async click(locator: Locator): Promise<void> {
    await this.motionApproach(locator);
    await locator.click();
  }

  /** Human-look hover: same glide + dwell as `click`, without the click. */
  async hover(locator: Locator): Promise<void> {
    await this.motionApproach(locator);
    await locator.hover();
  }

  /**
   * Human-look typing: motion-clicks the field, then types character by
   * character (`pressSequentially`) at a natural per-key cadence instead of
   * `fill()`'s instant paste. Not for native date/color inputs — their
   * segmented editing needs `fill()`.
   */
  async type(locator: Locator, text: string): Promise<void> {
    await this.motionApproach(locator);
    await locator.click();
    // 45–85 ms per key reads as fluent human typing; unscaled on purpose —
    // key cadence is the one thing that looks WRONG when slowed down.
    await locator.pressSequentially(text, {
      delay: 45 + Math.round(Math.random() * 40),
    });
  }

  /**
   * Pre-compile the routes the spec will visit BEFORE recording begins, so the
   * video doesn't open on Vite's first-navigation compile/blank screen. Each path
   * is navigated to network-idle then the page is returned to about:blank. Records
   * nothing. Pass paths relative to baseURL (the same you'd pass to `page.goto`).
   */
  async warmup(...paths: string[]): Promise<void> {
    for (const p of paths) {
      try {
        // oxlint-disable-next-line no-await-in-loop -- one Page navigates one route at a time; the warmups are sequential by nature
        await this.page.goto(p, { waitUntil: "networkidle" });
      } catch {
        // An auth redirect / guard still triggers the compile — swallow and move on.
      }
    }
    await this.page.goto("about:blank");
  }

  /** Scroll a below-the-fold element into view and settle one frame before the screenshot. */
  async scrollTo(locator: Locator): Promise<void> {
    await locator.scrollIntoViewIfNeeded();
    await this.page.evaluate(
      () =>
        // oxlint-disable-next-line promise/avoid-new -- wraps requestAnimationFrame, which has no promise API
        new Promise((resolve) => {
          requestAnimationFrame(() => {
            resolve(null);
          });
        })
    );
  }

  /**
   * Scroll to + glide onto a locator, then dwell — the shared approach phase of
   * `click`/`hover`/`type`. Every wait in here is bounded: the glide is cosmetic,
   * so a missing/detached target must fall through to the REAL action (which
   * fails with a proper timeout error), never stall until the test budget dies.
   */
  private async motionApproach(locator: Locator): Promise<void> {
    // Bounded: a mistyped locator must not burn the test budget inside the glide.
    try {
      await locator.scrollIntoViewIfNeeded({ timeout: 10_000 });
    } catch {
      return;
    }
    // Bounded for a subtler reason: a target that DETACHES between the scroll and
    // the measurement (a transient affordance — a toast, a just-dismissed dialog)
    // makes an unbounded boundingBox() wait for it to re-attach.
    const box = await locator.boundingBox({ timeout: 5000 }).catch(() => null);
    if (!box) {
      return;
    }
    await this.travelTo({
      x: box.x + box.width / 2,
      y: box.y + box.height / 2,
    });
    await this.page.waitForTimeout(Math.round(HOVER_DWELL_MS / SPEED));
  }

  /**
   * Glide the pseudo-cursor to `target` along an eased cubic-Bézier path. The
   * motion is produced by dispatching synthetic `mousemove` events inside the
   * page (one rAF loop = one protocol call, so launch-level slowMo taxes it
   * once, not per segment). The DOM cursor dot follows those events; the REAL
   * pointer interaction (hover states, mousedown → click ripple) still comes
   * from the Playwright action performed at the destination afterwards.
   */
  private async travelTo(target: { x: number; y: number }): Promise<void> {
    const viewport = this.page.viewportSize() ?? { height: 720, width: 1280 };
    const from = this.cursorPos ?? {
      x: viewport.width / 2,
      y: viewport.height * 0.62,
    };
    this.cursorPos = target;
    const distance = Math.hypot(target.x - from.x, target.y - from.y);
    if (!CURSOR_ENABLED || distance < 8) {
      return;
    }
    // ~335–600 ms of real travel scaled by distance, stretched to the recording
    // pace. A perpendicular bow (±12% of distance, side chosen at random) keeps
    // long moves from reading as laser-straight; long travels push the second
    // control point further along the path so the approach decelerates later (it
    // does NOT overshoot — a cubic only overshoots when a control point projects
    // past the endpoint, i.e. >1.0).
    const durationMs = Math.round(Math.min(600, 335 + distance * 0.27) / SPEED);
    const bow = distance * 0.12 * (Math.random() < 0.5 ? -1 : 1);
    const normalX = -(target.y - from.y) / distance;
    const normalY = (target.x - from.x) / distance;
    const overshoot = distance > 400 ? 0.04 : 0;
    const controlNear = {
      x: from.x + (target.x - from.x) * 0.3 + normalX * bow,
      y: from.y + (target.y - from.y) * 0.3 + normalY * bow,
    };
    const controlFar = {
      x:
        from.x + (target.x - from.x) * (0.75 + overshoot) + normalX * bow * 0.4,
      y:
        from.y + (target.y - from.y) * (0.75 + overshoot) + normalY * bow * 0.4,
    };
    try {
      await this.page.evaluate(
        // p0..p3 and mt (1 - t) are the standard cubic-Bézier names, kept verbatim so the
        // interpolation below reads as the textbook formula rather than a paraphrase of it.
        async ({ from: p0, c1: p1, c2: p2, to: p3, durationMs: total }) => {
          // oxlint-disable-next-line promise/avoid-new -- rAF-driven animation; no promise-based API exists for it
          await new Promise<void>((resolve) => {
            const startedAt = performance.now();
            const done = () => {
              resolve();
            };
            // Browsers pause requestAnimationFrame for a hidden or fully occluded page, so a
            // headed run behind another window would hang here forever. A wall-clock fallback
            // resolves the glide (cosmetic anyway) and lets the real action proceed.
            const bail = setTimeout(done, total + 2000);
            const settle = () => {
              clearTimeout(bail);
              done();
            };
            // oxlint-disable-next-line unicorn/consistent-function-scoping -- must stay inside the serialized page.evaluate body
            const ease = (t: number) =>
              t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
            const tick = (now: number) => {
              const raw = Math.min(1, (now - startedAt) / total);
              const t = ease(raw);
              const mt = 1 - t;
              const x =
                mt ** 3 * p0.x +
                3 * mt ** 2 * t * p1.x +
                3 * mt * t ** 2 * p2.x +
                t ** 3 * p3.x;
              const y =
                mt ** 3 * p0.y +
                3 * mt ** 2 * t * p1.y +
                3 * mt * t ** 2 * p2.y +
                t ** 3 * p3.y;
              document.dispatchEvent(
                new MouseEvent("mousemove", {
                  bubbles: true,
                  clientX: x,
                  clientY: y,
                })
              );
              if (raw < 1) {
                requestAnimationFrame(tick);
              } else {
                settle();
              }
            };
            requestAnimationFrame(tick);
          });
        },
        { c1: controlNear, c2: controlFar, durationMs, from, to: target }
      );
    } catch {
      // Navigation destroyed the execution context mid-glide — the motion is
      // cosmetic, the real action at the destination still lands.
    }
  }

  /**
   * Called by the fixture's page event handlers during recording.
   * @internal
   */
  recordConsole(event: Omit<ConsoleEvent, "afterStep">): void {
    this.consoleEvents.push({ ...event, afterStep: this.order });
  }

  /**
   * Persists the run manifest + sidecar. Call only AFTER the page is closed
   * (see the fixture teardown).
   * @internal
   */
  async finalize(video: Video | null): Promise<void> {
    // Save the Playwright-recorded video next to the shots so the report is self-contained.
    // saveAs waits for the recording to flush, which happens only when the page CLOSES — so the
    // fixture teardown closes the page before calling finalize. Calling saveAs with the page
    // still open deadlocks (saveAs waits for a close that waits for this teardown); copying
    // video.path() raw instead produces a truncated webm.
    let videoFile: string | undefined = video ? "video.webm" : undefined;
    if (video && videoFile) {
      await video.saveAs(path.join(this.runDir, videoFile)).catch(() => {
        videoFile = undefined;
      });
    }

    const manifest = {
      description: this.descriptionText,
      file: this.testInfo.file,
      status: this.testInfo.status,
      steps: this.steps,
      title: this.testInfo.title,
      video: videoFile,
    };
    fs.writeFileSync(
      path.join(this.runDir, "manifest.json"),
      JSON.stringify(manifest, null, 2)
    );

    // captions.json v2 — the timing manifest an optional tutorial caption burner
    // consumes (harmless when none exists).
    // Kept as a SEPARATE file so the report generator's manifest.json contract
    // stays untouched. Shape + both-sided pinning: see CaptionsManifestV2.
    const captionsManifest = buildCaptionsManifest({
      description: this.descriptionText,
      file: this.testInfo.file,
      finalizedMs: Date.now() - this.recordingEpochMs,
      project: this.testInfo.project.name,
      recordingStartedAt: new Date(this.recordingEpochMs).toISOString(),
      steps: this.steps,
      title: this.testInfo.title,
      video: videoFile,
      viewport: this.viewport,
    });
    fs.writeFileSync(
      path.join(this.runDir, "captions.json"),
      JSON.stringify(captionsManifest, null, 2)
    );

    const sidecar = this.consoleEvents.map((e) => JSON.stringify(e)).join("\n");
    fs.writeFileSync(path.join(this.runDir, "console-errors.jsonl"), sidecar);
  }

  /**
   * The DOM pseudo-cursor overlay init script. An absolutely-
   * positioned dot tracks `mousemove` at requestAnimationFrame cadence; a second
   * element renders a ripple ring on `mousedown`, scaled to the recording pace.
   * Both have `pointer-events: none` and max z-index so they never interfere
   * with selectors or element-visibility checks. Installed via `addInitScript`
   * so it re-arms on every navigation (each `page.goto` gets a fresh DOM).
   * @internal
   */
  static cursorInitScript(): string {
    return `
;(() => {
  if (window.__showcaseCursorInstalled) return;
  window.__showcaseCursorInstalled = true;

  const style = document.createElement('style');
  style.textContent = \`
    #__showcase_cursor, #__showcase_click_ripple {
      position: fixed;
      pointer-events: none;
      z-index: 2147483647;
      border-radius: 50%;
    }
    #__showcase_cursor {
      width: 20px; height: 20px;
      left: 0; top: 0;
      background: rgba(255, 69, 0, 0.35);
      border: 2px solid rgba(255, 69, 0, 0.95);
      box-shadow: 0 0 10px rgba(255, 69, 0, 0.55);
      transform: translate(-1000px, -1000px);
      transition: transform 60ms linear;
      will-change: transform;
    }
    #__showcase_click_ripple {
      width: 44px; height: 44px;
      border: 4px solid rgba(255, 69, 0, 0.85);
      opacity: 0;
    }
    @keyframes __showcase_ripple_pulse {
      0%   { transform: scale(0.4); opacity: 1; }
      100% { transform: scale(1.9); opacity: 0; }
    }
    .__showcase_click_fire { animation: __showcase_ripple_pulse ${RIPPLE_PULSE_MS}ms ease-out forwards; }
  \`;

  const mount = () => {
    if (!document.body) { requestAnimationFrame(mount); return; }
    if (document.getElementById('__showcase_cursor')) return;

    document.head.appendChild(style);

    const dot = document.createElement('div');
    dot.id = '__showcase_cursor';
    document.body.appendChild(dot);

    const ripple = document.createElement('div');
    ripple.id = '__showcase_click_ripple';
    document.body.appendChild(ripple);

    let raf = 0;
    let px = 0, py = 0;
    const move = (e) => {
      px = e.clientX; py = e.clientY;
      if (raf) return;
      raf = requestAnimationFrame(() => {
        dot.style.transform = \`translate(\${px - 10}px, \${py - 10}px)\`;
        raf = 0;
      });
    };
    document.addEventListener('mousemove', move, { capture: true, passive: true });
    document.addEventListener('mousedown', (e) => {
      ripple.style.left = (e.clientX - 22) + 'px';
      ripple.style.top  = (e.clientY - 22) + 'px';
      ripple.classList.remove('__showcase_click_fire');
      // force reflow so the animation restarts on rapid clicks
      void ripple.offsetWidth;
      ripple.classList.add('__showcase_click_fire');
    }, { capture: true, passive: true });
  };
  mount();
})();
`;
  }
}

export const test = base.extend<{ showcase: Showcase }>({
  showcase: async ({ page }, use, testInfo) => {
    const showcase = new Showcase(page, testInfo);

    if (CURSOR_ENABLED) {
      await page.context().addInitScript(Showcase.cursorInitScript());
    }

    // Sidecar: capture silent browser-side errors and failed XHRs during the recording.
    page.on("console", (msg) => {
      if (msg.type() === "error" || msg.type() === "warning") {
        showcase.recordConsole({
          kind: msg.type() === "error" ? "console.error" : "console.warn",
          text: msg.text(),
          tsIso: new Date().toISOString(),
        });
      }
    });
    page.on("pageerror", (err) => {
      showcase.recordConsole({
        kind: "pageerror",
        text: err.stack ?? err.message,
        tsIso: new Date().toISOString(),
      });
    });
    page.on("requestfailed", (req) => {
      const failure = req.failure();
      if (failure && failure.errorText !== "net::ERR_ABORTED") {
        showcase.recordConsole({
          kind: "requestfailed",
          text: `${req.method()} ${req.url()} — ${failure.errorText}`,
          tsIso: new Date().toISOString(),
        });
      }
    });

    // oxlint-disable-next-line react-hooks/rules-of-hooks -- Playwright fixture `use` callback, not a React hook
    await use(showcase);

    // video.saveAs (inside finalize) only completes once the page closes, and the page
    // fixture won't close it until THIS teardown returns — close it explicitly first,
    // or finalize deadlocks until the test timeout.
    const video = page.video();
    await page.close();
    await showcase.finalize(video);
  },
});
