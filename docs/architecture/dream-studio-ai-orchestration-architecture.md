# Dream Studio AI Orchestration Architecture

Status: public rendered view

Dream Studio orchestrates goal-oriented work through product authority, route-first milestones, Work Orders, adapters, telemetry, evidence, and dashboard attention. Adapter-specific surfaces are projections; Dream Studio remains the control plane.

## Orchestration Loop

1. Read PRD, stage gates, policies, and current structured state.
2. Select the next valid milestone.
3. Generate or resume a bounded Work Order.
4. Produce an adapter-specific context packet only when needed.
5. Execute through approved hooks, skills, workflows, tools, and agents.
6. Normalize results into Dream Studio records.
7. Validate, record evidence, and emit telemetry.
8. Update read models and dashboard attention.
9. Continue internally or stop at a real approval, blocker, release, rollback, or cleanup boundary.

## Adapter Model

Supported and future adapters include Claude Code, Codex, Cursor, Copilot, ChatGPT, MCP systems, browser tools, shell tools, local models, and other agents. Each adapter should:

- receive only the minimum context needed;
- write back normalized results;
- avoid owning primary authority;
- respect source, runtime, and approval boundaries;
- surface stale config as a repair Work Order instead of silently diverging.

## Operational Intelligence

The platform correlates route decisions, validations, security findings, tokens, workflows, hooks, tools, skills, models, research, decisions, and outcomes so the operator can see what worked, what failed, what needs approval, and what should be hardened next.

## Boundary

Dream Studio can publish sanitized source and docs. It must keep private local state, raw telemetry, cutover evidence, cleanup candidates, backups, local audit trails, and operator decision logs out of GitHub unless explicitly sanitized and approved.
