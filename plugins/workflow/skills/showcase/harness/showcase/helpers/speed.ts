/**
 * Single home of the showcase speed contract: the 0.1–3 clamp and the
 * slowMo-from-speed derivation. Imported by both the showcase fixture
 * (`helpers/showcase.ts`) and `playwright.showcase.config.ts`; the runner
 * (`scripts/run-showcase.mjs`) forwards the raw `SHOWCASE_SPEED` value and
 * relies on this clamp.
 */

export const MIN_SPEED = 0.1;
export const MAX_SPEED = 3;

/** slowMo at speed 1×, scaled inversely by the speed multiplier. */
export const BASE_SLOWMO_MS = 400;

/**
 * The floor also catches a NEGATIVE speed (truthy, so the `|| 1` in
 * `speedFromEnv` misses it), which would otherwise flow into every duration: a
 * negative CSS animation duration (the ripple never renders), a negative
 * waitForTimeout, a negative glide.
 */
export const clampSpeed = (n: number): number =>
  Math.min(MAX_SPEED, Math.max(MIN_SPEED, n));

/** Parse + clamp `SHOWCASE_SPEED` (runner-set; unset/garbage → 1). */
export const speedFromEnv = (raw: string | undefined): number =>
  clampSpeed(Number(raw ?? "1") || 1);

export const slowMoForSpeed = (speed: number): number =>
  Math.round(BASE_SLOWMO_MS / speed);
