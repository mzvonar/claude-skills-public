import { expect, test } from "../helpers/entry";

/**
 * EXAMPLE showcase spec — copy this as a starting point, then delete it.
 *
 * Runs under the `showcase` project (same stack + auth as the e2e suite).
 * Records a slow-mo, captioned walkthrough, reusing the e2e page objects and
 * seed helpers exactly like an e2e spec would.
 *
 *   node scripts/run-showcase.mjs example      (or `<pm> showcase example` once wired)
 */
test.describe("Person search", () => {
  test("happy path", async ({ page, showcase }) => {
    showcase.describe(
      "An operator opens the person search and sees the matching persons list."
    );

    // Warm up every route first so the video doesn't open on the dev server's first-compile blank.
    await showcase.warmup("/persons");

    await showcase.step("Open the person search", async () => {
      await page.goto("/persons");
      // End every screen-changing step on a real assertion — the screenshot is
      // taken the instant this fn returns, with no auto-wait.
      await expect(
        page.getByRole("heading", { name: /persons/iu })
      ).toBeVisible();
    });

    await showcase.pause();

    // Use the human-look motion helpers (showcase.click / hover / type) wherever
    // the pointer should be watchable on camera — they glide the cursor to the
    // target before performing the real action:
    // await showcase.step('Search by name', async () => {
    //   await showcase.type(page.getByRole('searchbox'), 'Doe');
    //   await showcase.click(page.getByRole('button', { name: /search/i }));
    //   await expect(page.getByRole('row')).not.toHaveCount(0);
    // });

    // TUTORIAL recordings (optional `tutorialMode`, see the skill): return the acted-on Locator from
    // a step fn so its bounding box lands in captions.json (subtitle placement),
    // and use the opts for voiceover text / forcing the subtitle band to the top
    // when the step's payoff sits in the bottom fifth of the frame:
    // await showcase.step(
    //   'Confirm the update',
    //   async () => {
    //     const cta = page.getByRole('button', { name: /confirm/i });
    //     await showcase.click(cta);
    //     await expect(page.getByText(/saved/i)).toBeVisible();
    //     return cta;
    //   },
    //   { voiceover: 'Click Confirm to save the record.', subtitlePosition: 'top' },
    // );
  });
});
