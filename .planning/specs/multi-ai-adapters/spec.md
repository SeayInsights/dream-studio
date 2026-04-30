# Feature Specification: Multi-AI Adapter Build System

**Topic Directory**: `.planning/specs/multi-ai-adapters/`
**Created**: 2026-04-29
**Status**: Draft — awaiting Director approval
**Phase**: Park until after wedding website editor

---

## Problem Statement

dream-studio's 38 skills and domain knowledge are written in plain markdown/YAML — already AI-agnostic in content. But they only activate inside Claude Code today. Every other AI platform (Cursor, Copilot, Windsurf) requires its own format. A build script that auto-generates platform adapter files from the existing SKILL.md source of truth closes this gap without rewriting any skill content.

**Key constraint:** The Python hook runtime (hard enforcement) cannot be ported. Adapters for non-Claude-Code platforms provide guidance-only (soft enforcement). This is acceptable — the domain knowledge and workflow logic are still fully portable.

---

## Approaches

### Approach A — Concatenation (dumb merge)
Read all SKILL.md files, strip frontmatter, concatenate into one large platform file.

- **Pro:** Simple to build, no template logic
- **Con:** Loses skill boundaries, becomes an unreadable wall of text. Cursor/Copilot work best with structured rules, not one blob. Gotchas and domain knowledge get buried.
- **Verdict:** Not viable for 38 skills.

### Approach B — Template-per-platform (recommended)
Each platform has a Jinja2 template defining how a skill maps to that platform's format. Build script: extract structured data from each skill → apply platform template → write to `dist/adapters/<platform>/`.

- **Pro:** Preserves skill structure. Adding a new platform = adding one template file. Fully automated. Output is readable and idiomatic for each platform.
- **Con:** Requires a light extraction layer to parse SKILL.md sections reliably.
- **Verdict:** Right balance of simplicity and extensibility.

### Approach C — Manifest-driven selective inclusion
A `adapters.yml` manifest controls which skills appear in which adapter, at what verbosity level (full / summary / triggers-only).

- **Pro:** Fine-grained control — a Cursor user may only want the build pipeline, not career ops.
- **Con:** Adds ongoing maintenance burden. Manifest goes stale. Increases complexity before the pattern is proven.
- **Verdict:** Good for v2 after Approach B is working.

### Recommendation: Approach B, with Approach C as a Phase 2 enhancement.

---

## User Stories

### User Story 1 — Cursor user gets full dream-studio workflow (P1)

A developer using Cursor runs `make adapters` and gets a `.cursorrules` file that activates dream-studio's pipeline (think→plan→build→review→verify→ship), routing keywords, and top gotchas — without touching any SKILL.md file.

**Why P1:** Cursor is the largest non-Claude-Code AI coding audience. This is the proof of concept for the entire portability claim.

**Independent Test:** Delete `.cursorrules`. Run `make adapters`. Verify `.cursorrules` exists in `dist/adapters/cursor/` with skill triggers and at least 3 gotchas from `skills/build/gotchas.yml`.

**Acceptance Scenarios:**
1. **Given** a fresh clone with no dist/ folder, **When** `make adapters` runs, **Then** `dist/adapters/cursor/.cursorrules` is created with all 38 skill trigger keywords present
2. **Given** a SKILL.md is updated, **When** `make adapters` runs again, **Then** the `.cursorrules` reflects the change without manual editing

---

### User Story 2 — Copilot user gets domain knowledge injected (P2)

A developer using GitHub Copilot runs `make adapters` and gets `.github/copilot-instructions.md` containing dream-studio's Power Platform domain knowledge (DAX patterns, M-query rules), security gotchas, and workflow routing — ready to commit to any repo.

**Why P2:** Copilot has the largest enterprise installed base. Domain knowledge injection is the highest-value addition for Copilot (it has no equivalent of Claude's domain packs).

**Independent Test:** Run `make adapters`. Verify `dist/adapters/copilot/.github/copilot-instructions.md` exists and contains DAX pattern content from `skills/domains/powerbi/dax-patterns.md`.

**Acceptance Scenarios:**
1. **Given** a repo with no Copilot instructions, **When** the adapter file is copied in, **Then** Copilot follows dream-studio's Power Platform domain rules in that repo
2. **Given** domain knowledge YAMLs are updated, **When** `make adapters` runs, **Then** Copilot instructions reflect the update

---

### User Story 3 — Generic system-prompt adapter for any AI (P3)

`make adapters` produces a `dist/adapters/system-prompt/system-prompt.md` — a single markdown file containing the full dream-studio workflow, all skill triggers, all gotchas, and domain knowledge — injectable into any AI via system prompt or context window.

**Why P3:** Catches every platform not explicitly supported (Windsurf, Gemini, local LLMs, etc.) with one generic output.

**Independent Test:** Run `make adapters`. Verify `dist/adapters/system-prompt/system-prompt.md` exists, is under 8,000 tokens, and contains content from at least 10 distinct skills.

**Acceptance Scenarios:**
1. **Given** any LLM with a system prompt field, **When** the system-prompt.md content is injected, **Then** the LLM follows dream-studio routing and workflow steps
2. **Given** `make adapters --platform system-prompt`, **Then** only the system-prompt adapter is regenerated (partial rebuild)

---

### Edge Cases

- What if a SKILL.md has no frontmatter triggers defined? → Skip skill in adapter, log warning. Never silently omit.
- What if a gotchas.yml is empty? → Omit gotchas section for that skill. Don't write an empty block.
- What if domain YAML is malformed? → Log error, skip that domain file, continue build. Never abort entire adapter run for one bad file.
- What if `dist/` already exists with old adapters? → Overwrite silently. Adapters are generated artifacts — no manual edits should survive.
- What if a new skill directory has no SKILL.md? → Skip with warning. Don't fail.

---

## Functional Requirements

- **FR-001**: Build script MUST run with `py scripts/build_adapters.py` or `make adapters`
- **FR-002**: Script MUST read all `skills/*/SKILL.md` files as the single source of truth
- **FR-003**: Script MUST extract per-skill: name, description, trigger keywords, workflow steps (numbered lists), and gotchas (from gotchas.yml avoid entries)
- **FR-004**: Script MUST generate `dist/adapters/cursor/.cursorrules` in Cursor XML-rule format
- **FR-005**: Script MUST generate `dist/adapters/copilot/.github/copilot-instructions.md` in flat markdown
- **FR-006**: Script MUST generate `dist/adapters/system-prompt/system-prompt.md` as a generic injectable
- **FR-007**: Script MUST support `--platform <name>` flag for partial rebuilds (rebuild one platform only)
- **FR-008**: Script MUST log: skills processed, skills skipped (with reason), output files written, total token estimate per adapter
- **FR-009**: SKILL.md files MUST remain unmodified by the build script
- **FR-010**: Adding a new platform MUST require only: one new template file in `scripts/adapter_templates/` + one entry in `scripts/adapters_config.yml` — no script edits
- **FR-011**: Domain knowledge files (`skills/domains/**/*.md`, `skills/domains/**/*.yml`) MUST be included in the system-prompt adapter and optionally in platform-specific adapters
- **FR-012**: Build script MUST output a token count estimate for each generated adapter so the user knows context cost before deploying

---

## Success Criteria

- **SC-001**: `make adapters` completes in under 10 seconds for all 38 skills on a standard machine
- **SC-002**: Generated `.cursorrules` contains trigger keywords for ≥ 35 of 38 skills (some skills are Claude Code-only and explicitly excluded)
- **SC-003**: system-prompt.md is under 8,000 tokens (fits in context for most LLMs without crowding code context)
- **SC-004**: When a SKILL.md trigger keyword is updated, the next `make adapters` run reflects the change in all adapter outputs
- **SC-005**: A developer unfamiliar with dream-studio can add a new platform adapter by reading `scripts/adapter_templates/README.md` alone — no other docs needed

---

## Assumptions

- SKILL.md files follow a consistent enough structure to extract triggers and workflow steps via regex/markdown parsing — no custom parser needed
- `dist/adapters/` is gitignored (generated artifacts) or committed as a release artifact — to be decided at plan time
- Windsurf rules format is identical enough to `.cursorrules` that the Cursor template covers it (verify at build time)
- Token budget for system-prompt adapter: 8K tokens max. If 38 skills exceed this, gotchas are truncated first, then workflow steps summarized
- The build script has no external dependencies beyond Python stdlib + the existing dream-studio venv

---

## Out of Scope (v1)

- Runtime hook enforcement on non-Claude-Code platforms (guidance-only for all adapters)
- Manifest-driven selective skill inclusion (Approach C — Phase 2)
- Auto-sync to platform config on save (watch mode)
- VS Code extension packaging
- Publishing adapters to platform marketplaces

---

## dream-studio Integration

**Skill Flow**: think → plan → build → review → verify → ship
**Output location**: `.planning/specs/multi-ai-adapters/`
**Build output**: `dist/adapters/<platform>/`
**New script**: `scripts/build_adapters.py`
**New templates**: `scripts/adapter_templates/<platform>.j2`
**New config**: `scripts/adapters_config.yml`
**Makefile target**: `make adapters`
