# harden — Changelog

## [1.1.1] - 2026-09-27

### Fixed
- Phase 2's Tier 1 file copy instructions pointed at `templates/project-standards/`
  "in the dream-studio repo" — a directory that does not exist at that path. The
  real location, verified against the working tree, is
  `packs/domains/templates/project-standards/` (9 files: README.md, Makefile,
  pyproject.toml, .coveragerc, SECURITY.md, CONTRIBUTING.md,
  .pre-commit-config.yaml, requirements.txt, requirements-dev.txt). Confirmed
  `context-template.md` (Phase 1's memory-system stub) is a separate file that
  already lives alongside this skill (`templates/context-template.md`, not the
  project-standards directory) and was not confused with the Tier 1 file list.

## [1.1.0] - 2026-08-04

### Added
- Phase 4: silent-default hunting lens (negative-space / fail-quiet), per ADR-0002
  (WO R6). Hunt code that resolves identity/authority/state by elimination and silently
  defaults on the miss path — the fix is affirmative: verify and refuse what you cannot
  verify (fail loud) rather than defaulting. Carries a Dream Studio worked example.

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
