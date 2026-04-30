# Implementation Plan: Firecrawl MCP + Doc Alignment

**Date**: 2026-04-30 | **Spec**: `.planning/specs/firecrawl-mcp/spec.md`
**Input**: Approved spec + doc audit findings

## Summary

Firecrawl MCP server is installed and configured but tools aren't loading reliably. Debug the loading issue, verify tool name prefix, then align all dream-studio documentation (web.md, tool-registry, README, tool-reference) with MCP server reality. Also fix 3 stale doc items and add 2 missing items identified in the doc audit.

## Technical Context

**Language/Version**: Markdown + YAML (doc edits), Bash (debugging)
**Primary Dependencies**: Firecrawl MCP v3.11.0, scraper-mcp, Claude Code MCP system
**Storage**: N/A
**Testing**: Manual verification — `ToolSearch("firecrawl")` returns results after fix
**Target Platform**: Claude Code plugin (cross-platform)
**Project Type**: Skill documentation + configuration alignment
**Constraints**: No code changes — all edits are markdown, YAML, or JSON

## Constitution Check

No `.planning/CONSTITUTION.md` exists for dream-studio. This work is doc-only and doesn't conflict with any architectural decisions in ARCHITECTURE.md.

## Project Structure

### Documentation (this feature)

```text
.planning/specs/firecrawl-mcp/
├── spec.md              # Approved spec
├── plan.md              # This file
├── tasks.md             # Task breakdown
└── doc-audit.md         # Documentation audit findings
```

### Files Being Modified

```text
skills/core/web.md                          # Tier 1 detection + new capabilities
skills/setup/tool-registry.yml              # Firecrawl entry: pip → MCP
skills/setup/modes/wizard/SKILL.md          # Detect existing MCP config
skills/setup/modes/jit/SKILL.md             # Detect existing MCP config
docs/tool-reference.md                      # MCP server install/verify
README.md                                   # Full Profile + MCP servers section
STRUCTURE.md                                # Pack structure rewrite
CONTRIBUTING.md                             # Branch prefix fix
.github/PULL_REQUEST_TEMPLATE.md            # New file
CHANGELOG.md                                # Verify entries
```

## Requirements Traceability

| Requirement ID | Description | Implemented By |
|---|---|---|
| FR-001 | Debug Firecrawl MCP loading | T001 |
| FR-002 | Verify actual tool name prefix | T002 |
| FR-003 | Update web.md detection logic | T003 |
| FR-004 | Add search/extract/map to web.md | T003 |
| FR-005 | Update capability matrix | T003 |
| FR-006 | Update tool-registry.yml | T004 |
| FR-007 | Update README Full Profile | T007 |
| FR-008 | Update tool-reference.md | T005 |
| FR-009 | Keep scraper-mcp as Tier 2 | T003 (verified in edit) |
| FR-010 | Update wizard/JIT detection | T006 |

## Dependencies

### External Dependencies
- Firecrawl MCP v3.11.0 (already installed)
- Node.js (already installed)

### Internal Dependencies
- `skills/core/web.md` — SSOT for web fallback chain
- `skills/setup/tool-registry.yml` — SSOT for tool metadata
- `README.md` — user-facing documentation

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| MCP loading issue is a Claude Code bug, not fixable by us | High | Document the issue; ensure detection logic handles "configured but not loading" gracefully |
| Tool name prefix differs from expected | Low | Verify empirically before editing web.md; use verified prefix everywhere |
| STRUCTURE.md rewrite misses new directories | Medium | Run `ls -R` on skills/ before writing |

## Success Metrics

- [ ] Firecrawl tools appear in ToolSearch (or root cause identified)
- [ ] All doc references to Firecrawl consistently say MCP server
- [ ] STRUCTURE.md matches actual directory layout
- [ ] CONTRIBUTING.md branch prefix matches CLAUDE.md
- [ ] PR template exists

## Execution Strategy

**T001-T002 are investigative** — must be done inline (not subagents) since they require session-level MCP interaction.

**T003-T006 can proceed after T002** — these depend on knowing the verified tool prefix.

**T007-T011 are independent doc fixes** — can run in parallel with T003-T006 (different files).

**Commit strategy**: One commit per logical group. Likely 3 commits:
1. Firecrawl alignment (web.md + tool-registry + tool-reference + wizard/JIT)
2. README updates (Full Profile + MCP section)
3. Stale doc fixes (STRUCTURE.md + CONTRIBUTING.md + PR template + CHANGELOG)
