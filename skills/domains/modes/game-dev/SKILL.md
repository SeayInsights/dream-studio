---
name: game-dev
model_tier: sonnet
description: Godot 4 consolidated patterns — 2D/3D player controllers, scene hierarchies, CSG blockouts, Blender→GLB pipeline with QA gates, two-tier automated/manual QA, and game design scaffolding. Trigger on any game build, review, QA, design, or asset-pipeline command.
pack: domains
chain_suggests: []
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
