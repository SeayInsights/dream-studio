# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] — 2026-04-16

### Added
- 10 hook handlers ported to `hooks/handlers/`, all built on `hooks/lib`:
  - `on-pulse` — cross-project health check; `github_repo` comes from `config.json`, not hardcoded
  - `on-milestone-start` / `on-milestone-end` — DCL-matched milestone marker in `~/.dream-studio/state/`
  - `on-context-threshold` — four-band warn/compact/handoff/block with project-dir auto-detection (override via `CLAUDE_PROJECTS_DIR`)
  - `on-quality-score` — advisory diff scan (tests, debug, secrets, size, scope); writes `quality-score.json`
  - `on-token-log` — appends token usage rows to `token-log.md`
  - `on-meta-review` — weekly retrospective reading `~/.dream-studio/planning/session-context.md`
  - `on-agent-correction` — pattern accumulation with auto-draft threshold (override via `DREAM_STUDIO_CORRECTIONS_PATH`)
  - `on-skill-load` — logs skill reads; surfaces `{{director_name}}` resolution from `config.json`
  - `on-tool-activity` — rolling activity snapshot under `state/activity.json`
- `hooks/hooks.json` — declares hooks on `UserPromptSubmit`, `Stop`, and `PostToolUse` (via `${CLAUDE_PLUGIN_ROOT}/hooks/run.sh`)
- 28 integration tests (one file per hook) — `pytest tests/` now runs 51 tests total

### Removed
- `_notion.py` and `_torii_feed.py` helpers — dream-studio core no longer talks to Notion or the TORII feed

## [0.3.0] — 2026-04-16

### Added
- `hooks/lib/paths.py` — `plugin_root`, `user_data_dir` (`~/.dream-studio/`), `project_root`, `meta_dir`, `state_dir`, `planning_dir`
- `hooks/lib/python_shim.py` — `detect_python()` tries `py`, `python3`, `python` in order, raises `PythonNotFoundError` with OS-specific install hints
- `hooks/lib/state.py` — `read_config`/`write_config`, `read_pulse`/`write_pulse`, schema-version guard via `SchemaVersionError`
- `hooks/run.sh` + `hooks/run.cmd` — cross-platform handler launchers that pick a Python interpreter and exec `hooks/handlers/<name>.py`, preserving `CLAUDE_PLUGIN_ROOT`
- `tests/` — 23 unit tests (paths, python_shim, state) with 97% line coverage on `hooks/lib`
- `requirements-dev.txt` pinning pytest + pytest-cov
- `.gitattributes` enforcing LF for `.sh`/Python and CRLF for `.cmd`/`.bat`
- CI matrix now installs deps and runs `pytest --cov=hooks/lib --cov-fail-under=80`

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
