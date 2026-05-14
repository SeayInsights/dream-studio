# Dream Studio Stack And Runtime

Status: draft_generated
Authority role: stack and runtime boundary documentation

Status labels: current, planned, deferred, optional, unknown.

| Surface | Status | Authority and boundary |
| --- | --- | --- |
| Python runtime | current | Local execution language for Dream Studio control-plane modules and tests. |
| CLI/scripts | current | Local entrypoints and helpers; must preserve approval boundaries. |
| Hooks | current | Lifecycle automation; treat as potentially mutating around git/recovery. |
| Agents | planned | Provider-agnostic routed workers for plan/build/review/verify/recover. |
| Skills | current | Local repeatable workflows selected by milestone and risk context. |
| Workflows | current/planned | Ordered evidence-producing procedures; should be state-driven. |
| Sessions | planned | Bounded execution context with resumable state and evidence refs. |
| Memory/context | planned | Scoped continuity packets, not hidden authority. |
| SQLite/local database authority | current/planned | Local structured authority where safe; mutation requires explicit approval. |
| File-backed meta artifacts | current | Evidence, rendered views, reports, handoffs, approvals, imports, exports. |
| Artifact index | planned | Canonical map from artifacts to roles, lifecycle, authority, and refs. |
| Handoff renderer | current/planned | Renders prompts from state and validates before ready. |
| Milestone planner/classifier | current/planned | Classifies next action and suppresses low-risk micro-prompts. |
| Policy/stop-gate engine | planned | Evaluates HITL, research, database, artifact, and risk gates. |
| Dashboard/projection layer | planned | Derived views from structured state; not primary truth. |
| FastAPI/dashboard surfaces | optional/deferred | Runtime surface only when explicitly scoped by a later milestone. |
| Git integration | current | Status, diff, staged diff, commit/push evidence under explicit Work Orders. |
| MCP/tool adapters | optional | Adapter boundary; must not change local-first authority. |
| Browser/runtime tools | optional | Requires explicit approval when runtime/browser validation is in scope. |
| Claude Code adapter | optional | Tool adapter, not product identity. |
| Codex adapter | optional | Tool adapter, not product identity. |
| Cursor/Copilot adapters | deferred | Future agent adapters behind the same authority policy. |
| TORII adapter | deferred | Paused external target and future cockpit/adapter surface only. |
| Cloud/org/global surfaces | deferred | No expansion without future PRD/stage-gate approval. |

## Runtime Principles

- Local-first state and evidence by default.
- Standard library and existing project modules preferred for policy logic.
- Dependency changes require explicit operator approval.
- Runtime SQLite mutation, migrations, DDL/DML, and dashboard/API/browser
  validation require explicit milestone approval.
- Reports, handoffs, and dashboards are rendered views from structured state.
