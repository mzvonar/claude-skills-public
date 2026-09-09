#!/usr/bin/env python3
"""
codebase-map / set_markdown.py  —  inject (or clear) a module's drill-down markdown
in enrichment.json without manual JSON escaping. No LLM.

Usage:
  set_markdown.py --module <id> --md-file outline.md  [--in .codemap]
  set_markdown.py --module <id> --clear               [--in .codemap]   # revert to auto-generated
"""
import os, json, argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", required=True)
    ap.add_argument("--md-file")
    ap.add_argument("--clear", action="store_true")
    ap.add_argument("--in", dest="indir", default=".codemap")
    args = ap.parse_args()

    epath = os.path.join(args.indir, "enrichment.json")
    enr = json.load(open(epath)) if os.path.exists(epath) else {"modules": {}}
    enr.setdefault("modules", {}).setdefault(args.module, {})

    if args.clear:
        enr["modules"][args.module].pop("markdown", None)
        action = "cleared (reverts to auto-generated endpoint list)"
    else:
        if not args.md_file:
            raise SystemExit("provide --md-file or --clear")
        md = open(args.md_file, encoding="utf-8").read().strip()
        enr["modules"][args.module]["markdown"] = md
        action = f"set ({md.count(chr(10)) + 1} lines)"

    json.dump(enr, open(epath, "w"), indent=1)
    print(f"{args.module}: markdown {action}  ->  {epath}")
    print("rebuild with: python3 build.py --in {0} --out <site>".format(args.indir))


if __name__ == "__main__":
    main()
