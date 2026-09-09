#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

/**
 * Render a self-contained HTML showcase report for a feature from the raw captures
 * the `showcase` fixture wrote under `<outDir>/<feature>/_raw/<run>/`.
 *
 * Usage: node showcase/report.mjs <feature>
 * Output: <outDir>/<feature>/index.html   (outDir: SHOWCASE_OUT_DIR, else <repo>/docs/showcases)
 *
 * Normally invoked by scripts/run-showcase.mjs, which resolves outDir / artifactNaming
 * from .claude/claude-skills.json and passes them down as env; run standalone it uses
 * the defaults under the nearest enclosing git repository.
 */

const [feature] = process.argv.slice(2);
if (!feature) {
  console.error("Usage: node showcase/report.mjs <feature>");
  process.exit(1);
}

const findRepoRoot = (from) => {
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
const OUT_ROOT = process.env.SHOWCASE_OUT_DIR
  ? path.resolve(process.env.SHOWCASE_OUT_DIR)
  : path.join(findRepoRoot(process.cwd()), "docs", "showcases");
const NAMING = process.env.SHOWCASE_ARTIFACT_NAMING || "<feature>";
const featureDir = path.join(
  OUT_ROOT,
  NAMING.replace("<feature>", feature).replace(
    "<date>",
    new Date().toISOString().slice(0, 10)
  )
);
const rawDir = path.join(featureDir, "_raw");

if (!fs.existsSync(rawDir)) {
  console.error(
    `No showcase runs found under ${rawDir}. Did the run match any *.showcase.ts spec?`
  );
  process.exit(1);
}

const esc = (s) =>
  String(s).replaceAll(
    /[&<>"]/gu,
    (c) => ({ '"': "&quot;", "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]
  );

const tryTranscodeMp4 = (runDir, webm) => {
  const webmPath = path.join(runDir, webm);
  const mp4 = "video.mp4";
  const mp4Path = path.join(runDir, mp4);
  // The runner re-renders the report after every recording. Skip the transcode
  // when video.mp4 is already newer than its source webm — re-recording one
  // spec must not re-encode every untouched run of the feature.
  if (
    fs.existsSync(mp4Path) &&
    fs.statSync(mp4Path).mtimeMs >= fs.statSync(webmPath).mtimeMs
  ) {
    return mp4;
  }
  try {
    execFileSync(
      "ffmpeg",
      [
        "-y",
        "-i",
        webmPath,
        "-c:v",
        "libx264",
        // veryfast: this mp4 is a preview-quality artifact — render speed over compression.
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        mp4Path,
      ],
      { stdio: "ignore" }
    );
    return mp4;
  } catch {
    // A failed transcode can leave a fresh-mtime partial mp4 the skip-check
    // above would then trust — remove it before falling back.
    fs.rmSync(mp4Path, { force: true });
    // ffmpeg absent or the transcode failed — webm only (won't play on iOS; see the skill).
  }
};

const runDirs = fs
  .readdirSync(rawDir, { withFileTypes: true })
  .filter(
    (d) =>
      d.isDirectory() &&
      fs.existsSync(path.join(rawDir, d.name, "manifest.json"))
  )
  .map((d) => d.name);

if (runDirs.length === 0) {
  console.error(`No runs with a manifest.json under ${rawDir}.`);
  process.exit(1);
}

const sections = runDirs.map((run) => {
  const runDir = path.join(rawDir, run);
  const manifest = JSON.parse(
    fs.readFileSync(path.join(runDir, "manifest.json"), "utf-8")
  );
  const rel = (p) => path.posix.join("_raw", run, p);

  let videoBlock = "";
  if (manifest.video) {
    const mp4 = tryTranscodeMp4(runDir, manifest.video);
    const v = fs.statSync(path.join(runDir, manifest.video)).mtimeMs;
    const sources = [
      mp4 ? `<source src="${rel(mp4)}?v=${v}" type="video/mp4" />` : "",
      `<source src="${rel(manifest.video)}?v=${v}" type="video/webm" />`,
    ].join("");
    videoBlock = `<video controls preload="metadata" style="max-width:100%;border-radius:8px;">${sources}</video>`;
  }

  const shots = manifest.steps
    .map(
      (s) => `
      <figure class="shot">
        <img src="${rel(s.shot)}" alt="${esc(s.caption)}" loading="lazy" />
        <figcaption><span class="num">${String(s.order).padStart(2, "0")}</span> ${esc(s.caption)}</figcaption>
      </figure>`
    )
    .join("");

  const status =
    manifest.status === "passed"
      ? '<span class="ok">passed</span>'
      : `<span class="bad">${esc(manifest.status)}</span>`;

  return `
    <section class="run">
      <h2>${esc(manifest.title)} ${status}</h2>
      ${manifest.description ? `<p class="desc">${esc(manifest.description)}</p>` : ""}
      ${videoBlock}
      <div class="grid">${shots}</div>
    </section>`;
});

const html = `<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Showcase — ${esc(feature)}</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 2rem; max-width: 1100px; margin-inline: auto; line-height: 1.5; }
  h1 { font-size: 1.4rem; }
  h2 { font-size: 1.1rem; margin-top: 2.5rem; }
  .desc { color: #666; max-width: 65ch; }
  .ok { color: #1a7f37; font-size: .8rem; } .bad { color: #cf222e; font-size: .8rem; }
  video { display: block; margin: 1rem 0 2rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1.2rem; }
  .shot { margin: 0; border: 1px solid #8883; border-radius: 8px; overflow: hidden; }
  .shot img { width: 100%; display: block; }
  figcaption { padding: .6rem .8rem; font-size: .85rem; }
  .num { display: inline-block; min-width: 1.6em; font-variant-numeric: tabular-nums; color: #888; }
</style></head>
<body>
  <h1>Showcase — ${esc(feature)}</h1>
  ${sections.join("\n")}
</body></html>`;

const out = path.join(featureDir, "index.html");
fs.writeFileSync(out, html);
console.info(out);
console.info(`open "${out}"`);
