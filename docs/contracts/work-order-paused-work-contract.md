# Work Order Paused Work Contract

## Purpose
PausedWork artifacts are file-backed continuity records for Work Orders that have been paused and may later be resumed. A PausedWork artifact lets a fresh session determine why work paused, what must be true before resume, which handoff to use, and which constraints remain active without relying on chat memory or narrative report prose.

PausedWork artifacts are not execution commands. They must not run Work Orders, mutate repositories, approve risk, run scans, run validation, stage files, commit files, push, write target artifacts, open Dream Studio runtime databases, write event ledgers, or bypass the Work Order authority model.

## Storage
PausedWork artifacts live under the paused Work Order storage path:

`~/.dream-studio/meta/work-orders/<paused-work-order-id>/continuity/paused_work.yaml`

The artifact may reference reports, Handoff Packets, approval artifacts, operator decisions, eval artifacts, or security artifacts. It must not require previous chat context to be useful.

## Required Fields
Every `paused_work.yaml` artifact must include:

| Field | Required | Meaning |
| --- | --- | --- |
| `paused_work_id` | yes | Stable artifact identifier. |
| `paused_phase_name` | yes | Human-readable paused phase name. |
| `paused_work_order_id` | yes | Work Order ID being paused or resumed. |
| `paused_from_phase` | yes | Phase that created or updated the pause state. |
| `paused_from_work_order_id` | yes | Work Order ID that created or updated the pause state. |
| `pause_reason` | yes | Why the work paused. |
| `blocking_condition` | yes | Condition that had to be resolved or still blocks resume. |
| `resume_condition` | yes | Concrete condition for safe resume. |
| `current_status` | yes | `paused`, `resume_ready`, `resumed`, `completed`, `resolved`, `closed`, `superseded`, `hold`, or `fail`. |
| `resume_allowed` | yes | Boolean gate; `true` only when source artifacts support resume. |
| `target_id` | yes | Target identifier, or `not_applicable`. |
| `target_path` | yes | Target path, or `not_applicable`. |
| `target_branch` | yes | Target branch, or `unknown`/`not_applicable`. |
| `target_head` | yes | Target HEAD, or `unknown`/`not_applicable`. |
| `release_gate` | yes | Release-gate state, or `not_applicable`. |
| `priority_findings` | yes | List of finding IDs or short finding names driving resume. |
| `forbidden_until_resume` | yes | Actions that remain forbidden before or during resume unless a later Work Order explicitly authorizes them. |
| `source_artifact_refs` | yes | File-backed reports, handoffs, evals, approvals, or security artifacts that justify the pause/resume state. |
| `required_resume_artifacts` | yes | Artifacts the receiver must read before resuming. |
| `resume_handoff_ref` | yes | Ready-to-copy Handoff Packet or prompt artifact to use for resume. |
| `created_at` | yes | Creation timestamp in ISO-like local form. |
| `updated_at` | yes | Last update timestamp in ISO-like local form. |

## Status Rules
`current_status: paused` means the work remains paused, even if `resume_allowed: true` says the blocker has been resolved and a fresh session may resume from the referenced handoff.

`current_status: resume_ready` may be used when the pause has been resolved and the next Work Order should start from `resume_handoff_ref`.

`current_status: resumed`, `completed`, `resolved`, `closed`, or `superseded` require a source artifact showing the later state.

`current_status: hold` or `fail` requires a blocking condition and must not claim resume readiness.

`current_status: completed` or `resolved` means the paused Work Order resumed and reached a file-backed terminal or completed result. The artifact must set `resume_allowed: false` and include completion/resolution references so a fresh session does not treat the old pause as still active.

## Resolution Fields
When a PausedWork artifact moves from `paused` or `resume_ready` to `resumed`, `completed`, or `resolved`, it should include:

| Field | Meaning |
| --- | --- |
| `resumed_by_work_order_id` | Work Order ID that resumed the paused work. |
| `resumed_by_phase` | Human-readable phase that resumed the paused work. |
| `resume_result` | Result or verdict produced by the resumed work. |
| `completion_report_ref` | File-backed report proving the resumed outcome. |
| `mutation_evidence_ref` | File-backed mutation or review evidence proving the resumed outcome, when applicable. |
| `next_recommended_phase` | Next bounded phase after completion/resolution. |
| `next_handoff_ref` | File-backed next Handoff Packet, when one has been generated. |

## Resume Gate Rules
A PausedWork artifact may set `resume_allowed: true` only when:

- the source artifacts listed in `source_artifact_refs` exist;
- the handoff in `resume_handoff_ref` exists;
- the resume condition is stated concretely;
- forbidden actions remain preserved;
- no target mutation, scan execution, validation execution, stage, commit, push, dashboard authority, DB/event, schema, Docker, TORII, cloud, org, global, or enterprise authority is implied unless a later Work Order explicitly authorizes it.

If any required source artifact is missing, `resume_allowed` must be `false` or the artifact must use `current_status: hold`.

## Not Chat Memory
PausedWork artifacts must be self-contained enough for a fresh session to recover the paused state from file-backed artifacts. They may summarize report prose, but they must not require the receiver to know previous conversation history.

Reports and Handoff Packets that discuss paused work should reference the PausedWork artifact path. Narrative report sections such as `Paused Work To Resume` are useful for human reading, but they are not the continuity source of truth unless backed by `paused_work.yaml`.

## Handoff Relationship
`resume_handoff_ref` points to the Handoff Packet or prompt artifact that the receiver should use after checking the PausedWork artifact. The Handoff Packet remains the execution prompt; the PausedWork artifact is continuity state and does not grant authority by itself.

If the referenced handoff is regenerated, the PausedWork artifact must be updated or superseded so `resume_handoff_ref`, `updated_at`, and source references remain accurate.

## Current Phase 18S.13 Case
For Phase 18S.13, the PausedWork artifact records that:

- Phase 18S.13 was paused because an earlier generated mutation handoff contained ambiguous stage/commit authority.
- Phase 18S.12A regenerated a mutation-only handoff.
- Resume is allowed only from the regenerated Phase 18S.13 handoff.
- Stage, commit, push, scans, target validation, dependency changes, lockfile changes, schema migrations, browser session architecture work, durable auth-state work, and untracked-entry inspection remain forbidden unless a later Work Order explicitly authorizes them.
- Release gate remains `REMEDIATE_BEFORE_RELEASE`.

## Static Eval Expectations
Static checks should verify:

- all required fields are documented;
- representative PausedWork YAML contains every required field;
- `resume_allowed` cannot be treated as execution approval;
- `source_artifact_refs`, `required_resume_artifacts`, and `resume_handoff_ref` are present;
- forbidden actions are preserved;
- paused work is not represented only by chat memory or report prose.
