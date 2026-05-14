# Human-In-The-Loop Contract

Phase: 16A - Work Order MVP Contract Foundation

Human-in-the-loop control defines which decisions require an operator, what cannot be delegated, and how manual execution is represented in Work Order evidence.

## Authority Principles

1. Humans/operators own approval decisions for mutation, escalation, export, and recovery.
2. AI tools may recommend, render, summarize, and validate within scope, but they cannot approve their own escalation.
3. Manual execution is represented as file-backed evidence in Phase 16.
4. Human decisions do not imply DB/event writes by default.

## Roles

| Role | Responsibility |
| --- | --- |
| `operator` | Selects target paths, creates or approves Work Orders, and owns local risk decisions. |
| `reviewer` | Reviews rendered packets, results, reports, or eval artifacts. |
| `executor` | Performs manual work outside automated Work Order execution when explicitly approved. |
| `observer` | Collects or reviews observe-only evidence. |
| `system` | Records file-backed artifacts and validations without autonomous approval authority. |

## Human Decision Types

- `approve_observe`
- `approve_render`
- `approve_manual_execution`
- `approve_export`
- `reject`
- `block`
- `revoke`
- `defer`

Mutation-capable decisions are future scope and must not be introduced in Phase 16 without explicit re-scoping.

## Non-Delegable Actions

These cannot be delegated to AI tools, dashboards, telemetry, adapters, research, enterprise analytics, Docker, cloud, org/global layers, or automatic policy:

- approval to mutate a target repo;
- approval to stage, commit, push, delete, move, or format target files;
- approval to write the native runtime DB;
- approval to run schema migrations;
- approval to restore or repair native DB/backups;
- approval to execute DreamySuite work;
- approval to export local/private evidence.

## Approval Responsibilities

Every approval record must include:

- decision type;
- approver;
- linked Work Order ID;
- linked target path;
- approved scope;
- reviewed evidence;
- timestamp;
- expiration or revocation rule;
- privacy/export classification.

Approval scope must be explicit and narrow. Approval must fail closed when scope is unclear.

## Manual Execution Representation

Phase 16 may represent manual execution as:

- a rendered manual packet;
- a human-supplied Work Result;
- evidence files;
- validation output;
- eval artifacts.

Manual execution evidence does not prove target repo mutation safety by itself. A target repo mutation eval is required before any mutation-capable mode is accepted.

## Validation Expectations

Static tests must prove:

- roles are documented;
- human decision types are documented;
- non-delegable actions are explicit;
- no mutation without explicit approval;
- manual execution is evidence, not autonomous execution.
