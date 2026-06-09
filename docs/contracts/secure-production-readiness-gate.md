# Secure Production Readiness Gate

Dream Studio uses `secure_production_readiness_gate` to determine whether a
project has enough evidence to move toward real end-user deployment. It is a
workflow/control framework, not a monolithic skill.

## Authority

The gate reads repo contracts and SQLite authority, classifies applicability,
and persists assessment records only when an approved workflow calls the
SQLite-backed recorder with an injected connection. It does not run scanners,
inspect secrets, mutate external projects, deploy, run Docker, or claim legal
compliance.

SQLite authority records are additive and live in:

- `production_readiness_assessment_runs`
- `production_readiness_control_results`
- `production_readiness_findings`
- `production_readiness_remediation_work_orders`
- `production_readiness_skill_control_mappings`
- `release_readiness_records`
- `compliance_review_flags`

## Control Families

The reusable framework includes:

- 47 enterprise security controls
- API resilience
- database readiness
- migration, rollback, and destructive-change readiness
- caching correctness
- privacy/compliance applicability
- accessibility
- observability and logging
- performance and scalability
- backup, restore, and rollback
- dependency and supply-chain risk
- code quality and architecture boundaries
- release and publication readiness

Each control declares its ID, name, category, skill owner, workflow owner,
applicability rules, evidence requirements, allowed states, blocking policy,
remediation path, dashboard visibility, health/readiness/release impact,
Contract Atlas impact, and overlap mapping.

Module contracts are readiness inputs. The gate may use
`core.module_contracts` and `/api/shared-intelligence/module-contracts` to
understand module ownership, optional dependencies, disabled-module behavior,
and install profile membership before deciding which readiness controls apply.
Those contract reads are non-executing and do not write SQLite.

Project Details consumes readiness records as a derived operating view. It may
show readiness score, control coverage, findings, remediation Work Orders,
release blockers, module/runtime profile fit, validation state, stack evidence,
and dependency graph status. Missing readiness or dependency evidence must be
shown as unavailable or partial; manifest-derived dependency names do not become
confirmed graph edges or readiness evidence without source refs.

Contract Atlas lifecycle freshness contributes to release/publication
readiness. The readiness gate can treat the lifecycle manifest as evidence that
the atlas, maturity ledger, docs drift, PRD/README impact detection, dashboard
freshness, and sanitized public export checks were evaluated. The manifest is
derived evidence only; it does not run readiness controls, create findings,
write SQLite, or claim compliance.

Expert workflow catalog status contributes to readiness when process quality is
in scope. The readiness gate can treat
`/api/shared-intelligence/expert-workflows` as evidence that implementation,
quality, debugging, performance, design, SEO/content, documentation, data/API,
and case-study workflows have owners, input/output
contracts, evidence requirements, validation requirements, scoring rubrics, and
privacy boundaries. The catalog does not execute workflows, create findings, or
write SQLite.

## Skill And Control Overlap

Existing skills and gates are canonical when they already work:

- security review maps to the 47 enterprise controls.
- quality secure remains OWASP/STRIDE process guidance.
- quality harden and structure-audit map to code quality and architecture.
- `ci_gate.py`, lint baseline, docs drift, and pip-audit map to release and
  supply-chain readiness.
- lightweight GitHub PR smoke maps to remote confidence, while local
  `ci_gate.py` remains the heavy release-readiness evidence layer.
- project intelligence health stays health; production readiness is tracked
  separately.

New specialized owners are declared only where no existing skill has clear
ownership, such as database readiness, API resilience, caching correctness, and
privacy/compliance applicability.

## Run Policy

- Lightweight impact classification always runs.
- Targeted applicable checks run during normal development.
- Full applicable review runs for project intake, release/merge, publication,
  deployment, live cutover, dependency/runtime/security/database/Docker changes,
  major architecture changes, external onboarding, and scheduled dogfood gates.
- Tiny changes do not run all 47 controls unless the classifier or release gate
  requires it.

## Scores

Project health and project readiness are separate:

- health reflects current condition, blockers, stale state, validation health,
  telemetry, dependency evidence, security findings, and operational status.
- readiness reflects whether the project is ready for real users, release,
  deployment, publication, enterprise use, or broader rollout.

Scores must be evidence-backed and include confidence, missing evidence, blocking
factors, and linked controls. If evidence is insufficient, the score is
`partial` or `unavailable` with a reason. Missing evidence is not silently scored
as zero.

## Findings And Remediation

Findings must include project, assessment, control, family, skill owner,
workflow owner, applicability, status, severity, blocking flag, score impact,
evidence refs, source refs, file/line when applicable, remediation Work Order,
and not-applicable reason where applicable.

Remediation Work Orders generated by the gate are proposed records until a
separate Work Order authority approves execution.

## Project Details Integration

Project Details consumes production readiness as a derived read model over the
SQLite-backed readiness authority. It must show the separate project health and
project readiness concepts, control coverage, findings, blockers, remediation
links, missing evidence, and legal/compliance review flags when present.

If no project-scoped readiness assessment exists, Project Details reports
readiness as `unavailable` with missing evidence and a next action rather than
inventing a score. Missing evidence is not zero readiness unless a specific
control declares missing evidence to be a failure.

Analytics-only ingestion may import source-backed readiness assessments,
control results, findings, and health/readiness scorecards into the existing
SQLite authority tables. This supports standalone analytics deployments where
another system produced the evidence. Imported readiness must remain
evidence-backed and partial or unavailable when evidence is insufficient; it
must not claim compliance or release readiness merely because a score field is
present.

## AI Adapter Usage Readiness

Production readiness includes honest AI adapter usage accounting. A project can
use AI outcome quality, validation results, rework, files touched, commands run,
security/readiness findings, and duration as operational value signals. It must
not use fabricated token-to-dollar conversion for health, readiness, or release
decisions.

Readiness records should show cost as `unknown` when provider metadata, usage
exports, billing API data, explicit estimate metadata, or configured
subscription allocation evidence is absent. Missing cost evidence can lower
cost-confidence, but it is not scored as zero spend.

Task attribution can strengthen readiness evidence by linking adapter work to
project, milestone, task, Work Order, process run, skills/workflows,
hooks/tools, files, commands, validation, outcome, rework, and
security/readiness impact. Unknown model/provider, unavailable file/command
data, and manual-review outcomes remain confidence or missing-evidence inputs,
not fake pass/fail or cost signals.

## Scoped Agent And Repo Intake Readiness

Public/demo outputs must exclude private career data unless redacted and
approved; career remains a deny-by-default private data class.

Scoped agents affect readiness through context minimization, permission
boundaries, output contracts, validation requirements, and result normalization.
An agent result is never source authority by itself.

GitHub repo intake affects supply-chain, license, attribution, maintainability,
and integration readiness. A dependency, fork/vendor, or copied-code path is
not ready unless license/legal/security/maintenance evidence and operator
approval exist.
## Platform Hardening Refresh

Secure production readiness can use platform-hardening records as evidence for permission controls, sanitized export gates, connector provenance, installer health, scheduled validation posture, and demo/case-study readiness. The gate still requires source-backed controls and must not overclaim production readiness from a demo or rollup packet alone.

## PRD Lifecycle Readiness

PRD authority is a readiness input. New project intake, in-flight
formalization, material change orders, and route reconciliation classify
database, API, caching, accessibility, observability, performance,
dependency/supply-chain, privacy/compliance, backup/rollback, code quality, and
release-readiness applicability. Missing evidence remains partial or
unavailable until a targeted or full applicable review supplies evidence.

<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->

<!-- reviewed: 2026-05-30, brownfield vertical slice migration 085. Stack profile + security_scan_runs. No semantic changes required to this document. -->

<!-- 2026-05-31: reg_projects deleted (migration 084); business_projects is canonical. pi_* tables dropped; project_intelligence and prd_authority updated to read detected_stack/stack_json from business_projects. -->

<!-- 2026-06-01: security_scan_runs → scan_runs, security_findings → findings, security_scan_deltas → scan_deltas (migration 089); brownfield intake prompt added; proving-index.md added. -->

<!-- 2026-06-03: Phase 19.2 adds findings.dismissed_at + dismissed_reason (migration 096 ALTER TABLE); dismiss endpoint at POST /api/v1/findings/{id}/dismiss; no production readiness gate change — dismissal tracking is additive instrumentation -->
<!-- 2026-06-05: phase-18-2 gap closure + popup refactor — no schema change, no migration; _repo_stack_evidence() removed from /details critical path; session_collector NULL project_id fix -->
<!-- 2026-06-05: Phase 18.6.2 — project_health_scorecards and project_readiness_scorecards dropped (migration 099). Both tables had 0 rows. Removed from authority table list. _record_scorecards() guarded in controls.py. -->

<!-- 2026-06-05: Wave 2 career annihilation — career_ops module, 15 career_* tables (migration 100), ds-career skill pack, /career-ops route, career_ops contract+profile, and career expert workflow removed. capability_center/scoped_agents/github_repo_intake unchanged. Dropped "career/portfolio" + "publish career artifacts, fill applications" from the expert-workflow readiness paragraph; renamed "## Career, Scoped Agent, And Repo Intake Readiness" to "## Scoped Agent And Repo Intake Readiness" and replaced the Career-Ops module readiness text with a career-as-private-data-class exclusion; scoped-agent and repo-intake readiness paragraphs unchanged. -->
<!-- 2026-06-06: Wave 4+5 ghost-surface removal reviewed — realtime websocket layer (stream/metrics, connection_manager, broadcast feeder, 2 project_intelligence ghost websockets), export/report/schedule routes + projections/exporters + scheduler/reports backends, and deprecated production_dashboard.py removed (-18,865 lines, no schema change). This doc did not describe the removed surfaces; no semantic change required. -->

<!-- 2026-06-06: Wave 6 — 13 verified-dead tables dropped (migration 101). no semantic change required. -->

<!-- reviewed: 2026-06-06, WO-B broken surfaces. docs/contracts/security-by-default-development-lifecycle-gate.md was touched with a review note (SARIF parser activation). No production readiness gate policy change; no readiness control, migration, or versioning file touched. No semantic change required. -->

<!-- Last reviewed 2026-06-07 — WO-F prd_* cluster drop (migration 103): migration 103 drops the entire prd_* cluster (prd_documents, prd_plans, prd_tasks, prd_sessions, prd_handoffs, session_tasks, prd_version_records, prd_amendment_records, prd_route_reconciliation_records) and the views vw_prd_progress and vw_task_details. AD-10 decision: business_projects IS what PRD was. All prd_* callers removed from studio_db.py, prd_authority.py (deleted), routes/prd.py (deleted), analytics_ingestion.py, module_contracts.py, dashboard_freshness.py, contract_atlas.py, contract_registry.py, project_intelligence.py, shared_intelligence.py, resume_from_handoff.py, and migrate_prd_schema.py (deleted). -->

<!-- Last reviewed 2026-06-08 — WO-Y migration 112: the production_readiness cluster (production_readiness_assessment_runs, production_readiness_control_results, production_readiness_findings, production_readiness_remediation_work_orders, production_readiness_skill_control_mappings) was dropped in migration 112 — all 5 tables had 0 rows. The readiness_events spine (migration 111) replaces this cluster for future production readiness control results. Production readiness gate policy unchanged; only the storage layer changed. -->

<!-- Last reviewed 2026-06-09 — WO-TS3 DuckDB-first read path: project_intelligence.py changes reviewed. Secure production readiness gate policy unchanged: same control framework, same evidence requirements, same authority boundaries. DuckDB analytics store is a read-only derived layer; production readiness evidence and control results remain in SQLite authority (readiness_events, findings_current_status). Gate contract is unaffected. -->
