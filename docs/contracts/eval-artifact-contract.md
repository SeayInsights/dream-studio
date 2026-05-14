# Eval Artifact Contract

Phase: 16A - Work Order MVP Contract Foundation

Eval artifacts are file-backed evidence records that judge whether a Work Order, skill, agent, workflow, model, tool, research artifact, or approval behaved as expected. Phase 16 eval artifacts are deterministic/local first.

## Authority Principles

1. Eval artifacts are evidence, not canonical runtime state.
2. Phase 16 eval artifacts are file-backed only.
3. Eval artifacts do not write real-runtime-DB events by default.
4. Eval artifacts do not create schema migrations or DB tables.
5. Eval artifacts do not grant dashboards, telemetry, adapters, research, enterprise analytics, Docker, cloud, or org/global authority.

## Required Fields

Every eval artifact must include:

| Field | Rule |
| --- | --- |
| `eval_id` | Stable local eval identifier. |
| `eval_type` | Named eval type. |
| `subject_type` | One of `skill`, `agent`, `workflow`, `work_order`, `model`, `tool`, `research`, `approval`. |
| `subject_id` | Identifier for the evaluated subject. |
| `linked_work_order_id` | Work Order ID when applicable. |
| `input_artifact` | Input file, packet, result, report, or source reference. |
| `expected_behavior` | Required behavior or invariant. |
| `observed_behavior` | Observed behavior or evidence summary. |
| `score` | Numeric, rubric, or `not_scored`. |
| `pass_fail` | `pass`, `fail`, or `incomplete`. Use `incomplete` when required evidence is missing, unavailable, or the eval is not the applicable mode-specific eval. |
| `evaluator` | `deterministic`, `human`, `rubric`, or `model_assisted`. |
| `evidence` | Evidence paths or inline summary. |
| `privacy_export_classification` | `local_only`, `exportable_with_redaction`, `aggregate_only`, or `non_exportable`. |
| `created_at` | ISO-8601 timestamp. |

## Required File-Backed Eval Types

Work Order MVP and approved Phase 17 mutation slices define file-backed eval artifacts for:

- `work_order_render_completeness`
- `skill_identifier_safety`
- `observe_only_compliance`
- `approved_mutation_compliance`
- `forbidden_action_compliance`
- `target_repo_mutation`
- `result_report_completeness`
- `next_work_order_recommendation`
- `handoff_prompt_completeness`
- `handoff_constraint_preservation`
- `handoff_execution_readiness`
- `handoff_fresh_session_sufficiency`
- `handoff_recovery_mode_completeness`
- `handoff_current_state_completeness`
- `handoff_recovery_option_clarity`
- `handoff_operator_decision_gate`
- `handoff_index_state_requirements`
- `handoff_hook_behavior_awareness`
- `handoff_push_execution_completeness`
- `handoff_push_target_constraints`
- `handoff_push_evidence_requirements`
- `operator_decision_request_completeness`
- `operator_decision_validity`
- `operator_decision_required_before_execution`
- `operator_decision_reason_completeness`

Before mutation-capable modes exist, `target_repo_mutation` must prove no mutation occurred. For explicit approved-mutation slices, `approved_mutation_compliance` must prove approval evidence exists and changed-file evidence stays inside the approved scope.

## Mode-Aware Mutation Semantics

| Work Order mode | Evidence state | Expected eval result |
| --- | --- | --- |
| `observe_only` | no mutation evidence and explicit before/after proof exists | `pass` |
| `observe_only` | mutation evidence exists | `fail` |
| `observe_only` | required before/after evidence missing | `incomplete` |
| `approval_required` | approval exists and changed files are all approved | `pass` |
| `approval_required` | unapproved or forbidden file changed | `fail` |
| `approval_required` | approval evidence missing | `fail` or `incomplete` depending on whether mutation evidence exists; never `pass` |
| `approval_required` | changed-file evidence missing | `incomplete` |

For `approval_required` Work Orders, `observe_only_compliance` must not be marked `pass` merely because an approved mutation occurred. It may be omitted, or emitted as `incomplete` with clear observed behavior explaining that `approved_mutation_compliance` is the applicable eval.

## Handoff Prompt Semantics

Handoff prompt evals are deterministic checks over generated next prompts in Work Order reports:

- `handoff_prompt_completeness` checks required Handoff Packet sections and fields exist.
- `handoff_constraint_preservation` checks authority constraints are preserved.
- `handoff_execution_readiness` checks `READY` and `READY_WITH_CONSTRAINTS` reports produce execution-oriented Handoff Packets, while `HOLD` and `FAIL` reports produce non-executing recovery or hold prompts. It also checks `Final Decision` belongs to the declared `Required Decision Taxonomy`.
- `handoff_fresh_session_sufficiency` checks the fresh-session rule and Handoff Understanding Report requirement are present.
- `handoff_recovery_mode_completeness` checks recovery prompts declare `handoff_type: recovery_decision`, include recovery-only sections, and do not blend decision with execution.
- `handoff_current_state_completeness` checks recovery prompts model local commit, branch-ahead, staged/index, no-push, and forbidden-file state.
- `handoff_recovery_option_clarity` checks recovery prompts list recovery options and recommend the safest option.
- `handoff_operator_decision_gate` checks recovery prompts require an operator decision before mutation or index changes.
- `handoff_index_state_requirements` checks recovery prompts with git staging include explicit index evidence requirements.
- `handoff_hook_behavior_awareness` checks recovery prompts involving pre-commit, lint-staged, or hooks warn that hooks may modify files and require working tree/index re-checks.
- `handoff_push_execution_completeness` checks push-execution prompts include approved target, forbidden target, before-push evidence, exact command, after-push evidence, readiness, verdict, and next report sections.
- `handoff_push_target_constraints` checks push-execution prompts constrain remote, branch, exact command, force-push, tags, other branches, other remotes, remote branch deletion, and extra refspecs.
- `handoff_push_evidence_requirements` checks push-execution prompts require approval artifact, fetch, expected HEAD, local commits, empty index, ahead/behind, before/after evidence, and no-forbidden-action proof.

These evals must not use model judging, execute generated prompts, inspect target repos, or write DB/event records. Missing critical context must produce `fail` or `incomplete`, not `pass`.

Missing `Phase Type` or `Required Decision Taxonomy` fails `handoff_prompt_completeness`. Push planning prompts must list `PUSH_READY_WITH_APPROVAL`, `RUN_BROADER_VALIDATION_FIRST`, `HOLD`, and `FAIL`. Commit planning, recovery decision, product closeout, approved mutation, and normal next Work Order prompts must list their documented decision sets.

## Operator Decision Eval Semantics

Operator decision evals are deterministic checks over file-backed artifacts under `<storage_root>/<work_order_id>/decisions/`.

- `operator_decision_request_completeness` checks `request.json` exists and includes the phase type, allowed taxonomy, question, recommended decision, risk, evidence, and reason requirement when a decision is required.
- `operator_decision_validity` checks `operator_decision.json` exists when needed and that the selected decision belongs to the request taxonomy.
- `operator_decision_required_before_execution` fails when an execution handoff is requested while the required operator decision is missing or invalid.
- `operator_decision_reason_completeness` fails when `requires_reason` is true and the recorded decision has an empty reason.

Operator decision evals must not execute the selected decision, mutate target repos, open the native runtime DB, or write event records.

## Evaluator Semantics

| Evaluator | Rule |
| --- | --- |
| `deterministic` | Uses static checks, file snapshots, command output, or structured artifact checks. |
| `human` | Records a human/operator decision or review. |
| `rubric` | Applies a written scoring rubric. |
| `model_assisted` | May summarize or classify evidence, but cannot be sole authority for approval or mutation. |

## File-Backed Storage

Eval artifacts should live under Work Order-controlled local state/meta paths, such as:

- `~/.dream-studio/meta/work-orders/<work_order_id>/evals/`
- `~/.dream-studio/projects/<project>/work-orders/<work_order_id>/evals/`

Tests must use temp/fake HOME paths.

## Privacy And Export

Default classification is `local_only`. Eval artifacts may contain target paths, raw output snippets, prompts, validation logs, or private evidence. Export requires explicit privacy classification and redaction where needed.

## Prohibitions

Eval artifacts must not:

- write to the native runtime DB by default;
- add DB tables;
- add schema migrations;
- emit real-runtime-DB events by default;
- mutate target repos;
- approve their own escalation;
- make model/tool comparison or cost-to-outcome scoring a Phase 16 requirement.

## Validation Expectations

Static tests must prove:

- required fields are documented;
- required Phase 16 eval types are documented;
- file-backed storage is required;
- DB/schema/event writes are prohibited;
- eval artifacts remain evidence only.
