#!/usr/bin/env node
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";

/**
 * Showcase runner. Boots the showcase Playwright config against a feature's
 * `*.showcase.ts` spec(s), then renders the HTML report and serves it on the LAN.
 *
 * Usage:  node scripts/run-showcase.mjs <feature> [+50%|-30%|--speed=1.5] [--no-cursor] [--headed]
 *         (wire it as the `showcase` package script so `<pm> showcase <feature>` works)
 *
 * <feature> matches spec files under showcase/specs/** by basename substring, e.g.
 * `person-search` -> showcase/specs/person-search.showcase.ts.
 *
 * Paths resolve from this file's location, not from cwd: the harness root is the
 * directory holding playwright.showcase.config.ts and showcase/. Per-repo settings
 * come from `.claude/claude-skills.json` (key `showcase`) in the enclosing repo:
 *   outDir, artifactNaming, ports { frontend, report }, serverEnv, backendMode
 * Every value is optional; see the skill's Configuration section for defaults.
 */

const PCT_FLAG_RE = /^[+-]\d+%$/u;
const PCT_PARSE_RE = /^(?<sign>[+-])(?<pct>\d+)%$/u;
const SPEED_FLAG_RE = /^--speed=(?<value>[\d.]+)$/u;
const SHOWCASE_SUFFIX_RE = /\.showcase\.ts$/u;

const HARNESS_ROOT = path.resolve(import.meta.dirname, "..");

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
const REPO_ROOT = findRepoRoot(HARNESS_ROOT);

// ---- per-repo config (.claude/claude-skills.json, key "showcase") ----
const loadConfig = () => {
  const file = path.join(REPO_ROOT, ".claude", "claude-skills.json");
  if (!fs.existsSync(file)) {
    return {};
  }
  try {
    return JSON.parse(fs.readFileSync(file, "utf-8")).showcase ?? {};
  } catch {
    console.warn(`▶ ignoring unparsable ${file}`);
    return {};
  }
};
const config = loadConfig();

// ---- package manager: lockfile in the repo root, else npm ----
const detectPm = () => {
  const lock = [
    ["pnpm-lock.yaml", "pnpm"],
    ["yarn.lock", "yarn"],
    ["bun.lockb", "bun"],
    ["bun.lock", "bun"],
    ["package-lock.json", "npm"],
  ].find(([f]) => fs.existsSync(path.join(REPO_ROOT, f)));
  return lock?.[1] ?? "npm";
};
const pm = detectPm();
/** `<pm> exec playwright …` spelled the way each manager wants it. */
const execPrefix = { bun: ["bunx"], npm: ["npx"], pnpm: ["pnpm", "exec"], yarn: ["yarn"] }[pm];

// ---- dev port: ports.frontend, then PORT in .env.local/.env, then -p/--port in the dev script, then 3000 ----
const detectDevPort = () => {
  if (config.ports?.frontend) {
    return Number(config.ports.frontend);
  }
  for (const envFile of [".env.local", ".env"]) {
    const p = path.join(REPO_ROOT, envFile);
    if (fs.existsSync(p)) {
      const m = /^\s*PORT\s*=\s*"?(?<port>\d+)"?/mu.exec(fs.readFileSync(p, "utf-8"));
      if (m) {
        return Number(m.groups.port);
      }
    }
  }
  const pkg = path.join(REPO_ROOT, "package.json");
  if (fs.existsSync(pkg)) {
    const dev = JSON.parse(fs.readFileSync(pkg, "utf-8")).scripts?.dev ?? "";
    const m = /(?:^|\s)(?:-p|--port)[\s=](?<port>\d+)/u.exec(dev);
    if (m) {
      return Number(m.groups.port);
    }
  }
  return 3000;
};

const argv = process.argv.slice(2);
const flags = argv.filter((a) => a.startsWith("-") || PCT_FLAG_RE.test(a));
const feature = argv.find((a) => !flags.includes(a));

if (!feature) {
  console.error(
    "Usage: node scripts/run-showcase.mjs <feature> [+50%|-30%|--speed=1.5] [--no-cursor] [--headed]"
  );
  process.exit(1);
}

// ---- speed resolution ----
let speed = 1;
for (const f of flags) {
  const pct = f.match(PCT_PARSE_RE);
  const explicit = f.match(SPEED_FLAG_RE);
  if (pct) {
    speed =
      pct.groups.sign === "+"
        ? 1 + Number(pct.groups.pct) / 100
        : 1 - Number(pct.groups.pct) / 100;
  } else if (explicit) {
    speed = Number(explicit.groups.value);
  }
}
// Forwarded raw via SHOWCASE_SPEED below; the single clamp (and the slowMo
// derivation) lives in showcase/helpers/speed.ts on the recording side.
speed ||= 1;

// ---- locate matching spec files ----
const specsRoot = path.join(HARNESS_ROOT, "showcase", "specs");
const matches = [];
const walk = (dir) => {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) {
      walk(full);
    } else if (e.name.endsWith(".showcase.ts") && e.name.includes(feature)) {
      matches.push(path.relative(HARNESS_ROOT, full));
    }
  }
};
if (fs.existsSync(specsRoot)) {
  walk(specsRoot);
}

if (matches.length === 0) {
  console.error(
    `No spec found under ${path.relative(REPO_ROOT, specsRoot)}/** matching "${feature}" (looking for *${feature}*.showcase.ts).`
  );
  process.exit(1);
}

const features = [
  ...new Set(
    matches.map((m) => path.basename(m).replace(SHOWCASE_SUFFIX_RE, ""))
  ),
];

// ---- resolved settings, exported to the config, the fixture and the report ----
const today = new Date().toISOString().slice(0, 10);
const outDir = path.resolve(REPO_ROOT, config.outDir ?? "docs/showcases");
const artifactNaming = (config.artifactNaming ?? "<feature>").replace("<date>", today);
const backendMode = config.backendMode ?? "local";
const frontendUrl = process.env.FRONTEND_BASE_URL ?? `http://localhost:${detectDevPort()}`;

// Explicit env on the command line beats serverEnv from the config file.
const env = {
  WEBSERVER_COMMAND: `${pm} run dev`,
  ...(config.serverEnv ?? {}),
  ...process.env,
  SHOWCASE_ARTIFACT_NAMING: artifactNaming,
  SHOWCASE_BACKEND_MODE: backendMode,
  SHOWCASE_CURSOR: flags.includes("--no-cursor") ? "off" : "on",
  SHOWCASE_FRONTEND_URL: frontendUrl,
  SHOWCASE_OUT_DIR: outDir,
  SHOWCASE_SPEED: String(speed),
};

// ---- run playwright ----
const [pwCmd, ...pwPrefix] = execPrefix;
const pwArgs = [
  ...pwPrefix,
  "playwright",
  "test",
  "-c",
  "playwright.showcase.config.ts",
  ...matches,
];
if (flags.includes("--headed")) {
  pwArgs.push("--headed");
}

console.info(
  `▶ showcase: ${features.join(", ")} — speed ${speed}×, backend ${backendMode}, frontend ${frontendUrl}`
);
const run = spawnSync(pwCmd, pwArgs, { cwd: HARNESS_ROOT, env, stdio: "inherit" });

// ---- render report(s) even on partial failure (a broken feature is worth seeing) ----
for (const f of features) {
  spawnSync("node", ["showcase/report.mjs", f], { cwd: HARNESS_ROOT, env, stdio: "inherit" });
}

// ---- always serve the report(s) over the LAN after creation ----
// A `file://` path is unusable from another device; a reviewer on the network needs an HTTP URL.
// Serve outDir on a fixed port so at most ONE server exists across re-runs (a second bind on the
// same port harmlessly fails and the running one keeps serving), detached so this one-shot command
// still exits. SHOWCASE_PORT env overrides config `ports.report`; the default is 8899.
const SHOWCASE_PORT =
  Number(process.env.SHOWCASE_PORT) || Number(config.ports?.report) || 8899;

const lanIp = () => {
  const ifaces = Object.values(os.networkInterfaces()).flat();
  const usable = ifaces.filter((i) => i && i.family === "IPv4" && !i.internal);
  // Prefer a real LAN address over docker/bridge ranges (172.16/12) so the URL is reachable.
  const preferred = usable.find((i) => !i.address.startsWith("172."));
  return (preferred || usable[0])?.address ?? "localhost";
};

const portListening = (port) =>
  new Promise((resolve) => {
    const socket = net.connect({ host: "127.0.0.1", port });
    socket.once("connect", () => {
      socket.destroy();
      resolve(true);
    });
    socket.once("error", () => resolve(false));
    socket.setTimeout(400, () => {
      socket.destroy();
      resolve(false);
    });
  });

const serveReports = async (featureNames) => {
  const ip = lanIp();
  const running = await portListening(SHOWCASE_PORT);
  if (running) {
    console.info(
      `\n▶ Serving showcases on the LAN (reusing the server already on :${SHOWCASE_PORT}):`
    );
  } else if (
    spawnSync("python3", ["--version"], { stdio: "ignore" }).status === 0
  ) {
    spawn(
      "python3",
      ["-m", "http.server", String(SHOWCASE_PORT), "--bind", "0.0.0.0", "--directory", outDir],
      { detached: true, stdio: "ignore" }
    ).unref();
    console.info(
      `\n▶ Serving showcases on the LAN (started a server on :${SHOWCASE_PORT}):`
    );
  } else {
    console.info(
      "\n▶ python3 not found — to serve the report over the LAN, run:\n" +
        `    python3 -m http.server ${SHOWCASE_PORT} --bind 0.0.0.0 --directory ${outDir}`
    );
    return;
  }
  for (const f of featureNames) {
    const name = artifactNaming.replace("<feature>", f);
    console.info(`    http://${ip}:${SHOWCASE_PORT}/${name}/index.html`);
  }
};

await serveReports(features);

process.exit(run.status ?? 1);
