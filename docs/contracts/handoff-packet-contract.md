# Handoff Packet Contract

## Purpose

A Handoff Packet is a ready-to-copy prompt artifact produced from a completed Work Order report. It allows a fresh AI session, model, tool, or human operator to continue from a prior Work Order without requiring previous chat or session context.

A Handoff Packet is not an execution command. It must not auto-execute generated instructions, mutate repositories, open the native runtime database, write event ledgers, or bypass the Work Order authority model.

## Required Fields And Sections

Every Handoff Packet prompt must include:

- phase name;
- handoff type;
- phase type;
- required decision taxonomy;
- final decision;
- decision rationale;
- source Work Order ID;
- next Work Order ID;
- Dream Studio repo path;
- target repo path, if any;
- baseline Dream Studio branch and HEAD, if known;
- baseline target repo branch and HEAD, if known;
- objective;
- capability boundary;
- approval mode;
- risk level;
- scope include;
- scope exclude;
- approved files, if mutation-gated;
- forbidden files;
- allowed actions;
- forbidden actions;
- approval artifact requirement, if mutation-gated;
- before/after evidence requirements;
- validation commands;
- eval requirements;
- report path;
- readiness rules;
- expected verdict;
- stop conditions;
- fresh-session rule;
- before-action Handoff Understanding Report requirement;
- first safe action.

The prompt may mark branch or HEAD values as `unknown` when they are not available from file-backed Work Order evidence, but it must still include the section.

## Decision Taxonomies

Every generated Handoff Packet must declare a `phase_type`, a `required_decision_taxonomy`, a `final_decision`, and a `decision_rationale`.

Allowed `phase_type` values and decision taxonomies:

| phase_type | Allowed decisions |
|---|---|
| `push_planning` | `PUSH_READY_WITH_APPROVAL`, `RUN_BROADER_VALIDATION_FIRST`, `HOLD`, `FAIL` |
| `commit_planning` | `READY_FOR_COMMIT_PLANNING`, `NEEDS_ONE_MORE_FIX`, `HOLD`, `FAIL` |
| `recovery_decision` | `LINT_REMEDIATION`, `NO_VERIFY_CONTINUATION`, `UNSTAGE_AND_HOLD`, `ROLLBACK`, `HOLD`, `FAIL` |
| `product_closeout` | `READY_FOR_HUMAN_REVIEW`, `READY_FOR_COMMIT_PLANNING`, `NEEDS_ONE_MORE_FIX`, `HOLD`, `FAIL` |
| `approved_mutation` | `MUTATION_COMPLETE`, `NEEDS_REMEDIATION`, `HOLD`, `FAIL` |
| `normal_next_work_order` | `CONTINUE_TO_NEXT_WORK_ORDER`, `REQUEST_HUMAN_APPROVAL`, `HOLD`, `FAIL` |

`push_planning` applies when the next phase decides between push readiness, broader validation, hold, or failure. `PUSH_READY_WITH_APPROVAL` may generate a separate approved push-execution prompt, but it must not execute the push. `RUN_BROADER_VALIDATION_FIRST` may generate a broader-validation planning prompt, but it must not run broad validation automatically. `HOLD` and `FAIL` may generate remediation or review prompts only.

`commit_planning` applies when the next phase decides whether reviewed changes are ready for commit planning, need one more fix, should hold, or failed.

`recovery_decision` applies when an earlier phase stopped and the operator must choose one recovery path. The prompt must preserve the four recovery options: `LINT_REMEDIATION`, `NO_VERIFY_CONTINUATION`, `UNSTAGE_AND_HOLD`, and `ROLLBACK`.

`product_closeout` applies to closeout audits that decide whether work is ready for human review, commit planning, one more fix, hold, or fail.

Product closeout and post-push retrospective handoffs must include `Readiness Rules` and `Expected Verdict`. Product closeout readiness rules must require the source report to confirm completed work and no forbidden action, preserve observe-only posture when applicable, hold on any mutation or authority drift, and require future implementation work to be opened as separate Work Orders. Product closeout expected verdicts must distinguish `PASS`, `PASS WITH RISKS`, `HOLD`, and `FAIL`.

Stale standalone Handoff Packet artifacts may be regenerated only by a Dream Studio generator path that reads the existing packet context and writes a regenerated packet under Work Order storage or Dream Studio `meta/audit`. Regeneration must not manually patch prompt text as the primary fix, inspect target repositories, run validation, push, stage, commit, or write artifacts inside a target repository.

Generic Handoff Packet templates must remain target-neutral. Product names, repository names, branch names, commit hashes, domain fields, dirty-file lists, and phase-specific labels may appear only when they come from file-backed Work Order context, target/profile-like input, fixtures, case studies, or historical audit artifacts. Generic core text should use neutral terms such as `target repo`, `source report`, `approval artifact`, and `push execution report` unless a profile or artifact supplies a more specific display name.

`approved_mutation` applies to a bounded approved mutation execution. It may decide `MUTATION_COMPLETE`, `NEEDS_REMEDIATION`, `HOLD`, or `FAIL`.

`normal_next_work_order` applies to ordinary non-specialized follow-up work.

The `final_decision` section must contain exactly one allowed value from the declared taxonomy. A prompt may use `HOLD` as the safe starting decision when the receiving phase report must choose the final action after evidence collection.

Security Review remediation-planning handoffs are `normal_next_work_order` Handoff Packets generated from file-backed Security Review artifacts. When the source release gate is `REMEDIATE_BEFORE_RELEASE`, the prompt must preserve the SecurityReviewReport path, ReleaseGateSummary path, finding and evidence artifact paths, dashboard projection input path, release-gate decision, finding IDs, target branch/HEAD constraints, known untracked-entry constraints, no-scan/no-validation/no-target-mutation boundaries, and the rule that actual remediation occurs only in a later approved mutation Work Order. Abbreviated security next prompts must fail deterministic handoff evals or remain withheld.

Approved security remediation mutation handoffs are `approved_mutation_execution` Handoff Packets for bounded target source/test mutation only. They must forbid staging, committing, and pushing, and must state that commit planning occurs in a later separate Work Order after mutation evidence exists. An approved mutation handoff must fail deterministic evals if its allowed actions say or imply that it may stage or commit.

## Handoff Types

Every generated prompt must declare exactly one `handoff_type`:

- `normal_next_work_order`;
- `approved_mutation_execution`;
- `commit_execution`;
- `recovery_decision`;
- `recovery_execution`;
- `hold_review`.

`normal_next_work_order`, `approved_mutation_execution`, and `commit_execution` may describe a next execution slice only when sequential readiness is `READY` or `READY_WITH_CONSTRAINTS`.

For `push_planning` prompts with `final_decision: PUSH_READY_WITH_APPROVAL`, a valid file-backed operator decision may generate an `approved_mutation_execution` push handoff. That push handoff must remain a Handoff Packet, not an auto-executed push.

Push-execution handoffs must include:

- `Approved Push Target`;
- `Forbidden Push Targets`;
- `Before-Push Evidence Requirements`;
- `Push Command`;
- `After-Push Evidence Requirements`;
- `Sequential Readiness Rules`;
- `Expected Verdict`;
- `Next Prompt/Report Requirement`.

The `Approved Push Target` section must identify the remote, branch, and exact command. The `Forbidden Push Targets` section must state no force push, no tags, no pushing any other branch, no pushing any other remote, no delete remote branch, and no push with extra refspecs.

The `Before-Push Evidence Requirements` section must require an approval artifact before push, Dream Studio status and HEAD, target repo status and HEAD, the expected branch, expected HEAD, exact local commits, empty index proof, `fetch origin`, ahead/behind proof, unrelated dirty-file exclusion, and no force-push/tag/other-branch proof.

The `After-Push Evidence Requirements` section must require push output, post-push status, post-push ahead/behind, post-push log, proof the local branch is no longer ahead by the expected commit count, proof unrelated dirty files remained local and uncommitted, proof no forbidden push target was used, and proof no edit/stage/commit occurred during the push phase.

`recovery_decision` is the default handoff type for `HOLD` reports. It is decision-only. It must not directly execute recovery unless the source report explicitly includes an operator-selected recovery path.

`recovery_execution` may be used only after an operator has selected one recovery path and the prompt includes the approval, scope, evidence, and stop-condition requirements for that specific path.

`hold_review` is for non-executing review prompts where no recovery path can yet be safely framed.

## Operator Decision Gate

When a report is `HOLD`, or when a planning/review phase requires an explicit operator choice before execution, Dream Studio must use a file-backed operator decision gate.

Decision requests are stored at:

`<storage_root>/<work_order_id>/decisions/request.json`

Operator decisions are stored at:

`<storage_root>/<work_order_id>/decisions/operator_decision.json`

An execution handoff must not be generated for a required decision until `operator_decision.json` exists, validates against the request taxonomy, and includes a reason when `requires_reason` is true. The operator decision is evidence only; it does not execute the selected path by itself.

## Recovery Decision Requirements

For `recovery_decision` handoffs, the prompt must include:

- `source_failure`;
- `current_state`;
- `known_safe_actions`;
- `forbidden_recovery_actions`;
- `recovery_options`;
- `recommended_option`;
- `operator_decision_required: true`;
- `do_not_execute_until_decision: true`;
- `index_state_requirements`, when git staging or index state is involved;
- `hook_behavior_risks`, when pre-commit, lint-staged, or other hooks were involved.

Recovery decision prompts must distinguish decision from execution. They may present options such as lint remediation, no-verify continuation, unstage-and-hold, or rollback, but they must require the operator to choose one path before any mutation or index change.

When a failure involves pre-commit, lint-staged, or hooks, the prompt must state that hooks may modify files, that the receiver must re-check working tree and index after any hook attempt, and that hooks must never be assumed non-mutating.

## Fresh-Session Rule

Every generated Handoff Packet prompt must include this exact rule:

> Assume you have no prior conversation context. Use only this prompt and referenced artifacts.

The receiver must treat previous conversation history as unavailable unless the Handoff Packet explicitly references a local artifact path.

## Handoff Understanding Report

Every generated Handoff Packet prompt must require the receiver to produce a Handoff Understanding Report before taking action.

The Handoff Understanding Report must include:

- objective;
- repositories involved;
- source Work Order ID;
- next Work Order ID;
- approval mode;
- risk level;
- approved files;
- forbidden files;
- allowed commands/actions;
- forbidden commands/actions;
- evidence required;
- validation required;
- eval requirements;
- stop conditions;
- first safe action;
- missing context, if any.

The Handoff Understanding Report is a before-action checkpoint. It does not grant mutation authority by itself.

## Pass/Fail Semantics

`PASS`: the handoff prompt contains enough context for a fresh session to proceed safely within the stated Work Order mode and authority constraints.

`FAIL`: the handoff prompt is missing critical safety or context fields, contradicts authority constraints, claims unsupported readiness, or omits required approval/evidence context.

`INCOMPLETE`: the handoff prompt is understandable but requires human clarification before execution.

## Safety Rules

- A handoff prompt must never claim the next phase is safe if required approval, evidence, eval, scope, or stop-condition context is missing.
- A handoff prompt must not weaken Work Order approval, observe-only, approved-mutation, target-repo mutation, forbidden-action, or skill identifier rules.
- A handoff prompt must preserve the default prohibitions against DB/event ledger integration, schema migrations, Docker expansion, dashboard/TORII/cloud/org/global/enterprise integration, unapproved target repo mutation, hooks/lib recreation, and skill identifier drift.
- A handoff prompt must not execute itself, invoke external AI tools, inspect live target repos to manufacture evidence, or write target repo artifacts.

## Relationship To Work Order Reports

Work Order reports may include:

- `Sequential Execution Readiness`;
- `Next Action Decision`;
- `Ready-To-Copy Next Prompt`.

Reports with `READY` or `READY_WITH_CONSTRAINTS` readiness may include an execution-oriented Handoff Packet. Reports with `HOLD` or `FAIL` readiness must not include an execution prompt; they may include a remediation or review prompt that explains what must be fixed before continuation.

For `HOLD`, generated remediation prompts default to `handoff_type: recovery_decision` and must include current state, recovery options, a recommended safest option, an operator decision gate, and any staged/index or hook-risk requirements.

## Deterministic Eval Types

Handoff Packet prompts are evaluated by deterministic file-backed eval artifacts:

- `handoff_prompt_completeness`;
- `handoff_constraint_preservation`;
- `handoff_execution_readiness`;
- `handoff_fresh_session_sufficiency`.
- `handoff_recovery_mode_completeness`;
- `handoff_current_state_completeness`;
- `handoff_recovery_option_clarity`;
- `handoff_operator_decision_gate`;
- `handoff_index_state_requirements`;
- `handoff_hook_behavior_awareness`.
- `handoff_push_execution_completeness`;
- `handoff_push_target_constraints`;
- `handoff_push_evidence_requirements`.
- `security_handoff_finding_refs_present`;
- `security_handoff_release_gate_preserved`;
- `security_handoff_target_constraints_preserved`;
- `security_handoff_remediation_scope_bounded`;
- `security_handoff_forbidden_actions_preserved`;
- `security_handoff_no_target_mutation_without_approval`;
- `security_handoff_no_commit_without_commit_phase`;
- `ready_to_copy_next_prompt_contract_compliance`.
- `operator_decision_request_completeness`;
- `operator_decision_validity`;
- `operator_decision_required_before_execution`;
- `operator_decision_reason_completeness`.

Missing critical context must produce `fail` or `incomplete`, not `pass`.

Missing `phase_type` or `required_decision_taxonomy` must fail `handoff_prompt_completeness`. A `final_decision` outside the declared taxonomy must fail `handoff_execution_readiness`.

Push-execution prompts must fail deterministic push evals when they omit the approved push target, forbidden push target constraints, exact push command, before-push approval/fetch/ahead-behind/HEAD/index gates, after-push evidence, sequential readiness rules, expected verdict, or next report requirement.
