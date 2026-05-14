# Dream Studio Architecture Brief

Status: draft_generated
Authority role: architecture authority summary

## Architecture Intent

Dream Studio is a local-first AI orchestration control plane. It coordinates
agentic work through product authority, stage gates, milestone state, policies,
evidence, validation, reports, and projections without treating prompts or
handoffs as primary authority.

## Control Plane

The control plane owns PRD authority loading, stage-gate routing, milestone
execution state, stop-gate policy, approvals, operator decisions, artifact
lifecycle policy, and next-action classification.

## Execution Engine

The execution engine runs Work Orders and internal steps inside approved
milestones. It should continue low-risk steps internally, record evidence
continuously, and stop at material risk boundaries.

## PRD And Stage-Gate Authority

The PRD owns product goals, non-goals, strategic constraints, and completion
criteria. Stage gates own ordered capability gates, required-before rules,
milestone sequence, routing constraints, stop gates, auto-continue policy, and
approval policy.

## Milestone Planner

The milestone planner reads active PRD, stage gate map, milestone state,
approvals, evidence, validations, and strategic constraints. It emits one of:

- continue_internal
- require_operator_approval
- hard_stop
- generate_handoff
- complete_milestone
- start_next_milestone

## Agent And Router Layer

Agents are routed by goal, milestone, risk, and available tool/skill boundaries.
Routing must remain model/provider/tool agnostic and must not assume one
particular agent runtime.

## Hook Engine

Hooks provide lifecycle integration for local automation. Hook behavior must be
treated as potentially mutating when staging, committing, recovery, or runtime
side effects are possible.

## Skill And Workflow Registry

Skills and workflows provide repeatable execution patterns. They are selected by
milestone need and approval mode, not by stale prompt chains.

## Research And Verification Subsystem

Research decisions classify whether research is not needed, allowed, required,
requires operator verification, blocked by source uncertainty, or blocked by
safety/sensitive context. Research evidence must include sources, confidence,
decision impact, and routing impact.

## Evidence And Artifact Subsystem

Evidence, reports, prompts, rendered views, exports, and retained attachments
are indexed and linked to Work Orders, milestones, validations, approvals, and
events. Markdown reports are summaries, not primary truth.

## SQLite And Structured Authority Subsystem

SQLite/local structured state should become operational authority where safe.
Database mutation, migrations, DDL/DML, schema changes, and rollback-affecting
operations require explicit approval and evidence milestones.

## File-Backed Evidence Subsystem

File-backed artifacts remain critical for audit, recovery, import/export, and
operator review. They must reference structured authority and evidence refs
instead of replacing them.

## Projection And Dashboard Subsystem

Dashboard and projection surfaces consume structured state, artifact indexes,
and evidence summaries. They are derived views, not primary truth. Runtime/API
implementation is a separate approved milestone boundary.

## Policy, Approval, And Stop-Gate Subsystem

The policy engine evaluates human-in-the-loop rules, stop gates, approval
requirements, research verification gates, artifact lifecycle boundaries,
database gates, and external project pause constraints.

## Handoff And Report Renderer

Handoffs and reports are rendered from structured state, policy, templates, and
evidence refs. Generated handoffs must self-validate before they are emitted as
ready.

## Adapter Boundary Layer

Adapters may connect Claude Code, Codex, Cursor, Copilot agents, TORII, MCP
systems, browser/runtime tools, or future cloud/org surfaces. Adapters are
deferred unless explicitly scoped and must not change the local-first authority
model.
