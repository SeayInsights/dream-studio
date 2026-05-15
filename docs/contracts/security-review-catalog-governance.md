# Security Review Catalog Governance

## Purpose

This document defines synchronization and governance rules for the Security Review Profile Pack catalog artifacts. It exists to prevent drift between the original source list, crosswalk, markdown catalog, structured YAML catalog, schema document, and sample YAML.

This governance contract is documentation and static-test guidance only. It does not authorize target repo access, scan execution, runtime implementation, CLI command implementation, profile registry implementation, DB/event/schema/Docker/dashboard/TORII/cloud/org/global/enterprise expansion, dependency changes, lockfile changes, or repository mutation.

## Canonical Artifact Roles

| Artifact | Canonical role |
| --- | --- |
| `docs/contracts/security-review-source-47-enterprise-scans.md` | Source standard for the operator-supplied original 47 enterprise security items. |
| `docs/contracts/security-review-47-scan-crosswalk.md` | Traceability authority from each source item to catalog scan IDs and coverage status. |
| `docs/contracts/security-review-scan-catalog.yaml` | Machine-readable catalog source for scan definitions. |
| `docs/contracts/security-review-scan-catalog.md` | Human-readable documentation for the catalog. |
| `docs/contracts/security-review-scan-definition-schema.md` | Schema authority for allowed fields, source-item references, and non-execution posture. |
| `docs/contracts/security-review-scan-catalog.sample.yaml` | Non-canonical illustrative excerpt for schema examples. |
| `docs/contracts/security-review-profile-pack-contract.md` | Profile-pack boundary contract for taxonomy, evidence, reporting, and authority constraints. |
| `docs/contracts/security-by-default-development-lifecycle-gate.md` | Lifecycle policy contract that applies the 47-control framework to goals, milestones, Work Orders, code changes, and release readiness. |

## Source-Of-Truth Rules

- The original 47 source list is the source standard. Changes to it require explicit operator approval and a new crosswalk review.
- The structured YAML catalog is the machine-readable catalog source for future Work Orders, reports, and projections.
- The crosswalk is the traceability authority for source-item coverage, coverage status, catalog scan IDs, rationale, and recommended action.
- The markdown catalog is human-readable documentation unless a later approved Work Order explicitly changes that role.
- The schema document defines allowed fields, source-item reference shape, and non-execution posture.
- The sample YAML is not canonical and must not be used to infer full catalog coverage.
- Security Review artifacts remain profile-pack data until a later approved Work Order defines execution scope, target profile inputs, validation profile inputs, evidence profile inputs, and safe failure behavior.
- The security lifecycle gate may classify applicability and release readiness from these artifacts, but it remains a non-executing read model and cannot authorize scans or mutation.

## Synchronization Rules

- YAML scan IDs must match markdown scan IDs.
- Every YAML scan must include `source_item_refs`.
- Every original source item from 1 through 47 must appear in at least one YAML scan.
- Every crosswalk row must map only to valid YAML scan IDs.
- Every YAML scan must keep `execution_status: "non_executing_definition"`.
- Every YAML scan must keep `command_template: null`.
- Catalog row additions require updates to the YAML catalog, markdown catalog, crosswalk, and static tests.
- YAML catalog changes require static tests before acceptance.
- Markdown catalog changes must not contradict the YAML catalog or crosswalk.
- Crosswalk coverage-status changes require a rationale update.
- Source list changes require explicit operator approval before any catalog or crosswalk rewrite.
- Scan execution requires a later approved Work Order and cannot be inferred from any catalog artifact.

## Drift Prevention Checks

Static checks must enforce:

- 75 YAML scans match markdown scan IDs.
- every YAML scan has source_item_refs.
- every source item 1-47 appears in at least one YAML scan.
- every crosswalk row maps to valid YAML scan IDs.
- every scan is non-executing.
- every command_template remains null.
- no target repo, runtime, CLI, dashboard, DB/event, Docker, TORII, cloud, org, global, enterprise, dependency, or lockfile authority is introduced.

## Allowed Edit Paths

- Source-list edits are allowed only with explicit operator approval and must trigger crosswalk and static-test review.
- Crosswalk edits are allowed to improve traceability, coverage status, rationale, or recommended action.
- YAML edits are allowed to refine scan definitions while preserving schema conformance and non-execution posture.
- Markdown catalog edits are allowed for human-readable alignment with YAML.
- Schema edits are allowed only for documentation/data shape clarification.
- Sample YAML edits are allowed only to keep examples aligned with the schema.

## Required Checks Before Acceptance

Before accepting any catalog governance change, run the focused static catalog tests and whitespace checks required by the active Work Order. At minimum, catalog governance changes should prove:

- the source list still contains exactly 47 source items;
- the crosswalk still maps all 47 source items once;
- the structured YAML catalog still contains exactly 75 unique scan definitions;
- source-item traceability remains complete;
- crosswalk scan IDs are valid YAML scan IDs;
- non-execution posture remains explicit;
- command templates remain null;
- no forbidden authority surface is introduced.

## Non-Execution Policy

Security Review catalog artifacts are not execution authority. They may describe future review intent, evidence needs, target profile inputs, validation profile inputs, and remediation handoff hints, but they must not grant target access, run scans, create commands, install dependencies, write target artifacts, mutate repositories, open native runtime databases, or bypass Work Order approval.

## Deferred Work

The following remain deferred to later approved Work Orders:

- generating one artifact from another;
- full profile registry implementation;
- scan execution;
- target profile implementation;
- validation profile implementation;
- evidence profile implementation;
- dashboard projection implementation;
- DB/event ledger integration;
- cloud/org/global/enterprise aggregation.
