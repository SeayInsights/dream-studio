---
description: Rules for UI code — HUD, menus, dialogs, inventory screens
globs:
  - "**/scripts/ui/**"
  - "**/scripts/gui/**"
  - "**/scripts/hud/**"
  - "**/scripts/menus/**"
  - "**/scripts/interface/**"
  - "**/scenes/ui/**"
  - "**/scenes/hud/**"
  - "**/scenes/menus/**"
  - "**/scenes/gui/**"
  - "**/ui/**/*.gd"
  - "**/hud/**/*.gd"
  - "**/src/ui/**"
  - "**/src/hud/**"
---

# UI Code Rules

## No Game State Ownership
- UI reads and displays — it never owns or mutates game state directly.
- Connect to signals from game systems. Never poll game state in `_process`.
- Button presses emit signals or call autoload methods — UI scripts don't contain gameplay logic.

## Localization-Ready
- All player-facing strings use `tr()` — no raw English strings in UI scripts.
- Design layouts to handle 40% text expansion (German, Portuguese) without overflow.
- Never split translatable strings across multiple `tr()` calls. Use format strings: `tr("DAMAGE_DEALT").format({"amount": dmg})`.

## Accessibility
- Minimum touch target: 44x44 logical pixels for any interactive element.
- Focusable controls must have a visible focus indicator.
- Support keyboard/gamepad navigation: set `focus_neighbor_*` properties.
- Color must not be the only indicator — pair with icons, text, or patterns.

## Architecture
- One scene per screen/panel. Compose via `CanvasLayer` stacking, not deep nesting.
- Theme resources for styling — never set fonts/colors inline on individual controls.
- Animate with Tween or AnimationPlayer, not manual property changes in `_process`.

## Performance
- Hide off-screen UI with `visible = false`, not transparency — invisible nodes skip rendering.
- Avoid `_process` in UI scripts. Use signals and `set_deferred` for state-driven updates.
