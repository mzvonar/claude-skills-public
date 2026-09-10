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

// The closed vocabulary is CORPUS DATA, not a constant. The first real ledger documented two
// words in its own header and used six; assuming the header cost 7 items, which migrated `open`
// into the untriaged set. Widening `migrate.py` alone is half a fix — every consumer that decides
// "is this open?" shares this list, or the newly-closed items still read as open here.
const CLOSED = /^(DONE|KILLED|CLOSED|SUPERSEDED|RETIRED|RESOLVED)\b/u;

// A YAML single-quoted scalar escapes one thing: a quote, doubled. Strip the wrapper and undo it,
// or the reader shows the escape — `Exception''s` reached every grooming pass because the writer
// was fixed and the round-trip was not. Only unwrap when the value is actually quoted: a bare
// scalar containing '' is not an escape.
const unquote = (v) => (/^'.*'$/su.test(v) ? v.slice(1, -1).replaceAll("''", "'")
  : /^".*"$/su.test(v) ? v.slice(1, -1) : v);

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
    if (m) out[m.groups.k] = unquote(m.groups.v.trim());
  }
  return out;
};

const items = readdirSync(dir)
  .filter((n) => n.endsWith(".md"))
  .map((n) => ({ file: n, ...(frontmatter(path.join(dir, n)) ?? {}) }))
  .filter((i) => i.id)
  .filter((i) => all || !CLOSED.test(i.status ?? ""));

if (flags.includes("--json")) {
  console.log(JSON.stringify(items, null, 2));
} else {
  for (const i of items) {
    console.log(`${i.id}  [${(i.status ?? "?").padEnd(17)}] ${i.summary}`);
    console.log(`${" ".repeat(9)}trigger: ${i.trigger ?? ""}   ← ${i.file}`);
  }
  console.log(`\n${items.length} ${all ? "total" : "open"} item(s)`);
}
