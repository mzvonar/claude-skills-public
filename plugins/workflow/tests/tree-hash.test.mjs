// tree-hash.py — "are these two copies of a directory still identical?"
//
// It once shipped IMPORTING A MODULE THAT WAS NEVER COMMITTED, so every invocation raised
// ModuleNotFoundError and the caller that swallowed stderr recorded "unavailable" instead of a
// digest — the check was inert in every consumer at once. A test that merely RUNS the script is
// what was missing; that row comes before any behavioural one for that reason.

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync, chmodSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, it } from "node:test";

const HASHER = path.join(import.meta.dirname, "..", "skills", "backlog", "scripts", "tree-hash.py");

const hash = (dir) => execFileSync("python3", [HASHER, dir], { encoding: "utf-8" }).trim();

const scratch = (files) => {
  const dir = mkdtempSync(path.join(tmpdir(), "dbk-th-"));
  for (const [rel, body] of Object.entries(files)) {
    const p = path.join(dir, rel);
    mkdirSync(path.dirname(p), { recursive: true });
    writeFileSync(p, body);
  }
  return dir;
};

describe("tree-hash.py", () => {
  it("runs, and returns a sha256 digest", () => {
    // The row that would have caught the missing import. It asserts nothing about the algorithm.
    const dir = scratch({ "SKILL.md": "x" });
    try {
      assert.match(hash(dir), /^[0-9a-f]{64}$/u);
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("is stable across runs on an unchanged tree", () => {
    const dir = scratch({ "SKILL.md": "x", "scripts/a.py": "print(1)\n" });
    try {
      assert.equal(hash(dir), hash(dir));
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("changes when a file's content changes — the whole point", () => {
    const dir = scratch({ "SKILL.md": "x" });
    try {
      const before = hash(dir);
      writeFileSync(path.join(dir, "SKILL.md"), "y");
      assert.notEqual(hash(dir), before, "an edited copy must not match its pin");
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("changes when a file is added, and when one is renamed", () => {
    // Content alone is not the subject: the path is hashed too, so a rename that preserves every
    // byte still moves the digest. Without the path, `git mv`-shaped drift would read as pristine.
    const dir = scratch({ "SKILL.md": "x" });
    try {
      const before = hash(dir);
      writeFileSync(path.join(dir, "NEW.md"), "");
      const added = hash(dir);
      assert.notEqual(added, before, "an added file must move the digest");

      const dir2 = scratch({ "RENAMED.md": "x" });
      try {
        assert.notEqual(hash(dir2), before, "a rename must move the digest");
      } finally {
        rmSync(dir2, { force: true, recursive: true });
      }
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("changes when a file's exec bit changes", () => {
    const dir = scratch({ "scripts/a.py": "print(1)\n" });
    try {
      chmodSync(path.join(dir, "scripts/a.py"), 0o644);
      const before = hash(dir);
      chmodSync(path.join(dir, "scripts/a.py"), 0o755);
      assert.notEqual(hash(dir), before, "the exec bit is part of what was vendored");
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("ignores __pycache__ and .pyc — running the skill must not look like editing it", () => {
    // A documented exclusion with no row is an untested claim. Merely importing a script writes
    // these, so without the exclusion every consumer that RAN the skill would report drift.
    const dir = scratch({ "scripts/a.py": "print(1)\n" });
    try {
      const before = hash(dir);
      mkdirSync(path.join(dir, "scripts", "__pycache__"), { recursive: true });
      writeFileSync(path.join(dir, "scripts", "__pycache__", "a.cpython-313.pyc"), "junk");
      writeFileSync(path.join(dir, "scripts", "stray.pyc"), "junk");
      assert.equal(hash(dir), before, "compiled artifacts must not move the digest");
    } finally {
      rmSync(dir, { force: true, recursive: true });
    }
  });

  it("exits 2 on a bad invocation rather than printing a digest", () => {
    // Usage failure must be distinguishable from "the tree hashed to nothing".
    for (const argv of [[], [path.join(tmpdir(), "dbk-does-not-exist")]]) {
      assert.throws(
        () => execFileSync("python3", [HASHER, ...argv], { encoding: "utf-8", stdio: "pipe" }),
        (e) => e.status === 2,
        `expected exit 2 for argv ${JSON.stringify(argv)}`,
      );
    }
  });
});
