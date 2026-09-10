// backlog.mjs — the surface every grooming pass actually reads.
//
// The writer was fixed to emit YAML's escape for an apostrophe (a doubled quote) and the readers
// were not, so `SomeException''s` reached the reader output on a real corpus. Fixing
// an encoder without its decoder leaves the round-trip broken in the direction people SEE.

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, it } from "node:test";

const READER = path.join(import.meta.dirname, "..", "skills", "backlog", "scripts", "backlog.mjs");

const withItems = (items) => {
  const dir = mkdtempSync(path.join(tmpdir(), "dbk-r-"));
  mkdirSync(path.join(dir, "deferred-work"));
  for (const [name, body] of Object.entries(items)) {
    writeFileSync(path.join(dir, "deferred-work", name), body);
  }
  return dir;
};

const read = (dir, ...flags) =>
  execFileSync("node", [READER, path.join(dir, "deferred-work"), ...flags], { encoding: "utf-8" });

describe("backlog.mjs", () => {
  it("decodes a YAML doubled quote back to an apostrophe", () => {
    const dir = withItems({
      "dw-001-x.md": "---\nid: dw-001\nsummary: 'owner''s item'\ntrigger: 'when it''s time'\nstatus: open\n---\n- **Body.**\n",
    });
    try {
      const json = JSON.parse(read(dir, "--json"));
      assert.equal(json[0].summary, "owner's item", "the doubled quote reached the reader's output");
      assert.equal(json[0].trigger, "when it's time");
      assert.doesNotMatch(read(dir), /''/u, "the human-readable output still shows the escape");
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("leaves a bare scalar alone, quotes and all", () => {
    // Only a QUOTED scalar carries the escape. An unquoted value containing '' is literal text, and
    // decoding it would corrupt the very records the fix exists to keep faithful.
    const dir = withItems({
      "dw-001-x.md": "---\nid: dw-001\nsummary: it''s bare\nstatus: open\ntrigger: t\n---\n- **Body.**\n",
    });
    try {
      assert.equal(JSON.parse(read(dir, "--json"))[0].summary, "it''s bare");
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("filters every closed word, not just DONE and KILLED", () => {
    // The vocabulary lives in three consumers. A reader that knows two of six shows retired work as
    // live — which is what the widened vocabulary in migrate.py exists to prevent.
    const items = {};
    for (const [i, w] of ["DONE", "KILLED", "CLOSED", "SUPERSEDED", "RETIRED", "RESOLVED"].entries()) {
      items[`dw-00${i + 1}-c.md`] =
        `---\nid: dw-00${i + 1}\nsummary: 'closed ${w}'\nstatus: ${w} (2026-01-01)\ntrigger: t\n---\n- **B.**\n`;
    }
    items["dw-009-open.md"] = "---\nid: dw-009\nsummary: 'still open'\nstatus: open\ntrigger: t\n---\n- **B.**\n";
    const dir = withItems(items);
    try {
      assert.equal(JSON.parse(read(dir, "--json")).length, 1, "a closed word leaked into the open set");
      assert.equal(JSON.parse(read(dir, "--json", "--all")).length, 7);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });
});
