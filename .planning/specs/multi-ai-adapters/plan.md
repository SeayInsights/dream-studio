# Implementation Plan: Multi-AI Adapter Build System

**Date**: 2026-04-30 | **Spec**: `.planning/specs/multi-ai-adapters/spec.md`
**Input**: Approved feature specification (status: approved, phase: ready to plan)

---

## Summary

Build a Python script (`scripts/build_adapters.py`) that reads all `skills/*/modes/*/SKILL.md` files as the SSOT and generates platform-specific adapter files via Jinja2 templates. Three adapters ship in v1: Cursor (`.cursorrules`), Copilot (`copilot-instructions.md`), and a generic system-prompt (`system-prompt.md`). Adding a fourth platform requires only a new template file and one config entry — no script edits.

---

## Technical Context

**Language/Version**: Python 3.11+ (stdlib + Jinja2 only)
**Primary Dependencies**: Jinja2 (add to `requirements.txt`); all else is Python stdlib (`pathlib`, `re`, `yaml`, `argparse`, `tiktoken` or char-count approximation)
**Storage**: File system only — reads from `skills/`, writes to `dist/adapters/`
**Testing**: Manual smoke test (`make adapters` → verify output files exist and contain expected content)
**Target Platform**: Local developer machine; CI-friendly (no GUI, no network)
**Project Type**: CLI build tool (single-script)
**Performance Goals**: Full build under 10 seconds for 38 skills (SC-001)
**Constraints**: No deps beyond Python stdlib + Jinja2. SKILL.md files must not be modified.
**Scale/Scope**: 7 packs × ~5 modes each = ~35–38 SKILL.md files; 3 platform adapters

---

## Constitution Check

- Approach B (template-per-platform) was the recommended approach in spec — using it.
- `dist/adapters/` is a generated artifact — must be added to `.gitignore`.
- SKILL.md files are the SSOT — build script is read-only against them (FR-009).
- No new skill pack, domain, or subdirectory is introduced — adding to existing `scripts/` directory.
- Token budget for system-prompt: 8K max. Truncation order: gotchas first, then workflow step summaries (spec assumption).

---

## Project Structure

### Documentation (this feature)

```text
.planning/specs/multi-ai-adapters/
├── spec.md              # Approved spec (SSOT for requirements)
├── plan.md              # This file
├── tasks.md             # Atomic task breakdown
└── traceability.yaml    # Feature-scoped traceability registry (note: .planning/traceability.yaml
                         #   is owned by the onboarding spec; this feature uses its own file)
```

### Source Code

```text
scripts/
├── build_adapters.py                  # Main build script (FR-001)
├── adapters_config.yml                # Platform registry (FR-010)
└── adapter_templates/
    ├── README.md                      # "Add a platform" guide (SC-005)
    ├── cursor.j2                      # Cursor .cursorrules template (FR-004)
    ├── copilot.j2                     # Copilot instructions template (FR-005)
    └── system-prompt.j2               # Generic injectable template (FR-006)

dist/adapters/                         # Generated — gitignored
├── cursor/
│   └── .cursorrules
├── copilot/
│   └── .github/
│       └── copilot-instructions.md
└── system-prompt/
    └── system-prompt.md

requirements.txt                       # Add: Jinja2>=3.1
.gitignore                             # Add: dist/
Makefile                               # Add: adapters target (FR-001)
```

**Structure Decision**: All new files land in `scripts/` (existing directory for Python tooling). The `dist/` directory is generated on every run, gitignored, and never manually edited.

---

## Complexity Tracking

| Concern | Why Needed | Simpler Alternative Rejected Because |
|---------|------------|-------------------------------------|
| Jinja2 templates per platform | Platform output formats differ structurally (XML rules vs flat markdown vs injectable MD) | Single concatenation approach loses skill boundaries and is unreadable at 38 skills (Approach A verdict in spec) |
| Token estimation | SC-003 requires system-prompt.md < 8K tokens; FR-012 requires per-adapter reporting | No stdlib alternative — use `len(text) / 4` approximation (accurate ±5%) or `tiktoken` if available |
| SKILL.md path discovery | Skills are at `skills/<pack>/modes/<mode>/SKILL.md` — two-level nesting, not flat | Flat glob would miss the pack/mode structure and pick up non-mode SKILL.md files (e.g., `skills/domains/SKILL.md`) |

---

## Requirements Traceability

| Requirement ID | Description | Priority | Implemented By |
|---------------|-------------|----------|----------------|
| FR-001 | `py scripts/build_adapters.py` and `make adapters` entry points | must | T007, T008 |
| FR-002 | Read all `skills/*/modes/*/SKILL.md` as SSOT | must | T003 |
| FR-003 | Extract name, description, triggers, workflow steps, gotchas per skill | must | T003 |
| FR-004 | Generate `dist/adapters/cursor/.cursorrules` | must | T004, T009 |
| FR-005 | Generate `dist/adapters/copilot/.github/copilot-instructions.md` | must | T005, T010 |
| FR-006 | Generate `dist/adapters/system-prompt/system-prompt.md` | must | T006, T011 |
| FR-007 | `--platform <name>` flag for partial rebuilds | must | T007 |
| FR-008 | Log: processed, skipped, output files, token estimate per adapter | must | T007 |
| FR-009 | SKILL.md files remain unmodified | must | T003 (read-only) |
| FR-010 | New platform = one template + one config entry, no script edits | must | T001, T002, T007 |
| FR-011 | Domain knowledge files included in system-prompt adapter | must | T006, T011 |
| FR-012 | Token count estimate per generated adapter | must | T007 |

---

## Dependencies

### External Dependencies
- `Jinja2>=3.1` — add to `requirements.txt`
- `PyYAML` — already in most Python environments; needed to parse `gotchas.yml` (add to `requirements.txt` if not present)
- `tiktoken` (optional) — for precise token counting; fall back to `len(text) // 4` if not installed

### Internal Dependencies
- `skills/*/modes/*/SKILL.md` — all mode-level skill files (SSOT, read-only)
- `skills/*/modes/*/gotchas.yml` — per-mode gotchas (read-only, optional per mode)
- `skills/domains/**/*.md` and `skills/domains/**/*.yml` — domain knowledge files (read-only)
- No other dream-studio skills or packs are modified by this feature

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| SKILL.md structure inconsistency across packs | High — parser silently misses triggers | Validate extraction count in FR-008 log; skip with warning (not fail) |
| system-prompt token budget exceeded | Medium — SC-003 broken | Truncation order defined in spec: gotchas first, then workflow step summaries |
| `dist/` accidentally committed | Low — bloats repo | Add `dist/` to `.gitignore` in T012 before any adapter is generated |
| Cursor XML format changes | Low — adapters stop working | Template lives in `cursor.j2`; fix = edit template only, no script changes |
| Windsurf format differs from Cursor | Medium — Cursor template doesn't cover it | Verified as assumption in spec; create separate `windsurf.j2` template in Phase 2 if needed |

---

## Success Metrics

- [ ] SC-001: `make adapters` completes < 10 seconds
- [ ] SC-002: `.cursorrules` contains triggers for ≥ 35 of 38 skills
- [ ] SC-003: `system-prompt.md` is under 8,000 tokens
- [ ] SC-004: Updating a SKILL.md trigger → next `make adapters` reflects the change
- [ ] SC-005: New platform addable by reading `scripts/adapter_templates/README.md` alone

---

## dream-studio Integration

**Skill Flow**: think → **plan** → build → review → verify → ship

**Output Location**: `.planning/specs/multi-ai-adapters/plan.md` and `tasks.md`

**Next Steps**:
1. Review plan and tasks with Director for approval
2. Run `dream-studio:core build` against `tasks.md`
3. Execute tasks in dependency order, committing after each logical group
