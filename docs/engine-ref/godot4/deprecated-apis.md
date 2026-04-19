# Godot 4 Deprecated APIs

APIs to avoid. Use the replacement instead.
Each entry tagged with verification status — see VERSION.md for tag definitions.

## Deprecated Class/Method Table

| Deprecated | Replacement | Since | Status | Notes |
|-----------|-------------|-------|--------|-------|
| `TileMap` | `TileMapLayer` | 4.3 | `[VERIFIED]` | One node per layer |
| `Navigation2D` / `Navigation3D` | `NavigationServer2D` / `NavigationServer3D` | 4.0 | `[VERIFIED]` | Node wrappers removed |
| `KinematicBody2D` / `KinematicBody3D` | `CharacterBody2D` / `CharacterBody3D` | 4.0 | `[VERIFIED]` | Renamed |
| `Spatial` | `Node3D` | 4.0 | `[VERIFIED]` | Renamed |
| `PoolStringArray` etc. | `PackedStringArray` etc. | 4.0 | `[VERIFIED]` | Renamed |
| `RigidBody.mode` | `RigidBody2D.freeze` / `RigidBody3D.freeze` | 4.0 | `[VERIFIED]` | Different API |
| `Texture` | `Texture2D` | 4.0 | `[VERIFIED]` | Base class renamed |
| `StreamTexture` | `CompressedTexture2D` | 4.0 | `[VERIFIED]` | Renamed |
| `yield()` | `await` keyword | 4.0 | `[VERIFIED]` | Language change |
| `export` keyword | `@export` annotation | 4.0 | `[VERIFIED]` | Language change |
| `onready` keyword | `@onready` annotation | 4.0 | `[VERIFIED]` | Language change |
| `tool` keyword | `@tool` annotation | 4.0 | `[VERIFIED]` | Language change |
| `String.http_escape()` | `String.uri_encode()` | 4.0 | `[HIGH-CONFIDENCE]` | Renamed |
| `OS.get_ticks_msec()` | `Time.get_ticks_msec()` | 4.0 | `[VERIFIED]` | Moved to Time singleton |
| `File` / `Directory` | `FileAccess` / `DirAccess` | 4.0 | `[VERIFIED]` | Static methods, no new() |
| `JavaScript` singleton | `JavaScriptBridge` | 4.0 | `[HIGH-CONFIDENCE]` | Renamed |
| `VisualServer` | `RenderingServer` | 4.0 | `[VERIFIED]` | Renamed |
| `Physics2DServer` | `PhysicsServer2D` | 4.0 | `[VERIFIED]` | Name reordered |
| `instance()` | `instantiate()` | 4.0 | `[VERIFIED]` | PackedScene method renamed |
| `change_scene()` | `change_scene_to_file()` | 4.0 | `[VERIFIED]` | SceneTree method renamed |
| `connect("sig", obj, "method")` | `sig.connect(obj.method)` | 4.0 | `[VERIFIED]` | Callable-based signals |

## Common LLM Mistakes

These are patterns Claude or other LLMs frequently suggest from Godot 3.x training data.
**Every one of these will cause an error in Godot 4.x.**

| # | Wrong (from training data) | Correct (Godot 4.x) | Status |
|---|---------------------------|---------------------|--------|
| 1 | `var file = File.new(); file.open(...)` | `FileAccess.open(path, mode)` (static, returns instance or null) | `[VERIFIED]` |
| 2 | `var dir = Directory.new(); dir.open(...)` | `DirAccess.open(path)` (static) | `[VERIFIED]` |
| 3 | `connect("signal", self, "_method")` | `signal.connect(_method)` (Callable) | `[VERIFIED]` |
| 4 | `$TileMap.set_cell(0, pos, tile_id)` | `$TileMapLayer.set_cell(pos, source_id, atlas_coords)` (no layer param) | `[VERIFIED]` |
| 5 | `get_tree().change_scene("res://...")` | `get_tree().change_scene_to_file("res://...")` | `[VERIFIED]` |
| 6 | `scene.instance()` | `scene.instantiate()` | `[VERIFIED]` |
| 7 | `export(int) var x` | `@export var x: int` | `[VERIFIED]` |
| 8 | `yield(timer, "timeout")` | `await timer.timeout` | `[VERIFIED]` |
| 9 | `VisualServer.xxx` | `RenderingServer.xxx` | `[VERIFIED]` |
| 10 | `KinematicBody2D` / `move_and_slide(vel)` | `CharacterBody2D` / set `velocity` then `move_and_slide()` (no param) | `[VERIFIED]` |

## Verification Checklist

When reviewing code that uses Godot APIs:
1. Scan for every entry in the "Common LLM Mistakes" table
2. Check class names against the deprecated table
3. If an API is marked `[UNVERIFIED]`, warn the user explicitly
4. If project.godot version > 4.4, treat ALL entries as `[UNVERIFIED]` unless re-checked

## Official References
- Full 3.x→4.0 migration: https://docs.godotengine.org/en/stable/tutorials/migrating/upgrading_to_godot_4.html
- 4.0→4.1 breaking changes: https://docs.godotengine.org/en/stable/tutorials/migrating/upgrading_to_godot_4.1.html
- 4.2 release notes: https://godotengine.org/article/godot-4-2-arrives-in-style/
- 4.3 release notes: https://godotengine.org/article/godot-4-3-is-here/
