# Codex Dream Studio Projection

adapter_id: codex
adapter_type: codex
project_id: dream-studio

Authority:
- Dream Studio SQLite authority is the source of truth.
- This adapter config is a generated projection.
- The adapter must not own canonical decisions, evidence, routes, or state.
- Config writes require a future explicit approval boundary.

Supported Context Packets:
- resume
- work_order_execution
- review
- release_gate

Supported Result Types:
- decision
- code_change
- validation
- evidence
- risk

Resume Rules:
- Use shared context packets and evidence refs.
- Normalize results back into Dream Studio records.
- Do not rely on private model memory as authority.
