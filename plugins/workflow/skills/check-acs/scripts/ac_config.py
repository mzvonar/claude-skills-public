#!/usr/bin/env python3
"""Per-repo configuration for check-acs, read from `.claude/claude-skills.json` (key `check-acs`).

  ac_config.py <key>          print the configured value (JSON for lists), or nothing if unset
  from ac_config import cfg   cfg('model'), cfg('outDir'), cfg('sectionPatterns')

The file is looked up by walking up from the current directory, so the scripts work from any
subdirectory of the repo. Every key is optional; callers apply their own defaults. Environment
variables (`AC_MODEL`) take precedence over the file — that resolution is the caller's job.
"""
import json, os, pathlib, sys

CONFIG_REL = pathlib.Path('.claude') / 'claude-skills.json'
SKILL_KEY = 'check-acs'

def find_config(start=None):
    d = pathlib.Path(start or os.getcwd()).resolve()
    for p in [d, *d.parents]:
        f = p / CONFIG_REL
        if f.is_file():
            return f
    return None

def load(start=None):
    f = find_config(start)
    if not f:
        return {}
    try:
        return json.loads(f.read_text()).get(SKILL_KEY, {}) or {}
    except (ValueError, OSError):
        return {}

def cfg(key, default=None, start=None):
    v = load(start).get(key)
    return default if v in (None, '', []) else v

if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('usage: ac_config.py <key>')
    v = cfg(sys.argv[1])
    if v is None:
        sys.exit(0)
    print(json.dumps(v) if isinstance(v, (list, dict)) else v)
