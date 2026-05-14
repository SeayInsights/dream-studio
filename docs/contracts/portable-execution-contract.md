# Portable Execution Contract

Phase: 11Y - Portable Primitive Contracts

Portable execution is the process of rendering Dream Studio primitives into target runtimes while preserving local authority boundaries.

## Canonical Primitive Definition

The canonical primitives are:

- skills
- workflows
- hooks
- agents

Their contracts define identity, inputs, outputs, authority, state access, validation, privacy, governance, and rendering expectations. Target-specific files are renderings of those primitives, not the canonical primitive definitions.

## Target-Specific Rendering

Rendering may adapt syntax, packaging, and available tools for a target. It must preserve:

- primitive identity;
- allowed and forbidden actions;
- approval requirements;
- state access limits;
- event/telemetry expectations;
- privacy/export classifications;
- validation requirements;
- local-first authority boundaries.

## Target Expectations

| Target | Rule |
| --- | --- |
| Claude rendering | May use Claude skill, hook, and sub-agent formats. Claude is a rendering target, not authority. |
| Codex rendering | May use repository instructions, local tools, and delegated agent prompts. Codex is a rendering target, not authority. |
| ChatGPT rendering | May use project instructions, custom tool policy, or prompt blocks. ChatGPT is a rendering target, not authority. |
| Cursor rendering | May use editor rules and project context files. Cursor is a rendering target, not authority. |
| MCP/local model rendering | May expose explicit tools or prompts with bounded state access. MCP servers and local models are renderings or tools, not authority. |
| Docker validation/sandbox rendering | May run isolated validation or sandboxed tool checks. Docker is optional infrastructure, not authority. |

## Adapter Boundaries

Adapters translate primitive definitions to target formats and translate target outputs back into Dream Studio-compatible evidence. Adapters must not own canonical state, require provider SDKs in authority paths, or make target metadata architecture truth.

## Governance/Privacy Boundaries

Portable rendering must preserve:

- non-exportable local state restrictions;
- redaction/aggregate export classifications;
- operator approval points;
- backup and restore warnings;
- scanner output as evidence only;
- local-only client/org tooling classifications.

## Event And Telemetry Expectations

Rendered primitives may emit telemetry or events only through approved Dream Studio owners. Telemetry describes execution. It does not replace orchestration truth. Target runtime logs are evidence, not canonical replay state.

## Prohibitions

Portable rendering must not:

- mutate the real local runtime DB during validation;
- restore, downgrade, repair, or migrate local state without explicit operator intent;
- mount native runtime state into Docker by default;
- move authority into dashboards, projections, telemetry, adapters, hooks, skills, workflows, agents, Docker, MCP servers, local models, providers, cloud services, or org/global layers;
- change canonical skill identifiers;
- recreate the retired hook library path.

## Validation Expectations

Tests should verify:

- all primitive contracts exist;
- render targets are named as non-authoritative;
- Docker remains optional and isolated;
- adapters remain replaceable edge renderers;
- active skill/workflow instructions do not point at retired helper paths;
- broad validation remains hash-guard clean.
