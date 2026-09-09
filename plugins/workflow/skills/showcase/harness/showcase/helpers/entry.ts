import { mergeTests } from "@playwright/test";

import { test as showcaseTest } from "./showcase";

/**
 * Showcase entry point. Gives a spec both the `showcase` fixture and every e2e
 * page-object fixture, so showcase specs reuse the exact action methods the e2e
 * specs use.
 *
 *   import { test, expect } from '../helpers/entry';
 *
 * ADAPT: once the e2e harness exports its own extended `test` (page objects,
 * seed helpers), merge it in here — until then this exports the bare showcase
 * fixture:
 *
 *   import { test as e2eTest } from '../../fixtures';
 *   export const test = mergeTests(showcaseTest, e2eTest);
 */
export const test = mergeTests(showcaseTest);

export { expect } from "@playwright/test";
