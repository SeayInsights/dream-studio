# power-platform — Changelog

## [1.2.0] - 2026-10-01

### Added
- `powerbi/brand-profile.md` + `powerbi/brand-profiles/default.yml` + `default-theme.json` —
  swappable brand-profile schema so no skill text hardcodes a client's colors/fonts/logo
- `powerbi/custom-visuals.md` — pbiviz custom-visual development: capabilities.json, settings.ts,
  visual.ts, theme-aware colors, packaging/sideload, certification checklist
- `powerbi/visual-verification.md` — two-path self-verification (static layout preview + live PBI
  Desktop screenshot), exec-grade checklist, troubleshooting loop
- `powerbi/pbir-gotchas.md` — dense PBIR/TMDL burn-case gotcha list
- `powerbi/report-visual-json.md` — report/page/visual.json authoring patterns
- `powerbi/quality-tiers-antipatterns.md` — anti-patterns to flag, quality-bar checklists
- `powerbi/pbi-workflows.md` — file-format glossary, PBIP edit/commit workflow, performance debugging
- `scripts/` — ported visual-verification and custom-visual tooling (layout preview, JSON
  validators, exec-quality scanner, Path A screenshot capture, pbiviz scaffold script with
  `-BrandProfile` parameterization)
- New trigger keywords: `build visual:`, `custom visual:`, `pbiviz:`, `verify report:`, `verify visual:`
- "Brand profile" subsection in SKILL.md — resolve the active profile before any theming work
- 7 new gotchas.yml entries covering custom-visual and PBIR/TMDL burn cases

### Fixed
- gotchas.yml `tmdl-tabs` entry corrected — TMDL requires tabs, never spaces (was backwards)

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
