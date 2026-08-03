# think — Changelog

## [1.2.0] - 2026-07-24

### Added
- Contract-bearing work is spec-first (WO R2): a new "Contract-bearing work → normative
  spec" subsection instructs authoring a normative RFC-2119 spec from the template and
  ratifying it (Draft→Reviewed→Ratified) before build/close, since the
  `api_contract_exists` gate now requires a Ratified spec.

## [1.1.0] - 2026-07-24

### Added
- Design decisions are recorded as ADRs (`docs/adr/`, WO R1): step 3 (Recommend)
  and a new "Design decisions → ADR" subsection instruct authoring an ADR from the
  template and linking it from the decision packet (`adr_id`) on significant design
  decisions.

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
