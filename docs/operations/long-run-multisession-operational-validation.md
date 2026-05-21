# Long-Run Multisession Operational Validation

Lifecycle status: tested_only

Long-run validation is a dogfood and stability gate, not a feature expansion
surface. It consumes evidence from realistic internal cycles and confirms that
Dream Studio remains stable across sessions, adapters, command surfaces,
dashboard/API use, installed-state checks, and release gates.

## Required Cycles

The closeout model requires evidence for:

- dashboard/authority inspection
- local dogfood route cycle
- release gate cycle
- installed command surface cycle
- Contract Atlas/docs drift check
- security/readiness classification
- expert workflow catalog and overlap check
- Career Ops private-boundary check
- Capability Center and scoped-agent context check
- GitHub repo intake workflow check
- adapter/router status check
- analytics-only profile check
- task attribution outcome check for a completed Work Order or recent project
  task when such evidence exists
- legacy install detection and migration dry-run check, including rollback and
  adapter repair boundaries
- dashboard command mode check, including `ds dashboard --status`,
  `ds dashboard --serve`, `ds dashboard --check`, and a 200 response from
  `/dashboard` from outside the source checkout

Each cycle must include evidence refs and pass/fail status. Missing evidence is
a failure, not a silent pass.

## Boundary Checks

The validation report blocks when it sees:

- prompt-chaining regressions
- hidden mutation
- evidence file sprawl
- dashboard authority drift
- expert workflow overlap decisions creating duplicate skill systems
- private Career Ops data leaking into public exports
- scoped agents receiving full conversation history, secrets, all Work Orders,
  all memories, or unrelated private data by default
- GitHub repo intake skipping license/security/overlap review before adoption
- task attribution inventing model/provider, file, command, token, cost,
  validation, outcome, or rework precision that was not recorded
- PRD lifecycle authority missing current version, milestone, Work Order,
  change-order, or route reconciliation context needed for safe continuation
- old path references returning
- synthetic/mock/test data leaking into live dashboard views
- adapter staleness drift
- external project mutation
- Docker execution without approval
- unintended live SQLite mutation
- live SQLite hash changing across a guarded release gate

## SQLite Guard

Release validation supplies the live SQLite hash before and after the gate. The
closeout can only pass when the hash is unchanged. Tests and release gates must
not write to the live installed database unless a specific approved live update
scope says they should.

## Closeout

When all required cycles pass, no forbidden boundary action appears, and the
SQLite hash guard passes, the milestone verdict is:

```text
LONG_RUN_MULTISESSION_OPERATIONAL_VALIDATION_COMPLETE
```
## Platform Hardening Refresh

Long-run validation should include the platform-hardening summary, policy previews, opt-in watcher definitions, connector dry-run behavior, sanitized export checks, and installer doctor/repair previews. These checks remain controlled validation cycles; they must not start uncontrolled background work, mutate external projects, publish private artifacts, or destructively mutate live SQLite.

<!-- Last reviewed 2026-05-20 — repo-wide `py -m black .` formatting applied; no behavior or policy change required here. -->

<!-- Last reviewed 2026-05-20 — pipeline optimization landed (migration 057 extends ds_work_order_types with workflow_template, precondition_skill, task_generator, resolution_instructions; CLI gains `ds project state` single-query, auto-advance, gotcha injection, brief mode); doc policy unchanged here. -->

<!-- Last reviewed 2026-05-20 — A1 extraction: 22 CLI handlers refactored into importable functions under core/projects, core/work_orders, core/design_briefs, core/milestones, core/skills, core/health. ds.py wrappers are now thin (call function, print result, return exit code). No policy or contract change in this doc. -->

<!-- Last reviewed 2026-05-20 — A2.1: `_work_order_start` decomposed into `read_work_order_brief`, `write_work_order_context`, `start_work_order` under `core/work_orders/start.py`. Stdin y/N prompt removed from the pure path; CLI wrapper preserves the legacy stderr warning + non-TTY auto-accept for operator terminals. No policy or contract change here. -->

<!-- Last reviewed 2026-05-20 — A2.2: `_work_order_close` decomposed into `run_gate_check`, `check_close_gates`, `close_work_order` under `core/work_orders/close.py`. `_run_gate_check` lifted out of `interfaces/cli/ds.py`; `core/projects/queries.py` now imports the predicate directly. CLI wrapper re-emits `[gate.bypassed] WARNING:` to stderr from the returned `bypassed_gates` list for operator-terminal parity. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.3: `_project_start` decomposed into the `start_project` composer under `core/projects/start.py`, which orchestrates `set_active_project` (mutations) + `get_next_work_order` (queries) + `start_work_order` (work_orders/start). CLI wrapper converts the compound result dict into the legacy operator-facing summary; no policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.4: `_skill_invoke` (heaviest CLI handler) decomposed into `load_skill_content` + `record_skill_invocation` + `seed_gate_artifact_files` under `core/skills/invocation.py`. Duplicate `_load_packs` / `_SKILL_SPECIFIER_RE` / `_SKILL_FM_RE` removed from `interfaces/cli/ds.py`; the canonical `_load_packs` lives in `core/skills/queries.py`. Phase A3 workflow runner can now compose these three functions directly. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.5: `_design_brief_create` lifted to `create_design_brief` in `core/design_briefs/mutations.py` (returns dict with brief_id, project_id, status, next_step). CLI wrapper preserves the legacy `Draft brief created:` stdout line. A2.4's lazy `from interfaces.cli.ds import _design_brief_create` in `core/skills/invocation.py` is now a direct `core.design_briefs.mutations` import. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.6: `_design_brief_lock` lifted to `lock_design_brief` in `core/design_briefs/mutations.py` (returns dict with brief_id, status='locked', locked_at; ok=False/error for missing brief). CLI wrapper preserves the legacy `Brief <id> locked.` stdout line and exit-1 JSON path. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.7: `_milestone_close` lifted to `close_milestone` in `core/milestones/close.py`. Pure function returns one canonical result dict across every path (missing milestone / open WOs / gate failures / forced bypass / success); CLI wrapper preserves the legacy mixed-format operator output (JSON for failures, plain-text on success, `[gate.bypassed] WARNING:` stderr on force). No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.8: `_update_command` no longer self-shells via `subprocess.run(['ds','integrate','install','claude_code','--execute'])`; instead it calls `ClaudeCodeInstaller.install('execute')` directly in-process, mirroring the `ds integrate install` code path. Skips interpreter respawn, keeps tracebacks intact, and lets callers patch the installer with `unittest.mock`. Final A2 handler. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A6.3: `_project_delete` lifted to `delete_project` in `core/projects/mutations.py` (returns dict; CLI wrapper preserves the `--confirm` operator-facing text). New `ds-project:manage` mode under `canonical/skills/ds-project/modes/manage/` wraps `get_project_list` + `set_active_project` + `deactivate_project` + `delete_project` per the AI-presents-from-database discipline. Final A6 PR. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — B.3: git pre-push hook + installer wiring landed. `ds workflow run pre-push --non-interactive` dispatches deterministic gates; `ClaudeCodeInstaller.git_repo_root` opt-in plants `<repo>/.git/hooks/pre-push`. No policy or contract change in this doc. -->
