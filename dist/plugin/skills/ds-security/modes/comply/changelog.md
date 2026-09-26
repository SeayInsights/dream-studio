# comply — Changelog

## [1.1.0] - 2026-09-26

### Added
- New `privacy` sub-mode: in-repo GDPR/HIPAA/CCPA data-handling audit (12 rules), moved from the
  quality pack's `database-compliance` mode as part of the pack-split campaign's security merge.
  `map`/`gaps`/`evidence` are unchanged.

### Fixed
- `pack:` field in config.yml and metadata.yml corrected from `quality` to `security` (stale
  since this mode's own creation; unrelated to the privacy merge but caught while touching these
  files).
- `metadata.yml`'s empty `triggers: []` populated with the real trigger set already documented in
  this file's own `## Trigger` section.

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
