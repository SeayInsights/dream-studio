# Security Review Scan Definition Schema

## Purpose

This document drafts the structured data shape for Security Review scan definitions. It is intended to make the expanded Security Review Scan Catalog consumable by future Work Orders, reports, and projections without parsing freeform markdown.

This schema is documentation/data only. It does not implement scan execution, authorize target repository access, add runtime code, add CLI commands, create a profile registry, write database/event ledgers, add schema migrations, expand Docker, or create dashboard/TORII/cloud/org/global/enterprise integration.

## Relationship To Existing Security Documents

- Source list: `docs/contracts/security-review-source-47-enterprise-scans.md`
- Coverage crosswalk: `docs/contracts/security-review-47-scan-crosswalk.md`
- Markdown catalog: `docs/contracts/security-review-scan-catalog.md`
- Sample structured excerpt: `docs/contracts/security-review-scan-catalog.sample.yaml`
- Catalog governance: `docs/contracts/security-review-catalog-governance.md`
- Security Review Profile Pack contract: `docs/contracts/security-review-profile-pack-contract.md`

The original source list remains exactly 47 operator-supplied enterprise security items. The structured catalog may contain more scan definitions because one source item can require multiple scan definitions and one scan definition can reference multiple source items.

## Non-Execution Boundary

Structured scan definitions are profile-pack data. They must not be treated as commands.

Rules:

- `execution_status` must be `non_executing_definition`.
- `command_template` is optional and must remain absent or `null` until a later approved Work Order defines command execution.
- target repository access requires a future scoped Work Order.
- scan execution requires future approval, validation profile data, evidence profile data, stop conditions, and artifact containment.
- runtime, DAST, infrastructure, cloud, registry, and network checks must remain deferred until target scope is approved.
- findings and coverage metadata are evidence, not mutation authority.

## Top-Level Document Shape

Recommended top-level fields:

| Field | Required | Purpose |
| --- | --- | --- |
| `catalog_schema_version` | yes | Version for this structured shape, e.g. `security_review_scan_definition.v0`. |
| `execution_status` | yes | Must be `non_executing_definition`. |
| `source_list_ref` | yes | Path to the original 47-item source list. |
| `crosswalk_ref` | yes | Path to the source-to-catalog crosswalk. |
| `profile_pack_contract_ref` | yes | Path to the Security Review Profile Pack contract. |
| `generated_from` | yes | Human-readable source context or Work Order ID. |
| `scan_definitions` | yes | List of structured scan definitions. |

## ScanDefinition Shape

Each `scan_definitions` item must include:

| Field | Required | Purpose |
| --- | --- | --- |
| `scan_id` | yes | Stable local scan identifier. |
| `title` | yes | Human-readable scan title. |
| `tier` | yes | `T0`, `T1`, `T2`, or `T3`. |
| `source_item_refs` | yes | One or more references to original 47-item source entries. |
| `category_id` | yes | Primary Security Review taxonomy category. |
| `scan_kind` | yes | `manual_review`, `static_command`, `external_report_review`, `artifact_review`, `config_review`, or `deferred`. |
| `intent` | yes | Security risk or evidence gap the scan is meant to reveal. |
| `phase_allowed` | yes | Work Order phase families where this scan may be planned. |
| `approval_mode_required` | yes | Required approval mode before any future execution or mutation. |
| `target_profile_inputs` | yes | Target profile fields needed before scoping. |
| `validation_profile_inputs` | yes | Validation profile fields needed before command planning. |
| `evidence_profile_inputs` | yes | Evidence fields the scan must produce or cite. |
| `mutation_risk` | yes | `none`, `writes_cache`, `writes_artifacts`, `updates_snapshots`, `formatting`, `network`, or `unknown`. |
| `network_risk` | yes | `none`, `local_only`, `external_metadata`, `external_service`, or `unknown`. |
| `artifact_write_risk` | yes | Artifact write posture before execution planning. |
| `prerequisites` | yes | Required evidence, scope, approvals, tools, or repo state before planning. |
| `expected_outputs` | yes | Expected report/evidence outputs when a later Work Order runs or reviews the scan. |
| `timeout_policy` | yes | Timeout class and stop behavior for later execution planning. |
| `safe_failure_mode` | yes | HOLD/FAIL behavior if the scan cannot run safely. |
| `false_positive_notes` | yes | Review caveats and likely false-positive areas. |
| `remediation_handoff_hint` | yes | Existing handoff family for findings or failures. |
| `execution_status` | yes | Must be `non_executing_definition`. |

Optional fields:

| Field | Purpose |
| --- | --- |
| `secondary_category_ids` | Additional taxonomy categories. |
| `coverage_status` | Coverage status for source-item mapping: `explicit`, `deferred_runtime`, `deferred_infrastructure`, `grouped`, `partial`, `not_applicable_by_default`, or `missing`. |
| `command_template` | Must be absent or `null` until a later approved execution Work Order defines it. |
| `notes` | Human-readable limitations or future implementation notes. |

## SourceItemRef Shape

Each `source_item_refs` entry must include:

| Field | Required | Purpose |
| --- | --- | --- |
| `source_list_ref` | yes | Path to `docs/contracts/security-review-source-47-enterprise-scans.md`. |
| `item_number` | yes | Original source item number from 1 to 47. |
| `item_name` | yes | Original source item name. |
| `domain` | yes | Original source domain heading. |
| `coverage_status` | yes | Coverage status from the crosswalk. |
| `coverage_rationale` | yes | Why the scan maps to the source item. |

## Required Traceability Rules

- Every structured scan definition must have at least one `source_item_refs` entry.
- Every original source item must appear in at least one structured scan definition before implementation readiness is claimed.
- Runtime and infrastructure-deferred source items may be represented by `scan_kind: deferred` or review-only scans, but must retain `execution_status: non_executing_definition`.
- The structured data shape must preserve the distinction between the 47-item source list and the expanded catalog.
- Missing or partial source coverage must produce HOLD or PASS WITH RISKS, not implementation readiness.

## Example Readiness Rules

The structured catalog is ready for future planning only when:

- source-item coverage is complete and file-backed;
- every scan has `execution_status: non_executing_definition`;
- every runtime or infrastructure scan has explicit deferred posture;
- no command templates imply execution;
- target profile, validation profile, and evidence profile inputs are identified but not executed.

## Deferred Work

Do not implement these in this schema draft:

- full structured catalog conversion;
- scan execution;
- runtime code;
- CLI commands;
- profile registry;
- database or event ledger storage;
- dashboard projections;
- target repository access;
- dependency or lockfile changes.
