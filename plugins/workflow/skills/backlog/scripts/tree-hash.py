#!/usr/bin/env python3
"""tree-hash.py — deterministic content hash of a directory.

    python3 tree-hash.py <dir>        → prints a sha256 hex digest

Answers "are these two copies of a directory still identical?" without a git history to diff —
e.g. a skill's shipped template tree against the copy bootstrapped into a repo, or a backlog
directory before and after a tool ran over it. Path, exec bit and content all count, so a rename
that keeps every byte still moves the digest.

Self-contained on purpose: an integrity check that imports its one function from elsewhere degrades
to "unavailable" when that import is missing, silently and in every consumer at once.
"""
import hashlib, os, sys


def tree_hash(root):
    """POSIX-sorted relative paths + exec bit + sha256 per file.

    `__pycache__` and `*.pyc` are excluded — they appear from merely running the skill and would
    make the digest unstable for a copy nobody edited.
    """
    rels = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if fn.endswith(".pyc"):
                continue
            rels.append(os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/"))
    h = hashlib.sha256()
    for rel in sorted(rels):
        p = os.path.join(root, rel)
        h.update(rel.encode() + b"\0")
        h.update((b"x" if os.access(p, os.X_OK) else b"-") + b"\0")
        with open(p, "rb") as f:
            h.update(hashlib.sha256(f.read()).hexdigest().encode() + b"\0")
    return h.hexdigest()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: tree-hash.py <dir>", file=sys.stderr); sys.exit(2)
    if not os.path.isdir(sys.argv[1]):
        print(f"not a directory: {sys.argv[1]}", file=sys.stderr); sys.exit(2)
    print(tree_hash(sys.argv[1]))
