# Godot 4 Best Practices

Patterns that differ from what LLMs may suggest based on older training data.
Each section tagged with verification status — see VERSION.md for tag definitions.

## Scene Architecture `[HIGH-CONFIDENCE]`
- **One script per node purpose.** Don't attach a 500-line script to a CharacterBody3D — split into components (movement, combat, inventory) as child nodes with their own scripts.
- **Use composition over inheritance.** Godot's node tree is already composition — lean into it. A `DamageReceiver` node is better than a `Damageable` base class.
- **Prefer scenes as prefabs.** Reusable entities are `PackedScene` resources, instantiated at runtime. Don't duplicate node subtrees manually.
- **Source:** Godot best practices docs, GDQuest tutorials

## GDScript Style `[VERIFIED]`
- **Type hints everywhere.** `func move(direction: Vector2) -> void:` — enables editor autocomplete and catches bugs at parse time.
- **Use `@export` with type hints** for Inspector-exposed properties: `@export var speed: float = 5.0`
- **Enums for states:** `enum State { IDLE, WALK, ATTACK }` — not string comparisons.
- **Static typing for arrays:** `var enemies: Array[Enemy] = []` — catches type errors at assignment.
- **Source:** GDScript style guide, 4.0+ docs

## Signals `[HIGH-CONFIDENCE]`
- **Emit from the node that owns the state change.** The player emits `health_changed`; the HUD connects to it. Never the reverse.
- **Prefer signal connections in `_ready()`** over the editor's signal panel — easier to track in version control.
- **Typed signals (4.2+):** `signal health_changed(new_value: int)` — self-documenting.
- **Source:** Godot signals tutorial, community best practices

## Resource Management `[VERIFIED]`
- **Use `preload()` for known assets** (compile-time loading): `const BULLET_SCENE = preload("res://scenes/bullet.tscn")`
- **Use `load()` only when the path is dynamic** (runtime loading).
- **Custom Resources** for data: extend `Resource` instead of storing game data in JSON when you need Inspector editing.
- **Source:** Resource docs, GDQuest resource tutorial

## Navigation `[HIGH-CONFIDENCE]`
- **NavigationAgent2D/3D** is the standard approach. Don't use raw `AStar2D` unless NavigationServer can't handle your case.
- **Bake navigation meshes** at edit time via `NavigationRegion2D/3D`. Runtime rebaking is expensive — avoid per-frame.
- **Set `path_desired_distance` AND `target_desired_distance`** on NavigationAgents — they serve different purposes (path following vs final arrival).
- **Source:** Navigation docs (significantly updated in 4.1-4.3)

## Multiplayer `[HIGH-CONFIDENCE]`
- **MultiplayerSpawner + MultiplayerSynchronizer** are the standard replication tools in 4.2+. Don't roll custom RPC replication.
- **Server-authoritative by default.** Client sends input RPCs, server validates and applies.
- **`@rpc` annotations** replace the old `remote`/`puppet`/`master` keywords entirely.
- **Test with `--headless`** flag for dedicated server builds.
- **Source:** High-level multiplayer docs, 4.2+ changelog

## Performance `[HIGH-CONFIDENCE]`
- **Use `_physics_process` only for physics.** Visual updates go in `_process` — don't tie animations to the physics tick rate.
- **`call_deferred()` for tree modifications.** Adding/removing nodes during a physics step can cause crashes.
- **Object pooling** for frequently spawned objects (bullets, particles). `queue_free()` + `instantiate()` every frame is expensive.
- **Autoload count matters.** Each autoload is a persistent node. Keep them under 10; prefer dependency injection for optional systems.
- **Source:** Performance docs, Godot profiler guide

## Export & Build `[HIGH-CONFIDENCE]`
- **Test exports early.** `godot --headless --export-release "preset" output` in CI.
- **Don't rely on editor-only features** (tool scripts, editor plugins) in runtime code.
- **Web exports:** avoid threads (`OS.get_thread_caller_id()` doesn't exist), large binary resources (pack into PCK), and file system access (use `user://` only).
- **Source:** Export docs, web platform limitations page

## Patterns LLMs Often Get Wrong `[VERIFIED]`

### move_and_slide() signature change
```gdscript
# WRONG (3.x pattern) — LLMs suggest this frequently
velocity = move_and_slide(velocity, Vector2.UP)

# CORRECT (4.x) — set velocity property, then call without args
velocity.y += gravity * delta
move_and_slide()  # uses self.velocity automatically
```

### FileAccess static pattern
```gdscript
# WRONG (3.x pattern)
var file = File.new()
file.open("user://save.json", File.WRITE)
file.store_string(data)
file.close()

# CORRECT (4.x) — static open, auto-closes on scope exit
var file = FileAccess.open("user://save.json", FileAccess.WRITE)
if file:
    file.store_string(data)
# No explicit close needed — closed when reference drops
```

### Typed signal connections
```gdscript
# WRONG (3.x string-based)
connect("health_changed", hud, "_on_health_changed")

# CORRECT (4.x Callable-based)
health_changed.connect(hud._on_health_changed)
# Or with lambda:
health_changed.connect(func(hp): hud.update_health(hp))
```
