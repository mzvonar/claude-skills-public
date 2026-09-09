#!/usr/bin/env node
// Structural check over a backlog: the index, the detail files, and the link between them.
//
//   node validate.mjs <index.md>          e.g. node validate.mjs docs/backlog/index.md
//   node validate.mjs <dir>               shorthand for <dir>/index.md
//
// The detail directory is the index's sibling named after its stem: `index.md` -> `index/`,
// `deferred-work.md` -> `deferred-work/`.
//
// Exit 0 = clean · 1 = findings (listed on stdout) · 2 = usage/IO.
//
// It does NOT judge content — whether a trigger is a good trigger is a person's call. It closes the
// drift that no reader would notice: a pointer to a file that is not there, a detail file nothing
// points at, a required field missing, and index entries a generator appended that grooming has not
// promoted yet.

import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const REQUIRED = ["id", "summary", "status"];
const DEFAULT_INDEX_NAME = "index.md";

// Policies differ in what makes an item ACTIONABLE, and nothing else.
//   deferred-work — an open item must say when it becomes actionable (`trigger`). Parked work with
//                   no trigger is untriaged: no bucket applies to it, so it cannot be groomed.
//   (default)     — a plain backlog. Items are actionable when picked; `trigger` is optional.
// Declared in the index's own frontmatter, so the policy is visible where you already look and no
// second config file has to be found, parsed or kept in sync.
const POLICIES = new Set(["deferred-work"]);

/** Frontmatter only — the body is never read, and a file without a fence has none. */
export const frontmatter = (text) => {
  const out = {};
  const lines = text.split("\n");
  if (lines[0]?.trim() !== "---") {
    return null;
  }
  for (const line of lines.slice(1)) {
    if (line.trim() === "---") {
      break;
    }
    const m = /^(?<k>[a-z_]+):\s*(?<v>.*)$/u.exec(line);
    if (m) {
      out[m.groups.k] = m.groups.v.trim().replace(/^['"]|['"]$/gu, "");
    }
  }
  return out;
};

/** Resolve `<dir>` or `<dir>/<index>.md` to the index file path. */
export const resolveIndex = (target) =>
  existsSync(target) && statSync(target).isDirectory() ? path.join(target, DEFAULT_INDEX_NAME) : target;

/**
 * @param {string} target the index file (`docs/backlog/index.md`), or its directory for `index.md`
 * @returns {{code: string, where: string, detail: string}[]} findings, empty when clean
 */
export const scanBacklog = (target) => {
  const findings = [];
  const add = (code, where, detail) => findings.push({ code, detail, where });

  const index = resolveIndex(target);
  const root = path.dirname(index);
  const indexName = path.basename(index);
  const stem = indexName.replace(/\.md$/u, "");
  const dir = path.join(root, stem);
  if (!existsSync(index)) {
    add("NO_INDEX", indexName, "the index does not exist");
    return findings;
  }
  const indexText = readFileSync(index, "utf-8");
  const policy = frontmatter(indexText)?.policy ?? "";
  if (policy && !POLICIES.has(policy)) {
    add("UNKNOWN_POLICY", indexName, `frontmatter declares \`policy: ${policy}\`, which this version does not implement`);
  }
  const requireTrigger = policy === "deferred-work";

  // --- the detail files ---
  const seen = new Map();
  if (existsSync(dir) && statSync(dir).isDirectory()) {
    for (const name of readdirSync(dir).toSorted()) {
      const where = `${stem}/${name}`;
      if (!name.endsWith(".md")) {
        add("STRAY_FILE", where, "not a .md detail file");
        continue;
      }
      const fm = frontmatter(readFileSync(path.join(dir, name), "utf-8"));
      if (fm === null) {
        add("NO_FRONTMATTER", where, "no `---` frontmatter block — nothing can classify it");
        continue;
      }
      for (const key of REQUIRED) {
        if (!fm[key]) {
          add("MISSING_FIELD", where, `frontmatter has no \`${key}\``);
        }
      }
      if (fm.id && seen.has(fm.id)) {
        add("DUPLICATE_ID", where, `id \`${fm.id}\` is also used by ${seen.get(fm.id)}`);
      }
      if (fm.id) {
        seen.set(fm.id, name);
      }
      const open = !/^(DONE|KILLED)/u.test(fm.status ?? "");
      if (requireTrigger && open && !fm.trigger) {
        add("NO_TRIGGER", where, "open with no `trigger` — untriaged, and no bucket applies to it");
      }
      if (!indexText.includes(name)) {
        add("UNINDEXED", where, "no index entry points at this file — invisible to the classifier");
      }
    }
  }

  // --- the index's own pointers ---
  for (const m of indexText.matchAll(/^\s*detail:\s*`?(?<p>[^`\s]+)`?\s*$/gmu)) {
    const rel = m.groups.p;
    if (!existsSync(path.join(root, rel))) {
      add("DANGLING_DETAIL", rel, "the index points at a detail file that does not exist");
    }
  }

  // --- generator appends that grooming has not promoted ---
  // Not a defect — a state. An entry appended by a tool has no detail file, so no trigger and no
  // status, and it stays untriaged until someone promotes it. Reported so it cannot be forgotten.
  const entries = [...indexText.matchAll(/^\s*-\s+(?:id|source_spec):/gmu)].length;
  const pointers = [...indexText.matchAll(/^\s*detail:/gmu)].length;
  if (entries > pointers) {
    add("UNPROMOTED_APPENDS", indexName, `${entries - pointers} index entr(ies) have no \`detail:\` — appended by a tool, not yet triaged`);
  }

  return findings;
};

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const target = process.argv[2];
  if (!target) {
    console.error("usage: validate.mjs <index.md | dir>");
    process.exit(2);
  }
  let findings;
  try {
    findings = scanBacklog(target);
  } catch (error) {
    console.error(`validate: ${error.message}`);
    process.exit(2);
  }
  for (const f of findings) {
    console.log(`${f.code}  ${f.where}: ${f.detail}`);
  }
  console.log(findings.length === 0 ? "backlog: index and detail files are consistent" : `backlog: ${findings.length} finding(s)`);
  process.exit(findings.length === 0 ? 0 : 1);
}
