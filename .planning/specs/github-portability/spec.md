---
feature: github-portability
status: awaiting-director-approval
created: 2026-04-29
skill: dream-studio:think
---

# Spec: GitHub-Ready Portability

## Problem Statement

dream-studio is on GitHub but has four blockers that prevent anyone from cloning and using it:

1. `learn/config.yml` has a hardcoded Windows path (`C:\Users\Dannis Seay\builds`) that fails for every other user
2. `learn/SKILL.md` Step 4 references a user-specific Claude memory path (`C--Users-Dannis-Seay`) that is meaningless on any other machine
3. `handoff/SKILL.md` JSON schema has no `project_root` field — a fresh terminal session receiving a handoff file cannot locate the project without out-of-band knowledge
4. Onboarding (`workflow: run studio-onboard`) asks 3 questions but never captures `projects_root` and never resolves user-specific values into the config

The goal: any developer clones the repo, runs onboarding, and has a fully working dream-studio — no manual path editing, no broken harvest, no lost handoffs.

---

## User Stories

### P1 — New user can clone and onboard without manual file editing
**As a new user**, I want to run one onboarding command after cloning and have all user-specific values configured automatically — so I don't have to hunt for hardcoded paths in skill files.

**Acceptance**: After `workflow: run studio-onboard`, `learn: harvest` runs without path errors and finds the user's project directories.

### P1 — Handoff file is self-contained for session resume
**As the Director**, I want a handoff file to contain the absolute project path — so a fresh Claude Code session receiving only the handoff file can locate and resume the project without being told where it lives.

**Acceptance**: `handoff-<topic>.json` contains `"project_root": "/absolute/path/to/project"`. A fresh session reading only this file can `cd` to the right directory and resume.

### P2 — Repo stays clean: no user paths in committed files
**As a contributor**, I want the committed skill files to contain zero user-specific paths — so git diff never shows personal directory names and contributors don't accidentally expose their file system layout.

**Acceptance**: `git grep "Dannis\|C:\\\\Users\|C--Users"` in the committed repo returns zero matches after portability changes.

### P2 — Auto-detect Claude memory path during onboarding
**As a new user**, I want onboarding to detect my Claude memory path automatically — so I don't have to understand the `C--Users-...` encoding scheme to configure harvest.

**Acceptance**: Onboarding resolves `claude_memory_path` without asking the user. Value written to `~/.dream-studio/config.json`. `learn: harvest` Step 4 reads it correctly.

### P3 — User can override projects_root without re-running full onboarding
**As the Director**, I want to update `projects_root` by editing one file in one place — so adding a new build root (e.g., a client laptop with different paths) takes under 60 seconds.

**Acceptance**: Editing `~/.dream-studio/config.json` `harvest.projects_root` is sufficient. No skill files need to be touched.

---

## Functional Requirements

**FR-001**: `~/.dream-studio/config.json` MUST be the single source of truth for all user-specific values. No user-specific values in committed skill files.

**FR-002**: Onboarding MUST ask for (or auto-detect) `projects_root` and write it to `~/.dream-studio/config.json`.

**FR-003**: Onboarding MUST auto-detect `claude_memory_path` using the deterministic encoding rule (`cwd` path → replace separators with `-`, drop colons) and write it to `~/.dream-studio/config.json`.

**FR-004**: `learn/config.yml` `projects_root` value MUST be replaced with an empty string or `null` in the committed repo. The skill MUST read the live value from `~/.dream-studio/config.json` at harvest time.

**FR-005**: `learn/SKILL.md` Step 4 MUST reference `claude_memory_path` from `~/.dream-studio/config.json` rather than a hardcoded path.

**FR-006**: `handoff/SKILL.md` MUST add `project_root` (absolute path of the project directory, captured at handoff time) to the JSON schema.

**FR-007**: Onboarding MUST be idempotent — re-running it updates values without breaking existing config.

---

## Success Criteria

**SC-001**: A fresh clone + onboarding on a machine with different username and path structure produces a working `learn: harvest` with no manual edits.

**SC-002**: `git grep -r "Dannis\|C--Users-Dannis"` in committed files returns zero matches.

**SC-003**: A handoff JSON file contains `project_root` pointing to an absolute path. A session reading only the JSON can resume without additional context.

**SC-004**: Re-running onboarding on an already-configured machine updates changed values and leaves unchanged values intact.

---

## Edge Cases

**EC-001 — User has no `~/.dream-studio/config.json`**: Skills that reference config values must fail gracefully with a message: "Run `workflow: run studio-onboard` to configure dream-studio before using this skill."

**EC-002 — User's projects are spread across multiple roots**: `projects_root` is a single path. Users with builds in two locations use `extra_paths` in config.json. Onboarding should mention this option but not require it.

**EC-003 — Claude memory path auto-detection fails** (e.g., Claude not yet used in this directory): Onboarding falls back to asking the user for the path rather than silently writing a wrong value.

**EC-004 — Windows vs Unix path separators**: The encoding for `claude_memory_path` differs between platforms. Onboarding must use platform-appropriate encoding (`\` → `-` on Windows, `/` → `-` on Unix, colons dropped on both).

**EC-005 — User clones to a path that changes later**: `project_root` in handoff JSON is the path at time of handoff. If the project moves, the field is stale. No fix needed — stale path is obvious; user updates the path in the resume command manually.

---

## Approaches Considered

### Option A: Onboard-time file rewriting (simplest to use, worst for git)
Onboarding reads skill files, replaces `{{PROJECTS_ROOT}}` and `{{MEMORY_PATH}}` placeholders with real values, writes back. Committed repo has placeholder tokens; post-onboard files have real values.

**Pros**: Skills work with zero runtime logic. No "read config.json first" step. Familiar pattern (like `.env` substitution).

**Cons**: Real paths end up in skill files. Users who commit from their fork expose their path layout. Onboarding must re-run to change values. Template vs resolved state is ambiguous. **Verdict: rejected** — violates FR-002 (committed files must stay clean).

### Option B: Runtime template resolution (most flexible, most complex)
Skills use `{{config.harvest.projects_root}}` syntax. A "config resolver" hook or step runs before any skill that needs config values, reads `~/.dream-studio/config.json`, substitutes tokens.

**Pros**: Repo is always clean. Config changes take effect immediately without touching skill files.

**Cons**: Requires a resolution mechanism that Claude Code doesn't have natively. Would need a hook or a mandatory "Step 0: resolve config" in every affected skill. Fragile — easy to add a new skill that forgets the resolution step. **Verdict: rejected** — over-engineered for the actual problem.

### Option C: `~/.dream-studio/config.json` as explicit reference, skills read it directly (recommended)
Skills are written as instructions to Claude. Instead of template tokens, the skill instructions say: *"Read `~/.dream-studio/config.json` for `harvest.projects_root`. If missing, stop and direct user to run onboarding."* The config.yml files in skills/ drop user-specific values entirely (empty string or `null`). Onboarding populates config.json. No substitution engine needed.

**Pros**: Clean repo — no tokens, no user paths. Works with how Claude Code actually works (instruction-following, not template processing). Single config location (`~/.dream-studio/config.json`). Onboarding is a one-time write; updating config.json immediately affects all skills. Matches existing pattern (config.json already used for `director_name`, `domain`, `primary_use`).

**Cons**: Skills need one explicit instruction added ("read from config.json"). Two files need updating in the repo (`learn/config.yml` value cleared, `learn/SKILL.md` Step 4 reworded). `handoff/SKILL.md` needs one new JSON field.

**Recommended: Option C** — minimal changes, clean git history, works with how Claude Code already operates.

---

## Implementation Scope (for plan phase)

**5 files change:**

1. `learn/config.yml` — set `projects_root: ""` (blank, not hardcoded path)
2. `learn/SKILL.md` — Step 4: replace hardcoded memory path with: "Read `claude_memory_path` from `~/.dream-studio/config.json`. If not set, stop and direct user to run onboarding."
3. `handoff/SKILL.md` — add `"project_root"` to JSON schema (populated from `pwd` at handoff time)
4. `handoff/SKILL.md` — add instruction to populate `project_root` in Step 6 (Write both files)
5. Onboarding workflow (`workflows/` or equivalent) — add two steps: ask/detect `projects_root`, auto-detect `claude_memory_path`, write both to `~/.dream-studio/config.json`

**One new skill instruction needed:**
Add a "Config check" step to `learn/SKILL.md` `## Harvest Mode`: before running harvest, verify `~/.dream-studio/config.json` exists and `harvest.projects_root` is non-empty. If missing: "Run `workflow: run studio-onboard` to configure harvest before continuing."

---

## What This Does NOT Change

- All `skills/**` logic — fully portable already
- `packs/**`, `hooks/**`, `docs/**` — no user-specific content
- The 3 existing onboarding questions (`director_name`, `domain`, `primary_use`)
- `.sessions/`, `meta/` — runtime dirs, not committed
- Any project-level GOTCHAS.md or CONSTITUTION.md — per-project, user-owned

---

## Next Step

Waiting for Director approval before moving to `dream-studio:plan`.
