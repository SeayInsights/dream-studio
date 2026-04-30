# Implementation Plan: dream-studio Onboarding

**Date**: 2026-04-30 | **Spec**: `.planning/specs/onboarding/spec.md`  
**Input**: Feature specification from spec.md

## Summary

Implement a first-run setup experience for dream-studio that works immediately with zero external dependencies (via fallbacks), while offering three progressive enhancement paths: wizard (guided install), as-needed (JIT prompts), and read-docs (manual setup). Core modules (web.md, git.md) detect available tools at runtime and use the best option, ensuring skills never fail due to missing tools.

## Technical Context

**Language/Version**: TypeScript 5.3 (skills), Markdown (core modules + documentation)  
**Primary Dependencies**: None — that's the point. Fallbacks use built-in Claude Code tools (WebSearch, WebFetch)  
**Storage**: `.dream-studio/setup-prefs.json` (user preferences, tool installation state)  
**Testing**: Manual verification via `dream-studio:setup status` + skill invocation tests  
**Target Platform**: Cross-platform (Windows/Mac/Linux) — detection logic per-platform  
**Project Type**: dream-studio skill (`setup`) + core modules (`web.md`, `setup.md`)  
**Performance Goals**: First-run prompt <1s, tool detection <2s, wizard completion <10min  
**Constraints**: Must work with zero setup (fallback mode), silent fallbacks (no warnings)  
**Scale/Scope**: 6 tools tracked (gh, firecrawl, playwright, + 3 future), 38 existing skills unmodified

## Constitution Check

*GATE: Must pass before implementation. Check against project constitution if exists.*

No `.planning/CONSTITUTION.md` exists yet for dream-studio. This implementation aligns with dream-studio principles:
- **Minimum viable first** — P1 delivers working skills with zero setup
- **Progressive enhancement** — P2 offers full-featured path without blocking P1
- **Documentation-driven** — P3 serves "read first" users
- **No breaking changes** — existing skills continue to work, fallbacks are additive

## Project Structure

### Documentation (this feature)

```text
.planning/specs/onboarding/
├── spec.md              # User stories, requirements (approved)
├── plan.md              # This file (implementation strategy)
├── tasks.md             # Task breakdown (output of this plan)
└── traceability.yaml    # Requirements → tasks mapping (this plan will create)
```

### Source Code

```text
# New skill
skills/setup/
├── SKILL.md             # Setup skill documentation
├── skill.ts             # Setup wizard + status command logic
├── modes/
│   ├── wizard.md        # Full setup wizard flow
│   ├── status.md        # Tool detection + status display
│   └── jit.md           # Just-in-time prompts
└── tool-registry.yml    # Tool metadata (name, detect cmd, install cmd, what it unlocks)

# New core modules
skills/core/
├── web.md               # Web access with Firecrawl → scraper-mcp → WebSearch fallback
└── setup.md             # Detection logic, preference management, tool state

# Updated core modules
skills/core/
└── git.md               # Add gh CLI detection + fallback to manual GitHub ops

# Configuration
.dream-studio/
└── setup-prefs.json     # User preferences (wizard/as-needed/read-docs, per-tool choices)

# Documentation
README.md                # Updated with three setup profiles (Minimal, Standard, Full)
```

**Structure Decision**: Keep `setup` as a dedicated skill (not merged into `quality` or `core`) because it has three distinct modes (wizard, status, jit) and will evolve independently. Core modules (`web.md`, `setup.md`) handle runtime detection and fallback logic — these are referenced by all skills, not just setup.

## Complexity Tracking

| Concern | Why Needed | Simpler Alternative Rejected Because |
|---------|------------|-------------------------------------|
| Three onboarding paths (wizard, as-needed, read-docs) | Users have different preferences — some want guided setup, some want self-service, some want no prompts | Single path (wizard only) would alienate "read first" users and create friction for casual evaluators |
| Per-tool state tracking | Users may install tools incrementally over time, wizard may be cancelled mid-setup, tools may be partially configured | Binary "setup done" flag doesn't capture reality of incremental adoption and failed installs |
| Cross-platform detection | Windows (`where`), Unix (`which`), different install commands per OS | Assuming single platform breaks 40%+ of potential users (Windows users are significant) |

## Requirements Traceability

| Requirement ID | Description | Implemented By |
|---------------|-------------|----------------|
| FR-001 | Detect first-run on any skill invocation, prompt once | T004, T005 |
| FR-002 | Save setup preference to `.dream-studio/setup-prefs.json` | T006 |
| FR-003 | Provide three onboarding paths (wizard, as-needed, read-docs) | T001, T010, T011, T012, T018 |
| FR-004 | Fallback tool logic in core modules (zero-dependency mode) | T007, T008, T014 |
| FR-005 | Wizard detects installed tools, shows current state | T010, T013 |
| FR-006 | Wizard shows what each tool unlocks | T010, T013 |
| FR-007 | Wizard provides one-command install per tool | T010, T013 |
| FR-008 | JIT prompts appear max once per tool, with "never" option | T012, T015 |
| FR-009 | Save per-tool preferences to setup-prefs.json | T006, T012 |
| FR-010 | README documents three profiles (Minimal, Standard, Full) | T018 |
| FR-011 | README per-tool explanations (what, why, how) | T018 |
| FR-012 | Provide `dream-studio:setup status` command | T011, T013 |
| FR-013 | Core modules detect tool availability at runtime | T007, T008, T009 |
| FR-014 | Fallback logic silent (no warnings when using fallbacks) | T007, T008 |
| FR-015 | Wizard handles browser auth flows for API keys | T013 (Firecrawl auth flow) |

## Dependencies

### External Dependencies
- None for P1 (fallback mode works with built-in tools)
- Optional for P2/P3: gh CLI, Firecrawl, Playwright (these are what we're installing)

### Internal Dependencies
- `skills/core/format.md` — for status command output formatting
- `skills/core/orchestration.md` — if setup wizard spawns subagents for install verification
- Existing skills remain unchanged — they'll reference `web.md` or `setup.md` as needed

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Cross-platform detection fails on Windows | High — 40% of users blocked | Test on all three platforms before merge, use platform-agnostic commands |
| Firecrawl API key flow breaks (external service) | Medium — wizard fails, but as-needed fallback works | Wrap auth flow in try-catch, fallback to "manual setup" instructions |
| JIT prompts annoy users who don't want tools | Medium — user frustration, abandonment | "never ask" option must be prominent, honored forever |
| Fallback quality degrades (WebSearch vs Firecrawl) | Low — feature works but output is worse | Document fallback behavior in web.md, set user expectations |
| Tool detection false positives (command exists but broken) | Medium — wizard thinks tool is installed but it's not | Status command should run tool with `--version` to verify it actually works |

## Success Metrics

- [ ] All functional requirements FR-001 through FR-015 implemented
- [ ] All user stories (US1-US5) testable independently
- [ ] Performance goals met: first-run prompt <1s, tool detection <2s, wizard <10min
- [ ] Cross-platform verified: Windows, Mac, Linux all detect tools correctly
- [ ] Integration with existing dream-studio patterns: core modules follow existing conventions

## dream-studio Integration

**Skill Flow**: think → **plan** → build → review → verify → ship

**Output Location**: `.planning/specs/onboarding/plan.md` and `tasks.md`

**Next Steps**: 
1. Review this plan with user for approval
2. Run `dream-studio:build` with the tasks.md file
3. Execute tasks in dependency order (Setup → Foundational → US1 → US2 → US3 → US4)
