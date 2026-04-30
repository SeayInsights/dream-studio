# client-work — Changelog

## [1.0.0] - 2026-04-28

### Added
- Initial architecture enhancement
- Added metadata.yml for skill tracking
- Added gotchas.yml for lessons learned
- Added config.yml for runtime configuration
- Established skill framework foundation

### Documentation
- Created examples (simple and complex scenarios)
- Added templates for agent prompts and output formats
- Added smoke test for quick validation
- Added core-imports.md for module dependencies (if applicable)

## [1.1.0] - 2026-04-28

### Added
- `powerbi/pbip-format.md` — .pbip folder structure, TMDL syntax examples, editing rules
- `bi-developer` subagent dispatch instruction with explicit triggers
- Power BI debug tables (DAX errors, M-query errors, semantic model validation)
- Power BI verify checklist (6-step ordered process)
- "Before you start" preload section — reads gotchas.yml + powerbi/ files first

### Changed
- SKILL.md: .pbip reference content moved out → `powerbi/pbip-format.md` (SKILL.md now references it)
- SKILL.md: now behavior + process only — no embedded reference content

### Fixed
- gotchas.yml populated with real lessons (was empty stubs)
- metadata.yml updated with correct tags, dependencies, subagent usage

## Version History

**v1.0.0 (2026-04-28)** — Architecture enhancement baseline
- Skill matured from prototype to structured framework
- Quality metrics tracking established
- Dependency graph documented
