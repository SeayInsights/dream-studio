# scan — Changelog

## [1.1.0] - 2026-09-27

### Fixed
- `SKILL.md`'s Step I3 `scan-meta.json` example was truncated mid-JSON by a botched
  extraction to `examples.md` (an unclosed code fence spliced directly into
  `## Detailed Reference`). The extraction also silently dropped Step I4 (`Present
  Summary`) and the entire `status` mode's step-by-step instructions (Steps T0-T4),
  even though `status` is one of the three modes advertised in `SKILL.md`'s own
  `## Modes` list. Restored the complete JSON example and moved the `status` mode's
  real instructions back into `SKILL.md`, matching how `setup` and `ingest` are
  already fully self-contained there. `examples.md` now holds only what it always
  should have: the output schema, generated-file locations, and anti-patterns.

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

## Version History

**v1.0.0 (2026-04-28)** — Architecture enhancement baseline
- Skill matured from prototype to structured framework
- Quality metrics tracking established
- Dependency graph documented
