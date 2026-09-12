#!/usr/bin/env node
// verify-migration.mjs — run between `migrate.py` and committing its output.
//
//   node verify-migration.mjs <source-ledger.md> <output-dir> [--index-name index.md]
//
// The output is `<output-dir>/<index-name>` plus the detail directory named after its stem — the
// same names `migrate.py` wrote (default `index.md` + `index/`).
//
// exit 0 = nothing lost, both extractions agree  ·  1 = findings  ·  2 = usage / IO
//
// `migrate.py` reports what it could not derive. This answers the different question — what it did
// not SEE — and every trap in reference/migration-traps.md was found by one of these two checks:
//
//   COVERAGE  does every non-blank source LINE, trimmed, appear somewhere in the output?
//             Line-level and trimmed, not byte-level: re-indentation is not loss, and the question
//             is whether the CONTENT survived. It will not catch a line that moved into a
//             different item, or one whose leading whitespace changed meaning. Item BODIES are
//             checked verbatim and whole, which is the exact half. Traps 6 and 7 were invisible to
//             every count: bodies read a clean 251/251 while 23 section intros and one whole item
//             were on the floor. A check whose unit is the thing the tool already models cannot
//             see what the tool does not model.
//
//   STATUS    does a SECOND extractor, written differently, agree on WHICH items are closed?
//             Traps 4 and 5. The counts were 44 against 40 and the near-match read as agreement
//             until the two were diffed as sets — four apart still looks close enough.
//
// On independence, honestly: this is a DIFFERENTIAL check, not an independent one. The real cross-
// check that found traps 4 and 5 was written by someone who had not read `migrate.py`, and no
// shipped file can preserve that. Two things still make it worth running — it is written in the
// other language, so the two cannot share code by accident, and it derives the status zone from
// the item's structure rather than by pattern, so they fail differently. What it will not do is
// notice a shape BOTH implementations get wrong. When this passes and something still looks off,
// hand-write a third extractor; that is what the traps document means by refusing a near-match.

import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

const argv = process.argv.slice(2);
const nameFlag = argv.indexOf("--index-name");
const indexName = nameFlag >= 0 ? argv[nameFlag + 1] : "index.md";
const positional = nameFlag >= 0 ? argv.filter((a, i) => i !== nameFlag && i !== nameFlag + 1) : argv;
const [source, outDir] = positional;
if (!source || !outDir || !indexName) {
  process.stderr.write("usage: verify-migration.mjs <source-ledger.md> <output-dir> [--index-name index.md]\n");
  process.exit(2);
}

let srcText;
try {
  srcText = readFileSync(source, "utf-8");
} catch (e) {
  process.stderr.write(`cannot read ${source}: ${e.message}\n`);
  process.exit(2);
}

const detailDir = path.join(outDir, indexName.replace(/\.md$/u, ""));
const indexPath = path.join(outDir, indexName);
let indexText, detailFiles;
try {
  indexText = readFileSync(indexPath, "utf-8");
  detailFiles = readdirSync(detailDir).filter((n) => n.endsWith(".md")).sort();
} catch (e) {
  process.stderr.write(`cannot read the migration output under ${outDir}: ${e.message}\n`);
  process.exit(2);
}

const details = detailFiles.map((name) => {
  const text = readFileSync(path.join(detailDir, name), "utf-8");
  const end = text.indexOf("\n---", 4);
  return {
    name,
    front: text.slice(0, end + 4),
    body: text.slice(end + 4).trim(),
    status: (/^status:[ \t]*(?<s>.*)$/mu.exec(text)?.groups.s ?? "").trim(),
  };
});

// ---------------------------------------------------------------- segmentation
// Section = a `## ` heading and everything to the next one. Item = a top-level `- ` bullet and
// everything to the next one, which is why an item's block can hold a trailing sub-heading.
// Segmentation MUST match migrate.py's, fold and all. It did not, once: migrate.py learned to fold
// a `### ` record and this did not, so the two counted 247 and 251 and every position after the
// first fold was off by one — 67 spurious status disagreements on a correct migration. A
// differential check whose two sides disagree about what an ITEM is compares nothing.
const FIELD_BULLET = /^- \*\*[A-Z][A-Za-z /]{0,24}:\*\*/u;
const lines = srcText.split("\n");
const secStarts = lines.map((l, i) => (l.startsWith("## ") ? i : -1)).filter((i) => i >= 0);
const items = [];
const sections = [];
for (const [k, a] of secStarts.entries()) {
  const b = secStarts[k + 1] ?? lines.length;
  const body = lines.slice(a + 1, b);
  const bullets = body.map((l, i) => (/^- /u.test(l) ? i : -1)).filter((i) => i >= 0);
  const subs = body.map((l, i) => (l.startsWith("### ") ? i : -1)).filter((i) => i >= 0);

  // A record need not contain a bullet — migrate.py folds a bulletless section into one item per
  // `### ` run, or into a single item when it has no sub-headings. This side MUST fold identically:
  // when migrate.py learned to fold `### `-field records and this did not, the two counted 247
  // against 251 and every position after the first fold was off by one, burying the real findings
  // under 67 spurious ones. A differential check whose sides disagree about what an ITEM is
  // compares nothing.
  const bulletlessUnits =
    bullets.length > 0
      ? []
      : subs.length > 0
        ? subs.map((s) => ({ start: s, e: subs.find((x) => x > s) ?? body.length }))
        : [{ start: 0, e: body.length }];
  sections.push({ head: lines[a], line: a + 1, hasItems: bullets.length > 0 || bulletlessUnits.length > 0 });

  const folded = new Map();
  for (const si of subs) {
    const end = subs.find((x) => x > si) ?? body.length;
    const run = bullets.filter((x) => x > si && x < end);
    if (run.length > 0 && run.every((x) => FIELD_BULLET.test(body[x]))) {
      folded.set(run[0], { si, end });
      for (const x of run.slice(1)) folded.set(x, null);
    }
  }

  for (const u of bulletlessUnits) {
    const block = body.slice(u.start, u.e).join("\n").replace(/\s+$/u, "");
    // When the whole section is the record, its OWN TEXT is the `## ` heading — which sits outside
    // the block, because migrate.py writes the body verbatim and the heading separately. Without
    // this override the two sides read different zones and disagree on status for every such
    // record: three on the corpus that motivated the fold, each a real closure read as open. (A
    // `### ` unit needs no override; its block already starts at the heading.)
    const own = u.start === 0 && subs.length === 0 ? lines[a] : undefined;
    if (block.trim()) items.push({ block, own, isRecord: true, line: a + 2 + u.start, sec: sections.length - 1 });
  }

  for (const [j, s] of bullets.entries()) {
    let start = s;
    let e = bullets[j + 1] ?? body.length;
    let isRecord = false;
    if (folded.has(s)) {
      const rec = folded.get(s);
      if (rec === null) continue;                      // a field absorbed into the record above
      isRecord = true;
      start = rec.si;
      e = rec.end;
    }
    const block = body.slice(start, e).join("\n").replace(/\s+$/u, "");
    if (block.trim()) items.push({ block, isRecord, line: a + 2 + start, sec: sections.length - 1 });
  }
}

const PREAMBLE = "\u0000preamble";
const findings = [];
const notices = [];
const add = (code, where, detail) => findings.push({ code, where, detail });

// ---------------------------------------------------------------- A. item parity
if (items.length > details.length) {
  add("ITEM_COUNT", path.basename(source),
    `${items.length} item blocks in the source, ${details.length} detail files — ${items.length - details.length} unaccounted for`);
}

// ---------------------------------------------------------------- B. verbatim bodies
const allBodies = details.map((d) => d.body).join("\n\n");
for (const it of items) {
  if (!allBodies.includes(it.block.trim())) {
    add("BODY_NOT_VERBATIM", `${path.basename(source)}:${it.line}`,
      `no detail file contains this item's block verbatim — ${it.block.split("\n")[0].slice(0, 70)}`);
  }
}

// ---------------------------------------------------------------- C. line coverage
// Everything else: section headings, intro prose, a section with no bullets at all. Line-level
// because that content has no unit of its own — it is not an item, so nothing counts it.
const haystack = `${allBodies}\n${indexText}`;
const uncovered = new Map();
for (const [i, raw] of lines.entries()) {
  const line = raw.trim();
  if (!line) continue;
  if (haystack.includes(line)) continue;
  const sec = sections.filter((s) => s.line <= i + 1).pop();
  // Content above the first `## ` is the file's PREAMBLE, and the migration replaces it with the
  // index's own header on purpose: a preamble typically documents the old layout ("one bullet =
  // one item", "mark it **DONE**"), which is exactly what stops being true. Reported, not failed —
  // but printed in full, because it is also where a policy note or an owner would have been.
  const key = sec ? sec.head.slice(0, 70) : PREAMBLE;
  if (!uncovered.has(key)) uncovered.set(key, []);
  uncovered.get(key).push({ n: i + 1, line });
}
for (const [sec, ls] of uncovered) {
  if (sec === PREAMBLE) {
    notices.push(`the preamble above the first section was replaced by the index header — ${ls.length} line(s), read them before committing:`);
    for (const l of ls) notices.push(`    ${String(l.n).padStart(5)}  ${l.line.slice(0, 96)}`);
    continue;
  }
  add("CONTENT_DROPPED", `${path.basename(source)}:${ls[0].n}`,
    `${ls.length} line(s) appear nowhere in the output, under ${sec} — first: ${ls[0].line.slice(0, 70)}`);
}

// ---------------------------------------------------------------- D. the second extractor
// Deliberately NOT migrate.py's method: code spans are stripped structurally, so prose that quotes
// the convention cannot match, rather than being excluded by spotting a `YYYY-MM-DD` placeholder.
// Same six words migrate.py knows. Sharing the VOCABULARY is fine — it is corpus data, and the two
// still derive the zone differently, which is the axis this check exists to compare. What sharing
// cannot catch is the vocabulary itself being wrong, and that is exactly how seven closed items
// shipped `open` past a green gate: both sides knew only DONE|KILLED. Hence UNKNOWN_MARKER below —
// it reports marker-shaped words neither side claims, which is the only signal a vocabulary gap has.
const CLOSED = /\*\*\s*(?:[^\w\s]\s*)?(?:DONE|KILLED|CLOSED|SUPERSEDED|RETIRED|RESOLVED)\b/u;
const HEADING_CLOSED = /(?:^|[—–\-|(]\s*)(DONE|KILLED|CLOSED|SUPERSEDED|RETIRED|RESOLVED)\b/u;
const HEDGE = /(HALF|NOT|MOSTLY|PARTLY|PARTIALLY|NEARLY)\s*$/iu;
const STRUCK = /^-\s+~~/u;

const ownText = (block) => {
  const out = [];
  for (const [k, ln] of block.split("\n").entries()) {
    if (k && /^\s+[-*] /u.test(ln)) break;          // a child bullet is context, not status
    if (k && ln.trim() && !/^\s/u.test(ln)) break;  // the left margin has left the item
    out.push(ln);
  }
  return out.join(" ").split(/\s+/u).join(" ");
};

const theirs = new Set();
details.forEach((d, i) => { if (d.status && d.status !== "open") theirs.add(i + 1); });

const mine = new Set();
items.forEach((it, i) => {
  const flat = ownText(it.own ?? it.block);
  if (STRUCK.test(flat)) { mine.add(i + 1); return; }
  const bare = flat.replace(/`[^`]*`/gu, " ");
  const m = CLOSED.exec(bare);
  if (m && !HEDGE.test(bare.slice(0, m.index + 2).replace(/\*\*/gu, " "))) { mine.add(i + 1); return; }
  // A RECORD's own text is a heading, and a heading is already emphasised — so its author has no
  // reason to bold the marker, and every pattern above needs a `**`. Anchored to the heading's
  // start or the position after a separator, exactly as migrate.py's HEADING_MARK is: when a
  // definition changes, the question is not "did I fix it" but "who else holds a copy".
  if (!it.isRecord) return;
  const h = HEADING_CLOSED.exec(bare.replace(/^#+\s*/u, ""));
  if (h && !HEDGE.test(bare.slice(0, h.index + h[0].length - h[1].length))) mine.add(i + 1);
});

// Diffed as SETS. Comparing sizes is what let a 4-item disagreement read as agreement.
if (items.length === details.length) {
  for (const n of [...mine].filter((n) => !theirs.has(n)).sort((a, b) => a - b)) {
    add("STATUS_DISAGREE", `${path.basename(source)}:${items[n - 1].line}`,
      `this extractor reads CLOSED, the migration wrote '${details[n - 1].status}' — ${ownText(items[n - 1].block).slice(0, 80)}`);
  }
  for (const n of [...theirs].filter((n) => !mine.has(n)).sort((a, b) => a - b)) {
    add("STATUS_DISAGREE", `${path.basename(source)}:${items[n - 1].line}`,
      `the migration wrote '${details[n - 1].status}', this extractor reads OPEN — ${ownText(items[n - 1].block).slice(0, 80)}`);
  }
} else if (details.length < items.length) {
  add("STATUS_UNCHECKED", path.basename(source),
    "fewer detail files than source items, so they cannot be lined up — fix that before reading any status");
} else {
  // MORE detail files than source items is the ordinary post-adoption state: the index is
  // hand-maintained from here, so items get added and the source ledger stops being a mirror.
  // Reported, not failed — a gate that can never go green again after the day it was adopted is
  // one people stop running, and this check is still worth running for the coverage half.
  notices.push(`${details.length - items.length} more detail file(s) than source items — added since the migration.`);
  notices.push("    Status comparison skipped: items and detail files can no longer be lined up by position.");
}

// ---------------------------------------------------------------- E. vocabulary gaps
// A word sitting where a status marker sits, on an item that migrated OPEN, that neither side
// recognises. Reported as a NOTICE with one example each, because most are ordinary emphasis
// (`**STILL OPEN…`, `**DECIDED at…`) and a few are the ledger's own closed vocabulary that this
// tool has never heard of. Telling those apart is a person's job; SEEING them is not, and nothing
// else in either tool can. This is the check that would have caught the seven.
const MARKERISH = /\*\*\s*(?:[^\w\s]\s*)*([A-Z][A-Z]{3,})\b/gu;
const unknown = new Map();
if (items.length === details.length) {
  items.forEach((it, i) => {
    if (theirs.has(i + 1)) return;                       // it migrated closed; nothing was missed
    const bare = ownText(it.block).replace(/`[^`]*`/gu, " ");
    for (const m of bare.matchAll(MARKERISH)) {
      if (CLOSED.test(`**${m[1]}`)) continue;
      if (!unknown.has(m[1])) unknown.set(m[1], { n: 0, eg: bare.slice(0, 74), line: it.line });
      unknown.get(m[1]).n += 1;
    }
  });
}
if (unknown.size) {
  notices.push(`${unknown.size} marker-shaped word(s) on items that migrated OPEN are not in the closed vocabulary.`);
  notices.push("    If any of these retires an item in your ledger, add it to CLOSED_WORDS in migrate.py and re-run:");
  for (const [w, v] of [...unknown].sort((a, b) => b[1].n - a[1].n)) {
    notices.push(`    ${String(v.n).padStart(3)}x  ${w.padEnd(12)} e.g. :${v.line}  ${v.eg}`);
  }
}

// ---------------------------------------------------------------- report
for (const n of notices) process.stdout.write(`${n.startsWith("    ") ? "" : "NOTICE             "}${n}\n`);
for (const f of findings) process.stdout.write(`${f.code.padEnd(18)} ${f.where}: ${f.detail}\n`);
process.stdout.write(
  findings.length === 0
    ? `verify-migration: ${items.length} items, ${sections.length} sections — nothing dropped, both extractions agree on ${mine.size} closed\n`
    : `verify-migration: ${findings.length} finding(s) — do NOT commit this migration yet\n`,
);
process.exit(findings.length === 0 ? 0 : 1);
