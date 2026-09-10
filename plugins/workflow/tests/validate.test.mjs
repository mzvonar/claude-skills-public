import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, it } from "node:test";

import { scanBacklog } from "../skills/backlog/scripts/validate.mjs";

// The index name is a parameter (the default is `index.md`); the fixtures use a non-default name
// so the stem -> detail-directory derivation is exercised, not just assumed.
const INDEX_NAME = "deferred-work.md";
const STEM = "deferred-work";

// A deferred-work index declares its policy; a plain backlog omits it. That one line is the whole
// difference between the two modes.
const INDEX =
  "---\npolicy: deferred-work\n---\n\n# index\n\n" +
  `- id: dw-001\n  summary: A\n  detail: \`${STEM}/dw-001-a.md\`\n` +
  `- id: dw-002\n  summary: B\n  detail: \`${STEM}/dw-002-b.md\`\n`;

const detail = (fm) => `---\n${Object.entries(fm).map(([k, v]) => `${k}: ${v}`).join("\n")}\n---\n\n- The record.\n`;

/** A clean two-item backlog. Every offender below is one mutation away from this. */
const cleanTree = () => {
  const dir = mkdtempSync(path.join(tmpdir(), "dbk-v-"));
  mkdirSync(path.join(dir, STEM));
  writeFileSync(path.join(dir, STEM, "dw-001-a.md"), detail({ id: "dw-001", status: "open", summary: "'A'", trigger: "'when X'" }));
  writeFileSync(path.join(dir, STEM, "dw-002-b.md"), detail({ id: "dw-002", status: "DONE (2026-01-01)", summary: "'B'" }));
  writeFileSync(path.join(dir, INDEX_NAME), INDEX);
  return dir;
};

const scan = (dir) => scanBacklog(path.join(dir, INDEX_NAME));
const codes = (f) => f.map((x) => x.code).toSorted();

describe("scanBacklog", () => {
  it("finds nothing in a clean backlog — the positive control", () => {
    // Without this, every offender row below also passes against a scanner that flags everything.
    const dir = cleanTree();
    try {
      assert.deepEqual(scan(dir), []);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("reports a missing index rather than reporting a clean empty backlog", () => {
    const dir = mkdtempSync(path.join(tmpdir(), "dbk-empty-"));
    try {
      assert.deepEqual(codes(scan(dir)), ["NO_INDEX"]);
      // A bare directory means `<dir>/index.md`, the default name.
      assert.deepEqual(scanBacklog(dir).map((f) => f.where), ["index.md"]);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  // Exact finding sets, never `contains`: a surface the scanner is blind to yields zero findings,
  // which no content match distinguishes from a clean tree.
  const offenders = [
    ["an index pointer to a file that is not there", (d) =>
      writeFileSync(path.join(d, INDEX_NAME), `---\npolicy: deferred-work\n---\n\n- id: dw-009\n  summary: X\n  detail: \`${STEM}/gone.md\`\n`),
      ["DANGLING_DETAIL", "UNINDEXED", "UNINDEXED"]],
    ["a detail file nothing points at", (d) =>
      writeFileSync(path.join(d, STEM, "dw-003-c.md"), detail({ id: "dw-003", status: "open", summary: "'C'", trigger: "'t'" })),
      ["UNINDEXED"]],
    ["an open item with no trigger — untriaged, not keep-deferred", (d) =>
      writeFileSync(path.join(d, STEM, "dw-001-a.md"), detail({ id: "dw-001", status: "open", summary: "'A'" })),
      ["NO_TRIGGER"]],
    ["a detail file with no frontmatter at all", (d) =>
      writeFileSync(path.join(d, STEM, "dw-001-a.md"), "- just a bullet, no fence\n"),
      ["NO_FRONTMATTER"]],
    ["two detail files claiming the same id", (d) =>
      writeFileSync(path.join(d, STEM, "dw-001-a.md"), detail({ id: "dw-002", status: "open", summary: "'A'", trigger: "'t'" })),
      ["DUPLICATE_ID"]],
    // Expectation corrected against the run, and recorded rather than quietly fixed: this was
    // written as MISSING_FIELD + NO_TRIGGER. It is MISSING_FIELD alone — the item HAS a trigger,
    // and an absent `status` reads as open, which is the safe default. The next reader will make
    // the same guess.
    ["a required field missing", (d) =>
      writeFileSync(path.join(d, STEM, "dw-001-a.md"), detail({ id: "dw-001", trigger: "'t'", summary: "'A'" })),
      ["MISSING_FIELD"]],
    ["a stray non-markdown file in the detail directory", (d) =>
      writeFileSync(path.join(d, STEM, "notes.txt"), "scratch\n"),
      ["STRAY_FILE"]],
    ["a generator append with no detail file — untriaged, reported not failed-silently", (d) =>
      writeFileSync(path.join(d, INDEX_NAME),
        INDEX + "- source_spec: `spec-9.md`\n  summary: appended by a tool\n  evidence: why\n"),
      ["UNPROMOTED_APPENDS"]],
    // A file name appearing in PROSE is not a pointer. `indexText.includes(name)` accepted one, so
    // an unreferenced detail file read as indexed — invisible to the classifier and reported clean.
    ["a detail file mentioned only in prose, never pointed at", (d) => {
      writeFileSync(path.join(d, STEM, "dw-003-orphan.md"),
        "---\nid: dw-003\nsummary: 'Orphan.'\ntrigger: 'someday'\nstatus: open\n---\n- **Orphan.**\n");
      writeFileSync(path.join(d, INDEX_NAME),
        INDEX + `\nSee also \`${STEM}/dw-003-orphan.md\`, which nothing points at.\n`);
    }, ["UNINDEXED"]],
    // Two entries pointing at one file. The expected set is DUPLICATE_POINTER *alone*, and that is
    // the whole finding: three entries and three pointers stay balanced, so the count-based
    // UNPROMOTED_APPENDS check sees nothing while one entry has no detail file of its own. Written
    // expecting both, corrected by running it — the count is exactly what cannot notice this.
    ["two index entries pointing at the same detail file", (d) =>
      writeFileSync(path.join(d, INDEX_NAME),
        `${INDEX}- id: dw-777\n  summary: a duplicate pointer\n  detail: \`${STEM}/dw-001-a.md\`\n`),
      ["DUPLICATE_POINTER"]],
    // The OTHER append shape: a generator that writes one bare bullet per finding, no key at all.
    // Keying only on `source_spec:` was blind to it — an append could land with NOTHING reporting.
    ["a bare-bullet generator append, the older shape with no key", (d) =>
      writeFileSync(path.join(d, INDEX_NAME),
        INDEX + "- Guard the corrupt-enum read path — pre-existing, deferred.\n"),
      ["RAW_APPEND"]],
  ];

  for (const [name, mutate, expected] of offenders) {
    it(`flags ${name}`, () => {
      const dir = cleanTree();
      try {
        mutate(dir);
        assert.deepEqual(codes(scan(dir)), [...expected].toSorted());
      } finally {
        rmSync(dir, { force: true, recursive: true });
      }
    });
  }

  it("a plain backlog does not require a trigger — that rule is the deferred-work policy", () => {
    // The mode's whole surface. Without the policy line an item with no trigger is ordinary: a
    // backlog item is actionable when picked, not when a condition fires.
    const dir = cleanTree();
    try {
      writeFileSync(path.join(dir, INDEX_NAME), INDEX.replace("---\npolicy: deferred-work\n---\n\n", ""));
      writeFileSync(path.join(dir, STEM, "dw-001-a.md"), detail({ id: "dw-001", status: "open", summary: "'A'" }));
      assert.deepEqual(scan(dir), []);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("refuses a policy it does not implement rather than silently ignoring it", () => {
    // A typo or a policy from a newer version must not read as "no policy" — that would silently
    // drop whichever rules the author was relying on.
    const dir = cleanTree();
    try {
      writeFileSync(path.join(dir, INDEX_NAME), INDEX.replace("policy: deferred-work", "policy: kanban"));
      assert.deepEqual(codes(scan(dir)), ["UNKNOWN_POLICY"]);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("does not read detail bodies — only frontmatter decides", () => {
    // The body may quote the convention (`status: open` in prose) without changing the verdict;
    // that quoting is exactly what fooled the migrator's first status detector.
    const dir = cleanTree();
    try {
      writeFileSync(path.join(dir, STEM, "dw-002-b.md"),
        detail({ id: "dw-002", status: "DONE (2026-01-01)", summary: "'B'" }) +
        "\nRetire an item by writing `status: open` -> `status: KILLED (date)`.\n");
      assert.deepEqual(scan(dir), []);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });
});
