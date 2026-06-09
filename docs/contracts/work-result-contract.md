# Work Result Contract

Phase: 16A - Work Order MVP Contract Foundation

A Work Result records what happened after a Work Order was observed, rendered, manually executed, or otherwise evaluated. In Phase 16, Work Results are file-backed local evidence artifacts.

## Authority Principles

1. Work Results are evidence, not canonical runtime state.
2. Work Results do not write the native runtime DB by default.
3. Work Results do not become workflow, orchestration, decision, memory, dashboard, adapter, telemetry, research, enterprise, Docker, cloud, or org/global authority.
4. Raw outputs are local/private by default unless explicitly classified.

## Required Fields

Every Work Result must include:

- `result_id`
- `linked_work_order_id`
- `status`
- `summary`
- `raw_output_ref`
- `structured_findings`
- `validation_results`
- `eval_artifacts`
- `warnings`
- `risks`
- `next_work_order_recommendation`
- `created_by`
- `created_at`
- `privacy_export_classification`

## Status Meanings

| Status | Meaning |
| --- | --- |
| `not_started` | No result has been recorded. |
| `observed` | Observe-only evidence was collected. |
| `rendered` | Execution packets were rendered only. |
| `manual_result_recorded` | Human/operator supplied result evidence. |
| `validated` | Validation evidence was recorded. |
| `blocked` | Stop condition or missing approval prevented progress. |
| `failed` | The attempted work failed with evidence. |
| `reported` | A report was produced. |

## Raw Output Preservation

Raw outputs may include logs, terminal output, generated text, manually supplied notes, or rendered packet references.

Raw output is local/private by default. It must be referenced through local file-backed artifacts and must not be exported without privacy/export classification and redaction where required.

## Structured Extraction

Structured findings may include:

- changed scope observed;
- validation commands and outcomes;
- warnings;
- risks;
- decisions requested;
- evidence links;
- source/provenance links;
- next Work Order recommendations.

Structured extraction does not promote raw evidence into canonical state.

## Next Work Order Recommendation

Recommendations must include:

- recommended objective;
- reason;
- risk level;
- suggested approval mode;
- explicit non-goals;
- required validation;
- whether target repo mutation would be needed in a future phase.

A recommendation does not create or approve the next Work Order automatically.

## Handoff Packet Relationship

A Work Result may feed report generation for a Handoff Packet. The Handoff Packet turns the next Work Order recommendation into a fresh-session-safe prompt only when deterministic report and handoff evals permit it.

The generated prompt remains evidence and guidance. It is not auto-executed, does not grant mutation authority, and must require a Handoff Understanding Report before the receiving session takes action.

When a Work Result recommends a specialized next phase, the Handoff Packet must preserve the matching decision taxonomy. Push-planning, commit-planning, recovery-decision, product-closeout, approved-mutation, and normal follow-up prompts must list their allowed decisions and require the receiving report to choose exactly one `Final Decision`.

When a report is `HOLD` or a transition to execution requires an explicit operator decision, the report must use file-backed decision artifacts. A `decision_request` asks for one decision from the required taxonomy. An `operator_decision` records the selected decision, actor, timestamp, reason, approved next handoff type, constraints, and privacy classification. The decision remains evidence only; it does not execute the selected work.

## Validation Expectations

Static tests must prove:

- result fields are documented;
- statuses are defined;
- raw output is local/private by default;
- next Work Order recommendation is evidence only;
- Work Results are file-backed and do not write DB/events by default.
