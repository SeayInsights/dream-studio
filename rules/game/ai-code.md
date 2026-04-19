---
description: Rules for NPC/enemy AI code — behavior trees, state machines, pathfinding
globs:
  - "**/scripts/ai/**"
  - "**/scripts/npc/**"
  - "**/scripts/enemies/**"
  - "**/scripts/behavior/**"
  - "**/scripts/mobs/**"
  - "**/ai/**/*.gd"
  - "**/npc/**/*.gd"
  - "**/enemies/**/*.gd"
  - "**/src/ai/**"
  - "**/src/npc/**"
  - "**/src/enemies/**"
---

# AI Code Rules

## Performance Budget
- AI logic runs on a timer (0.1–0.5s), NOT every `_physics_process` frame.
- Use `NavigationAgent3D`/`NavigationAgent2D` — don't roll custom pathfinding unless NavigationServer can't handle it.
- Limit active AI agents: if 50+ entities exist, use LOD — distant entities run simplified logic or sleep.

## Architecture
- State machines or behavior trees, not sprawling if/else chains.
- All tuning parameters (aggro range, patrol speed, attack cooldown) in data files or exported Resources — not hardcoded.
- AI scripts must be debuggable: expose current state as a property so it shows in the Inspector and can be logged.

## Debuggability
- Every AI agent should have a `get_debug_info() -> Dictionary` method returning current state, target, and last decision reason.
- Use `@tool` scripts or debug draw (draw_line, draw_sphere) for visualizing patrol paths, detection ranges, and navigation targets during development.

## Behavior Design
- Clear behavior hierarchy: idle → alert → engage → flee. Each state has entry/exit conditions.
- NPCs must handle edge cases: target dies mid-pursuit, navigation path becomes invalid, spawn point is blocked.
- Randomize timing slightly (±10%) to prevent synchronized AI behavior that looks robotic.
