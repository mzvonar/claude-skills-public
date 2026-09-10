// verify-migration.mjs — the check that runs between migrating and committing.
//
// Its whole job is to FIRE, so every row here breaks something specific and asserts the code that
// catches it. The clean control comes first and is not optional: every negative row would also
// pass on a checker that reports nothing at all.
//
// Measured against the real corpus's own history: run against the migration that shipped with
// traps 4–7 live, it reports 85 CONTENT_DROPPED and exactly the 4 STATUS_DISAGREE items that were
// found by hand — at lines 507, 1956, 3408 and 3413.

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, it } from "node:test";

const SKILL = path.join(import.meta.dirname, "..", "skills", "backlog", "scripts");
const MIGRATE = path.join(SKILL, "migrate.py");
const VERIFY = path.join(SKILL, "verify-migration.mjs");

const CORPUS = `# Deferred work

Preamble prose that documents the old layout and is replaced on purpose.

## Section one, with intro prose

Context that no item repeats — why these were parked and who owns them.

- **A closed item.** **DONE (2026-08-04)** shipped.
- **An open item.** It stays open.
  - **KILLED (2026-09-01)** a child bullet, which is context and not a status.

## Section two

- **Another open item.** With a body of its own.
`;

// Runs migrate then verify, and returns verify's exit code and output rather than throwing.
const run = (mutate = () => {}, corpus = CORPUS) => {
  const dir = mkdtempSync(path.join(tmpdir(), "dbk-vm-"));
  const src = path.join(dir, "source.md");
  writeFileSync(src, corpus);
  const out = path.join(dir, "out");
  execFileSync("python3", [MIGRATE, src, out], { encoding: "utf-8" });
  mutate({ dir, out, src, detailDir: path.join(out, "index"), index: path.join(out, "index.md") });
  let status = 0;
  let stdout = "";
  try {
    stdout = execFileSync("node", [VERIFY, src, out], { encoding: "utf-8" });
  } catch (e) {
    status = e.status;
    stdout = `${e.stdout ?? ""}${e.stderr ?? ""}`;
  }
  return { dir, status, stdout };
};

const detail = (detailDir, needle) => {
  const name = readdirSync(detailDir).find((n) => n.includes(needle));
  assert.ok(name, `no detail file matching ${needle} in ${readdirSync(detailDir)}`);
  return path.join(detailDir, name);
};

describe("verify-migration.mjs", () => {
  it("passes a clean migration — the positive control", () => {
    // Mandatory: every row below would also pass against a checker that finds nothing, ever.
    const { dir, status, stdout } = run();
    try {
      assert.equal(status, 0, `expected a clean pass, got:\n${stdout}`);
      assert.match(stdout, /nothing dropped, both extractions agree on 1 closed/u);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("treats the replaced preamble as a NOTICE, not a failure", () => {
    // The migration replaces the file's preamble with the index header on purpose. Reported so the
    // adopter reads it — a policy note or an owner would have lived there — but it cannot fail.
    const { dir, status, stdout } = run();
    try {
      assert.equal(status, 0);
      assert.match(stdout, /NOTICE/u);
      assert.match(stdout, /Preamble prose that documents the old layout/u);
      assert.doesNotMatch(stdout, /CONTENT_DROPPED/u);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("catches a section's intro prose going missing — traps 6 and 7", () => {
    // The failure with no signature: item counts stay perfect while a section's context is gone.
    const { dir, status, stdout } = run(({ index }) => {
      const t = readFileSync(index, "utf-8");
      writeFileSync(index, t.replace("Context that no item repeats — why these were parked and who owns them.\n", ""));
    });
    try {
      assert.equal(status, 1, `expected a finding, got:\n${stdout}`);
      assert.match(stdout, /CONTENT_DROPPED/u);
      assert.match(stdout, /Context that no item repeats/u);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("catches a status the second extractor disagrees with — traps 4 and 5", () => {
    const { dir, status, stdout } = run(({ detailDir }) => {
      const f = detail(detailDir, "a-closed-item");
      writeFileSync(f, readFileSync(f, "utf-8").replace(/^status: .*$/mu, "status: open"));
    });
    try {
      assert.equal(status, 1, `expected a finding, got:\n${stdout}`);
      assert.match(stdout, /STATUS_DISAGREE/u);
      assert.match(stdout, /this extractor reads CLOSED, the migration wrote 'open'/u);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("catches the disagreement in the other direction too", () => {
    // Both directions matter: a migration that retires a live item is worse than one that misses a
    // closure, and a one-directional check would call it clean.
    const { dir, status, stdout } = run(({ detailDir }) => {
      const f = detail(detailDir, "an-open-item");
      writeFileSync(f, readFileSync(f, "utf-8").replace(/^status: open$/mu, "status: DONE (2026-01-01)"));
    });
    try {
      assert.equal(status, 1, `expected a finding, got:\n${stdout}`);
      assert.match(stdout, /the migration wrote 'DONE \(2026-01-01\)', this extractor reads OPEN/u);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("catches a detail body that is no longer the source's text", () => {
    const { dir, status, stdout } = run(({ detailDir }) => {
      const f = detail(detailDir, "another-open-item");
      writeFileSync(f, readFileSync(f, "utf-8").replace("With a body of its own.", "Reworded."));
    });
    try {
      assert.equal(status, 1, `expected a finding, got:\n${stdout}`);
      assert.match(stdout, /BODY_NOT_VERBATIM/u);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("catches a whole item that never reached a detail file", () => {
    const { dir, status, stdout } = run(({ detailDir }) => unlinkSync(detail(detailDir, "another-open-item")));
    try {
      assert.equal(status, 1, `expected a finding, got:\n${stdout}`);
      assert.match(stdout, /ITEM_COUNT/u);
      // With the counts out of step, items cannot be lined up with detail files — so the status
      // comparison says it did not run rather than reporting a screenful of false disagreements.
      assert.match(stdout, /STATUS_UNCHECKED/u);
      assert.doesNotMatch(stdout, /STATUS_DISAGREE/u);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("segments a `### ` record exactly as migrate.py does", () => {
    // The two sides must agree on what an ITEM is. When migrate.py learned to fold a `### ` record
    // and this did not, they counted 247 against 251 and every position after the first fold was
    // off by one — 67 spurious status disagreements on a correct migration. A differential check
    // whose halves disagree about the unit compares nothing, and it fails LOUDLY, which is worse
    // than useless: it buries the real findings.
    const RECORD = `# Deferred work

## A section

- **An ordinary item before the record.** Still an item.

### A record — **KILLED (2026-08-04)**

- **What:** the parked thing.
- **Trigger:** the work that unparks it.
`;
    const { dir, status, stdout } = run(undefined, RECORD);
    try {
      assert.equal(status, 0, `expected agreement, got:\n${stdout}`);
      assert.match(stdout, /2 items, 1 sections/u);
      assert.doesNotMatch(stdout, /STATUS_DISAGREE/u);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("does not fold when an ordinary bullet trails the record's fields", () => {
    // The guard's cost, pinned rather than discovered later: an ordinary item sharing the `### `
    // run means the heading is not unambiguously a record, so nothing folds and the fields stay
    // separate items. That is the SAFE direction — over-merging destroys summaries — but it is a
    // real limitation, and the ledger that hits it will read as three items where it means two.
    // Both sides behave identically here, which is what keeps the gate meaningful either way.
    const MIXED = `# Deferred work

## A section

### A record — **KILLED (2026-08-04)**

- **What:** the parked thing.
- **Trigger:** the work that unparks it.

- **An ordinary item sharing the run.** Suppresses the fold.
`;
    const { dir, status, stdout } = run(undefined, MIXED);
    try {
      assert.equal(status, 0, `the two sides must still agree:\n${stdout}`);
      assert.match(stdout, /3 items, 1 sections/u);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("does not fail on items added by hand after adoption — only skips the comparison", () => {
    // The ordinary post-adoption state: the index is hand-maintained, so detail files outnumber the
    // source ledger's items and position-matching stops working. A gate that goes permanently red
    // the day after it is adopted is one people stop running, and its coverage half still works.
    const { dir, status, stdout } = run(({ detailDir }) => {
      writeFileSync(path.join(detailDir, "dw-099-added-later.md"),
        "---\nid: dw-099\nsummary: 'Added by hand after adoption.'\ntrigger: 'someday'\nstatus: open\n---\n- **Added by hand after adoption.**\n");
    });
    try {
      assert.equal(status, 0, `a hand-added item must not fail the gate:\n${stdout}`);
      assert.match(stdout, /more detail file\(s\) than source items — added since the migration/u);
      assert.doesNotMatch(stdout, /STATUS_UNCHECKED/u);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("names marker-shaped words the vocabulary does not know — the vocabulary gap's only signal", () => {
    // The check that would have caught the seven. A vocabulary both implementations share is the
    // one thing a differential check is structurally blind to, so it cannot be a comparison — it
    // has to be "here are the words your ledger uses that neither of us claims", for a person.
    const WORDS = `# Deferred work

## Section

- **RETIRED (2026-09-03) — resolved elsewhere.** A closure this build understands.
- **ESCALATED (2026-09-03) — handed to the platform team.** One it does not.
- **An ordinary open item.** No marker at all.
`;
    const { dir, status, stdout } = run(undefined, WORDS);
    try {
      assert.equal(status, 0, `the notice must not fail the gate:\n${stdout}`);
      assert.match(stdout, /marker-shaped word\(s\) on items that migrated OPEN/u);
      assert.match(stdout, /ESCALATED/u);
      // RETIRED is in the vocabulary and closed its item, so it is not a gap.
      assert.doesNotMatch(stdout, /1x {2}RETIRED/u);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("honours --index-name so a generator-owned index name still verifies", () => {
    const dir = mkdtempSync(path.join(tmpdir(), "dbk-vm-"));
    const src = path.join(dir, "source.md");
    writeFileSync(src, CORPUS);
    const out = path.join(dir, "out");
    try {
      execFileSync("python3", [MIGRATE, src, out, "--index-name", "deferred-work.md"], { encoding: "utf-8" });
      const stdout = execFileSync("node", [VERIFY, src, out, "--index-name", "deferred-work.md"], { encoding: "utf-8" });
      assert.match(stdout, /nothing dropped, both extractions agree on 1 closed/u);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("exits 2 on a bad invocation, never 1", () => {
    // Usage failure must not be readable as "the migration has findings".
    for (const argv of [[], [path.join(tmpdir(), "dbk-nope.md"), path.join(tmpdir(), "dbk-nope")]]) {
      assert.throws(
        () => execFileSync("node", [VERIFY, ...argv], { encoding: "utf-8", stdio: "pipe" }),
        (e) => e.status === 2,
        `expected exit 2 for argv ${JSON.stringify(argv)}`,
      );
    }
  });
});
