# Execution Packet Contract

Phase: 16A - Work Order MVP Contract Foundation

An execution packet is a target-specific rendering of a Work Order for a human or tool runtime. The Work Order remains the canonical local instruction record. The packet is a derived rendering.

## Authority Principles

1. Work Order definition is canonical for Phase 16 local planning.
2. Execution packets are target-specific renderings.
3. Renderers must not execute packets.
4. Rendering must not mutate target repos or the native runtime DB.
5. Target tools are not authority. Codex, Claude, ChatGPT, Cursor, manual execution, Docker sandboxing, adapters, dashboards, telemetry, research, and enterprise analytics remain non-authoritative.

## Targets

Supported target labels:

- `codex`
- `claude`
- `chatgpt`
- `cursor`
- `manual`
- `docker_sandbox`

The `docker_sandbox` target is optional validation/sandbox infrastructure. It must not mount or mutate real local runtime state by default.

## Required Packet Fields

Every rendered packet must include:

- `packet_id`
- `target`
- `linked_work_order_id`
- `project_name`
- `target_path`
- `objective`
- `approval_mode`
- `risk_level`
- `scope.include`
- `scope.exclude`
- `allowed_skills`
- `allowed_agents`
- `workflow`
- `forbidden_actions`
- `validation_commands`
- `expected_outputs`
- `stop_conditions`
- `evidence_requirements`
- `privacy_export_classification`
- `rendered_at`
- `renderer`
- `render_only`

`render_only` must be true in Phase 16.

## Render-Only Semantics

Renderers may:

- transform a Work Order into target-specific instructions;
- include target-specific formatting;
- include validation expectations;
- include approval and stop-condition language;
- write the packet as a file-backed artifact in fake-home-safe storage.

Renderers must not:

- execute the packet;
- run shell commands from the packet;
- mutate target repos;
- write to the native runtime DB;
- emit real-runtime-DB events;
- run migrations;
- execute DreamySuite;
- grant broader authority than the Work Order.

## Target Mapping

| Target | Rendering rule |
| --- | --- |
| `codex` | Render as Codex task instructions with explicit tools, approvals, validation, and stop conditions. |
| `claude` | Render as Claude-compatible instructions with the same semantic boundaries. |
| `chatgpt` | Render as project/task prompt instructions with explicit non-authority limits. |
| `cursor` | Render as editor/task instructions without file mutation authority. |
| `manual` | Render as human checklist and evidence instructions. |
| `docker_sandbox` | Render as isolated validation instructions only. Docker remains optional and non-authoritative. |

## Validation Expectations

Static tests must prove:

- packet fields are documented;
- all targets are named;
- render-only semantics are explicit;
- renderers do not execute packets;
- target tools remain non-authoritative;
- DB/schema/event writes are prohibited by rendering.
