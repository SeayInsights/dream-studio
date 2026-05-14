# Security Review Report Artifact Contract

## Purpose

This contract defines file-backed Security Review report, finding, evidence, accepted-risk, release-gate, and next Work Order recommendation artifact shapes. The shapes are intended for future Work Orders, reports, and dashboard projections without making a dashboard or scan catalog authoritative.

This contract is documentation/data only. It does not run scans, inspect target repositories, mutate target repositories, add runtime execution code, add CLI commands, create a profile registry, write database/event ledgers, add schema migrations, expand Docker, implement dashboards, add TORII/cloud/org/global/enterprise integration, modify dependencies, or change lockfiles.

Dashboard projection rules for these artifacts are documented in `docs/contracts/dashboard-projection-model-contract.md`. The projection contract may read and display Security Review artifacts, but it must not replace this contract or become authority.

## Artifact Roles

| Artifact | Role |
| --- | --- |
| `SecurityReviewReport` | Top-level file-backed result for a scoped security review. |
| `SecurityFindingRecord` | One finding tied to a scan, evidence, severity, release impact, and remediation hint. |
| `SecurityEvidenceRecord` | File-backed evidence that supports scans, findings, or no-forbidden-action proof. |
| `AcceptedRiskRecord` | File-backed risk acceptance summary that references an operator decision artifact. |
| `ReleaseGateSummary` | Release-gate decision, rationale, blockers, accepted risks, deferred scans, and required next actions. |
| `SecurityNextWorkOrderRecommendation` | Bounded next Work Order recommendation or Handoff Packet reference. |

## Storage Guidance

Security Review artifacts should be stored under Dream Studio Work Order storage or Dream Studio meta/audit paths. They must not be written inside target repositories unless a later approved Work Order explicitly authorizes target artifact writes.

Recommended Work Order storage paths:

- `<storage_root>/<work_order_id>/security/review_report.yaml`
- `<storage_root>/<work_order_id>/security/findings/*.yaml`
- `<storage_root>/<work_order_id>/security/evidence/*.yaml`
- `<storage_root>/<work_order_id>/security/accepted_risks/*.yaml`
- `<storage_root>/<work_order_id>/security/release_gate.yaml`

## SecurityReviewReport

Required fields:

| Field | Required | Purpose |
| --- | --- | --- |
| `report_id` | yes | Stable report identifier. |
| `source_work_order_id` | yes | Work Order that produced the report. |
| `target_id` | yes | Target profile identifier or `not_applicable` for planning-only reports. |
| `security_pack_id` | yes | Security Review Profile Pack identifier. |
| `catalog_ref` | yes | Path to the structured scan catalog used for the review. |
| `review_scope` | yes | File-backed scope, target access posture, scan set, and exclusions. |
| `approval_mode` | yes | Work Order approval mode for the review. |
| `verdict` | yes | `PASS`, `PASS WITH RISKS`, `HOLD`, or `FAIL`. |
| `release_gate_decision` | yes | Embedded `ReleaseGateSummary` or reference to one. |
| `taxonomy_coverage` | yes | Categories reviewed, categories skipped, and gap reasons. |
| `scan_summary` | yes | Scan IDs, scan status, scan kind, and evidence refs. |
| `findings_summary` | yes | Finding counts by severity, confidence, release impact, and status. |
| `evidence_inventory` | yes | Evidence records and external report references. |
| `accepted_risks` | yes | Accepted risk records or an empty list. |
| `no_forbidden_action_proof` | yes | Proof no forbidden actions occurred. |
| `next_work_order_recommendation` | yes | Bounded next Work Order recommendation. |
| `ready_to_copy_handoff_packet` | optional | Handoff Packet path or inline packet only if it satisfies the Handoff Packet contract. |

## SecurityFindingRecord

Required fields:

| Field | Required | Purpose |
| --- | --- | --- |
| `finding_id` | yes | Stable finding identifier. |
| `scan_id` | yes | Scan definition that produced or motivated the finding. |
| `source_item_refs` | yes | Original source items covered by the finding. |
| `category_id` | yes | Security taxonomy category. |
| `title` | yes | Human-readable finding title. |
| `summary` | yes | Short finding explanation. |
| `affected_assets` | yes | Files, services, endpoints, repos, or systems affected. |
| `severity` | yes | `info`, `low`, `medium`, `high`, `critical`, or `blocker`. |
| `confidence` | yes | `low`, `medium`, `high`, or `confirmed`. |
| `exploitability` | yes | `unknown`, `unlikely`, `possible`, `likely`, or `active`. |
| `scope` | yes | `local`, `target`, `multi_target`, `release`, or `organization`. |
| `release_impact` | yes | `none`, `warn`, `needs_approval`, or `block_release`. |
| `privacy_impact` | yes | `none`, `local_only`, `sensitive`, `regulated`, or `unknown`. |
| `remediation_urgency` | yes | `backlog`, `next_cycle`, `before_push`, `before_release`, or `immediate_hold`. |
| `evidence_refs` | yes | Evidence IDs or file-backed refs. |
| `recommended_action` | yes | Bounded recommendation. |
| `remediation_scope_hint` | yes | Suggested Work Order scope for remediation. |
| `status` | yes | Finding status. |

Allowed finding statuses:

- `open`
- `accepted_risk`
- `remediated`
- `false_positive`
- `deferred`
- `unknown`

## SecurityEvidenceRecord

Required fields:

| Field | Required | Purpose |
| --- | --- | --- |
| `evidence_id` | yes | Stable evidence identifier. |
| `source_work_order_id` | yes | Work Order that produced or collected the evidence. |
| `scan_id` | yes | Scan definition associated with the evidence. |
| `target_id` | yes | Target identifier or `not_applicable`. |
| `evidence_kind` | yes | `status_proof`, `command_result`, `external_report`, `manual_review`, `artifact_ref`, or `operator_decision`. |
| `evidence_refs` | yes | File paths, artifact IDs, report refs, or citations. |
| `before_status` | yes | Pre-action status when target access is in scope, otherwise `not_applicable`. |
| `after_status` | yes | Post-action status when target access is in scope, otherwise `not_applicable`. |
| `command_result` | yes | Exit code, output summary, timeout, and artifact refs, or `not_run`. |
| `external_report_ref` | yes | External report path/ref or `none`. |
| `no_forbidden_action_proof` | yes | Proof no forbidden action occurred. |
| `no_target_mutation_proof` | yes | Proof target repos were not mutated, or why not applicable. |
| `no_generated_artifact_proof` | yes | Proof generated artifacts stayed out of target repos. |
| `evidence_limitations` | yes | Gaps, assumptions, inaccessible sources, and false-positive caveats. |

## AcceptedRiskRecord

Required fields:

| Field | Required | Purpose |
| --- | --- | --- |
| `risk_id` | yes | Stable accepted-risk identifier. |
| `finding_id` | yes | Finding accepted by the operator. |
| `operator_decision_artifact` | yes | File-backed operator decision path. |
| `accepted_by` | yes | Operator or accountable party. |
| `reason` | yes | Human-readable risk acceptance reason. |
| `constraints` | yes | Scope, time, release, target, or mitigation constraints. |
| `expiry_or_review_date` | yes | Date or review trigger. |
| `residual_risk_summary` | yes | Risk that remains after acceptance. |

Accepted risk must reference a valid file-backed operator decision artifact. A report must not treat accepted risk as remediation or release approval by itself.

## ReleaseGateSummary

Required fields:

| Field | Required | Purpose |
| --- | --- | --- |
| `decision` | yes | Exactly one release-gate taxonomy value. |
| `rationale` | yes | Why this decision is correct from evidence. |
| `blocking_findings` | yes | Finding IDs blocking release, or empty list. |
| `accepted_risks` | yes | Accepted risk IDs, or empty list. |
| `deferred_scans` | yes | Scan IDs deferred by scope, approval, runtime, infrastructure, or evidence constraints. |
| `required_next_actions` | yes | Bounded required next actions. |

Allowed release-gate decisions:

- `SECURITY_CLEAR`
- `SECURITY_CLEAR_WITH_RISKS`
- `ACCEPT_RISK_WITH_APPROVAL`
- `REMEDIATE_BEFORE_RELEASE`
- `RUN_ADDITIONAL_SECURITY_REVIEW`
- `HOLD`
- `FAIL`

## SecurityNextWorkOrderRecommendation

Required fields:

| Field | Required | Purpose |
| --- | --- | --- |
| `recommended_work_order_id` | yes | Proposed next Work Order ID. |
| `recommended_phase_name` | yes | Proposed phase name. |
| `recommended_handoff_type` | yes | Handoff type from the Handoff Packet contract. |
| `recommended_phase_type` | yes | Phase type from the Handoff Packet contract. |
| `decision_taxonomy` | yes | Allowed decisions for the next phase. |
| `recommended_decision` | yes | Starting or expected decision. |
| `scope_summary` | yes | Bounded scope. |
| `forbidden_actions` | yes | Actions still forbidden. |
| `requires_operator_decision` | yes | Boolean. |
| `handoff_packet_ref` | optional | Ready-to-copy Handoff Packet path only if generated and valid. |

## Dashboard Boundary

Future dashboards may project these artifacts but must not become authority. Dashboards may show security posture, taxonomy coverage, scan summary, findings, evidence, release-gate decisions, accepted risks, and next Work Orders.

Dashboards must not run scans, approve risk, mutate repositories, stage files, commit files, push, write target artifacts, bypass Work Order reports, bypass operator decisions, or replace Handoff Packets.

## Non-Execution Rules

- Report artifacts are evidence and planning data, not execution commands.
- Finding records do not authorize remediation.
- Evidence records do not authorize target access.
- Accepted risk records require file-backed operator decisions.
- Release-gate summaries do not replace Work Order reports.
- Ready-to-copy Handoff Packets are allowed only when they satisfy the Handoff Packet contract and preserve authority constraints.
- Missing evidence, missing operator decisions, or unclear release impact must produce `HOLD` or `PASS WITH RISKS`, not silent `PASS`.

Security Review reports that recommend remediation planning must not rely on abbreviated ready-to-copy prompts. When a report has `release_gate_decision: REMEDIATE_BEFORE_RELEASE`, finding records, evidence records, and a remediation-planning `next_work_order_recommendation`, the generated Handoff Packet must include all Handoff Packet Contract fields plus security preservation context:

- SecurityReviewReport, ReleaseGateSummary, finding, evidence, dashboard projection, and source report artifact refs;
- release-gate decision and release-gate decision rules;
- all finding IDs or short finding references;
- target path, target branch, target HEAD, and known dirty/untracked constraints from file-backed evidence;
- explicit no-scan, no-target-validation, no-target-mutation, no-secret, and no-untracked-entry-inspection boundaries;
- a bounded remediation-planning objective;
- the requirement that actual remediation mutation occurs only in a later approved mutation Work Order.

Security handoff generation must fail deterministic evals when these fields are missing, and must not claim execution readiness when required context is unavailable.

Security remediation mutation handoffs must preserve the Work Order boundary between mutation, commit planning, commit execution, and push. An `approved_mutation_execution` handoff with `phase_type: approved_mutation` may authorize bounded source/test mutation only; it must forbid staging, committing, and pushing, must defer commit planning to a later separate Work Order after mutation evidence exists, and must fail deterministic evals if its allowed actions say or imply that it may stage or commit.

## Validation Expectations

Static checks for this contract should verify:

- all required artifact shapes are documented;
- required report/finding/evidence/accepted-risk/release-gate fields are present;
- release-gate decision values are explicit;
- sample artifacts remain non-executing and not target-specific;
- dashboard projection language is non-authoritative;
- no target repo, scan execution, runtime, CLI, profile registry, DB/event/schema/Docker/dashboard/TORII/cloud/org/global/enterprise, dependency, or lockfile authority is introduced.
