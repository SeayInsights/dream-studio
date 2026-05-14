# Work Orders Operations

Status: Current file-backed Work Orders and Handoff Packet operations

Work Orders are local, file-backed records for bounded AI-assisted work. They define objective, scope, approval mode, constraints, validation, expected evidence, and stop conditions.

The current Work Order MVP can create, validate, render, record results, generate reports, and produce deterministic file-backed eval artifacts. Generated next prompts are Handoff Packets: ready-to-copy prompts that must be fresh-session safe and must not auto-execute.

## File-Backed Posture

Work Orders are:

- file-backed only;
- local/private by default;
- stored under Dream Studio-controlled state/meta paths in later implementation slices;
- tested with fake HOME/temp directories;
- non-mutating against target repos for create, validate, render, status, record-result, and report;
- non-authoritative over local canonical runtime state.

Work Orders are not:

- DB tables;
- schema migrations;
- real-runtime-DB event writes by default;
- dashboard features;
- cloud/org/global sync;
- enterprise integration;
- Docker authority;
- autonomous execution.

## Commands

| Command | Behavior |
| --- | --- |
| `create` | Create a file-backed Work Order definition under explicit local state/meta. |
| `validate` | Validate required fields, target path explicitness, approval mode, forbidden actions, and authority limits. |
| `status` | Read file-backed Work Order status. |
| `render` | Produce Codex, Claude, or other target packets without executing them. |
| `record-result` | Record file-backed Work Result evidence. |
| `report` | Summarize Work Order, packets, results, evals, warnings, risks, and next action. |
| `regenerate-handoff` | Rebuild an existing standalone Handoff Packet artifact through the current generator without inspecting or mutating target repositories. |
| `generate-security-next-handoff` | Build a remediation-planning Handoff Packet from file-backed Security Review artifacts without inspecting or mutating target repositories. |
| `generate-security-mutation-handoff` | Build a mutation-only Security Remediation Handoff Packet from file-backed planning/security artifacts; generated prompts must forbid stage, commit, and push. |
| `decision-request` | Show a file-backed operator decision request and recorded decision status. |
| `request-decision` | Create a pending operator decision request from the phase decision taxonomy. |
| `decide` | Record a file-backed operator decision after validating it against the request taxonomy. |

These commands must not mutate target repos by default.

## Storage

Recommended future storage roots:

- `~/.dream-studio/meta/work-orders/`
- `~/.dream-studio/projects/<project>/work-orders/`

Tests must use fake HOME/temp equivalents. Commands must not auto-discover, open, migrate, repair, or write the native runtime DB.

## Paused Work Continuity

Paused Work state must be file-backed when a Work Order is paused and expected to resume later. The continuity artifact is:

`~/.dream-studio/meta/work-orders/<paused-work-order-id>/continuity/paused_work.yaml`

The PausedWork contract is documented in `docs/contracts/work-order-paused-work-contract.md`. A report may include a human-readable `Paused Work To Resume` section, but fresh sessions must recover pause/resume status from `paused_work.yaml` and referenced artifacts, not chat memory or report prose alone.

Reports or Handoff Packets that resume paused work should reference the PausedWork artifact path, the `resume_handoff_ref`, the `resume_condition`, and the still-forbidden actions. `resume_allowed: true` does not grant mutation, stage, commit, push, scan, validation, dashboard, DB/event, schema, Docker, TORII, cloud, org, global, or enterprise authority by itself; the receiving Work Order and Handoff Packet still control authority.

## Eval Artifacts

The file-backed Work Order MVP produces deterministic eval artifacts:

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
- `security_handoff_finding_refs_present`
- `security_handoff_release_gate_preserved`
- `security_handoff_target_constraints_preserved`
- `security_handoff_remediation_scope_bounded`
- `security_handoff_forbidden_actions_preserved`
- `security_handoff_no_target_mutation_without_approval`
- `security_handoff_no_commit_without_commit_phase`
- `ready_to_copy_next_prompt_contract_compliance`
- `operator_decision_request_completeness`
- `operator_decision_validity`
- `operator_decision_required_before_execution`
- `operator_decision_reason_completeness`

Eval artifacts are evidence only and local/private by default.

For approved mutation slices, `approved_mutation_compliance` is the applicable mutation-mode eval. It requires file-backed approval evidence plus explicit changed-file or snapshot evidence. `observe_only_compliance` remains strict for `observe_only` Work Orders and must not be treated as proof for approved mutation slices.

## Handoff Packets And Next Prompts

Reports may include:

- `Sequential Execution Readiness`
- `Next Action Decision`
- `Ready-To-Copy Next Prompt`

Readiness values:

| Readiness | Meaning |
| --- | --- |
| `READY` | The result, recommendation, and blocking eval evidence are complete. |
| `READY_WITH_CONSTRAINTS` | Continuation is possible, but incomplete non-blocking evidence must be carried forward. |
| `HOLD` | The next action needs review, remediation, or missing evidence before execution. |
| `FAIL` | A blocking failure prevents continuation until fixed. |

Reports with `READY` or `READY_WITH_CONSTRAINTS` may include an execution-oriented Handoff Packet. Reports with `HOLD` or `FAIL` must not include an execution prompt. `HOLD` reports default to `handoff_type: recovery_decision`, which may describe recovery options but must not execute recovery until the operator chooses one path.

Every Handoff Packet must include the fresh-session rule, the before-action Handoff Understanding Report requirement, authority constraints, scope, evidence requirements, validation commands, eval requirements, stop conditions, and the first safe action. Handoff Packets are not auto-executed.

Every Handoff Packet must also include `Readiness Rules` and `Expected Verdict`. Product closeout and post-push retrospective handoffs use stricter rules: proceed only when the source report confirms completed work and no forbidden action, preserve observe-only posture, hold on any mutation or authority drift, and move future implementation into separate Work Orders.

Stale standalone Handoff Packet artifacts can be regenerated through the current generator with:

`python interfaces/cli/ds_work_order.py regenerate-handoff --from-file <existing-handoff.md> --to-file <audit-or-work-order-output.md>`

The command rebuilds an existing Handoff Packet from its embedded context and writes only under Work Order storage or the sibling Dream Studio `meta/audit` path. It must not inspect, mutate, validate, or execute against a target repository.

Security Review reports with remediation-oriented next Work Order recommendations can generate a complete next Handoff Packet from file-backed `SecurityReviewReport`, `ReleaseGateSummary`, finding, evidence, and dashboard projection artifacts:

`python interfaces/cli/ds_work_order.py generate-security-next-handoff --source-report <phase-report.md> --security-report <review_report.yaml> --release-gate <release_gate.yaml> --findings-dir <findings-dir> --evidence-dir <evidence-dir> --dashboard-projection <projection_inputs.yaml> --to-file <audit-output.md> --output-report-path <next-report.md>`

The command evaluates the generated packet before writing it. It must preserve release-gate decisions, finding references, target branch/HEAD constraints, untracked-entry constraints, no-scan/no-validation/no-target-mutation boundaries, and the requirement that actual remediation occurs only in a later approved mutation Work Order.

Approved security remediation mutation handoffs are generated separately from remediation-planning handoffs. They may authorize bounded source/test mutation only after an approval artifact exists, but they must not authorize staging, committing, or pushing; commit planning belongs in a later separate Work Order after mutation evidence exists.

Generic Work Order and Handoff core must stay target-neutral. Target names, product domains, branches, commit hashes, dirty-file policies, and phase-specific report labels belong in Work Order artifacts, target/profile-like context, fixtures, case studies, or historical audit reports. Core templates should default to terms like `target repo`, `source report`, `approval artifact`, and `push execution report`; any specific target display name must come from input context rather than hardcoded core prose.

Every Handoff Packet must also include `Phase Type`, `Required Decision Taxonomy`, `Final Decision`, and `Decision Rationale`. The taxonomy is phase-specific:

| Phase Type | Required decisions |
| --- | --- |
| `push_planning` | `PUSH_READY_WITH_APPROVAL`, `RUN_BROADER_VALIDATION_FIRST`, `HOLD`, `FAIL` |
| `commit_planning` | `READY_FOR_COMMIT_PLANNING`, `NEEDS_ONE_MORE_FIX`, `HOLD`, `FAIL` |
| `recovery_decision` | `LINT_REMEDIATION`, `NO_VERIFY_CONTINUATION`, `UNSTAGE_AND_HOLD`, `ROLLBACK`, `HOLD`, `FAIL` |
| `product_closeout` | `READY_FOR_HUMAN_REVIEW`, `READY_FOR_COMMIT_PLANNING`, `NEEDS_ONE_MORE_FIX`, `HOLD`, `FAIL` |
| `approved_mutation` | `MUTATION_COMPLETE`, `NEEDS_REMEDIATION`, `HOLD`, `FAIL` |
| `normal_next_work_order` | `CONTINUE_TO_NEXT_WORK_ORDER`, `REQUEST_HUMAN_APPROVAL`, `HOLD`, `FAIL` |

The receiving phase report must choose exactly one allowed `Final Decision`. For planning prompts, `HOLD` may be used as the safe starting value until evidence collected in the receiving phase supports a more specific decision.

Recovery decision prompts must include source failure, current state, known safe actions, forbidden recovery actions, recovery options, recommended option, an operator decision gate, and explicit `do_not_execute_until_decision: true`. If git staging or hooks were involved, they must also require staged/index evidence and warn that pre-commit or lint-staged hooks may modify files.

When `phase_type` is `push_planning`, the final decision is `PUSH_READY_WITH_APPROVAL`, and a valid operator decision exists, the next handoff may be an `approved_mutation_execution` push handoff. Push-execution handoffs must include approved push target, forbidden push targets, before-push evidence requirements, exact push command, after-push evidence requirements, sequential readiness rules, expected verdict, and next report requirements. They must require an approval artifact before push, `fetch origin`, expected HEAD and local commits, empty index proof, ahead/behind proof, and explicit no-force-push/no-tags/no-other-branch constraints. They must not push automatically.

## Operator Decision Artifacts

When a report is `HOLD` or a transition from planning/review into execution requires an explicit operator choice, Dream Studio records decision evidence under:

- `<storage_root>/<work_order_id>/decisions/request.json`
- `<storage_root>/<work_order_id>/decisions/operator_decision.json`

`request.json` includes the Work Order ID, phase type, required decision taxonomy, pending status, operator question, allowed decisions, recommended decision, risk summary, required evidence, reason requirement, and creation time.

`operator_decision.json` includes the request ID, Work Order ID, selected decision, decision actor, timestamp, reason, approved next handoff type, constraints, and privacy classification.

Recording a decision never executes the selected work. Execution handoffs that require an operator decision must remain blocked until a valid `operator_decision.json` exists.

## Historical Target-Proof Case Study Notes

Historical case-study note: the phrase "DreamySuite is Phase 17 only" described a completed Phase 16/17 proof-target boundary. It is retained here only as historical context and is not current generic operations authority.

Historical static-guardrail note: Phase 16A was "contract and static guardrails only"; acceptance fixtures used the phrases "There is no Work Order CLI", "Planned Commands", and "These commands must not mutate target repos during Phase 16". These are legacy guardrail terms only. Current commands are listed above.

The historical proof-target fixture also said it must not touch, inspect, clone, modify, validate, or execute against DreamySuite. That sentence remains here as case-study context only; the current generic rule applies to every target repository.

Current generic operations guidance is target-neutral: target-specific paths, branches, dirty-file policies, product names, and validation command groups belong in Work Order artifacts, fixtures, case studies, or future target/profile-like context. Generic Work Order commands must not inspect, mutate, validate, or execute against any target repository unless a bounded approved Work Order explicitly authorizes that action.

## Troubleshooting

Stop if:

- a command tries to open the native runtime DB;
- a schema migration is proposed;
- Work Order DB tables are proposed;
- real-runtime-DB event writes are proposed by default;
- target repo mutation begins;
- a target repository is touched outside explicit Work Order authority;
- enterprise integration appears;
- Docker becomes required or authoritative;
- cloud/org/global sync appears;
- the retired `hooks/lib` path is recreated;
- skill identifiers drift from `ds-<slug>` form.

## Static Validation

Static Work Order validation confirms:

- required contracts exist;
- authority boundaries are documented;
- file-backed storage is required;
- DB/schema/event writes are prohibited;
- target repo mutation is prohibited;
- target-specific proof-target details remain artifact, fixture, case-study, or profile/context data rather than generic operations authority.
