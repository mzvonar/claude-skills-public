// The three migration traps, as permanent fixtures.
//
// Each was LIVE in migrate.py against a real 3,622-line ledger, and each is silent: the migration
// completes and the counts look plausible. A synthetic corpus containing all three is the only way
// they stay closed — nothing about the shipped output would reveal a regression.

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, it } from "node:test";

const MIGRATE = path.join(import.meta.dirname, "..", "skills", "backlog", "scripts", "migrate.py");

// One section, seven items. Six are closed in six different real spellings; one is open. Two further
// bullets look closed and are not. A migrator that reads this correctly finds SIX.
const CORPUS = `# Deferred work

## Deferred from: code review of item-11

- **DONE (2026-08-04)** the documented spelling.
- **✅ DONE (2026-08-04, item-35)** emoji prefix and a second field in the parens.
- **DONE upstream (2026-08-31, some-branch)** a word between the marker and the paren.
- **KILLED (2026-07-27, superseded)** the killed spelling.
- ~~struck through, no marker at all~~ retired in place.
- **DONE (2026-08-31, a long parenthetical that wraps onto the following line and only
  closes here) the line-spanning case.**
- **An open item.** It stays open.
  - **❌ KILLED (2026-09-01)** a NESTED sub-bullet — context for the parent, not a status for it.
- **A second open item.** Its body quotes the convention: mark it \`**DONE (YYYY-MM-DD)**\` when retired.
- **Third open item.** Progress note only: the rem switch is HALF DONE (2026-07-20), not finished.
`;

const migrate = (corpus, extraArgs = [], stem = "index") => {
  const dir = mkdtempSync(path.join(tmpdir(), "dbk-"));
  const src = path.join(dir, "source.md");
  writeFileSync(src, corpus);
  const out = path.join(dir, "out");
  const stdout = execFileSync("python3", [MIGRATE, src, out, ...extraArgs], { encoding: "utf-8" });
  const files = readdirSync(path.join(out, stem));
  const status = files.map((f) => {
    const t = readFileSync(path.join(out, stem, f), "utf-8");
    return /^status: (?<s>.*)$/mu.exec(t)?.groups.s ?? "";
  });
  return { dir, files, status, stdout };
};

describe("migrate.py", () => {
  it("counts every closed spelling, and no false positive", () => {
    const { dir, status } = migrate(CORPUS);
    try {
      const closed = status.filter((s) => /^(DONE|KILLED)/u.test(s));
      const open = status.filter((s) => s === "open");
      // SIX closed: documented, emoji, word-before-paren, KILLED, struck-through, line-spanning.
      // THREE open: the nested-KILLED parent, the convention-quoting body, the HALF DONE note.
      assert.equal(closed.length, 6, `closed spellings: got ${JSON.stringify(status)}`);
      assert.equal(open.length, 3, `open items: got ${JSON.stringify(status)}`);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("does not let a nested sub-bullet's status leak onto its parent", () => {
    // Trap 2. A character window over the item block reaches the child; scope is the bullet line.
    const { dir, files, status } = migrate(CORPUS);
    try {
      const i = files.findIndex((f) => f.includes("an-open-item"));
      assert.notEqual(i, -1, `expected an item file for the nested-child parent, got ${files}`);
      assert.equal(status[i], "open", "the parent of a KILLED sub-bullet must stay open");
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("reads a status parenthetical that wraps onto the next line", () => {
    // Trap 3. Requiring the closing paren on line 1 silently drops this item.
    const { dir, status } = migrate(CORPUS);
    try {
      assert.ok(status.includes("DONE (2026-08-31)"), `line-spanning date lost: ${JSON.stringify(status)}`);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("is lossless — every source item body survives verbatim", () => {
    const { dir, files } = migrate(CORPUS);
    try {
      const out = path.join(dir, "out", "index");
      const bodies = files.map((f) => readFileSync(path.join(out, f), "utf-8").split("---\n")[2]);
      for (const probe of ["the line-spanning case", "HALF DONE (2026-07-20)", "context for the parent"]) {
        assert.ok(bodies.some((b) => b.includes(probe)), `dropped from every detail body: ${probe}`);
      }
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("reports items it could not derive a trigger for, rather than inventing one", () => {
    const { dir, stdout } = migrate(CORPUS);
    try {
      assert.match(stdout, /open with NO trigger: [1-9]/u, `expected untriaged items to be reported: ${stdout}`);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("writes index.md + index/ by default, and the index pointers use that stem", () => {
    const { dir } = migrate(CORPUS);
    try {
      const index = readFileSync(path.join(dir, "out", "index.md"), "utf-8");
      assert.match(index, /^ {2}detail: `index\/dw-001-[^`]+\.md`$/mu, index);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("keeps a generator-owned index name via --index-name", () => {
    // A tool that appends to `deferred-work.md` by name must keep finding it after migration.
    const { dir, files } = migrate(CORPUS, ["--index-name", "deferred-work.md"], "deferred-work");
    try {
      assert.ok(existsSync(path.join(dir, "out", "deferred-work.md")), "index kept its name");
      assert.ok(files.length > 0, "detail files live under the stem directory");
      const index = readFileSync(path.join(dir, "out", "deferred-work.md"), "utf-8");
      assert.match(index, /detail: `deferred-work\//u);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });
});
