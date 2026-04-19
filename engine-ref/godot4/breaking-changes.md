# Godot 4 Breaking Changes

Changes that will cause errors if you use the old API. Sorted by severity.
Each entry tagged with verification status — see VERSION.md for tag definitions.

## HIGH — Will not compile / immediate crash

### TileMap → TileMapLayer (4.3) `[VERIFIED]`
- **Old:** `TileMap` node with multiple layers via `layer` parameter
- **New:** `TileMapLayer` node — one node per layer, compose in scene tree
- **Migration:** Replace `$TileMap.set_cell(layer, coords, source, atlas)` with `$TileMapLayer.set_cell(coords, source, atlas)`
- **Why it breaks:** `TileMap` class is deprecated and emits warnings. `set_cell()` signature changed (no layer parameter on TileMapLayer).
- **Source:** Godot 4.3 release notes, TileMap deprecation notice

### Tween is no longer a Node (4.0+) `[VERIFIED]`
- **Old (3.x):** `var tween = Tween.new(); add_child(tween)`
- **New:** `var tween = create_tween()` — returns a RefCounted, not a Node
- **Why it breaks:** `add_child(tween)` will error. Tweens auto-bind to the calling node.
- **Source:** Godot 4.0 migration guide

### @export instead of export keyword (4.0+) `[VERIFIED]`
- **Old (3.x):** `export var speed = 10`
- **New:** `@export var speed: float = 10.0`
- **Why it breaks:** Parser error on old syntax.
- **Source:** Godot 4.0 GDScript migration

### Signal syntax (4.0+) `[VERIFIED]`
- **Old (3.x):** `connect("signal_name", target, "method_name")`
- **New:** `signal_name.connect(target.method_name)` or `signal_name.connect(callable)`
- **Why it breaks:** Old string-based connect is removed.
- **Source:** Godot 4.0 migration guide

### instance() → instantiate() (4.0+) `[VERIFIED]`
- **Old (3.x):** `var node = scene.instance()`
- **New:** `var node = scene.instantiate()`
- **Why it breaks:** `instance()` method removed from PackedScene.
- **Source:** Godot 4.0 API diff

### change_scene() → change_scene_to_file() (4.0+) `[VERIFIED]`
- **Old (3.x):** `get_tree().change_scene("res://scene.tscn")`
- **New:** `get_tree().change_scene_to_file("res://scene.tscn")`
- **Why it breaks:** Method renamed, old name removed.
- **Source:** Godot 4.0 API diff

## MEDIUM — Subtle bugs or deprecation warnings

### NavigationAgent path_desired_distance (4.1+) `[HIGH-CONFIDENCE]`
- **Old:** `target_desired_distance` was the only distance check
- **New:** `path_desired_distance` (for path following) and `target_desired_distance` (for final target) are separate
- **Why it matters:** Using only `target_desired_distance` can cause agents to skip waypoints.
- **Source:** NavigationAgent class docs, 4.1 changelog

### MultiplayerSynchronizer visibility (4.2+) `[HIGH-CONFIDENCE]`
- **Old:** Manual RPC visibility management
- **New:** `MultiplayerSynchronizer` has built-in `visibility_for` and `public_visibility` properties
- **Why it matters:** Rolling your own when built-in exists is wasted work.
- **Source:** MultiplayerSynchronizer class docs

### PhysicsServer2D/3D direct state (4.0+) `[VERIFIED]`
- **Old (3.x):** `Physics2DDirectBodyState`
- **New:** `PhysicsDirectBodyState2D` (class name reordered)
- **Why it matters:** Wrong class name → error.
- **Source:** Godot 4.0 API diff

### File/Directory → FileAccess/DirAccess (4.0+) `[VERIFIED]`
- **Old (3.x):** `var file = File.new(); file.open(path, File.READ)`
- **New:** `var file = FileAccess.open(path, FileAccess.READ)` — static method, returns instance or null
- **Why it matters:** `File` class removed entirely. `FileAccess` uses static constructors.
- **Source:** Godot 4.0 migration guide

### Input.is_action_just_pressed in _physics_process `[HIGH-CONFIDENCE]`
- **Behavior:** `is_action_just_pressed` can return true for multiple frames if checked in `_physics_process` (which runs at fixed rate while input is polled at render rate).
- **Fix:** For single-shot actions (jump, fire), check in `_unhandled_input()` or `_input()`, or use `Input.is_action_just_pressed` only in `_process`.
- **Source:** Godot input handling docs, community-confirmed behavior

### yield() → await (4.0+) `[VERIFIED]`
- **Old (3.x):** `yield(get_tree().create_timer(1.0), "timeout")`
- **New:** `await get_tree().create_timer(1.0).timeout`
- **Why it matters:** `yield` keyword removed from GDScript.
- **Source:** Godot 4.0 GDScript migration

## LOW — New features not in training data

### Compositor effects (4.3+) `[UNVERIFIED]`
- `CompositorEffect` resource for custom post-processing
- Not available in training data — must read docs if needed
- **Risk:** API details may differ from what LLM suggests. Always verify.

### AnimationMixer (4.2+) `[HIGH-CONFIDENCE]`
- Base class for `AnimationPlayer` and `AnimationTree`
- `AnimationPlayer` now inherits from `AnimationMixer`
- Mostly backward-compatible but new methods available
- **Source:** 4.2 release notes

### GDScript typed arrays (4.0+, refined 4.2+) `[HIGH-CONFIDENCE]`
- `Array[int]`, `Array[Node2D]` — fully typed arrays
- `PackedStringArray` etc. still exist for performance
- Type errors caught at assignment, not just usage
- **Source:** GDScript reference docs

### Node3D.basis → Transform3D.basis access pattern (4.0+) `[UNVERIFIED]`
- Access patterns for transform manipulation may have subtle differences
- Verify `transform.basis` usage against current docs for your version
