# Dream Studio Docker Module Profiles

Lifecycle status: tested_only

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
