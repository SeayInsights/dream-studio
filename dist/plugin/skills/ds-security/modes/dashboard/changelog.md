# security-dashboard — Changelog

## [1.1.0] - 2026-09-27

### Fixed
- `template` mode's own instructions (in both `SKILL.md` and `examples.md`) claimed a
  Power BI `.pbit` file gets copied to `~/Downloads/`. No `.pbit` ever shipped with
  this repo — only `templates/security/powerbi/dashboard-spec.md`, a markdown spec.
  Rewrote `template` mode to accurately describe what it delivers today: the spec
  plus a connection README, with building the actual `.pbit` in Power BI Desktop
  left as an explicit human step.

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
