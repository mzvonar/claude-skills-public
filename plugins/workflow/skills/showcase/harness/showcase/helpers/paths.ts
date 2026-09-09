import fs from "node:fs";
import path from "node:path";

/**
 * Showcase output paths.
 *
 * Rendered artifacts live under `<repo root>/docs/showcases/` by default and are
 * gitignored. The runner (`scripts/run-showcase.mjs`) resolves the configured
 * `outDir` / `artifactNaming` from `.claude/claude-skills.json` and passes them
 * down as `SHOWCASE_OUT_DIR` / `SHOWCASE_ARTIFACT_NAMING`; when the fixture runs
 * without the runner (plain `playwright test`) it falls back to the defaults
 * under the nearest enclosing git repository, so no path here depends on cwd.
 */
const findRepoRoot = (from: string): string => {
  let dir = path.resolve(from);
  for (;;) {
    if (fs.existsSync(path.join(dir, ".git"))) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) {
      return path.resolve(from);
    }
    dir = parent;
  }
};

export const REPO_ROOT = findRepoRoot(process.cwd());
export const SHOWCASE_OUTPUT_ROOT = process.env.SHOWCASE_OUT_DIR
  ? path.resolve(process.env.SHOWCASE_OUT_DIR)
  : path.join(REPO_ROOT, "docs", "showcases");

/** Per-feature folder name template; `<feature>` and `<date>` are substituted. */
const ARTIFACT_NAMING = process.env.SHOWCASE_ARTIFACT_NAMING || "<feature>";

export const artifactName = (feature: string) =>
  ARTIFACT_NAMING.replace("<feature>", feature).replace(
    "<date>",
    new Date().toISOString().slice(0, 10)
  );

/** Final rendered report dir for a feature: `<outDir>/<artifactNaming>/`. */
export const showcaseFeatureDir = (feature: string) =>
  path.join(SHOWCASE_OUTPUT_ROOT, artifactName(feature));

/** Raw per-run capture dir the fixture writes to; the report generator consumes it. */
export const showcaseRawDir = (feature: string) =>
  path.join(showcaseFeatureDir(feature), "_raw");

const SHOWCASE_SUFFIX = /\.showcase\.ts$/u;
const NON_FEATURE_CHARS = /[^a-zA-Z0-9._-]/gu;

/**
 * Derive a feature id from a spec file path.
 * `.../foo-bar.showcase.ts` -> `foo-bar`.
 */
export const featureFromSpecFile = (file: string) =>
  path
    .basename(file)
    .replace(SHOWCASE_SUFFIX, "")
    .replace(NON_FEATURE_CHARS, "-");
