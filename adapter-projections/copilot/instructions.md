# GitHub Copilot Dream Studio Projection

adapter_id: copilot
adapter_type: copilot
project_id: dream-studio

Authority:
- Dream Studio SQLite authority is the source of truth.
- This adapter config is a generated projection.
- The adapter must not own canonical decisions, evidence, routes, or state.
- Config writes require a future explicit approval boundary.

Supported Context Packets:
- repo_instructions
- review

Supported Result Types:
- code_suggestion
- review
- evidence

Resume Rules:
- Use shared context packets and evidence refs.
- Normalize results back into Dream Studio records.
- Do not rely on private model memory as authority.
