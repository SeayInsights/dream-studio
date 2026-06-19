# Dream Studio Docker Module Profiles

Lifecycle status: tested_only

**2026-06-12 (WO b1961e3e):** No Docker profile changes. ci.yml smoke suite updated to include resurrection guard tests.

**2026-06-10 (WO-CONSTITUTION-GATES):** No Docker profile changes. ci.yml smoke suite updated to include dependency rule gate tests.

Docker is optional for Dream Studio core. The local-first SQLite authority model
must work without Docker.

## Intended Roles

Docker may support:

- repeatable local/dev execution
- optional module isolation
- security scanner isolation
- worker or adapter isolation
- dashboard/API service profiles when explicitly enabled
- future team/department deployment consistency
- validation sandboxes

## Profile Concepts

Current optional profile contracts:

- `security-scanners`
- `agent-workers`
- `workflow-workers`
- `validation-sandboxes`
- `dashboard-api`
- `adapters`

Each profile should bind or configure the approved SQLite path explicitly. No
profile should create a competing authority database by default.

Each profile declares:

- enabled modules
- required mounts
- explicit SQLite authority path policy
- secrets/config handling
- network exposure
- read/write boundaries
- telemetry emitted
- fallback when Docker is unavailable
- validation requirements
- approval requirements

## Fallback Modes

When Docker is unavailable:

- core telemetry writes continue through local SQLite
- module registry marks Docker-backed modules as `enabled=false` or
  `execution_mode=local_unavailable`
- dashboard modules display empty-state behavior
- validation sandboxes fall back to approved local tests

## Boundaries

This document does not start containers. The static profile tests also do not
start containers, build images, add dependencies, or enable dashboard/API runtime behavior. Docker
execution requires a separate explicit operator approval. Docker must never own
Dream Studio authority, create a competing SQLite database, or become required
for core, analytics-only, security-only, dashboard, shared-intelligence,
adapter-router, or local-first operation unless a future profile explicitly
enables and approves that runtime.

<!-- 18.1.14b review 2026-05-25: ML analytics modules (projections/ml/) and org intelligence (core/org_intelligence/) are now real implementations. The dashboard-api Docker profile may need to declare scipy/statsmodels/scikit-learn as optional dependencies in a future profile update. Not blocking — ML features degrade gracefully when optional deps are absent. -->

Release-gate validation for Docker profile contracts runs without Docker and
with isolated temporary Dream Studio runtime state. A passing release gate does
not imply container execution, host mounts, network exposure, or access to the
active installed SQLite database.

## SQLite Mount Policy

Container profiles receive an explicit host SQLite authority path when approved.
The default is no host-state mount. Any writable work belongs in container-local
temporary state unless a later approved runtime Work Order scopes a write
boundary. A container-local database may be used only as temporary scratch, not
as Dream Studio authority.

## Validation

The static validation suite checks that every Docker profile is optional,
declares fallback behavior, does not mount host state by default, does not
create an authority database, uses an explicit SQLite authority path, and
forbids host writes by default.

<!-- Last reviewed 2026-05-20 — public sanitized Contract Atlas export refresh hardened against POSIX absolute paths in core/shared_intelligence/contract_atlas.py; no policy change required here. -->

<!-- Last reviewed 2026-05-22 — TA3 reviewed; no changes required for this doc. -->


<!-- Last reviewed 2026-05-24 — Phase 18.1.13: ds validate and ds doctor --help text updated to explicitly identify each command's health-check plane. README.md health-checks section added. fresh-install-validation.md updated to require both commands. No policy or runtime behavior change in this doc. -->


<!-- Last reviewed 2026-05-27 — Phase 18.1.17: PR Smoke CI expanded to multi-OS matrix (ubuntu-latest, macos-latest, windows-latest). pip-audit dependency vulnerability scan added to PR Smoke. Full CI workflow now also triggers on push to main (not just manual dispatch) and adds pytest-cov coverage gate (fail_under=8%). No policy or publication boundary change in this doc. -->


<!-- Last reviewed 2026-05-27 — Phase 18.1.18: FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true added to all 4 CI workflows ahead of 2026-06-02 mandatory Node.js 24 transition. INSTALL.md added as standalone installation reference. CHANGELOG updated with Phase 18.1.16-18.1.17 notes. No policy or publication boundary change in this doc. -->

<!-- Last reviewed 2026-05-27 — fix/ci-gate-db-path-collision: ci_gate.py _isolated_test_env() now uses separate mkdtemp calls for HOME and DREAM_STUDIO_DB_PATH so conftest.guard_real_homedir's _db_redirected check returns True and the CI abort guard does not fire on test DB writes. No release gate policy change; this is a CI isolation bug fix only. -->

<!-- Last reviewed 2026-05-28 — fix/linux-ci-failures-batch2: docker-compose.yml was removed in this batch (not referenced by any active CI or test path). No docker module profile policy change. -->

<!-- Last reviewed 2026-05-29 — Phase 18.4.6 migration-risk gate: flake8-baseline.txt stale-entry cleanup + pre-push migration-risk gate added. No docker module profile change. -->

<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->

<!-- reviewed: 2026-05-30, brownfield vertical slice migration 085. Stack profile + security_scan_runs. No semantic changes required to this document. -->

<!-- 2026-06-05: Wave 2 reviewed — validate-skills.yml CI workflow fixed to exclude deleted SKILL.md files (--diff-filter=d). No release-gate or publication policy change; no semantic change required in this doc. -->

<!-- 2026-06-06: WO-D dead discovery route removal — flake8-baseline.txt stale-entry cleanup. No docker module profile change; deleted routes were internal only with no Docker boundary impact. -->
<!-- Last reviewed 2026-06-07 — WO-H hygiene & gate bookkeeping: flake8-baseline regenerated. No change to Docker module profiles or SQLite mount policy. -->

<!-- Last reviewed 2026-06-07 — WO-N behavioral eval harness (18.8.3): full-ci.yml updated to add eval harness unit tests step. Step runs tests/evals/behavioral/test_eval_harness.py excluding TestLiveJudge (skipped in CI — requires functional claude -p subprocess). No change to publication boundary, release gate policy, Docker profiles, or privacy classification. CI-only, post-merge, ubuntu-latest. -->

<!-- Last reviewed 2026-06-07 — WO-N2 (fix/wo-n2-deterministic-evals): removed eval harness step from full-ci.yml. No change to publication boundary, release gate policy, Docker profiles, or privacy classification. CI eval step removal is internal-only. -->
<!-- Last reviewed 2026-06-09 — WO-F2 dead-code cleanup: removed 18 stale entries from flake8-baseline.txt for check_old_dbs.py and shared/mcp-integrations/ (already deleted in prior waves). Removed broken agent-browser.md link from verify/SKILL.md. No change to publication boundary, release gate policy, Docker profiles, or privacy classification. Release gate baseline pruned — only removing entries for files that no longer exist. -->

<!-- Last reviewed 2026-06-10 — WO-DEBT-H (chore/wo-debt-h-hygiene): regenerated flake8-baseline.txt from 707 (stale, 126+ entries for deleted files) down to 509 clean entries. No change to baseline policy, publication boundary, privacy classification, Docker profiles, or release gate enforcement logic. Baseline content change only — dead-file violations removed. -->

<!-- Last reviewed 2026-06-11 — WO-FULLCI-RED ci_gate.py truncation fix: ci_gate.py updated to emit failures to stderr before JSON. Docker module profiles and Docker-optional core semantics are unchanged. -->

<!-- Last reviewed 2026-06-12 — WO f0e8f2c0 ci_gate.py failing_tests field: ci_gate JSON verdict adds failing_tests list. Docker module profiles and Docker-optional core semantics are unchanged. -->

<!-- Last reviewed 2026-06-13 — fix/full-ci-duplicate-test-run: removed duplicate pytest+coverage step from full-ci.yml; ci_gate.py already runs the full test suite internally. Bumped timeout-minutes from 45 to 60 as headroom. No change to publication boundary, privacy classification, or gate enforcement policy. -->

<!-- Last reviewed 2026-06-15 — WO-BLAST-RADIUS-GATE: new pr-smoke blast-radius gate. Docker module profiles and Docker-optional core semantics are unchanged. -->


<!-- Last reviewed 2026-06-19 — WO-LIVE-DATA-GATE: .github/workflows/ci.yml pr-smoke gains a "Dashboard truth gate" step (`ds doctor dashboard-truth`) — a read-only live-authority invariant check that vacuously passes on the fresh CI DB, so unrelated PRs are unaffected. No release/publication boundary, packaging, or module-profile change. -->
