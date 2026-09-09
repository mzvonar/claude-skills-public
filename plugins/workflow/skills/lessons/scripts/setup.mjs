#!/usr/bin/env node
// Idempotent bootstrap for the `lessons` skill in ANY repo:
//   1. creates the lessons inbox (default docs/lessons-inbox.md) if missing
//   2. appends the standing capture rule to CLAUDE.md if missing (creating CLAUDE.md if absent)
// Optional overrides come from .claude/claude-skills.json, key "lessons":
//   orchestratorSkills (string[]), inboxPath (string), guidelinesSkill (string)
// Usage: node setup.mjs [repo-root]   — defaults to the git root of the current directory.
// Commits nothing. Safe to re-run.

import { execSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const SKILL = "/workflow:lessons";
const DEFAULTS = {
  inboxPath: "docs/lessons-inbox.md",
  guidelinesSkill: "/workflow:update-guidelines",
  orchestratorSkills: [],
};

function repoRoot(arg) {
  if (arg) return resolve(arg);
  try {
    return execSync("git rev-parse --show-toplevel", {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return process.cwd();
  }
}

function nonEmptyString(value, fallback) {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function loadSettings(root) {
  const configPath = join(root, ".claude", "claude-skills.json");
  let section = {};
  if (existsSync(configPath)) {
    try {
      const parsed = JSON.parse(readFileSync(configPath, "utf8"));
      if (parsed && typeof parsed.lessons === "object" && parsed.lessons !== null) {
        section = parsed.lessons;
      }
    } catch (err) {
      console.warn(`warning: ignoring unparsable ${configPath}: ${err.message}`);
    }
  }
  const orchestratorSkills = Array.isArray(section.orchestratorSkills)
    ? section.orchestratorSkills.filter((s) => typeof s === "string" && s.trim()).map((s) => s.trim())
    : DEFAULTS.orchestratorSkills;
  return {
    inboxPath: nonEmptyString(section.inboxPath, DEFAULTS.inboxPath),
    guidelinesSkill: nonEmptyString(section.guidelinesSkill, DEFAULTS.guidelinesSkill),
    orchestratorSkills,
  };
}

// "outside `/a` / `/b`, which own their own lesson pipeline" — or the generic form.
function outsidePhrase(orchestratorSkills) {
  if (orchestratorSkills.length === 0) {
    return "outside your story orchestrator, if any — an orchestrated flow owns its own lesson pipeline";
  }
  const names = orchestratorSkills.map((s) => `\`${s}\``).join(" / ");
  const verb = orchestratorSkills.length === 1 ? "has" : "have";
  return `outside ${names}, which ${verb} ${orchestratorSkills.length === 1 ? "its" : "their"} own lesson pipeline`;
}

function inboxTemplate(settings) {
  return `# Lessons inbox

Transient, append-only buffer for durable lessons captured during **ad-hoc work** (${outsidePhrase(settings.orchestratorSkills)}). This is **not a permanent home** — entries live here only until the user says **"process the lessons"**, at which point the \`${SKILL}\` skill promotes each to its real destination (a skill body, CLAUDE.md, an ADR, a narrative doc, the wiki, memory) or discards it, then removes the entry.

Capture trigger + routing rules live in the \`${SKILL}\` skill. **Newest entries go at the top of the log, directly under the marker below.**

<!-- LESSONS-LOG -->

## YYYY-MM-DD — short title of the lesson   (example row — delete once you add a real one)
- **Context:** what work / branch / file this came from
- **Lesson:** the durable insight, stated as an actionable rule (what to do, and why)
- **Candidate home:** (optional guess) skill:<name> · CLAUDE.md · ADR · anchor · wiki · memory · discard
`;
}

const CLAUDE_MARKER = "Lessons capture (ad-hoc work)";

function claudeBlock(settings) {
  const opening =
    settings.orchestratorSkills.length === 0
      ? "Outside a story orchestrator (if this repo has one)"
      : `Outside ${settings.orchestratorSkills.map((s) => `\`${s}\``).join(" / ")}`;
  const inbox = settings.inboxPath;
  return `
---

## ${CLAUDE_MARKER} — append, process later

${opening} there is no lesson → guideline pipeline, so reusable insights from ad-hoc work get lost. **Whenever ad-hoc work surfaces a durable lesson — a correction worth keeping, a non-obvious gotcha, a rejected approach and why, a rule that should exist — append a dated entry to [\`${inbox}\`](${inbox})** the moment it's noticed (don't fix-and-forget; scrollback isn't reliably re-scannable later). The inbox is a transient buffer, never a durable home. Later, when the user says **"process the lessons"**, the \`${SKILL}\` skill drains it and promotes each entry to its real home (a skill body, CLAUDE.md via \`${settings.guidelinesSkill}\`, an ADR, a narrative doc, the wiki, or memory) or discards it. Standing instruction. Full format + routing → \`${SKILL}\`.
`;
}

function main() {
  const root = repoRoot(process.argv[2]);
  const settings = loadSettings(root);
  const inboxAbs = join(root, settings.inboxPath);
  const claudePath = join(root, "CLAUDE.md");

  const created = [];
  const skipped = [];

  if (existsSync(inboxAbs)) {
    skipped.push(`${settings.inboxPath} (already exists)`);
  } else {
    mkdirSync(dirname(inboxAbs), { recursive: true });
    writeFileSync(inboxAbs, inboxTemplate(settings));
    created.push(settings.inboxPath);
  }

  if (!existsSync(claudePath)) {
    writeFileSync(claudePath, `# Project Guidelines\n${claudeBlock(settings)}`);
    created.push("CLAUDE.md (created + capture rule)");
  } else {
    const current = readFileSync(claudePath, "utf8");
    if (current.includes(CLAUDE_MARKER)) {
      skipped.push("CLAUDE.md capture rule (already present)");
    } else {
      writeFileSync(claudePath, `${current.trimEnd()}\n${claudeBlock(settings)}`);
      created.push("CLAUDE.md capture rule (appended)");
    }
  }

  console.log("lessons skill — setup");
  console.log(`  repo root: ${root}`);
  if (settings.orchestratorSkills.length) {
    console.log(`  orchestrators: ${settings.orchestratorSkills.join(", ")}`);
  }
  if (created.length) console.log(`  created:   ${created.join(", ")}`);
  if (skipped.length) console.log(`  skipped:   ${skipped.join(", ")}`);
  console.log("Nothing committed — review and commit when ready.");
}

main();
