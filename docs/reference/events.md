# Dream Studio Events Reference

Complete catalog of all event types in the dual-canonical architecture.

**Primary source:** `canonical/events/types.py`  
**Routing registry:** `config/event_type_registry.py`  
**Taxonomy reference:** `docs/canonical/event_taxonomy_v1.json`  
**Total defined:** 97+ event types across 2 canonical tables

---

## Architecture Overview

Events flow through a dual-canonical spine:

```
spool.writer.write_event()
    → spool file (~/.dream-studio/events/spool/)
        → spool.ingestor.ingest()
            → business_canonical_events   (SDLC/operator events)
            → ai_canonical_events         (AI execution events)
```

**Routing is determined by** `routes_to` in the event type registry:
- `("business",)` — business_canonical_events only
- `("ai",)` — ai_canonical_events only
- `("business", "ai")` — both tables (paired events)
- `()` — raw_claude_code_events only (mechanical detail, Commitment 9)

**Projections** consume `business_canonical_events` to populate SDLC read-model tables (`business_work_orders`, `business_tasks`, etc.).

---

## Business / SDLC Events

Pure operator actions. Route to `business_canonical_events`. Drive all SDLC projections.

### Projects

| Event type | String value | Description |
|-----------|-------------|-------------|
| `PROJECT_CREATED` | `project.created` | New project registered |
| `PROJECT_DELETED` | `project.deleted` | Project deleted (cascade) |
| `PROJECT_ACTIVATED` | `project.activated` | Project set active (status → active) |
| `PROJECT_DEACTIVATED` | `project.deactivated` | Project deactivated (status → paused) |
| `PROJECT_REGISTERED` | `project.registered` | _(Deprecated — no callers)_ |
| `PROJECT_UPDATED` | `project.updated` | _(Deprecated — no callers)_ |

### Milestones

| Event type | String value | Description |
|-----------|-------------|-------------|
| `MILESTONE_CREATED` | `milestone.created` | New milestone created |
| `MILESTONE_DELETED` | `milestone.deleted` | Milestone deleted |
| `MILESTONE_COMPLETED` | `milestone.completed` | Milestone closed after verification |

### Work Orders

| Event type | String value | Description |
|-----------|-------------|-------------|
| `WORK_ORDER_CREATED` | `work_order.created` | New work order created |
| `WORK_ORDER_DELETED` | `work_order.deleted` | Work order deleted (cascade) |
| `WORK_ORDER_STARTED` | `work_order.started` | Work order entered `in_progress` |
| `WORK_ORDER_CLOSED` | `work_order.closed` | Work order closed (gates passed) |
| `WORK_ORDER_BLOCKED` | `work_order.blocked` | Work order blocked with reason |
| `WORK_ORDER_UNBLOCKED` | `work_order.unblocked` | Work order unblocked → `in_progress` _(registry-only)_ |

### Tasks

| Event type | String value | Description |
|-----------|-------------|-------------|
| `TASK_CREATED` | `task.created` | New task added to work order |
| `TASK_STARTED` | `task.started` | Work begun on task _(no call site yet — registered for TA2)_ |
| `TASK_DELETED` | `task.deleted` | Task deleted (cascade) |
| `TASK_COMPLETED` | `task.completed` | Task marked complete |

### Design Briefs

| Event type | String value | Description |
|-----------|-------------|-------------|
| `DESIGN_BRIEF_CREATED` | `design_brief.created` | Draft design brief created |
| `DESIGN_BRIEF_UPDATED` | `design_brief.updated` | Field updated on draft brief |
| `DESIGN_BRIEF_LOCKED` | `design_brief.locked` | Brief locked (human approval gate passed) |
| `DESIGN_BRIEF_DELETED` | `design_brief.deleted` | Brief deleted (cascade) |

### Documents & Preflight

| Event type | String value | Description |
|-----------|-------------|-------------|
| `DOCUMENT_CREATED` | `document.created` | Document created in document store |
| `DOCUMENT_UPDATED` | `document.updated` | Document updated |
| `DOCUMENT_ARCHIVED` | `document.archived` | Document archived |
| `PREFLIGHT_CREATED` | `preflight.created` | Preflight finding recorded on work order _(registry-only)_ |
| `PREFLIGHT_STATUS_CHANGED` | `preflight.status_changed` | Preflight finding status updated _(registry-only)_ |

### Gates & Skills

| Event type | String value | Description |
|-----------|-------------|-------------|
| `GATE_BYPASSED` | `gate.bypassed` | Gate check bypassed with `--force` |
| `GATE_PRE_PUSH_FAILED` | `gate.pre_push.failed` | Pre-push gate failed |
| `SKILL_INVOKED` | `skill.invoked` | Dream Studio skill invoked via CLI |

---

## AI Execution Events

AI execution facts. Route to `ai_canonical_events`.

### Session & Prompt Lifecycle

| Event type | String value | Description |
|-----------|-------------|-------------|
| `SESSION_LIFECYCLE_STARTED` | `session.lifecycle.started` | Host AI session begun; `session_id` established |
| `SESSION_LIFECYCLE_ENDED` | `session.lifecycle.ended` | Host AI session ended normally |
| `PROMPT_LIFECYCLE_SUBMITTED` | `prompt.lifecycle.submitted` | User submitted a prompt (raw text redacted) |
| `PROMPT_LIFECYCLE_VALIDATED` | `prompt.lifecycle.validated` | Prompt passed Dream Studio validation gates |

### Token & Context

| Event type | String value | Description |
|-----------|-------------|-------------|
| `TOKEN_CONSUMPTION_RECORDED` | `token.consumption.recorded` | Token count for a session turn |
| `TOKEN_CONSUMED` | `token.consumed` | Per-tool token consumption with full SDLC attribution (TA3) |
| `CONTEXT_THRESHOLD_CROSSED` | `context.threshold.crossed` | Context window crossed configured threshold |

### Skill Execution

| Event type | String value | Description |
|-----------|-------------|-------------|
| `SKILL_LIFECYCLE_LOADED` | `skill.lifecycle.loaded` | DS skill activated for this session |
| `SKILL_LIFECYCLE_COMPLETED` | `skill.lifecycle.completed` | DS skill primary action completed |
| `SKILL_EXECUTED` | `skill.executed` | Skill execution telemetry with status and duration |
| `SKILL_BUDGET_EXCEEDED` | `skill.budget_exceeded` | Skill exceeded configured token/context budget |

### Workflow & Execution

| Event type | String value | Description |
|-----------|-------------|-------------|
| `WORKFLOW_PROGRESS_UPDATED` | `workflow.progress.updated` | Workflow milestone progressed |
| `WORKFLOW_NODE_COMPLETED` | `workflow.node.completed` | Workflow DAG node completed |
| `WORKFLOW_LEARNED` | `workflow.learned` | Workflow pattern learned from execution history |
| `WORKFLOW_COMPLETED` | `workflow.completed` | Workflow run completed |
| `EXECUTION_STARTED` | `execution.started` | Execution run started |
| `EXECUTION_COMPLETED` | `execution.completed` | Execution run completed |
| `EXECUTION_FAILED` | `execution.failed` | Execution run failed |
| `EXECUTION_COMPLETE` | `execution.complete` | GitHub PR execution completed |
| `TESTS_EXECUTED` | `execution.tests_executed` | Test suite executed and results collected |

### Wave Orchestration

| Event type | String value | Description |
|-----------|-------------|-------------|
| `WAVE_STARTED` | `wave.started` | Execution wave started |
| `WAVE_COMPLETED` | `wave.completed` | Execution wave completed |
| `WAVE_FAILED` | `wave.failed` | Execution wave failed |
| `WAVE_TASK_UPDATED` | `wave.task_updated` | Wave task status updated |

### Research Pipeline

| Event type | String value | Description |
|-----------|-------------|-------------|
| `RESEARCH_VALIDATED` | `research.validated` | Research result validated by session outcome |
| `RESEARCH_COMPLETED` | `research.completed` | Research query completed and result stored |
| `RESEARCH_CACHE_STORED` | `research.cache_stored` | Research result stored in cache |
| `RESEARCH_CACHE_CLEARED` | `research.cache_cleared` | Research cache entry cleared for topic |

### Analysis Pipeline

| Event type | String value | Description |
|-----------|-------------|-------------|
| `ANALYSIS_STARTED` | `analysis.started` | Project analysis pipeline started |
| `ANALYSIS_DISCOVERY_COMPLETED` | `analysis.discovery_completed` | Discovery phase completed |
| `ANALYSIS_RESEARCH_COMPLETED` | `analysis.research_completed` | Research phase completed |
| `ANALYSIS_AUDIT_COMPLETED` | `analysis.audit_completed` | Audit phase completed |
| `ANALYSIS_BUG_ANALYSIS_COMPLETED` | `analysis.bug_analysis_completed` | Bug analysis phase completed |
| `ANALYSIS_SYNTHESIS_COMPLETED` | `analysis.synthesis_completed` | Synthesis phase completed |
| `ANALYSIS_COMPLETED` | `analysis.completed` | Full analysis pipeline completed |
| `ANALYSIS_FAILED` | `analysis.failed` | Analysis pipeline failed |

### Repository Analysis

| Event type | String value | Description |
|-----------|-------------|-------------|
| `REPO_ANALYZED` | `repo.analyzed` | External repository analysis completed |
| `REPO_EXTRACTION_STORED` | `repo.extraction.stored` | Repository pattern extraction stored |

### Audit & Quality

| Event type | String value | Description |
|-----------|-------------|-------------|
| `AUDIT_VIOLATIONS_CLEARED` | `audit.violations_cleared` | Audit violations cleared before new scan |
| `AUDIT_VIOLATION_FOUND` | `audit.violation_found` | Architecture violation detected |
| `AUDIT_IMPROVEMENTS_CLEARED` | `audit.improvements_cleared` | Audit improvements cleared before new scan |
| `AUDIT_IMPROVEMENT_FOUND` | `audit.improvement_found` | Improvement opportunity detected |
| `QUALITY_SCORE_RECORDED` | `quality.score.recorded` | Quality score computed for an artifact |

### AI Governance

| Event type | String value | Description |
|-----------|-------------|-------------|
| `GUARDRAIL_DECISION` | `guardrail.decision` | Guardrail policy decision logged for compliance audit |
| `INTEGRATION_HEALTH_CHANGED` | `integration.health.changed` | Integration health state transition |

---

## Paired Events

Route to **both** `business_canonical_events` and `ai_canonical_events`. AI-driven work that produces business artifacts.

| Event type | String value | Description |
|-----------|-------------|-------------|
| `SECURITY_FINDING_RECORDED` | `security.finding.recorded` | Security finding from SARIF scan recorded |
| `SECURITY_FINDING_LOGGED` | `security.finding.logged` | Security finding written to canonical log |
| `SECURITY_FINDING_RESOLVED` | `security.finding.resolved` | Security finding marked resolved |
| `SECURITY_SCAN_COMPLETED` | `security.scan.completed` | Security scan ran against a file or diff |
| `AUDIT_VIOLATION_FOUND` | `audit.violation_found` | Architecture violation detected _(see Audit & Quality above)_ |
| `AUDIT_IMPROVEMENT_FOUND` | `audit.improvement_found` | Improvement opportunity detected _(see Audit & Quality above)_ |
| `QUALITY_SCORE_RECORDED` | `quality.score.recorded` | Quality score computed _(see Audit & Quality above)_ |
| `HOOK_FINDING_CREATED` | `system.hook.finding.created` | Hook analysis finding created |

---

## System / Hook-Emitted Events

Emitted by hooks and runtime infrastructure. Route to `ai_canonical_events`.

| Event type | String value | Description |
|-----------|-------------|-------------|
| `SESSION_RECORDED` | `system.session.recorded` | Session record inserted to DB (distinct from lifecycle hook) |
| `SESSION_CLOSED` | `system.session.closed` | Session record closed with outcome and token counts |
| `HANDOFF_CREATED` | `system.handoff.created` | Session handoff document created |
| `HOOK_EXECUTION_LOGGED` | `system.hook.execution.logged` | Hook execution logged with status, duration, exit code |
| `HOOK_FINDING_CREATED` | `system.hook.finding.created` | Hook analysis finding created _(also paired)_ |
| `LESSON_CAPTURED` | `system.lesson.captured` | Operational lesson learned |
| `APPROACH_CAPTURED` | `system.approach.captured` | Skill approach pattern captured for reuse |
| `PROJECT_STATS_UPDATED` | `system.project_stats.updated` | Project session or token stats updated |
| `TASK_STATUS_UPDATED` | `system.task_status.updated` | PRD task status updated |
| `RISK_SCORE_COMPUTED` | `risk.score.computed` | Risk score computed for a security event |

### Security (AI-only)

| Event type | String value | Description |
|-----------|-------------|-------------|
| `SECURITY_SCAN_STARTED` | `security.scan.started` | Security scan initiated _(registry-only)_ |
| `SECURITY_SCAN_FAILED` | `security.scan.failed` | Security scan failed _(registry-only)_ |

---

## Raw-Only Events

Route to `raw_claude_code_events` only. Mechanical detail — not projected. (Commitment 9)

| Event type | String value | Description |
|-----------|-------------|-------------|
| `TOOL_EXECUTION_STARTED` | `tool.execution.started` | Tool call began (tool name + args shape; no raw output) |
| `TOOL_EXECUTION_COMPLETED` | `tool.execution.completed` | Tool call completed (result shape; no raw output) |
| `HOOK_TOOL_ACTIVITY` | `hook.tool_activity` | Legacy per-tool hook activity event (pre-18.1.2) |

---

## Diagnostic Events

| Event type | String value | Description |
|-----------|-------------|-------------|
| `EVENT_VALIDATION_FAILED` | `event.validation.failed` | Spool event failed schema validation (operational diagnostic) |

---

## Event Payload Structure

All canonical events share this envelope:

```json
{
  "event_id": "<UUID>",
  "event_type": "<type string>",
  "event_timestamp": "<ISO 8601 UTC>",
  "schema_version": 1,
  "trace": {
    "domain": "business|ai",
    "project_id": "<UUID or null>",
    "milestone_id": "<UUID or null>",
    "work_order_id": "<UUID or null>",
    "task_id": "<UUID or null>"
  },
  "payload": { /* event-specific data */ },
  "correlation_id": "<UUID or null>",
  "severity": "info|warn|error"
}
```

---

## Counts by Category

| Category | Count |
|----------|-------|
| Business/SDLC (business-only routing) | 31 |
| AI execution (ai-only routing) | 50+ |
| Paired (business + ai) | 9 |
| Raw-only | 3 |
| Diagnostic | 1 |
| Deprecated | 2 |
| **Total defined** | **97+** |

---

## Cross-references

- Schema tables that consume these events: [`docs/reference/schema.md`](schema.md) — `business_canonical_events`, `ai_canonical_events`, `raw_claude_code_events`
- Hooks that emit events: [`docs/reference/hooks.md`](hooks.md)
- Projection engine: `core/projections/runner.py` — consumes business events → read-model tables
