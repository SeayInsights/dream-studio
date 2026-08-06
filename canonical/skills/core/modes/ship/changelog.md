# ship — Changelog

## [1.2.0] - 2026-08-06

### Added
- Public-release path: the gate consults `docs/operations/public-release-readiness.md` (the
  release-blocker checklist — sustained-green full-ci, zero open release-blocking WOs, clean
  publication boundary, finalized packaging, ship-closeout + operator GO) for a public
  Dream Studio marketplace/plugin release (WO-REL-CI-BASELINE).

## [1.1.0] - 2026-08-02

### Added
- Change discipline rules (WO R5): affirm change impact before close
  (`ds work-order affirm-impact`, enforced by the change_impact_affirmed gate) and use
  conventional commits/reverts (`revert(scope):`, never GitHub-UI `Revert "..."`).

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
