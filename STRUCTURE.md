# Dream Studio Project Structure

Dream Studio is a local-first AI orchestration and operational intelligence platform. This file is a public map of the source tree, not a runtime-state manifest.

## Top-Level Layout

```text
dream-studio/
  .claude/                         optional Claude Code adapter projection
  .claude-plugin/                  optional Claude Code adapter metadata
  .github/                         GitHub workflows and templates
  agents/                          public specialist-agent templates
  core/                            authority, telemetry, release, work-order, and shared-intelligence code
  docs/                            public product and architecture documentation
  hooks/                           hook registration and dispatch surface
  interfaces/                      CLI and adapter command surfaces
  packs/                           pack-level context, agents, and templates
  projections/                     API and dashboard projections
  skills/                          repeatable skill instructions and registries
  tests/                           unit, integration, runtime, and validation tests
  workflows/                       YAML workflow definitions
```

## Runtime State Boundary

The user-local runtime directory is not part of the source tree and must not be committed:

```text
~/.dream-studio/
  state/studio.db
  meta/
  backups/
```

Generated Work Orders, handoffs, local audit trails, raw telemetry, backups, cleanup records, cutover evidence, and private operator decisions belong in local state unless separately sanitized and approved for publication.

## Adapter Boundary

The `.claude/` and `.claude-plugin/` directories describe one adapter surface. Dream Studio also supports or plans adapter projections for Codex, Cursor, Copilot, ChatGPT, MCP systems, shell tools, local models, and future tools. No adapter is the source of truth.
