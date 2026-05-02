---
ds:
  pack: domains
  mode: game-dev
  mode_type: build
  inputs: [game_spec, scene_design, asset_requirements, mechanics]
  outputs: [implementation, scenes, scripts, tests]
  capabilities_required: [Read, Write, Edit, Grep, Bash, LSP]
  model_preference: sonnet
  estimated_duration: 1-4hrs
---

# Game Dev — Godot 4 Consolidated Patterns

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
Any game build, review, QA, design, or asset pipeline command.

## Architecture
- **Signal-driven**: emit upward, never call downward
- **Autoload singletons** for shared managers (ResourceLedger, SettlementManager, FactionManager, etc.)
- **game_state.gd** as single source of truth for serialization
- **godot-mcp** over shell-mcp. **blender-mcp** over shell-mcp.
- Structure: `scenes/ Â· scripts/ Â· assets/ Â· tests/ Â· design/`

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
