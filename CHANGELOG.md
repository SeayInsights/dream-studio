# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-04-16

### Added
- 18 skills ported from studio as `skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`):
  - Process: `think`, `plan`, `build`, `review`, `verify`, `debug`
  - Domain: `saas-build`, `game-dev`, `client-work`, `design`, `mcp-build`, `dashboard-dev` (was `torii-dev`)
  - Quality: `polish`, `secure`, `ship`
  - Studio: `recap`, `handoff`, `learn`

### Changed
- Flat skills layout (`skills/<name>/SKILL.md`) instead of category folders, matching Claude Code plugin convention
- `design` skill: brand tokens table converted to fill-in template
- `mcp-build` skill: `@seayinsights/` package scope generalized to `@<your-scope>/`
- `client-work` skill: "Notion Client Projects" generalized to "the project tracker"
- `saas-build` skill: dropped the specific project list line

### Removed
- All SeayInsights-specific references (brand name, Dannis, repo URLs, Notion workspace IDs)
- TORII product branding from the dashboard skill (now `dashboard-dev`, fully generic)

## [0.1.0] — 2026-04-16

### Added
- `.claude-plugin/plugin.json` manifest (name, version, author, license, repository)
- `.claude-plugin/marketplace.json` self-hosted dev marketplace entry
- `README.md`, `LICENSE` (MIT), `.gitignore`, `CHANGELOG.md`
- `.github/workflows/ci.yml` scaffold (lint + pytest matrix on Windows/macOS/Linux × py3.10/3.11/3.12, empty tests OK)
- Repo bootstrapped, initial commit on `main`
- Verified `claude plugins list` shows `dream-studio@0.1.0` after local install

## [0.0.1] — 2026-04-16

### Added
- Scaffolding
