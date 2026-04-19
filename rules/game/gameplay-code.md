---
description: Rules for gameplay code — movement, combat, abilities, game systems, mechanics
globs:
  # Standard Godot layout
  - "**/scripts/gameplay/**"
  - "**/scripts/systems/**"
  - "**/scripts/mechanics/**"
  - "**/scripts/combat/**"
  - "**/scripts/movement/**"
  - "**/scripts/abilities/**"
  # Alternative flat layout
  - "**/gameplay/**/*.gd"
  - "**/systems/**/*.gd"
  - "**/mechanics/**/*.gd"
  # src/ prefix variant
  - "**/src/gameplay/**"
  - "**/src/systems/**"
  - "**/src/mechanics/**"
---

# Gameplay Code Rules

## Data-Driven Values
- All numeric constants (speed, damage, cooldowns, costs, thresholds) MUST come from `balance.json` or a Resource — never hardcode.
- Load via: `var config := preload("res://data/balance.json")` or export vars on a Resource.
- If a magic number appears in gameplay code, extract it before committing.

## Physics
- Always multiply movement/forces by `delta` — frame-rate-independent or it ships broken.
- Use `move_and_slide()` (CharacterBody2D/3D), never `move_and_collide()` unless you need the collision response object.

## Architecture
- Gameplay scripts emit signals upward — never call parent/sibling methods directly.
- One script per mechanic. A script that handles both combat AND inventory is two scripts.
- State machines: use an enum + `match` block, not boolean flags. `is_attacking && !is_dodging && is_grounded` is a bug waiting to happen.

## Dependencies
- Gameplay code must NOT reference UI nodes or UI scripts. Emit a signal; let UI listen.
- Gameplay code must NOT reference engine internals (rendering, audio buses). Use autoload managers as intermediaries.

## Testing
- Every mechanic needs at least one automated test: input → expected state change.
- Test edge cases: zero values, max values, simultaneous inputs.
