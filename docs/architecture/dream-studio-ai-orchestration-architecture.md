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

---

## Current State vs. Architecture Vision

**This section reflects honest current reality as of Phase 18.1.12. The
architecture above describes the target state; this section describes where
we actually are today.**

### Canonical events — claim vs. reality

The architecture states that canonical events are authoritative and that all
observability flows through them. In practice:

- **2 of 22 hook handlers** route their telemetry through canonical events
  (via `business_canonical_events`). These are the SDLC work-order event
  types (`work_order.created`, `work_order.started`, etc.) introduced in
  Phase 18.1 and enforced by `spool/writer.py`.
- **20 of 22 hook handlers** write telemetry directly to the hook-specific
  SQLite tables (`ds_hook_executions`, timing JSONL, etc.) or to local files.
  They bypass the canonical events spool entirely.

This is not a bug — it reflects the incremental migration path. The
architecture is correct; the implementation is partway there.

**Workstream closing the gap:** Phase 18.5 — Telemetry Spine Completion.
When 18.5 lands, all hook handlers will route through canonical events and
the claim in this document will be fully true.

### Hook dispatcher fail-open — claim vs. reality (CLOSED in 18.1.12)

The dispatcher was documented as fail-open (always exits 0). In reality,
`on-game-validate.py` called `sys.exit(2)`, which escaped the
`except Exception` wrapper in `dispatch_tracking.py` (SystemExit is a
BaseException, not an Exception subclass). This caused AI sessions to block
with exit code 2 when game files had validation issues.

**Fixed in Phase 18.1.12:**
- `on-game-validate.py` replaced `sys.exit(2)` with a stderr advisory
- `dispatch_tracking.py` and `runtime/dispatch/hooks.py` now catch
  `BaseException` instead of `Exception`
- Individual hook handlers (`on-pulse.py`, `on-stop-handoff.py`,
  `on-meta-review.py`) now have defensive `try/except` wrappers
- `tests/unit/runtime/test_dispatcher_systemexit.py` verifies the guarantee

This is the canonical example of architectural-claim-vs-reality drift. The
fix is in the code; this note exists so future readers know when and why it
happened.
