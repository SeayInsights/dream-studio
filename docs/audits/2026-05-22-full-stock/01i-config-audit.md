# Pass 1i — Configuration Audit
*Phase 1 analysis | 2026-05-22*

---

## Stated Architectural Intents

The following five intents are evaluated throughout this audit as lenses for assessing alignment or divergence:

1. **SQLite-first authority** — All runtime STATE must be SQLite-backed. File-based state is v1 rot.
2. **Security audit during brownfield onboarding** — Security skills run during project intake; findings stored in SQLite.
3. **Security audit as SDLC lifecycle gate** — Greenfield projects must pass security audit before going live.
4. **Canonical events as the spine** — All state changes flow through `canonical_events`.
5. **Marker file authority for attribution** — `.dream-studio-project` markers are identity source.

---

## Environment Variables

All variables are classified by:
- **State:** ACTIVE (read in production code at runtime) / TEST_GUARD (only in conftest.py / test files) / TEST_GATE (enables test suite behavior, not conftest-only) / PLATFORM_PROBE (passive OS detection, read-once) / CI_INJECT (set by CI environment, read by gates)
- **Intent1:** Whether the variable configures a file-path for runtime state (potential Intent #1 violation)

### DS_ Prefixed Variables

| Variable | Default | Primary Files | Controls | State | Intent1 |
|---------|---------|---------------|---------|-------|---------|
| DS_ACTIVE_TASK_PATH | `~/.dream-studio/state/active_task.json` | `core/sdlc/active_task.py` | Path to active_task.json — current operator task pointer | ACTIVE | **File-path var** |
| DS_CWD_RESOLVER_ROOT | None (no override) | `core/sdlc/cwd_resolver.py` | Caps the directory walk in tests; no-op in production | TEST_GUARD | Partial (walk boundary, not state store) |
| DS_DIAGNOSTICS_DIR | `~/.dream-studio/diagnostics` (inferred) | `runtime/hooks/core/on-post-tool-use.py`, `core/telemetry/diagnostics.py` | Diagnostics output directory | ACTIVE | **File-path var** |
| DS_DREAM_STUDIO_HOME | None | `integrations/manifest.py` | Dream Studio home for integration manifest writes | ACTIVE | File-path var (also test-guarded) |
| DS_MACHINE_ID_PATH | `~/.dream-studio/state/machine_id` | `core/telemetry/machine_id.py` | Path to machine_id file | ACTIVE | **File-path var** |
| DS_PLATFORM_PROFILE_PATH | `~/.dream-studio/state/platform.json` | `core/config/platform.py` | Path to platform profile JSON | ACTIVE | **File-path var** |
| DS_SPOOL_ROOT | `~/.dream-studio/events` | `spool/config.py`, `emitters/claude_code/run.py` | Root directory for spooled event files | ACTIVE | **File-path var** |

**Note on DS_ TEST_GUARDs:** `DS_CWD_RESOLVER_ROOT`, `DS_ACTIVE_TASK_PATH`, `DS_MACHINE_ID_PATH`, `DS_PLATFORM_PROFILE_PATH`, `DS_DIAGNOSTICS_DIR`, `DS_DREAM_STUDIO_HOME`, and `DS_SPOOL_ROOT` are all set in the `guard_real_homedir` autouse fixture in `tests/conftest.py`. This means they appear in both production code (ACTIVE) and test isolation — they are *production env vars that are also test-guarded*, not test-only vars.

---

### DREAM_STUDIO_ Prefixed Variables

| Variable | Default | Primary Files | Controls | State | Intent1 |
|---------|---------|---------------|---------|-------|---------|
| DREAM_STUDIO_BASE_REF | None | `interfaces/cli/contract_atlas_lifecycle_gate.py`, `interfaces/cli/contract_docs_drift_gate.py` | Git base ref for CI drift gates; also checked via GITHUB_BASE_REF | CI_INJECT | No |
| DREAM_STUDIO_CHANGED_FILES | None | `interfaces/cli/contract_atlas_lifecycle_gate.py`, `interfaces/cli/contract_docs_drift_gate.py` | CI-injected changed file list for drift gates | CI_INJECT | No |
| DREAM_STUDIO_CONFIG | None | `core/installed_runtime.py` | Installed adapter config path override | ACTIVE | File-path var |
| DREAM_STUDIO_CORRECTIONS_PATH | None | `core/learning/correction_patterns.py` | Path to operator correction patterns file | ACTIVE | **File-path var** |
| DREAM_STUDIO_DB_PATH | `~/.dream-studio/state/studio.db` | `core/config/database.py` | Primary SQLite DB path override | ACTIVE | File-path var (to SQLite — this is the canonical store) |
| DREAM_STUDIO_DEBUG | `""` | `core/telemetry/debug.py` | Enables debug output to stderr (`"1"` or `"true"`) | ACTIVE | No |
| DREAM_STUDIO_ENABLE_WORK_ORDER_EVAL_TELEMETRY | None | `core/work_orders/evals.py` | Enables eval telemetry emission | ACTIVE | No |
| DREAM_STUDIO_HOME | `/tmp/dream-studio-home` (Docker default) | `core/config/paths.py`, `scripts/docker_runtime_check.py` | Dream Studio home directory; Docker isolation default | ACTIVE | File-path var |
| DREAM_STUDIO_MODEL | None | `runtime/hooks/meta/on-skill-complete.py` | Overrides model selection for skill completion hooks | ACTIVE | No |
| DREAM_STUDIO_RUN_LEGACY_API_INTEGRATION | None (`!= "1"` skips tests) | `projections/api/test_api_integration.py` | Enables legacy API integration tests | TEST_GATE | No |
| DREAM_STUDIO_RUN_LEGACY_RESEARCH_DIAGNOSTICS | None | `interfaces/cli/debug_trust_score.py` | Enables legacy research diagnostics | TEST_GATE | No |
| DREAM_STUDIO_RUNTIME_WRITE_VERIFY | None (`!= "1"` skips) | `tests/runtime_verification/test_write_paths.py` | Enables runtime write path verification tests | TEST_GATE | No |
| DREAM_STUDIO_SOURCE_ROOT | None | `core/installed_productization.py` | Source root path for installed productization; written to shell wrappers | ACTIVE | File-path var |
| DREAM_STUDIO_TELEMETRY_DB | None | `core/work_orders/evals.py` | Alternate telemetry DB path for evals | ACTIVE | File-path var (to SQLite DB) |
| DREAM_STUDIO_TELEMETRY_DISABLED | None | `core/telemetry/emitters.py` | Disables all telemetry emission | ACTIVE | No |
| DREAM_STUDIO_WORK_ORDER_ROOT | `~/.dream-studio/meta/work-orders` | `core/work_orders/models.py`, `core/work_orders/storage.py` | Work order storage root directory; `STORAGE_CLASS = "file_backed"` constant in same module | ACTIVE | **File-path var** |

---

### CLAUDE_ Prefixed Variables

| Variable | Default | Primary Files | Controls | State | Intent1 |
|---------|---------|---------------|---------|-------|---------|
| CLAUDE_CODE | None | `core/work_orders/mutations.py` | Detects Claude Code adapter context (presence check) | ACTIVE | No |
| CLAUDE_FILE_PATH | `""` | `runtime/hooks/domains/on-game-validate.py`, `runtime/hooks/quality/on-agent-correction.py` | Current file path injected by Claude Code hook runtime | ACTIVE | No (hook context, not state store) |
| CLAUDE_MODEL | `"claude"` | `runtime/hooks/meta/on-skill-complete.py` | Model name from Claude Code environment | ACTIVE | No |
| CLAUDE_PLUGIN_ROOT | None | `core/config/paths.py`, `runtime/hooks/meta/on-skill-metrics.py`, `.claude/hooks/dispatch/hooks.py` | Root path of Claude Code plugin; used to resolve skill/rules paths | ACTIVE | File-path var (plugin root, not state) |
| CLAUDE_PROJECTS_DIR | None | `control/context/monitor.py`, `core/utils/compact_utils.py` | Claude projects directory path | ACTIVE | File-path var (Claude-injected, not state store) |
| CLAUDE_SESSION_ID | `"unknown"` | `runtime/hooks/meta/on-session-start.py`, `runtime/hooks/meta/on-skill-load.py` | Active Claude Code session ID | ACTIVE | No |
| CLAUDE_USER_MESSAGE_TEXT | `""` | `core/utils/milestone.py` | User message text from hook context | ACTIVE | No |

---

### GITHUB_ Prefixed Variables

| Variable | Default | Primary Files | Controls | State | Intent1 |
|---------|---------|---------------|---------|-------|---------|
| GITHUB_BASE_REF | None | `interfaces/cli/contract_atlas_lifecycle_gate.py`, `interfaces/cli/contract_docs_drift_gate.py` | GitHub Actions base ref; fallback for DREAM_STUDIO_BASE_REF | CI_INJECT | No |
| GITHUB_PERSONAL_ACCESS_TOKEN | `""` | `interfaces/cli/pulse_collector.py` | GitHub API token for pulse collector | ACTIVE | No |

---

### Other Variables (OS / Platform / Third-Party)

| Variable | Default | Primary Files | Controls | State | Intent1 |
|---------|---------|---------------|---------|-------|---------|
| ANALYTICS_SMTP_PASS | None | `projections/config/settings.py` | SMTP password for analytics email | ACTIVE | No |
| ANALYTICS_SMTP_USER | None | `projections/config/settings.py` | SMTP username for analytics email | ACTIVE | No |
| ANTHROPIC_API_KEY | None | `interfaces/cli/ci_gate.py` | Anthropic API authentication for CI gate | ACTIVE | No |
| COMSPEC | `""` | `core/config/platform.py` | Windows shell path (cmd.exe detection) | PLATFORM_PROBE | No |
| EMAIL_PASSWORD | None | `projections/core/email/sender.py` | Email sender password | ACTIVE | No |
| EMAIL_USERNAME | `"your-email@gmail.com"` | `projections/core/email/sender.py` | Email sender username | ACTIVE | No |
| HOME | `/tmp/dream-studio-user` (Docker default) | `.claude/hooks/run.py`, `emitters/claude_code/run.py` | User home directory; Docker isolation default | ACTIVE | No (OS var) |
| ITERM_SESSION_ID | None | `core/config/platform.py` | iTerm2 session detection | PLATFORM_PROBE | No |
| JINA_API_KEY | None | `control/research/web.py` | Jina AI API key for web research | ACTIVE | No |
| POWERSHELL_DISTRIBUTION_CHANNEL | None | `core/config/platform.py` | PowerShell Core detection | PLATFORM_PROBE | No |
| PSModulePath | None | `core/config/platform.py` | Windows PowerShell detection (presence check) | PLATFORM_PROBE | No |
| PULSE_COOLDOWN_SEC | `"60"` | `interfaces/cli/pulse_collector.py` | Cooldown seconds between pulse collections | ACTIVE | No |
| SENTRY_DSN | None | `core/telemetry/telemetry.py`, `packs/domains/templates/project-standards/hooks/lib/telemetry.py` | Sentry error reporting DSN | ACTIVE | No |
| SHELL | `""` | `core/config/platform.py` | Unix shell path (platform detection) | PLATFORM_PROBE | No |
| TERM | `""` | `core/config/platform.py` | Terminal type string | PLATFORM_PROBE | No |
| TERM_PROGRAM | `""` | `core/config/platform.py` | Terminal program name | PLATFORM_PROBE | No |
| USERPROFILE | `str(Path.home())` | `.claude/hooks/run.py`, `emitters/claude_code/run.py`, `interfaces/cli/ds_memory.py` | Windows user profile path | ACTIVE | No |
| WT_SESSION | None | `core/config/platform.py` | Windows Terminal detection (presence check) | PLATFORM_PROBE | No |

**Total variable count:** 44 os.* reads + 7 string-literal-only = 51 distinct variables across the codebase.

---

## Special Focus: File-Path Variables (Intent #1)

The following env vars configure file paths that point to runtime state stores. Under Intent #1 (SQLite-first authority), these are evaluated against whether a SQLite equivalent exists.

| Variable | Points To | File-Based Store Type | SQLite Equivalent? | Assessment |
|---------|-----------|----------------------|-------------------|------------|
| DS_SPOOL_ROOT | `~/.dream-studio/events/` | Event spool directory (JSON files per event, JSON session files in `.sessions/`) | Yes — `canonical_events` table; spool is intentional pre-ingestion buffer | **Transitional** — spool is the write buffer, SQLite is the target. Ingestor runs on Stop hook. Architecture is correct if spool is always flushed. |
| DS_ACTIVE_TASK_PATH | `~/.dream-studio/state/active_task.json` | Single JSON file tracking current task_id, work_order_id, milestone_id, project_id | `ds_tasks`, `ds_work_orders` tables exist | **Intent #1 violation** — active task is a file-based pointer. SQLite has the full task graph but the active pointer lives in a file. |
| DS_MACHINE_ID_PATH | `~/.dream-studio/state/machine_id` | Plain text file with UUID | None found | **Intent #1 violation** — machine identity persisted to file, not SQLite. |
| DS_PLATFORM_PROFILE_PATH | `~/.dream-studio/state/platform.json` | JSON platform detection snapshot | None found | **Intent #1 violation** — platform detection result persisted to file, not SQLite. |
| DS_DIAGNOSTICS_DIR | `~/.dream-studio/diagnostics/` (inferred) | Directory of diagnostic output files | None found | **Intent #1 violation** — diagnostic output writes to file system, no SQLite table. |
| DREAM_STUDIO_WORK_ORDER_ROOT | `~/.dream-studio/meta/work-orders/` | YAML/JSON work order documents; `STORAGE_CLASS = "file_backed"` literal in models.py | `ds_work_orders` table exists | **Intent #1 violation** — work orders have a SQLite table but a parallel file-backed store still exists with an explicit `STORAGE_CLASS = "file_backed"` constant. |
| DREAM_STUDIO_CORRECTIONS_PATH | None (defaults via `meta_dir()`) | Corrections markdown / log file in `~/.dream-studio/meta/` | None found | **Intent #1 violation** — operator corrections are file-only, no SQLite table. |
| DREAM_STUDIO_HOME | `/tmp/dream-studio-home` (Docker) | Top-level home directory for all file stores | Partial — SQLite lives inside this directory | **Architectural root** — this is the parent of all other file-path vars. SQLite-first does not eliminate this var but everything under it should eventually be in SQLite. |
| DREAM_STUDIO_DB_PATH | `~/.dream-studio/state/studio.db` | SQLite database file | IS the SQLite store | **Aligned** — this is the canonical database path override. It is the one file-path env var that IS the SQLite authority. |
| DREAM_STUDIO_TELEMETRY_DB | None | Alternate SQLite DB path for eval telemetry | Alternate SQLite store | **Aligned** — alternative SQLite path for telemetry, not a parallel file store. |
| DS_DREAM_STUDIO_HOME | None | Integration manifest write target | None found | **Intent #1 violation** — integration manifest writes to a file under this path, not SQLite. |
| DREAM_STUDIO_SOURCE_ROOT | None | Source root path baked into shell wrapper scripts | N/A (install-time path, not runtime state) | **Acceptable** — install-time configuration, not runtime state. |
| DREAM_STUDIO_CONFIG | None | Installed adapter config file path | None found | **Intent #1 violation** — adapter config is file-backed, no SQLite equivalent. |

**Summary:** Of 13 file-path env vars, 9 point to file-based runtime state with no SQLite equivalent. 2 point to SQLite. 1 is the spool buffer (intentionally transitional). 1 is install-time only.

---

## Core Config Files

### `core/config/database.py`

- **Role:** Declared "SINGLE SOURCE OF TRUTH" for all SQLite connections. Provides `get_connection()`, `DatabaseContext`, `DatabaseRuntime` singleton, `transaction()`, `health_check()`, and `initialize_database()`.
- **DB path resolution:** `DREAM_STUDIO_DB_PATH` env var → `~/.dream-studio/state/studio.db`.
- **Singleton:** `DatabaseRuntime._instance` (thread-safe double-checked locking). Reads via `_read_only_db_path()` check the singleton before falling back to `_default_db_path()`.
- **Settings on every connection:** WAL mode, `foreign_keys=ON`, `busy_timeout=30000ms`, row factory.
- **Migration integration:** `_initialize_database()` calls `core.config.sqlite_bootstrap.run_migrations()` on singleton init.
- **Legacy shims:** `get_connection()`, `db_path()`, `DatabaseContext` are preserved for backward compatibility alongside the newer `transaction()` contextmanager and `DatabaseRuntime.get_connection_context()`.
- **Observation:** Two parallel connection paths exist — the legacy `get_connection()` and the singleton `DatabaseRuntime.get_connection_context()`. Both set the same PRAGMA values, but the legacy path re-enables WAL per-connection whereas the singleton only sets it on init. Subtle behavioral difference under re-use.

### `core/config/paths.py`

- **Role:** Cross-platform path resolution for all hooks and config. Canonical source for user data dir, state dir, meta dir, sessions, planning, memory, spool placement, and plugin root.
- **Key env vars consumed:** `CLAUDE_PLUGIN_ROOT`, `DREAM_STUDIO_HOME`.
- **Notable paths:**
  - `user_data_dir()` → `~/.dream-studio/` (DREAM_STUDIO_HOME override)
  - `state_dir()` → `~/.dream-studio/state/`
  - `meta_dir()` → `~/.dream-studio/meta/`
  - `sessions_dir()` → `~/.dream-studio/.sessions/` (note hidden directory with dot prefix)
  - `planning_dir()` → `~/.dream-studio/planning/`
  - `memory_dir()` → `~/.claude/projects/<slug>/memory/`
- **plugin_root():** Three-tier resolution: `CLAUDE_PLUGIN_ROOT` env → walk-up looking for `.claude-plugin/plugin.json` → infer from file location. Raises `RuntimeError` on complete failure.
- **check_for_update():** Writes daily sentinel files to `state_dir()` (`.update-checked-<date>`). File-based sentinel, no SQLite equivalent.
- **warn_version_mismatch():** Writes sentinel files to `state_dir()` (`.version-warned-<version>`). File-based sentinel.
- **Observation:** `sessions_dir()` returns `~/.dream-studio/.sessions/` (hidden dot-directory inside user_data_dir). This differs from `project_sessions_dir(name)` which returns `~/.dream-studio/projects/<name>/sessions/`. Two session path conventions exist simultaneously.

### `core/config/platform.py`

- **Role:** Detects OS, shell, Python version, and terminal. Persists to `~/.dream-studio/state/platform.json`.
- **Env var consumed:** `DS_PLATFORM_PROFILE_PATH` (override for tests).
- **Detection probes:** `PSModulePath` (Windows PowerShell), `POWERSHELL_DISTRIBUTION_CHANNEL` (PS Core), `COMSPEC` (cmd.exe), `SHELL` (Unix), `WT_SESSION` (Windows Terminal), `ITERM_SESSION_ID` (iTerm2), `TERM_PROGRAM`, `TERM`.
- **`ensure_platform_recorded()`:** Overwrites on every call — no idempotency guard. Called at install and `ds doctor`.
- **`get_platform_profile()`:** Reads from file; falls back to `ensure_platform_recorded()` if absent or corrupt. Creates file on read if missing.
- **Observation:** Platform profile is file-backed (`platform.json`). No SQLite table. This is an Intent #1 violation for "runtime state."

### `core/config/state.py`

- **Role:** Config and pulse state I/O for `~/.dream-studio/config.json` and `~/.dream-studio/meta/pulse-latest.json`.
- **Dual-write:** `write_config()` and `write_pulse()` attempt to emit canonical events via `LegacyBridge`. The bridge is lazily initialized and fails silently — never blocks config/pulse writes.
- **`backup_db()`:** Called by `write_pulse()` on every pulse write. Uses SQLite Online Backup API to copy `studio.db → studio.db.bak`. Day-1-of-month triggers VACUUM. Then calls `_maybe_cloud_push()`.
- **`_maybe_cloud_push()`:** Reads `~/.dream-studio/state/backup-config.json`; spawns a subprocess if `auto_push` enabled. Uses `studio_db.set_sentinel()` for push tracking.
- **Schema guards:** All persisted documents carry `schema_version`; readers raise `SchemaVersionError` if document is newer than code supports (current: v1).
- **Atomic writes:** Uses `tempfile.mkstemp` + `os.replace` for all JSON writes.
- **Observation:** `config.json` and `pulse-latest.json` remain file-based state. `write_pulse()` triggers a DB backup on every call, which means backup frequency is coupled to pulse write frequency — potentially very frequent.

### `core/config/sqlite_bootstrap.py`

- **Role:** Migration authority. Intentionally independent of the runtime singleton. Reads SQL files from `core/event_store/migrations/`.
- **`run_migrations()`:** Creates `_schema_version` table if absent; applies pending numbered migrations in order; silently skips `duplicate column name`, `no such module`, and specific `no such table` errors for known v1 tables.
- **`bootstrap_database()`:** Creates or migrates a DB at any path with full PRAGMA settings.
- **Observation:** The silent-skip list in `run_migrations()` is hardcoded to specific table names (`fts_gotchas`, `memory_entries`, `ds_documents`, `canonical_events`). New tables that encounter `no such table` errors during migration will raise, not silently skip.

### `shared/config.py` (DEPRECATED)

- **Status:** Explicitly deprecated. Module docstring says "For path resolution, import from `core.config.paths` directly."
- **What remains:** `DreamStudioConfig` class managing `~/.dream-studio/config.json` for `project_roots` and cleanup settings. All path properties delegate to `core.config.paths`.
- **Still functional:** `project_roots`, `auto_cleanup_temp`, `keep_temp_days`.
- **Migration version embedded:** `_create_default()` hardcodes `"migration_version": 13` in the default config JSON — this is a legacy artifact not connected to the SQLite migration system.
- **Module-level singleton:** `_config_instance` at module level. Lives as long as the process.

### `shared/paths.py` (DEPRECATED)

- **Status:** Explicitly deprecated. Emits `DeprecationWarning` on import (stacklevel=2).
- **What remains:** `PathResolver` class whose every method delegates to `core.config.paths`. `get_resolver()` module-level singleton.
- **Observation:** The deprecation warning is emitted at import time. Any code that still imports `shared.paths` will emit a warning in every process that touches it.

---

## Tool Configuration (pyproject.toml)

### pytest settings

```toml
[tool.pytest.ini_options]
testpaths = ["tests", "analytics/tests"]
asyncio_mode = "auto"
addopts = "-v --color=no"
filterwarnings = ["ignore::DeprecationWarning", "ignore::PendingDeprecationWarning"]
markers = [
    "runtime_reliability: Phase 5 runtime reliability gate — core contracts that must always pass",
]
```

- **testpaths:** `tests/` and `analytics/tests/`. The `projections/api/test_api_integration.py` file is in `projections/` which is NOT in `testpaths` — it will not run in standard `pytest` invocation. It requires explicit path or separate invocation.
- **DeprecationWarnings suppressed globally.** This means `shared.paths` import warnings from still-using code will be silently swallowed during test runs.
- **One marker defined:** `runtime_reliability`. No markers for security tests, integration tests, smoke tests, or contract tests. Gate-style tests (e.g. `test_write_paths.py`) use pytest `skipif` on env var presence rather than markers.
- **asyncio_mode = "auto":** All async test functions are automatically treated as async tests without explicit `@pytest.mark.asyncio`.

### Coverage configuration

```toml
[tool.coverage.run]
source = ["hooks/lib", "packs/domains/domain_lib"]
omit = [
    "hooks/lib/workflow_state.py",
    "hooks/lib/traceability.py",
    # Wave 0 infrastructure (temporary - add tests in Wave 1)
    "hooks/lib/deprecation.py",
    "hooks/lib/document_store.py",
    "hooks/lib/migrate_files_to_sqlite.py",
    "hooks/lib/research_engine.py",
    "hooks/lib/research_methods.py",
    "hooks/lib/wave_executor.py",
    # Wave 6 learning systems (temporary - add tests in follow-up)
    "hooks/lib/pattern_learning.py",
    "hooks/lib/workflow_learning.py",
    "hooks/lib/token_optimization.py",
    "hooks/lib/repo_analyzer.py",
    # Progressive disclosure & discovery systems (temporary - add tests in follow-up)
    "hooks/lib/skill_router.py",
    "hooks/lib/skill_calibration.py",
    "hooks/lib/component_extractor.py",
    "hooks/lib/findings_summarizer.py",
    "hooks/lib/team_context.py",
]
[tool.coverage.report]
fail_under = 70
```

**Critical observation:** Coverage source is scoped to `hooks/lib` and `packs/domains/domain_lib` only. This means:
- `core/` — not measured
- `runtime/` — not measured
- `spool/` — not measured
- `emitters/` — not measured
- `interfaces/` — not measured
- `control/` — not measured
- `projections/` — not measured
- `integrations/` — not measured

The `fail_under = 70` threshold applies only to the measured subset. Coverage of the overall codebase is unknown. The 70% figure is not a codebase-wide health indicator.

**Omission categories and stated reasons:**
- `workflow_state.py`, `traceability.py` — no reason stated; likely legacy/stale
- Wave 0 infrastructure (6 files) — labeled "temporary - add tests in Wave 1"
- Wave 6 learning systems (4 files) — labeled "temporary - add tests in follow-up"
- Progressive disclosure systems (5 files) — labeled "temporary - add tests in follow-up"

All 17 omitted files are in `hooks/lib/`. No audit timestamp on any omission. "Temporary" labels have no associated work orders or issue refs.

### Pre-commit hooks

```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 24.0.0
    hooks:
      - id: black         # Python formatting
  - repo: https://github.com/PyCQA/flake8
    rev: 7.0.0
    hooks:
      - id: flake8        # Linting (max-line-length=100, tests/* ignores E501/F401)
  - repo: local
    hooks:
      - id: conventional-commits
        name: Conventional commit message format
        language: pygrep
        stages: [commit-msg]
        entry: '^(feat|fix|docs|chore|refactor|test|ci|style|perf|build|revert)(\(.+\))?: .{1,72}'
```

**Three hooks total.**
- No security-related pre-commit hook (no `bandit`, `pip-audit`, `detect-secrets`, `safety`, or similar).
- No type-checking hook (pyright not in pre-commit).
- Conventional commit enforcement is regex-only; body length and scope are not validated beyond the 72-char subject cap.
- Both `black` and `flake8` use pinned revisions (24.0.0, 7.0.0).

### `pyrightconfig.json` — Type Checking Scope

```json
{
  "include": ["hooks", "tests"],
  "extraPaths": ["hooks"],
  "pythonVersion": "3.10",
  "typeCheckingMode": "basic",
  "reportMissingModuleSource": "none"
}
```

- **Scope:** Only `hooks/` and `tests/` directories. Excluded: `core/`, `runtime/`, `spool/`, `emitters/`, `interfaces/`, `control/`, `projections/`, `integrations/`, `packs/`, `canonical/`, `scripts/`.
- **pythonVersion:** `"3.10"` — the codebase targets Python 3.12 (MEMORY.md says Python 3.12 installed). Pyright is type-checking against 3.10 semantics. Match operator (`case`/`match`) syntax from 3.10+ is covered, but 3.12 type narrowing improvements are not leveraged.
- **typeCheckingMode:** `"basic"` — the lowest non-off level. Does not catch many type errors that `standard` or `strict` would.
- **reportMissingModuleSource:** `"none"` — suppresses warnings about third-party stubs. This masks cases where the wrong type stub is used.
- **Net effect:** The majority of the codebase (`core/`, `runtime/`, `interfaces/`, etc.) has no static type coverage at all. `hooks/` and `tests/` have basic-mode coverage only.

---

## Findings

### F1 — Coverage configuration is disconnected from codebase reality
`[tool.coverage.run]` measures `hooks/lib` and `packs/domains/domain_lib` only. The `fail_under = 70` threshold is met against this narrow slice. `core/`, `runtime/`, `interfaces/`, `spool/`, `emitters/`, and all other production directories are not measured. The 70% number is not a valid codebase health indicator.

### F2 — 9 of 13 file-path env vars point to runtime state with no SQLite equivalent
File-backed state configurable via env var includes: active task pointer (`DS_ACTIVE_TASK_PATH`), machine identity (`DS_MACHINE_ID_PATH`), platform profile (`DS_PLATFORM_PROFILE_PATH`), diagnostics output (`DS_DIAGNOSTICS_DIR`), integration manifests (`DS_DREAM_STUDIO_HOME`), operator corrections (`DREAM_STUDIO_CORRECTIONS_PATH`), adapter config (`DREAM_STUDIO_CONFIG`), and work order documents (`DREAM_STUDIO_WORK_ORDER_ROOT`). The spool (`DS_SPOOL_ROOT`) is the one file-backed store explicitly designed as a pre-SQLite buffer.

### F3 — DREAM_STUDIO_WORK_ORDER_ROOT has explicit `STORAGE_CLASS = "file_backed"` constant
In `core/work_orders/models.py`, line 13: `STORAGE_CLASS = "file_backed"`. This is not a dead comment — it is a string constant exported from the module. A `ds_work_orders` SQLite table exists, but work orders are still loaded from disk documents via `load_work_order_file()`. This is a partially-migrated dual-store situation, with the file-backed path still formally named.

### F4 — 17 coverage omissions in `hooks/lib` carry "temporary" labels with no work order references
All are labeled "add tests in Wave 1 / Wave 6 / follow-up" with no associated work order IDs, issue numbers, or completion dates. Several (`migrate_files_to_sqlite.py`, `document_store.py`) are likely dead code from v1 file→SQLite migration that was never fully cleaned up.

### F5 — No security-related pre-commit hook
Three hooks: black, flake8, conventional commits. No `bandit`, `pip-audit`, `detect-secrets`, or `safety` hook. Security scanning is only available as an explicit CLI command (`ds security-review`), not enforced at commit time.

### F6 — Pyright scope excludes all of `core/`, `runtime/`, `interfaces/`
The three highest-impact production directories have no static type checking. Pyright is configured only for `hooks/` and `tests/` at `basic` level against Python 3.10.

### F7 — `write_pulse()` triggers a full DB backup on every invocation
`core/config/state.py:write_pulse()` calls `backup_db()` unconditionally. Pulse writes can be frequent. This means `sqlite3.backup()` runs on every pulse write, creating potential I/O contention.

### F8 — 35 of 39 operational env vars have no documentation in canonical docs
Only `DREAM_STUDIO_DB_PATH`, `DREAM_STUDIO_HOME`, `DS_PLATFORM_PROFILE_PATH`, `CLAUDE_CODE`, and `CLAUDE_PLUGIN_ROOT` appear in canonical docs. All others — including secrets (`ANTHROPIC_API_KEY`, `SENTRY_DSN`, `JINA_API_KEY`, `EMAIL_PASSWORD`, `GITHUB_PERSONAL_ACCESS_TOKEN`) and operational toggles (`DREAM_STUDIO_DEBUG`, `DREAM_STUDIO_TELEMETRY_DISABLED`) — are undocumented in any `docs/` file outside the audit directory.

### F9 — `projections/api/test_api_integration.py` is outside pytest testpaths
`testpaths = ["tests", "analytics/tests"]` — the `projections/` directory is not listed. Tests there will not run in standard `pytest` execution. They are also gated by `DREAM_STUDIO_RUN_LEGACY_API_INTEGRATION != "1"`, making them doubly opt-in.

### F10 — DeprecationWarnings globally suppressed in pytest config
`filterwarnings = ["ignore::DeprecationWarning"]` masks deprecation warnings including those from `shared.paths` import (which emits `DeprecationWarning` at import time). Code still importing the deprecated module will not surface in test output.

### F11 — `shared/config.py` hardcodes `migration_version: 13` in default config
The `_create_default()` method in `shared/config.py` writes `"migration_version": 13` to the JSON config. This is a legacy artifact from before the SQLite migration system. It is not connected to the `_schema_version` table. The value is stale (54 migrations have been applied).

### F12 — Two session directory conventions exist simultaneously
`sessions_dir()` in `core/config/paths.py` returns `~/.dream-studio/.sessions/` (hidden dot-directory). `project_sessions_dir(name)` returns `~/.dream-studio/projects/<name>/sessions/` (non-hidden). Both exist in the same `paths.py` module. It is unclear which is canonical for which use case.

---

## Intent Divergence

| Intent | Status | Evidence |
|--------|--------|---------|
| 1 — SQLite-first authority | **Divergent** | 9 runtime state stores remain file-backed with env var overrides; `STORAGE_CLASS = "file_backed"` is an active constant; spool-to-SQLite is the only explicitly transitional file store |
| 2 — Security audit during brownfield onboarding | Not assessable from config layer | No env var, config key, or pyproject.toml entry controls this behavior; it is a skill invocation, not a config path |
| 3 — Security audit as SDLC gate | Not enforced at config layer | No pre-commit hook enforces it; no pytest marker gates it; gating is convention-based |
| 4 — Canonical events as the spine | Partially aligned | `write_config()` and `write_pulse()` dual-write via `LegacyBridge`; dual-write is fail-open (silent on bridge absence) — spine is not guaranteed |
| 5 — Marker file authority for attribution | Aligned | `.dream-studio-project` marker usage confirmed in production code: `core/projects/mutations.py`, `core/sdlc/cwd_resolver.py`, `emitters/claude_code/project.py`, `emitters/claude_code/run.py`, `interfaces/cli/ds.py` |

---

## Open Questions

1. **When will the `STORAGE_CLASS = "file_backed"` work order store be migrated to SQLite-only?** The `ds_work_orders` table exists but the file-backed path is still active. Is there a migration plan or work order for this?

2. **What is the intended lifetime of the 17 omitted coverage files?** The Wave 0 and Wave 6 "temporary" labels have no attached work orders. Are these planned for test coverage or planned for deletion?

3. **Is `DS_DIAGNOSTICS_DIR` intentionally file-only or is there a SQLite `diagnostics` table planned?** The diagnostics dir is produced by the post-tool-use hook and has no SQLite equivalent.

4. **Should `DS_MACHINE_ID_PATH` and machine identity move to a `ds_identity` table?** Machine ID is currently a plain text file. It functions as a device fingerprint for telemetry. If telemetry goes to SQLite, this is a natural candidate to move.

5. **Is the `DREAM_STUDIO_TELEMETRY_DB` alternate DB path intentional isolation (multi-tenant), or legacy drift from before the `DREAM_STUDIO_DB_PATH` unification?** These appear to be different things but could be consolidation candidates.

6. **Why is `projections/api/test_api_integration.py` outside `testpaths` and double-gated?** Is this test file actively maintained or a migration artifact?

7. **Is `write_pulse()` triggering `backup_db()` on every call the intended behavior?** Given that pulse writes may be frequent (one per session-related event), this could mean dozens of SQLite backups per session.

8. **Should the operator-guide or a new env-vars.md document the 35 undocumented env vars?** Many are secrets or toggles that operators need to know about for deployment and debugging.
