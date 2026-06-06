# Publication Boundary

Dream Studio is public source plus private local authority. The public GitHub repository should accurately represent the current product without publishing private operational history.

## Public Allowlist

The public repo may contain:

- product source code;
- public documentation;
- schema migrations and tests;
- examples, templates, and synthetic fixtures;
- adapter projection templates;
- sanitized demos;
- sanitized release notes;
- public license, security, and contribution guidance.

## Private By Default

Keep these out of Git unless separately sanitized and approved:

- `.dream-studio/` runtime state;
- SQLite DB files, WAL/SHM files, dumps, and backups;
- local Work Orders, handoffs, continuation packets, approval artifacts, and operator decisions;
- raw telemetry, raw logs, hook traces, dashboard runtime logs, and token traces;
- unsanitized task attribution evidence, including private file paths,
  commands, Work Order context, validation output, adapter traces, or
  security/readiness impact details that expose private operational history;
- cutover, cleanup, rollback, dogfood, release, and local audit evidence;
- generated prompts and private context packets;
- private career profiles, resumes, cover letters, role strategies,
  application records, recruiter/contact notes, compensation strategy,
  browser automation evidence, and career scorecards;
- GitHub repo intake evidence that includes unsanitized adoption analysis,
  license/security notes, private Work Orders, or attribution/legal review
  context;
- external-project details not intentionally public;
- private external-target intake evidence, dirty-state snapshots, Work Orders,
  handoffs, validation reports, and route decisions;
- secret, credential, token, or private data values.

## Current Repo Hygiene

`.gitignore` excludes local runtime state, database files, backups, logs, and local evidence exports. If a private file has been committed in the past, remove it from current tracking without deleting the local copy, then classify whether history rewrite is required.

**Phase 18.1.14b (2026-05-25):** `core/org_intelligence/` and `projections/ml/` were brought in from the enterprise repo and are now part of the public OSS repo under the main Apache-2.0 license. No proprietary framing, no license gates, no private content. The enterprise repo itself (`../dream-studio-enterprise/`) remains external and is excluded from tracking via `.gitignore`.

Repo publication readiness is checked through the repo-owned command:

```powershell
python interfaces\cli\repo_publication_readiness.py --strict
```

The command audits tracked file paths, ignored/untracked boundaries, Git history
path names, Apache-2.0 references, README/PRD product framing, and
private-content/secret-pattern rules without printing matched secret values.
Use `--execute --output-dir docs\publication` only when intentionally
refreshing public publication evidence artifacts.

## Git History Policy

- Non-secret historical product docs can usually remain in history after current-state cleanup.
- Private local DB backups, raw logs, local evidence, or sensitive operator state in history require a history rewrite risk assessment.
- Secrets, credentials, tokens, or sensitive private data in history require immediate operator approval before any rewrite and should trigger rotation guidance.
- Never force-push or rewrite remote history without explicit operator approval.

## Documentation Rule

Public docs should describe Dream Studio as a local-first AI orchestration and operational intelligence platform. Adapter-specific docs may describe Claude Code, Codex, Cursor, Copilot, ChatGPT, MCP, shell, or local-model surfaces, but must not frame any adapter as the product itself.

Installed command docs may include `ds dashboard --status`, `--serve`,
`--open`, and `--check` as public-safe command names. They must not include
private local URLs, local runtime paths, dashboard screenshots from live
operator state, or raw dashboard/API payloads unless separately sanitized.

External project and Docker docs may describe the public-safe policy and module
contracts, but must not publish private target details, local scans, target
dirty-state output, target paths, container runtime evidence, or operational
approval artifacts. Final productization closeout can be summarized publicly
only as sanitized readiness status; private release evidence stays local.

Career data is a deny-by-default private data class: resumes,
profile fields, application history, automation traces, and career strategy are
private by default. Public portfolio or case-study outputs require explicit
operator approval and redaction.

GitHub repo intake may be documented as a workflow, but actual evaluation
evidence remains private until license, attribution, security, and publication
boundaries are satisfied.

Task attribution may be documented as a product capability, but live operator
records are private by default. Public examples must be synthetic or sanitized
and must not expose private Work Orders, file paths, command output, raw
validation evidence, security findings, or external-project details.

Platform-hardening may be documented as a product capability, but raw
evaluation evidence, policy decisions, connector payloads, local watch results,
team rollup source material, installer logs, and demo/case-study evidence are
private by default. Public outputs must use the `public_sanitized` visibility
profile and must exclude raw Work Orders, handoffs, operator decisions, local
paths, raw telemetry, local evidence, cutover/rollback details, private project
details, career/application data, compensation strategy, secrets/auth/config
values, and unsanitized security findings.

## Contract Atlas Export Rule

The Contract Atlas is private/local by default. Public atlas exports are allowed
only when sanitized: local paths, live runtime state, local adapter config
contents, private evidence paths, backups, raw telemetry, and operator-specific
metadata must be removed or replaced with non-sensitive placeholders.

`ds contract-atlas-refresh --output-dir <dir> --execute` is the supported export
refresh surface. It writes the public sanitized atlas and freshness manifest to
an explicit directory, and writes a private/internal atlas only when
`--include-private` is supplied. Private/internal exports are not repo-safe and
must remain in operator-local runtime or review locations.

## Release-Gate Runtime Boundary

Release-gate validation evidence may be summarized publicly only after the gate
runs against isolated temporary Dream Studio state and the active installed
SQLite hash remains unchanged. Public pilot or demo packets should reference
sanitized release status, not raw gate output containing local paths, runtime
state locations, or private operational evidence.

## Legacy Upgrade Boundary

Legacy install detection and migration docs may describe the generic safe
upgrade process, but public exports must not include old source paths, backup
paths, launcher contents, Claude/Codex settings, adapter projections, local
runtime paths, or row-level migration evidence. Old Work Orders, handoffs,
reports, evidence folders, audit files, prompts, caches, logs, backups, and
rollback details remain private unless separately sanitized and approved.

## PRD Lifecycle Boundary

PRD lifecycle behavior may be documented publicly, but project-specific PRD
versions, assumptions, open questions, change orders, route reconciliations,
evidence refs, and Work Order details are private unless explicitly exported
through a sanitized profile. Public examples must be synthetic or redacted and
must not expose private operator history, local paths, external-project details,
career data, or unsanitized security/readiness findings.

## README Currency At Release

README.md accuracy is a **release-boundary human judgment**, not a per-PR mechanical
coupling. The per-PR docs-drift gate does not enforce README review (that coupling
was removed in Phase 18.4 consolidation because CI-gate and lint-baseline changes
were training content-free stamps — "No README content change required" — not real
reviews). Instead, README currency is confirmed at release time:

Before release or public publication: confirm README.md accurately reflects this
cycle's product-level changes — new or changed top-level capabilities, install flow
changes, core concept updates, and user-facing surface changes. This is a human
review at the release boundary, not a file-glob trigger. The release-validation
command (`python interfaces/cli/repo_publication_readiness.py --strict`) checks
README/PRD product framing as part of its validation; that's the automated signal.
README accuracy for specific feature/change cycles is reviewed by the operator
exercising judgment about product-level communication, not by an automated gate
that fires on every baseline cleanup.

<!-- Last reviewed 2026-05-20 — public sanitized Contract Atlas export refresh hardened against POSIX absolute paths in core/shared_intelligence/contract_atlas.py; no policy change required here. -->

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

<!-- Last reviewed 2026-05-21 — Platform profile publication boundary: `~/.dream-studio/state/platform.json` is private local state and must not be committed to git. It contains OS name, OS version, shell, Python version, and terminal — enough context to fingerprint a machine. Treat it the same as `studio.db`: ignored by git, never included in public docs, demos, or exports. The module source (`core/config/platform.py`) is public repo source. -->

<!-- Last reviewed 2026-05-21 — TA0 SDLC entity creation events: interfaces/cli/ds.py change in this PR is a CLI handler refactor only. _project_register now delegates to core.projects.mutations.register_project() instead of containing an inline INSERT. This aligns the CLI with the A2 refactor pattern already applied to all other project/milestone/work-order handlers. No new CLI surface, no new permissions, no installer change, no runtime path change, no adapter boundary change. No policy or contract change in this doc. -->

<!-- Last reviewed: TA2 (2026-05-22) — no structural change required for this workstream -->

<!-- Last reviewed 2026-05-22 — TA3 reviewed; no changes required for this doc. -->

<!-- Last reviewed 2026-05-22 — Phase 18.1.5: docs/architecture/projection-framework.md added as a public architecture reference covering projection lifecycle, CLI commands, L3 table design, dead-letter/retry behavior, and how to write new projections. Content is public-safe product documentation with no private operational content, local paths, or operator-specific state. No publication boundary policy change required. -->


<!-- Last reviewed 2026-05-23 -- Phase 18.1.7: ds_* project-spine tables renamed to business_* via migration 070. No policy or boundary change in this doc; runtime table names updated. -->


<!-- Last reviewed 2026-05-24 — Phase 18.1.13: ds validate and ds doctor --help text updated to explicitly identify each command's health-check plane. ds validate description now reads: DB authority plane (schema version, migrations, module profiles). ds doctor description now reads: Claude Code integration plane (skills, agents, hooks, routing, version). Each help text cross-references the other command. README.md health-checks section expanded; docs/operations/fresh-install-validation.md updated to require both commands. No runtime behavior change. No new CLI surface. No policy or contract change in this doc. -->

<!-- Last reviewed 2026-05-26 — Phase 18.1.15b: docs/contributing/pre-push-hook.md added as public contributor documentation describing the six pre-push gate checks. This is an intentional publication — no private artifact risk. No policy or boundary change in this doc. -->


<!-- Last reviewed 2026-05-27 — Phase 18.1.17: PR Smoke CI expanded to multi-OS matrix (ubuntu-latest, macos-latest, windows-latest). pip-audit dependency vulnerability scan added to PR Smoke. Full CI workflow now also triggers on push to main (not just manual dispatch) and adds pytest-cov coverage gate (fail_under=8%). No policy or publication boundary change in this doc. -->


<!-- Last reviewed 2026-05-27 — Phase 18.1.18: FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true added to all 4 CI workflows ahead of 2026-06-02 mandatory Node.js 24 transition. INSTALL.md added as standalone installation reference. CHANGELOG updated with Phase 18.1.16-18.1.17 notes. No policy or publication boundary change in this doc. -->

<!-- Last reviewed 2026-05-27 — fix/ci-gate-db-path-collision: ci_gate.py _isolated_test_env() now uses separate mkdtemp calls for HOME and DREAM_STUDIO_DB_PATH so conftest.guard_real_homedir's _db_redirected check returns True and the CI abort guard does not fire on test DB writes. No release gate policy change; this is a CI isolation bug fix only. -->

<!-- Last reviewed 2026-05-27 — Phase 18.2.5: ProjectProjection added for project.created/activated/deactivated/deleted events; migrations 076 and 077 add event-tracking columns to business_projects. No platform hardening sequence changes, no publication boundary changes, no contract atlas or dashboard projection mapping changes. -->

<!-- Last reviewed 2026-05-28 — fix/linux-ci-failures-batch2: repo_publication_readiness.py extended with two precision exclusions: (1) contract_atlas.py added to _skip_private_content_scan_path() for known regex literal; (2) canonical/skills/quality/modes/security/ added to _skip_secret_scan_path() for deliberate fake API keys in smoke test docs. No publication boundary policy change. -->

<!-- Last reviewed 2026-05-29 — Phase 18.4.6 migration-risk gate: flake8-baseline.txt stale-entry cleanup + pre-push migration-risk gate added. No publication boundary change; migration SQL files and sqlite_bootstrap.py are not publication-boundary concerns. -->

<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->

<!-- reviewed: 2026-05-30, brownfield vertical slice migration 085. Stack profile + security_scan_runs. No semantic changes required to this document. -->

<!-- 2026-06-01: security_scan_runs → scan_runs, security_findings → findings, security_scan_deltas → scan_deltas (migration 089); brownfield intake prompt added; proving-index.md added. -->

<!-- 2026-06-05: Phase 18.6.2 reviewed — module_contracts.py removed project_health_scorecards and project_readiness_scorecards from analytics_only read_dependencies (tables dropped in migration 099). No semantic change to this document required. -->

<!-- 2026-06-05: Wave 2 career annihilation — career_ops module, 15 career_* tables (migration 100), ds-career skill pack, /career-ops route, career_ops contract+profile, and career expert workflow removed. capability_center/scoped_agents/github_repo_intake unchanged. Reworded only the one module sentence ("Career Ops may be documented as an optional private module") to "Career data is a deny-by-default private data class"; the private-export deny lists naming career profiles/resumes/career data are privacy policy and stay verbatim. -->

<!-- 2026-06-06: Wave 6 — 13 verified-dead tables dropped (migration 101). no semantic change required. -->
