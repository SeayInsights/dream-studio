# Operator Decision Contract

## Purpose

Operator Decision artifacts make human/operator choices explicit before Dream Studio moves from HOLD, review, or planning into an execution handoff.

Operator decisions are file-backed evidence. They do not execute work, mutate target repositories, open the native runtime DB, write event ledgers, or grant authority outside the Work Order boundary.

## Decision Request

A decision request is written to:

`<storage_root>/<work_order_id>/decisions/request.json`

Required fields:

- `decision_request_id`
- `work_order_id`
- `phase_type`
- `required_decision_taxonomy`
- `status`: `pending_operator_decision`
- `question`
- `allowed_decisions`
- `recommended_decision`
- `risk_summary`
- `required_evidence`
- `requires_reason`
- `created_at`

The `allowed_decisions` field must match the taxonomy for `phase_type`. The `recommended_decision` must be one of `allowed_decisions`.

## Operator Decision

An operator decision is written to:

`<storage_root>/<work_order_id>/decisions/operator_decision.json`

Required fields:

- `decision_request_id`
- `work_order_id`
- `decision`
- `decided_by`
- `decided_at`
- `reason`
- `approved_next_handoff_type`
- `constraints`
- `privacy_export_classification`

The `decision` must be one of the request's `allowed_decisions`. If `requires_reason` is true, `reason` must be non-empty.

## Rules

- Execution handoffs that require an operator decision cannot be generated when the operator decision is missing.
- The operator decision must be file-backed.
- Recording an operator decision must not mutate a target repo.
- Recording an operator decision must not open the native runtime DB.
- Recording an operator decision does not execute work by itself.
- Handoff and report evals must fail or remain incomplete when required decision evidence is missing; they must not silently pass.

## CLI

The Work Order CLI may expose:

- `decision-request --id <work_order_id>` to show request and decision status.
- `request-decision --id <work_order_id> --phase-type <phase_type> --question <text> --recommended <decision>` to create `request.json`.
- `decide --id <work_order_id> --decision <decision> --reason <text> --decided-by operator` to create `operator_decision.json`.

These commands operate only under Work Order storage paths.
