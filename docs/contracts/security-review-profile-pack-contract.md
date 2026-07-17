# Security Review Profile Pack Contract

## Purpose

The Security Review Profile Pack is a documentation and profile-data contract for planning security review work. It defines taxonomy, scan-definition shape, evidence requirements, severity, finding records, remediation handoff placement, report shape, and release-gate decisions.

The pack is not generic Work Order core. It is not a scan runner, profile registry, dashboard, database integration, event ledger, cloud service, enterprise system, or plugin ecosystem.

## Authority Boundary

Security Review Profile Pack data is advisory planning and evidence structure. It does not execute scans, inspect target repositories, mutate target repositories, install dependencies, update lockfiles, write generated target artifacts, push, stage, commit, open the native runtime database, or bypass Work Order approval.

All security review execution must remain inside the existing Work Order authority model:

- `observe_only` phases may inspect only file-backed evidence and approved artifacts.
- `approval_required` phases require file-backed approval before mutation or scan execution.
- target repo access requires explicit Work Order scope.
- findings and scan outputs are evidence, not workflow authority.
- accepted risk requires a file-backed operator decision with a reason.

## Relationship To Existing Contracts

The pack binds to existing Dream Studio primitives:

- Work Orders define scope, approval mode, risk, validation posture, expected outputs, and stop conditions.
- Handoff Packets carry fresh-session-safe continuation prompts.
- Approval artifacts gate mutation.
- Operator decision artifacts gate risk acceptance and execution choices.
- Eval artifacts provide deterministic evidence quality checks.
- Result and report artifacts record evidence and next recommendations.

The pack may provide security-specific data and templates, but it must not replace these primitives.

## Lifecycle Gate Integration

The Security Review Profile Pack is consumed by
`core/security/lifecycle.py` as Dream Studio's security-by-default development
lifecycle gate. The gate uses the 47 enterprise security controls as the
canonical framework, maps applicable controls to this pack and the security
skill, and reports whether each control is applicable, not applicable with a
reason, deferred to manual review, or unknown.

The lifecycle gate applies to every goal, milestone, Work Order, and code
change. Full applicable 47-control review is required for project intake,
release or merge, publication, deployment, live cutover, dependency/runtime/
security/database/Docker changes, major architecture changes, external project
onboarding, and scheduled dogfood gates.

The secure production readiness gate consumes this lifecycle gate and maps
security review evidence into broader deployment readiness. It must not fork the
47-control framework or create duplicate security skills when an existing
security skill mode already covers the control well.

Project portfolio hydration consumes the same normalized finding contract for
All Projects and Project Details. Live operator views must summarize only
current legitimate project findings by default. Legacy findings that lack a
high-confidence current project mapping stay retention-only or manual-review
records; they are not copied into project cards and are not recreated as a
parallel finding system.

Analytics-only ingestion can import already-normalized finding records into the
same finding contract. It does not authorize scans, target repo inspection,
dependency installation, Docker, or remediation. Imported findings still need
source refs, evidence refs, severity, status, project id, file/line when
available, and remediation path when available.

Module contracts may declare that a module affects security/readiness posture,
but they do not replace this profile pack or the 47-control framework. Security
reviewers can use `/api/shared-intelligence/module-contracts` to understand
module ownership and optional dependencies before selecting controls.

Security reviewers may also use
`/api/shared-intelligence/contract-atlas/freshness` to confirm that atlas,
maturity, docs, PRD/README, and sanitized export freshness gates are current.
That route is a derived release-readiness signal only. It must not create
findings, run scans, inspect secrets, or replace profile-pack evidence.

Security reviewers may use `/api/shared-intelligence/expert-workflows` to map
implementation, debugging, design, documentation, API, data modeling, and SEO
workflow outputs to existing skill owners and evidence
requirements. The route is a catalog, not a scanner. It must not inspect
secrets or create findings.

Project Details can display normalized security findings, 47-control
applicability, and module/profile fit together with stack evidence. That view is
for operator orientation only. It must not create findings, run scans, inspect
target repo secrets, or treat inferred dependency evidence as a confirmed
security control result.

Companion artifact-shape contracts:

- Report, finding, evidence, accepted-risk, release-gate, and next Work Order shapes: `docs/contracts/security-review-report-artifact-contract.md`
- Sample non-executing report artifact: `docs/contracts/security-review-report.sample.yaml`

## Security Taxonomy

Security taxonomy categories group scans and findings. A category does not authorize execution.

Required initial categories:

| Category ID | Name | Purpose |
| --- | --- | --- |
| `dependency_supply_chain` | Dependency and Supply Chain | Package vulnerabilities, lockfile risk, provenance, dependency policy. |
| `secrets_exposure` | Secrets Exposure | Hardcoded secrets, committed credentials, token patterns, secret-scanning evidence. |
| `static_code_security` | Static Code Security | Source analysis, injection patterns, unsafe APIs, auth bypass patterns. |
| `configuration_posture` | Configuration Posture | Security headers, environment settings, debug flags, unsafe defaults. |
| `auth_session_access` | Auth, Session, and Access Control | Authentication, authorization, session lifetime, token handling, permission boundaries. |
| `api_surface` | API and Integration Surface | Route exposure, input validation, rate limits, CORS, webhook validation. |
| `data_handling_privacy` | Data Handling and Privacy | PII handling, retention, encryption expectations, export classification. |
| `build_release_integrity` | Build and Release Integrity | CI gates, artifact provenance, release branch state, build inputs. |
| `infrastructure_runtime` | Infrastructure and Runtime | Hosting config, container/runtime posture, cloud settings when explicitly in scope. |
| `observability_incident` | Observability and Incident Readiness | Logging safety, auditability, alert evidence, incident handoff readiness. |

## ScanDefinition

A scan definition describes a possible review check. It is data, not an execution command.

The companion catalog draft lives at `docs/contracts/security-review-scan-catalog.md` and must remain documentation/data until a later approved Work Order authorizes implementation.

Required fields:

| Field | Required | Purpose |
| --- | --- | --- |
| `scan_id` | yes | Stable local identifier. |
| `title` | yes | Human-readable scan name. |
| `category_id` | yes | Primary security taxonomy category. |
| `intent` | yes | Risk the scan is meant to reveal. |
| `scan_kind` | yes | `manual_review`, `static_command`, `external_report_review`, `artifact_review`, `config_review`, or `deferred`. |
| `phase_allowed` | yes | Phase types where the scan may be planned or run. |
| `approval_mode_required` | yes | Required Work Order approval mode before execution. |
| `target_profile_inputs` | yes | Target profile fields needed to scope the scan. |
| `validation_profile_inputs` | yes | Command and mutation-risk fields needed for command-based scans. |
| `evidence_profile_inputs` | yes | Evidence fields the scan must produce or cite. |
| `command_template` | optional | Non-executed command template for a command-based scan. |
| `mutation_risk` | yes | `none`, `writes_cache`, `writes_artifacts`, `updates_snapshots`, `formatting`, `network`, or `unknown`. |
| `network_risk` | yes | `none`, `local_only`, `external_metadata`, `external_service`, or `unknown`. |
| `artifact_write_risk` | yes | Whether reports, caches, generated files, or other artifacts may be written. |
| `prerequisites` | yes | Required repo state, installed tools, auth, or evidence before execution planning. |
| `expected_outputs` | yes | Expected file-backed artifacts or report sections. |
| `timeout_policy` | yes | Expected timeout class and stop behavior. |
| `safe_failure_mode` | yes | HOLD behavior when the scan cannot run safely. |
| `false_positive_notes` | optional | Known review caveats. |
| `remediation_handoff_hint` | yes | Handoff family for failures or findings. |

The future 47-scan catalog must be reviewed as data before any scan command is implemented or executed.

## Evidence Model

Security evidence must be explicit, file-backed, and separated from execution.

Required evidence fields:

| Field | Purpose |
| --- | --- |
| `evidence_id` | Stable local evidence identifier. |
| `source_work_order_id` | Work Order that produced or collected the evidence. |
| `scan_id` | Scan definition that requested the evidence. |
| `target_id` | Target profile identifier when a target is in scope. |
| `before_status` | Pre-action repository state when target access is approved. |
| `after_status` | Post-action repository state. |
| `branch_head` | Branch and HEAD proof. |
| `index_state` | Empty or expected index proof. |
| `diff_name_only` | Working tree file list proof. |
| `cached_diff_name_only` | Staged file list proof. |
| `command_result` | Exit code, output summary, timeout status, and artifact refs. |
| `external_report_ref` | Existing external report path or citation. |
| `finding_refs` | Finding IDs supported by the evidence. |
| `no_forbidden_action_proof` | Proof no forbidden action occurred. |
| `no_target_mutation_proof` | Proof target repos were not touched or mutated when observe-only. |
| `no_generated_artifact_proof` | Proof generated files stayed out of target repos. |
| `approval_artifact` | Approval path and summary for mutation-gated work. |
| `operator_decision_artifact` | Decision request and decision paths for accepted risk or gated choices. |
| `evidence_limitations` | Gaps, assumptions, inaccessible sources, and false-positive caveats. |

Missing evidence must produce HOLD or PASS WITH RISKS, not silent PASS.

## Severity Model

Security severity must distinguish impact, confidence, exploitability, scope, release impact, privacy impact, and remediation urgency.

Required fields:

| Field | Values |
| --- | --- |
| `severity` | `info`, `low`, `medium`, `high`, `critical`, `blocker` |
| `confidence` | `low`, `medium`, `high`, `confirmed` |
| `exploitability` | `unknown`, `unlikely`, `possible`, `likely`, `active` |
| `scope` | `local`, `target`, `multi_target`, `release`, `organization` |
| `release_impact` | `none`, `warn`, `needs_approval`, `block_release` |
| `privacy_impact` | `none`, `local_only`, `sensitive`, `regulated`, `unknown` |
| `remediation_urgency` | `backlog`, `next_cycle`, `before_push`, `before_release`, `immediate_hold` |

Severity rules:

- `blocker` maps to `block_release` unless an explicit operator risk acceptance exists.
- `critical` defaults to `block_release` for release gates.
- `high` defaults to `needs_approval` or `block_release` depending on exploitability and scope.
- low-confidence findings may still require HOLD when release impact is unclear.
- accepted risk requires a file-backed operator decision with a reason.

## FindingRecord

A finding record is the unit summarized by security reports and targeted by remediation handoffs.

Required fields:

- `finding_id`
- `scan_id`
- `control_id`
- `project_id`
- `category_id`
- `title`
- `summary`
- `affected_assets`
- `file_path`
- `line`
- `severity`
- `confidence`
- `release_impact`
- `evidence_refs`
- `remediation_path`
- `recommended_action`
- `remediation_scope_hint`
- `status`

Allowed finding statuses:

- `open`
- `accepted_risk`
- `remediated`
- `false_positive`
- `deferred`
- `unknown`

## Remediation Handoff Placement

Security remediation must use existing Handoff Packet mechanics. The pack must not create a new mutation channel.

| Situation | Handoff Type | Phase Type | Requirement |
| --- | --- | --- | --- |
| Finding needs triage | `hold_review` | `normal_next_work_order` or future `security_review` | Review-only, no mutation. |
| Operator must choose risk acceptance or remediation | `recovery_decision` or decision-gated planning handoff | future `security_review` | Requires file-backed operator decision. |
| Remediation is approved | `approved_mutation_execution` | `approved_mutation` | Requires approved files, forbidden files, before/after evidence, validation, and evals. |
| Remediation fails validation | `recovery_decision` | `recovery_decision` | Current recovery model applies. |
| Finding is accepted risk | `normal_next_work_order` or `hold_review` | future `security_review` | Requires operator decision artifact and review constraint. |
| Post-remediation verification | `normal_next_work_order` or approval-gated validation handoff | future `security_review` | Must not rerun broad scans without approval. |

## Security Review Report Contract

A Security Review report must be fresh-session safe and file-backed.

Required sections:

1. Verdict: `PASS`, `PASS WITH RISKS`, `HOLD`, or `FAIL`.
2. Scope and authority: target/profile IDs, approval mode, forbidden actions, validation posture.
3. Security taxonomy coverage: categories reviewed, categories not reviewed, and gap reasons.
4. Scan summary: scan IDs, scan kinds, status, evidence refs, and limitations.
5. Findings summary: counts by severity, confidence, release impact, and status.
6. Critical or blocking findings: finding IDs, evidence, and recommended action.
7. Accepted risks: operator decision paths, reasons, constraints, and review notes.
8. Evidence inventory: file-backed refs for reports, status, command output, approvals, decisions, and evals.
9. No-forbidden-action proof: no target mutation, no generated target artifacts, no push/stage/commit when forbidden.
10. Release-gate decision: exactly one allowed value from the release-gate taxonomy.
11. Next Work Order recommendation: bounded handoff for remediation, acceptance, verification, or release planning.
12. Ready-to-copy Handoff Packet only if it passes the Handoff Packet contract.

## Release-Gate Decision Taxonomy

Allowed release-gate decisions:

| Decision | Meaning | Allowed next prompt |
| --- | --- | --- |
| `SECURITY_CLEAR` | No blocking findings and evidence is complete. | Release planning or product closeout. |
| `SECURITY_CLEAR_WITH_RISKS` | No blockers, but bounded residual risks remain. | Release planning with risks or operator risk review. |
| `ACCEPT_RISK_WITH_APPROVAL` | Findings remain, but operator may accept risk. | Operator decision request or risk-acceptance handoff. |
| `REMEDIATE_BEFORE_RELEASE` | Findings require remediation before release. | Remediation planning handoff. |
| `RUN_ADDITIONAL_SECURITY_REVIEW` | Evidence is incomplete or targeted scans are needed. | Security validation planning handoff. |
| `HOLD` | State is unclear, unsafe, or decision is missing. | Hold/review handoff. |
| `FAIL` | Forbidden action occurred, authority drift happened, or release must be blocked. | Failure/remediation handoff. |

The release-gate decision must be exactly one allowed value. A future implementation may add `phase_type: security_review`, but this contract does not modify core decision taxonomies.

## Profile Pack Attachment

The Security Review Profile Pack binds to the minimal draft shapes from Phase 18C:

- TargetProfileDraft supplies target id, display name, repo path when authorized, branch policy, dependency/schema/generated-artifact policies, and output restrictions.
- ValidationProfileDraft supplies command sets, mutation risk, write risk, timeout policy, no-validation phases, and post-validation evidence.
- EvidenceProfileDraft supplies reusable proof requirements.
- HandoffTemplateBindingDraft supplies handoff family, required sections, evals, readiness rules, and expected verdict templates.

The pack is an input to Work Order generation, reporting, and handoff planning. It is not a replacement for Work Orders.

## Non-Goals

This contract does not authorize:

- implementation of the 47 scans;
- scan command execution;
- target repo inspection or mutation;
- runtime execution code;
- profile registry implementation;
- plugin ecosystem creation;
- database storage or event ledger writes;
- schema migrations;
- Docker expansion;
- dashboard projection integration;
- TORII, cloud, org, global, or enterprise integration;
- dependency changes;
- security remediation.

## Safety Rules

- Security scans are profile-pack data/templates until a later approved Work Order implements execution.
- Command templates must not be executed from the contract.
- Networked or mutating scans require explicit Work Order approval before execution.
- Findings are evidence, not automatic authority.
- Accepted risk requires a file-backed operator decision.
- Security reports must not claim release readiness when required scan, evidence, severity, approval, or decision context is missing.

## Usage Accounting Review Profile

AI usage accounting changes should use the existing security review profile
pack instead of creating a separate security skill. Applicable checks include
secret exposure, logging redaction, telemetry integrity, database schema safety,
provider credential handling, and release-readiness evidence. Cost unknowns are
not security findings by themselves; fake cost precision or credential
inspection would be review findings.

## Task Attribution Review Profile

Task attribution changes use the same profile pack. Applicable checks include
evidence integrity, source classification, logging redaction, security/readiness
impact linkage, and no fake model/provider, file, command, validation, outcome,
token, or cost precision. Imported or untracked adapter work must remain
classified as such until high-confidence Dream Studio authority exists.

## Capability, Agent, And GitHub Intake Review Profile

Scoped-agent changes must include context-minimization checks: no full
conversation history, secrets, all Work Orders, all memories, unrelated
projects, raw local evidence, or private career data by default.

GitHub repo intake changes must include license, attribution, security,
supply-chain, dependency health, maintenance, overlap, and legal/security
review routing checks before any adoption path is considered.
## Platform Hardening Refresh

Security review profile packs can consume platform-hardening policy decisions, connector-ingested SARIF or dependency evidence, and privacy/export checks as inputs. The pack remains responsible for evidence-backed findings and must not treat connector data, demo packets, or sanitized exports as live security authority without source refs.

## PRD Lifecycle Review Profile

PRD intake, formalization, change orders, and route reconciliation should use
the same security review profile pack when they touch security, privacy,
database/schema, integrations, release targets, public/private boundaries, or
legal/compliance assumptions. The profile maps those impacts to existing
controls instead of creating a competing PRD-specific security system.

<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->

<!-- reviewed: 2026-05-30, brownfield vertical slice migration 085. Stack profile + security_scan_runs. No semantic changes required to this document. -->

<!-- 2026-05-31: reg_projects deleted (migration 084); business_projects is canonical. pi_* tables dropped; project_intelligence and prd_authority updated to read detected_stack/stack_json from business_projects. -->

<!-- 2026-06-01: security_scan_runs → scan_runs, security_findings → findings, security_scan_deltas → scan_deltas (migration 089); brownfield intake prompt added; proving-index.md added. -->

<!-- 2026-06-03: Phase 19.2 dismiss endpoint (POST /api/v1/findings/{id}/dismiss) feeds dismissed_finding friction signals; security-review-profile pack contract unchanged — no new scan rules, only operator dismissal tracking -->
<!-- 2026-06-05: phase-18-2 gap closure + popup refactor — no schema change, no migration; _repo_stack_evidence() removed from /details critical path; session_collector NULL project_id fix -->

<!-- 2026-06-05: Wave 2 career annihilation — career_ops module, 15 career_* tables (migration 100), ds-career skill pack, /career-ops route, career_ops contract+profile, and career expert workflow removed. capability_center/scoped_agents/github_repo_intake unchanged. Dropped "career/application" + application-submission/browser-automation clauses from the expert-workflow mapping paragraph; renamed "## Career, Capability, Agent, And GitHub Intake Review Profile" to "## Capability, Agent, And GitHub Intake Review Profile" and removed the Career Ops review-profile paragraph; the scoped-agent "private career data by default" exclusion stays as a privacy class. -->
<!-- 2026-06-06: Wave 4+5 ghost-surface removal reviewed — realtime websocket layer (stream/metrics, connection_manager, broadcast feeder, 2 project_intelligence ghost websockets), export/report/schedule routes + projections/exporters + scheduler/reports backends, and deprecated production_dashboard.py removed (-18,865 lines, no schema change). This doc did not describe the removed surfaces; no semantic change required. -->

<!-- 2026-06-06: Wave 6 — 13 verified-dead tables dropped (migration 101). no semantic change required. -->

<!-- reviewed: 2026-06-06, WO-B broken surfaces. projections/api/routes/security.py change (SARIF parser activation) does not modify any review profile pack, scan catalog, or profile-pack contract shape. No semantic change required. -->

<!-- Last reviewed 2026-06-07 — WO-F prd_* cluster drop (migration 103): migration 103 drops the entire prd_* cluster (prd_documents, prd_plans, prd_tasks, prd_sessions, prd_handoffs, session_tasks, prd_version_records, prd_amendment_records, prd_route_reconciliation_records) and the views vw_prd_progress and vw_task_details. AD-10 decision: business_projects IS what PRD was. All prd_* callers removed from studio_db.py, prd_authority.py (deleted), routes/prd.py (deleted), analytics_ingestion.py, module_contracts.py, dashboard_freshness.py, contract_atlas.py, contract_registry.py, project_intelligence.py, shared_intelligence.py, resume_from_handoff.py, and migrate_prd_schema.py (deleted). -->

<!-- Last reviewed 2026-06-08 — WO-Y findings event-spine: security.py route endpoints (/security/dismiss, /security/sarif-findings, /security/cve-matches, /security/manual-reviews, /security/stats) updated to read from security_events + findings_current_status instead of retired sec_sarif_findings/sec_cve_matches/sec_manual_reviews. dismiss_finding() now calls set_finding_status('false_positive'). sec_cve_matches and sec_manual_reviews endpoints return empty with retirement notes. No review profile pack schema changes; scan catalog shape preserved. -->

<!-- Last reviewed 2026-06-09 — WO-TS3 DuckDB-first read path: project_intelligence.py route changes reviewed. No security review profile pack schema changes. DuckDB analytics store is a derived read model; all security scan, finding, and review evidence still written to SQLite authority (security_events, findings_current_status). The scanner→evidence-surface boundary enforced by this contract is unchanged. -->

<!-- Last reviewed 2026-06-09 — WO-TS4 correction: reverting wrong-scope DuckDB-first paths. No security review profile pack schema changes. Security evidence remains in SQLite authority. Contract unchanged. -->

<!-- Last reviewed 2026-06-14 — WO-DASH-VALIDATION-GAPS (T3): project_intelligence.py classifier change reviewed. No review profile pack schema changes. No security control, scan definition, finding contract, or evidence model changed. Contract unchanged. -->

<!-- Last reviewed 2026-06-20 — WO-SPLIT-PROJECT-INTEL (feat/split-project-intel-routes): project_intelligence.py (2480 lines) split into projections/api/lib/ (security_helpers, stack_helpers, project_helpers) and four route files (project_list, project_detail, project_artifacts, project_security). Pure module reorganization — no SQL queries, schema, migration, business logic, or API contract changed. -->

<!-- reviewed 2026-06-26: migration 128 dead-tables removal — no content changes required -->

<!-- Last reviewed 2026-06-27 — Wave 2 substrate realignment (migration 131, worktree-agent-a910d590fedb5c672): no security-review-profile-pack change. migration 131 retires dormant shared-intelligence tables only; the contract-atlas security/production-readiness sections that the pack feeds drop their retired-table references but the review-profile catalog, scan surfaces, and compliance_review_flags/release_readiness_records authority are unchanged. -->

<!-- Last reviewed 2026-06-28 — Batch 1 canonical-first migration (migration 133): compliance_review_flags and release_readiness_records dropped. These tables were never written to in production (persist=False early-return). Security review profile pack feeds security_events, scan_runs, findings_current_status — all retained. No pack contract change. -->

<!-- Last reviewed 2026-07-04 — migration 140 (WO dff23cb0-950f-4607-bb30-e1a353a6f8ba): findings_current_status dropped (pure derived state — FindingsProjection.fold_spine() upsert over security_events, 15 rows). Security review profile pack now feeds security_events + scan_runs only; findings_current_status's role (current-status lookup) is served by core/findings/current_status.py::FINDINGS_CURRENT_STATUS_SQL, computed at read time from security_events instead of a stored table. security.py route endpoints (/security/dismiss, /security/findings, /security/sarif, /security/stats) preserve their existing response shapes. No review profile pack schema change; scan catalog shape preserved. -->

<!-- Reviewed 2026-07-05 — WO 6d978483 (PEP 585/604 modernization [2/2]): source files in this domain received mechanical type-annotation modernization only (PEP 585 builtin generics, PEP 604 unions, datetime.UTC) via ruff UP safe autofixes. No contract, behavior, schema, routing, API-shape, or CLI-surface change — reviewed, no doc content change needed. -->

<!-- Last reviewed 2026-07-15 — WO-SCHEMALEAN (migration 147): capability_route_records dropped. No security-review-profile-pack contract change — touched only via a shared-intelligence source file in this domain's glob. -->
