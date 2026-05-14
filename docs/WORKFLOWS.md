# Workflow Guide

Dream Studio workflows coordinate local AI operations through route decisions, Work Orders, validations, evidence, telemetry, and operator approvals.

## Workflow Types

| Workflow | Purpose |
| --- | --- |
| Goal to milestone | Interpret a goal, choose the next stage-gate-valid milestone, and produce bounded Work Orders |
| Work Order execution | Execute approved source, validation, research, or evidence steps with file scope and rollback guidance |
| Release gate | Verify CI/CD profile, local parity validation, branch/PR state, GitHub checks, blockers, and merge policy |
| Dashboard attention | Surface approvals, warnings, blockers, prompt-required items, and route state |
| Shared intelligence | Generate context packets, normalize adapter results, capture learning events, and harden components |
| Backup/cutover | Rehearse and perform local installed-state changes only under explicit approval |

## Route Decisions

Common route decisions:

- `continue_internal`
- `require_operator_approval`
- `hard_stop`
- `generate_handoff`
- `complete_milestone`
- `start_next_milestone`

Routine report writing, evidence creation, checklist review, or next-milestone availability is not a handoff reason by itself.

## Evidence Requirements

Mutating Work Orders should record:

- clean starting status;
- approved files;
- allowed and forbidden actions;
- before/after status;
- validation commands and results;
- changed-file proof;
- rollback guidance;
- final route decision.

## Approval Boundaries

Separate approval is required for:

- live installed-state mutation;
- live SQLite mutation or migration;
- cleanup, deletion, archive execution, compaction, or deduplication;
- push, tag, merge, deploy, or history rewrite;
- external project mutation;
- secret or sensitive value inspection.

## Adapter Use

Adapters receive scoped context packets and return normalized results. Claude Code, Codex, Cursor, Copilot, ChatGPT, MCP systems, shell tools, local models, and future adapters remain surfaces over Dream Studio authority.

## Publication Safety

Generated Work Orders, handoffs, raw telemetry, cutover evidence, dogfood traces, local audit trails, backups, and cleanup manifests are private by default. Public examples should be synthetic or sanitized.
