# Security-By-Default Development Lifecycle Gate

Dream Studio treats security as a lifecycle control, not a standalone tab. Every
goal, milestone, Work Order, and code change receives a lightweight security
impact classification. Targeted controls run when the change signal is narrow;
full applicable review is required for high-risk lifecycle events.

## Canonical Framework

The canonical framework is the 47 enterprise security controls in
`docs/contracts/security-review-source-47-enterprise-scans.md`. The structured
scan catalog and crosswalk map those controls into Dream Studio's security
skill and review surfaces:

- `docs/contracts/security-review-47-scan-crosswalk.md`
- `docs/contracts/security-review-scan-catalog.yaml`
- `skills/security/SKILL.md`

The security skill may satisfy or orchestrate controls, but the 47-control
framework remains the policy authority.

## Lifecycle Policy

Full applicable 47-control review is required at:

- project intake
- release or merge readiness
- publication
- deployment or live cutover
- dependency, runtime, security, database, or Docker changes
- major architecture changes
- external project onboarding
- scheduled dogfood gates

Lightweight classification remains required for ordinary changes. Controls that
do not apply must record a reason. Unknown or deferred controls route to manual
review or dashboard attention; they do not silently pass.

## Finding Contract

Normalized findings must include:

- project
- file
- line
- severity
- control id
- status
- evidence
- remediation path

Live operator views must not include synthetic or demo findings. Derived
dashboard/API views may summarize findings, but the finding authority remains
SQLite evidence or file-backed review artifacts.

## Readiness Effect

Security status affects project health and release readiness:

- `ready`: security lifecycle clear
- `needs_manual_review`: release held for manual control review
- `unknown_requires_review`: release held for unknown control handling
- `blocked_by_open_findings`: release blocked by current findings

The lifecycle gate is non-executing. It classifies, routes, and records the
required control posture; it does not run scans, inspect secrets, mutate repos,
or write SQLite.

The secure production readiness gate consumes this lifecycle gate rather than
forking the 47-control model. Production readiness can add API, database,
caching, accessibility, observability, performance, dependency, code-quality,
privacy, rollback, and release controls, but enterprise security control
authority remains here.

Module boundary contracts provide the dependency context for lightweight
security classification. A change to `security_only`, `analytics_only`,
`adapter_router`, `external_project`, or `docker_optional` can alter which
controls are applicable, but the module contract route remains read-only and
does not execute scans, mutate repositories, run Docker, or write SQLite.

Contract Atlas lifecycle freshness is a release-gate signal, not a security
scan. The `/api/shared-intelligence/contract-atlas/freshness` route may appear
beside the security lifecycle route in the shared-intelligence router; it does
not inspect secrets, create findings, mutate SQLite, or change 47-control
applicability. Security docs still drift with router changes to confirm the
non-execution boundary.

The expert workflow route is also non-executing. Security reviewers may use
`/api/shared-intelligence/expert-workflows` to see whether implementation,
debugging, design, documentation, API, or data modeling
workflows require security/readiness evidence, but the route does not run
scans, inspect secrets, mutate
SQLite, or change 47-control applicability.

Capability Center, scoped-agent, and GitHub repo intake routes are
also non-executing security-relevant surfaces. Scoped agents add
context-minimization and permission-boundary checks, including treating career
data as a deny-by-default private data class. GitHub repo intake adds license,
security, supply-chain, dependency, attribution, and overlap review before
third-party adoption. These routes do not inspect secrets, execute agents,
mutate external projects, copy code, or add dependencies.

## Project Portfolio Hydration

All Projects and Project Details consume normalized security findings as a
derived view over current security authority. Findings must remain traceable to
their source rows or evidence refs and include project, file, line, severity,
status, control or rule where available, and remediation path where available.

Project Details now exposes the 47-control applicability list, summary counts,
manual-review count, unknown count, and source framework refs alongside project
health, readiness, stack evidence, validation state, and attention items. This
dashboard route is still non-executing: it does not run scans, inspect secrets,
mutate external projects, draw inferred dependency edges as confirmed, or write
SQLite.

Migrated findings may be assigned to current projects only through
high-confidence mapping, such as an exact project id or the legacy
`project_<project_id_with_underscores>` alias. Findings that cannot be assigned
without ambiguity must be classified as `manual_review_required`,
`unassigned_legacy_finding`, `retention_only`, or `not_applicable` and kept out
of normal operator project cards until reviewed.

The 47 enterprise controls must be visible or honestly unavailable at the
project level. Not-applicable controls require reasons, unknown controls route
to manual review or dashboard attention, and synthetic/demo/test findings must
not appear in live operator views.

Analytics-only ingestion may import normalized security findings from approved
external producers into `security_findings`. This is an authority ingestion
path, not a scanner. It must preserve source/evidence refs, project mapping,
severity, status, rule/control where available, and remediation path where
available. Hooks, agents, workflows, Claude, Codex, and Docker are optional
producers, not required security dependencies.

## AI Usage Accounting Impact

Changes to adapter billing mode, token visibility, cost visibility, provider
usage source handling, telemetry collectors, or dashboard cost display receive
lightweight security impact classification. They normally target privacy,
secrets, logging, telemetry integrity, and release-readiness controls rather
than running the full 47-control review on every edit.

Full applicable review is still required if the accounting change affects
provider credentials, billing APIs, deployment, live cutover, external project
onboarding, database schema, or release/merge readiness. Findings must avoid
printing secrets or provider billing credentials.

## Task Attribution Impact

Task attribution changes receive lightweight security classification because
they link AI/adapter work to files, commands, validation, outcomes, and
security/readiness impact. Applicable checks include telemetry integrity,
evidence refs, logging redaction, source classification, and prevention of fake
model/provider, token, cost, file, command, or outcome precision.

The task attribution routes are non-executing derived views. They do not run
security scans, inspect secrets, mutate SQLite, authorize adapter execution, or
change 47-control applicability by themselves.

## PRD Lifecycle Impact

Project intake, in-flight PRD formalization, Project Change Orders, and route
reconciliation all receive lightweight security/readiness impact
classification. Material changes to security, privacy, data model,
integrations, release targets, or public/private boundaries require targeted or
full applicable review according to the lifecycle policy before authority is
marked current.
## Platform Hardening Refresh

The policy/permission engine is a supporting control-plane surface for the security-by-default lifecycle gate. High-risk actions such as secret access, destructive cleanup, external mutation, push/deploy, Docker execution, and package changes are denied or deferred by default and must record evidence, approval, rollback, and dashboard attention requirements.

<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->

<!-- reviewed: 2026-05-30, brownfield vertical slice migration 085. Stack profile + security_scan_runs. No semantic changes required to this document. -->

<!-- 2026-05-31: reg_projects deleted (migration 084); business_projects is canonical. pi_* tables dropped; project_intelligence and prd_authority updated to read detected_stack/stack_json from business_projects. -->

<!-- 2026-06-01: security_scan_runs → scan_runs, security_findings → findings, security_scan_deltas → scan_deltas (migration 089); brownfield intake prompt added; proving-index.md added. -->

<!-- 2026-06-03: Phase 19.2 adds findings.dismissed_at + dismissed_reason (migration 096 ALTER TABLE); dismiss endpoint POST /findings/{id}/dismiss; no lifecycle gate bypass — dismissed findings are tracked, not suppressed -->
<!-- 2026-06-05: phase-18-2 gap closure + popup refactor — no schema change, no migration; _repo_stack_evidence() removed from /details critical path; session_collector NULL project_id fix -->

<!-- 2026-06-05: Wave 2 career annihilation — career_ops module, 15 career_* tables (migration 100), ds-career skill pack, /career-ops route, career_ops contract+profile, and career expert workflow removed. capability_center/scoped_agents/github_repo_intake unchanged. Dropped "career/application" + application-form/submission clauses from the expert-workflow paragraph, removed "Career Ops" from the non-executing-surfaces list and its dedicated sentence (folding career-data-deny-by-default into the scoped-agent description), and removed "career submission" from the policy/permission-engine high-risk action list (the action existed only via the removed career module). -->
<!-- 2026-06-06: Wave 4+5 ghost-surface removal reviewed — realtime websocket layer (stream/metrics, connection_manager, broadcast feeder, 2 project_intelligence ghost websockets), export/report/schedule routes + projections/exporters + scheduler/reports backends, and deprecated production_dashboard.py removed (-18,865 lines, no schema change). This doc did not describe the removed surfaces; no semantic change required. -->

<!-- 2026-06-06: Wave 6 — 13 verified-dead tables dropped (migration 101). dropped sec_hook_checks was 0-row and had no live writer; security lifecycle gate unchanged. No semantic change required. -->

<!-- reviewed: 2026-06-06, WO-B broken surfaces. projections/api/routes/security.py: wired parse_sarif_file() into POST /security/sarif/import. No security lifecycle gate policy change; parser was already a classified in-repo implementation (projections/parsers/sarif_parser.py). No new security controls added or removed. Activation satisfies the T007 stub note and removes a live endpoint returning false "not yet implemented" errors. -->

<!-- Last reviewed 2026-06-07 — WO-F prd_* cluster drop (migration 103): migration 103 drops the entire prd_* cluster (prd_documents, prd_plans, prd_tasks, prd_sessions, prd_handoffs, session_tasks, prd_version_records, prd_amendment_records, prd_route_reconciliation_records) and the views vw_prd_progress and vw_task_details. AD-10 decision: business_projects IS what PRD was. All prd_* callers removed from studio_db.py, prd_authority.py (deleted), routes/prd.py (deleted), analytics_ingestion.py, module_contracts.py, dashboard_freshness.py, contract_atlas.py, contract_registry.py, project_intelligence.py, shared_intelligence.py, resume_from_handoff.py, and migrate_prd_schema.py (deleted). -->

<!-- Last reviewed 2026-06-08 — WO-Y findings event-spine (AD-10): security findings now land on security_events append-only spine via record_finding() in core/findings/mutations.py. set_finding_status() appends finding.status_changed events. Status is NOT a column — it is an event. Current status is projected by FindingsProjection into findings_current_status. sarif_parser.py now calls record_finding() instead of INSERT INTO sec_sarif_findings directly (AD-6 emit-only pattern). Governance test updated: SCANNER_EVIDENCE_TABLES now includes security_events and findings_current_status. Security lifecycle gate contract unchanged: the scanner→evidence-surface boundary remains enforced; the target tables are now the spine tables. -->

<!-- Last reviewed 2026-06-09 — WO-TS3 DuckDB-first read path: project_intelligence.py and discovery_internal.py route changes add a DuckDB analytics read layer before SQLite authority lookups. No security boundary changes: DuckDB is NEVER-AUTHORITY; SQLite business_projects/business_canonical_events remain the canonical source. The fail-open pattern means DuckDB unavailability cannot block or bypass authority checks. Security lifecycle gate contract unchanged: the same gate rules, classification triggers, and evidence requirements apply. -->

<!-- Last reviewed 2026-06-09 — WO-TS4 correction: reverting wrong-scope DuckDB-first paths in project_intelligence.py and discovery_internal.py. No security boundary changes: business entity reads now go directly to SQLite business_projects (authority). Security lifecycle gate contract unchanged. -->

<!-- Last reviewed 2026-06-14 — WO-DASH-VALIDATION-GAPS (T3): project_intelligence.py _classify_project_authority() softened — projects with no path recorded now classified as registered_no_path (kept in default operator view); projects with a path recorded but not found locally now classified as path_unverified (kept in default operator view). Previously both cases were classified as manual_review_required and excluded from the default view. Reviewed for security implications: no security boundary changed, no gate bypassed. The classifier controls dashboard visibility only; it does not affect any control applicability decision, scan trigger, or finding record. Security lifecycle gate policy unchanged. -->

<!-- Last reviewed 2026-06-20 — WO-SPLIT-PROJECT-INTEL (feat/split-project-intel-routes): project_intelligence.py (2480 lines) split into projections/api/lib/ (security_helpers, stack_helpers, project_helpers) and four route files (project_list, project_detail, project_artifacts, project_security). Pure module reorganization — no SQL queries, schema, migration, business logic, or API contract changed. -->
