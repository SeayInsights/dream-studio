# Observe-only Tier 0 Security Review Work Order Template

## Purpose

This template defines a reusable observe-only Tier 0 Security Review Work Order shape. It is meant to help a future phase point Dream Studio at a real target without inventing scope, evidence, release-gate behavior, or dashboard projection fields.

This template is documentation/template data only. It is not a completed security review. It does not inspect target repos, run scans, execute commands, mutate repositories, add runtime code, add CLI commands, implement dashboards, create profile registries, write database/event ledgers, add schema migrations, expand Docker, add TORII/cloud/org/global/enterprise integration, modify dependencies, or change lockfiles.

## Source Contracts

The template binds to these existing contracts:

- Security Review Profile Pack: `docs/contracts/security-review-profile-pack-contract.md`
- Structured scan catalog: `docs/contracts/security-review-scan-catalog.yaml`
- Security catalog governance: `docs/contracts/security-review-catalog-governance.md`
- Security Review report artifacts: `docs/contracts/security-review-report-artifact-contract.md`
- Dashboard projection model: `docs/contracts/dashboard-projection-model-contract.md`
- Handoff Packet contract: `docs/contracts/handoff-packet-contract.md`

## Template Identity

Recommended template fields:

| Field | Required | Purpose |
| --- | --- | --- |
| `template_id` | yes | Stable template identifier, recommended `security_review_tier0_observe_only`. |
| `template_version` | yes | Template version. |
| `work_order_kind` | yes | `security_review`. |
| `tier` | yes | `T0`. |
| `approval_mode` | yes | `observe_only`. |
| `risk_level` | yes | Recommended `medium`. |
| `execution_status` | yes | Must be `non_executing_template`. |
| `not_a_target_review` | yes | Must be true until instantiated for a scoped target. |

## Required Target Intake Fields

A future instantiated Work Order must provide target intake data. This template must not bind to a real target by itself.

Required intake fields:

- `target_id`
- `display_name`
- `repo_path`
- `repo_kind`
- `default_branch`
- `active_branch_policy`
- `remote_name`
- `allowed_read_scope`
- `target_output_restrictions`
- `generated_artifact_policy`
- `dependency_change_policy`
- `schema_migration_policy`
- `known_dirty_policy`
- `privacy_export_classification`

Target intake is scope evidence only. It does not authorize mutation, command execution, scan execution, dependency installation, lockfile changes, generated target artifacts, push, stage, commit, or remediation.

## Tier 0 Scan Selection Rules

Tier 0 scan selection must be derived from `docs/contracts/security-review-scan-catalog.yaml`.

Selection rules:

- include scan definitions where `tier` is `T0`;
- require `execution_status: "non_executing_definition"`;
- require `command_template: null`;
- require at least one `source_item_refs` entry;
- preserve `scan_id`, `category_id`, `scan_kind`, `approval_mode_required`, `mutation_risk`, `network_risk`, `artifact_write_risk`, `evidence_profile_inputs`, and `remediation_handoff_hint`;
- do not add scans that are not present in the structured catalog;
- do not execute command-based scans, even when `scan_kind` is `static_command`.

Current Tier 0 scan IDs:

- `sec.dependency.vulnerability_inventory`
- `sec.dependency.lockfile_integrity`
- `sec.secrets.high_entropy_patterns`
- `sec.secrets.env_template_drift`
- `sec.static.injection_patterns`
- `sec.static.unsafe_eval_exec`
- `sec.auth.access_boundary_review`
- `sec.auth.session_cookie_policy`
- `sec.api.cors_policy_review`
- `sec.api.input_validation_surface`
- `sec.release.branch_state_evidence`
- `sec.release.forbidden_artifact_write_check`
- `sec.static.xss_output_encoding`
- `sec.static.memory_safety_boundary_review`
- `sec.static.concurrency_race_review`
- `sec.static.ssrf_request_boundary_review`
- `sec.static.xxe_parser_review`
- `sec.auth.broken_auth_logic_review`

## Observe-only Review Boundary

The instantiated Work Order must stay observe-only unless a later approved Work Order changes the mode.

Allowed observe-only behavior:

- inspect file-backed Work Order scope and target intake;
- inspect file-backed security catalog/profile/report contracts;
- inspect pre-existing file-backed evidence explicitly provided by the Work Order;
- record findings and limitations as file-backed Dream Studio artifacts;
- recommend next Work Orders.

Forbidden behavior:

- touching target repos unless the instantiated Work Order explicitly scopes read-only target access;
- mutating target repos;
- running scans;
- running target validation;
- installing dependencies;
- updating lockfiles;
- writing generated artifacts inside target repos;
- staging, committing, or pushing;
- implementing scan execution;
- adding runtime code, CLI commands, dashboard UI/API/runtime projection builders, profile registry, DB/event/schema/Docker/dashboard/TORII/cloud/org/global/enterprise surfaces;
- claiming the template has reviewed a real target.

## Evidence Requirements

Before review:

- capture Work Order ID, phase name, approval mode, risk level, and report path;
- capture target intake fields or mark them missing;
- capture Security Review Profile Pack, structured catalog, report artifact contract, and dashboard projection contract refs;
- prove the selected Tier 0 scan list came from the structured catalog;
- prove no scan execution is authorized;
- prove output locations are outside target repos.

During review:

- collect only file-backed evidence allowed by the instantiated Work Order;
- record evidence limitations when target access, command output, external reports, or scan execution are missing;
- create findings only from file-backed evidence;
- keep all command results as `not_run` unless a future Work Order explicitly authorizes execution.

After review:

- produce a `SecurityReviewReport`;
- produce `SecurityEvidenceRecord` entries for evidence and limitations;
- produce `SecurityFindingRecord` entries when findings exist;
- produce `AcceptedRiskRecord` entries only when a file-backed operator decision exists;
- produce a `ReleaseGateSummary`;
- produce `DashboardProjectionSnapshot` readiness fields or projection inputs;
- prove no forbidden action occurred;
- recommend a bounded next Work Order.

## Output Artifact Expectations

Recommended output paths under Work Order storage:

- `<storage_root>/<work_order_id>/security/review_report.yaml`
- `<storage_root>/<work_order_id>/security/evidence/*.yaml`
- `<storage_root>/<work_order_id>/security/findings/*.yaml`
- `<storage_root>/<work_order_id>/security/accepted_risks/*.yaml`
- `<storage_root>/<work_order_id>/security/release_gate.yaml`
- `<storage_root>/<work_order_id>/dashboard/projection_inputs.yaml`

Outputs must not be written inside target repositories unless a later approved Work Order explicitly authorizes target artifact writes.

## Release-gate Decision Handling

Allowed release-gate decisions:

- `SECURITY_CLEAR`
- `SECURITY_CLEAR_WITH_RISKS`
- `ACCEPT_RISK_WITH_APPROVAL`
- `REMEDIATE_BEFORE_RELEASE`
- `RUN_ADDITIONAL_SECURITY_REVIEW`
- `HOLD`
- `FAIL`

Decision rules:

- use `SECURITY_CLEAR` only when Tier 0 evidence is complete, no blocking findings exist, and no required approval is missing;
- use `SECURITY_CLEAR_WITH_RISKS` when no blockers exist but bounded residual risks or evidence limitations remain;
- use `ACCEPT_RISK_WITH_APPROVAL` only when a file-backed operator decision can accept residual risk;
- use `REMEDIATE_BEFORE_RELEASE` when findings require remediation before release;
- use `RUN_ADDITIONAL_SECURITY_REVIEW` when Tier 0 evidence is incomplete or target/validation scope is needed;
- use `HOLD` when target intake, evidence, approval, operator decision, or authority context is unclear;
- use `FAIL` if a forbidden action occurs.

## Dashboard Projection Readiness Fields

The review should produce projection-ready fields without implementing a dashboard:

- `work_order_id`
- `phase_name`
- `approval_mode`
- `risk_level`
- `readiness`
- `verdict`
- `final_decision`
- `next_action`
- `report_ref`
- `handoff_ref`
- `blocking_risks`
- `security_review_report_ref`
- `target_id`
- `security_pack_id`
- `release_gate_decision`
- `taxonomy_coverage`
- `scan_status_counts`
- `findings_by_severity`
- `findings_by_release_impact`
- `blocking_findings`
- `accepted_risks`
- `deferred_scans`
- `evidence_inventory_refs`
- `next_work_order_recommendation`

Dashboard projection data remains read-only and non-authoritative.

## Recommended Next Work Order Outcomes

The template may recommend:

- target intake completion;
- observe-only Tier 0 review execution against an explicitly scoped target;
- additional security review planning;
- remediation planning;
- risk acceptance decision;
- release planning with risks;
- dashboard projection implementation planning.

It must not recommend automatic scan execution, automatic remediation, automatic risk acceptance, automatic push, or dashboard authority.
