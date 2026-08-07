# review — Changelog

## [1.2.0] - 2026-08-04

### Added
- Stage-2 checklist item 8: silent-default / fail-quiet (negative-space lens), per
  ADR-0002 (WO R6). Flag identity/authority/state resolved by elimination or a swallowed
  correctness-changing failure that yields a plausible-but-wrong result with no alert; the
  remedy is to verify and refuse what cannot be verified rather than defaulting.

## [1.1.0] - 2026-08-02

### Added
- Stage 2 gains a "Change discipline" check (WO R5): flag GitHub-UI `Revert "..."`
  subjects and missing change-impact affirmations before they surface at close.

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
