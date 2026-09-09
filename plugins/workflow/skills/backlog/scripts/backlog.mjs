#!/usr/bin/env node
// The backlog, as the classifier sees it: one line per item, frontmatter only.
// Bodies are never read — grooming needs the trigger and the status, not the prose.
//
//   node backlog.mjs <index.md | detail-dir> [--all] [--json]     default: open items only
//
// Given the index file (`docs/backlog/index.md`) the detail directory is its sibling named after
// the stem (`docs/backlog/index/`); a directory is used as-is.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

const [target, ...flags] = process.argv.slice(2);
if (!target) {
  console.error("usage: backlog.mjs <index.md | detail-dir> [--all] [--json]");
  process.exit(2);
}
const all = flags.includes("--all");
const dir =
  existsSync(target) && statSync(target).isDirectory()
    ? target
    : path.join(path.dirname(target), path.basename(target).replace(/\.md$/u, ""));

// Frontmatter only: stop at the closing fence, so a 20KB body costs nothing.
const frontmatter = (file) => {
  const out = {};
  const lines = readFileSync(file, "utf-8").split("\n");
  if (lines[0]?.trim() !== "---") return null;
  for (const line of lines.slice(1)) {
    if (line.trim() === "---") break;
    const m = /^(?<k>[a-z_]+):\s*(?<v>.*)$/u.exec(line);
    if (m) out[m.groups.k] = m.groups.v.replace(/^['"]|['"]$/gu, "");
  }
  return out;
};

const items = readdirSync(dir)
  .filter((n) => n.endsWith(".md"))
  .map((n) => ({ file: n, ...(frontmatter(path.join(dir, n)) ?? {}) }))
  .filter((i) => i.id)
  .filter((i) => all || !/^(DONE|KILLED)/u.test(i.status ?? ""));

if (flags.includes("--json")) {
  console.log(JSON.stringify(items, null, 2));
} else {
  for (const i of items) {
    console.log(`${i.id}  [${(i.status ?? "?").padEnd(17)}] ${i.summary}`);
    console.log(`${" ".repeat(9)}trigger: ${i.trigger ?? ""}   ← ${i.file}`);
  }
  console.log(`\n${items.length} ${all ? "total" : "open"} item(s)`);
}
