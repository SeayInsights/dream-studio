# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.9.0] — 2026-04-29

### Added
- **ARCHITECTURE.md** — Documents the two-layer design: `packs/` (Python hook runtime) vs `skills/` (Claude guidance), key paths, how they connect, and the full new-skill checklist
- **skills/domains/ingest-log.yml** — External knowledge registry tracking every repo analyzed: URL, stars, domain, files touched, analysis date, refresh-due date. Backfilled with 11 repos from the 2026-04-28 integration
- **`workflow: repo-ingest`** node in `skills/workflow/SKILL.md` — Formalizes external repo intake: domain detection, dedup check, ≤10 pattern extraction, domain YAML write, ingest-log entry. Replaces ad-hoc ingestion with a tracked, repeatable workflow
- **`.planning/specs/infra-lessons-ingest/`** — Plan and tasks for this release

### Fixed
- **`~/.dream-studio/config.json`** — Now includes `director_name` and `claude_memory_path`; silences the "Setup not complete" warning that fired every session
- **`skills/learn/config.yml`** — `harvest.projects_root` now set to `builds/`; enables `learn: harvest` to auto-discover projects

### Changed
- **skills/build/gotchas.yml** — Added `compact-at-75-percent` best practice: run `/compact` proactively between waves before context approaches 75% (promoted from 26 pending draft lessons)
- **skills/STRUCTURE.md** — Added Skill Depth Policy section: JIT enrichment only, no sprint; skill tier table (Enhanced / Standard / JIT-pending)
- **skills/polish/SKILL.md** — Now references `checklists/` directory with all 4 checklists named inline
- **skills/mcp-build/SKILL.md**, **dashboard-dev/SKILL.md**, **saas-build/SKILL.md** — Added `## Depth Status` section marking each as JIT-pending
- **skills/workflow/SKILL.md** — `repo-ingest` built-in workflow node added (see Added above)

### Meta
- 26 pending draft lessons triaged: 22 rejected (context-threshold noise + sonnet-theme), 4 high-context theme promoted to `build/gotchas.yml`
- Draft lesson queue cleared to 0

## [0.8.0] — 2026-04-29

### Added — Skill & Workflow Improvements (TR-001–TR-013)
- **skills/explain/** — New `explain` skill: traces entry point through layers to output, depth adapts to question; includes SKILL.md, metadata, gotchas, config, changelog
- **skills/coach/analysts/route-classifier.yml** — Route-classifier analyst persona for mapping unmatched intents to nearest skill
- **skills/coach/modes.yml** — `route-classify` mode entry for coach
- **skills/core/repo-map.md** — New core module: repo-map generation patterns, registered in REGISTRY.md
- **skills/domains/bi/dax-patterns.md** — DAX calculation patterns for Power BI domain knowledge base
- **skills/domains/bi/m-query-patterns.md** — M-query data transformation recipes for Power BI
- **skills/client-work/powerbi/pbip-format.md** — PBIP format reference for Power BI project files
- **hooks/lib/skill_metrics.py** — Appends skill usage records (name, duration, tokens) to `~/.dream-studio/skill-metrics.jsonl` on every invocation
- **scripts/sync-cache.ps1** — PowerShell cache sync utility

### Changed
- **CLAUDE.md** — Added routing fallback clause: unmatched intents route to `coach` with `route-classify` mode (TR-012)
- **skills/coach/SKILL.md** — Added `route-classify` mode (TR-012)
- **skills/build/SKILL.md** — Repo-map generation step at Step 0 (TR-006), per-task checkpoints at every step (TR-007), worktree isolation instruction for parallel dispatch (TR-008), auto-learn suggestion at checkpoint (TR-013)
- **skills/debug/SKILL.md** — Step 1.5 failing-test capture gate (TR-011), auto-learn suggestion (TR-013)
- **skills/verify/SKILL.md** — Red-green bug fix verification section (TR-011)
- **skills/review/SKILL.md** — JSON reviewer schema for structured findings output (TR-003)
- **skills/core/orchestration.md** — JSON agent schema, static-before-dynamic prompt ordering (TR-003/TR-004), repo-map field in implementer template (TR-006), pipeline gate check pattern (TR-009)
- **skills/core/format.md** — Task-level checkpoint format variant (TR-007)
- **skills/build/config.yml** — Checkpoint threshold set to 1 task (TR-007)
- **workflows/fix-issue.yaml** — `create-issue` node after diagnose (TR-001), write-failing-test conditional node (TR-005)
- **workflows/idea-to-pr.yaml** — Conditional security branch (TR-005)
- **settings.json** — PostToolUse metrics hook for Skill tool (TR-010)
- 30+ SKILL.md files updated with content improvements across all packs
- Updated gotchas.yml for build, debug, plan, review, secure, think, verify
- Regenerated `skills/dream-studio-catalog.md` — now covers 38 skills

## [0.7.0] — 2026-04-28

### Added — Skill Architecture Enhancement (Phase 2)
- **skills/*/metadata.yml** — Evolution tracking, quality metrics (success_rate, times_used, avg_token_usage), dependency tracking for all 37 skills
- **skills/*/gotchas.yml** — Structured lessons learned (avoid, best_practices, edge_cases, limitations, deprecated) for all 37 skills
- **skills/*/config.yml** — Runtime configuration and performance budgets for all 37 skills
- **skills/*/changelog.md** — Version history for all 37 skills
- **skills/generate-catalog.py** — Auto-generates dream-studio-catalog.md from skill metadata
- **skills/dream-studio-catalog.md** — Auto-generated searchable skill dashboard with quality metrics, dependency graph, health status
- **skills/STRUCTURE.md** — Complete architecture guide (skill structure, file purposes, creating/updating skills, best practices)
- **skills/templates/** — Templates for metadata.yml, gotchas.yml, config.yml for new skill creation
- **skills/build/examples/** — Simple + complex usage examples with input/output (also for plan, review, verify, ship)
- **skills/build/templates/** — Agent prompts (implementer, reviewer) and output formats (checkpoint, findings-report, plan-format)
- **skills/build/smoke-test.md** — Quick validation tests (also for plan, review, verify, ship)
- **skills/build/core-imports.md** — Module dependency documentation and impact analysis (also for plan, review, verify, ship)

### Changed
- **skills/core/REGISTRY.md** — Updated with Phase 2 architecture enhancement history
- **README.md** — Added Skill Architecture section documenting structured framework
- All 37 skills now follow standardized structure with metadata, gotchas, config, and changelog

### Infrastructure
- **Makefile** — standard targets: `test`, `lint`, `fmt`, `security`, `install-dev`, `status`
- **pyproject.toml** — black, flake8, pytest, and coverage config (replaces need for separate `.coveragerc`)
- **hooks/lib/time_utils.py** — `utcnow()` utility; replaced all bare `datetime.now(timezone.utc)` calls in handlers and `context_handoff.py`
- **hooks/lib/models.py** — Pydantic v2 models (`UserPromptSubmitPayload`, `PostToolUsePayload`, `StopPayload`) for stdin validation in handlers
- **hooks/lib/audit.py** — append-only event log writing to `~/.dream-studio/audit.jsonl`
- **hooks/lib/telemetry.py** — optional Sentry error tracking stub (activated by `SENTRY_DSN` env var)
- **SECURITY.md** — vulnerability disclosure process (30-day SLA, dannis.seay@twinrootsllc.com)
- **CONTRIBUTING.md** — branch naming, commit format, PR checklist, code style guide
- **requirements.txt** — runtime dependencies (pydantic, sentry-sdk) split from dev deps
- **requirements-dev.txt** — added freezegun, factory-boy, black, flake8, pip-audit, pre-commit
- **.pre-commit-config.yaml** — black and flake8 hooks
- **scripts/bom.py** — Bill of Materials script (git SHA, Python version, pip freeze, build date)
- **skills/harden/SKILL.md** — `/harden` skill: 20-item audit + gap-fill from templates
- **templates/project-standards/** — reusable template files (Makefile, pyproject.toml, SECURITY.md, CONTRIBUTING.md, requirements files, hooks/lib stubs)
- **tests/factories.py** — factory_boy factories for hook payload models
- **on-tool-activity** hook: one-time `/harden audit` nudge on first Edit/Write in unhardened projects

### Changed
- `on-token-log.py`, `on-milestone-start.py`, `on-milestone-end.py`, `on-pulse.py`, `on-meta-review.py`, `context_handoff.py` — all `datetime.now(timezone.utc)` replaced with `utcnow()` from `time_utils`
- `on-token-log.py`, `on-context-threshold.py` — added Pydantic payload validation with graceful fallback on `ValidationError`
- `test_hook_on_pulse.py`, `test_hook_on_milestone_end.py`, `test_hook_on_token_log.py` — added `@freeze_time` to time-sensitive tests

## [0.6.1] — 2026-04-19

### Added
- **skills/domain-re/** — Real estate analysis skill: forensic skeptic (sonnet) + diplomatic executor (haiku) + battle-tested strategist (sonnet); modes: lease-analysis, credit-check, renewal-economics, rollover-analysis; 3 analysts, anti-sycophancy design
- **skills/coach/** — Claude Code workflow coach: evaluates workflow-fit, context-health, pr-hygiene, agent-dispatch; `full-audit` mode runs all four in parallel with consensus-report synthesis
- **skills/secure/** — Rewritten as parallel analyst-orchestrated skill: 6 OWASP analysts (injection, auth, exposure, access-control, misconfig, dependencies) + 6 STRIDE analysts; `any-reject` verdict (any HIGH = BLOCKED); incomplete review defaults to BLOCKED; ship gate integration
- **~/.claude/agents/**: typescript-expert, python-expert, go-expert, devops-engineer, ml-engineer, bi-developer — six language and domain expert agents (global scope)
- **~/.claude/CLAUDE.md** — Claude Code patterns section: context rewind threshold (~300-400k tokens), PR size target (~120 lines), subagent dispatch at >50% context

## [0.6.0] — 2026-04-17

### Changed
- **verify** skill: added Iron Law gate, Common Failures table, Red Flags list, Rationalization Prevention table, evidence patterns (borrowed from Superpowers verification-before-completion)
- **review** skill: two-stage review ordering — spec compliance first, then code quality; subagent reviewer dispatch templates; "Do Not Trust the Report" principle (borrowed from Superpowers subagent-driven-development)
- **build** skill: subagent-driven execution with fresh agent per task, pre-inlined context injection, dependency-wave parallel execution, model selection heuristic, implementer prompt template, phase-locked transitions (borrowed from Superpowers + GSD)
- **handoff** skill: dual-output (markdown + JSON), recovery state machine for programmatic resume, context pressure triggers (borrowed from GSD pause/resume pattern)
- **on-context-threshold** hook: doubled all thresholds (WARN 1500→3000, COMPACT 2500→5000, HANDOFF 3500→7000, URGENT 4500→9000)

## [0.5.0] — 2026-04-16

### Added
- `agents/chief-of-staff.md`, `agents/engineering.md`, `agents/game.md`, `agents/client.md` — four agent personas flattened from `<name>/CLAUDE.md` layout; Dannis/SeayInsights references replaced with `{{director_name}}` placeholder resolved at skill-load time
- `agents/director.md` — fill-in-blanks Director persona template (name, role, focus, hard limits, tool preferences)
- `agents/context/director-preferences.md`, `director-corrections.md`, `session-context.md`, `session-primer.md`, `fullstack-standards.md` — ported from studio, generalized (notion-studio-mcp calls and brand-specific tokens removed; `{{director_name}}` placeholder)
- `on-context-threshold.py` slug builder now replaces spaces with `-` on both drive-letter and fallback branches (mirrors studio fix from commit `25208c9`); new unit test covers Windows-path-with-spaces, Unix-path-with-spaces, and no-spaces cases
- Integration test `test_projects_dir_slug_replaces_spaces` (52 tests total)

### Removed
- `agents/torii/` — TORII is a separate product, not shipped with dream-studio
- All `notion-studio-mcp` auto-logging calls from agent personas (log_agent_action, log_escalation, get_pending_escalations, etc.)
- References to `studio-ops`, `dannis-naomi`, specific project repos
- "SeayInsights brand tokens" section in `fullstack-standards.md` — now a fill-in-blanks block

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
