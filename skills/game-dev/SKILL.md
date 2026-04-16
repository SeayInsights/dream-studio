---
name: game-dev
description: Godot 4 consolidated patterns — 2D/3D player controllers, scene hierarchies, CSG blockouts, Blender→GLB pipeline with QA gates, two-tier automated/manual QA, and game design scaffolding. Trigger on any game build, review, QA, design, or asset-pipeline command.
---

# Game Dev — Godot 4 Consolidated Patterns

## Trigger
Any game build, review, QA, design, or asset pipeline command.

## Architecture
- **Signal-driven**: emit upward, never call downward
- **Autoload singletons** for shared managers (ResourceLedger, SettlementManager, FactionManager, etc.)
- **game_state.gd** as single source of truth for serialization
- **godot-mcp** over shell-mcp. **blender-mcp** over shell-mcp.
- Structure: `scenes/ · scripts/ · assets/ · tests/ · design/`

---

## 2D Patterns

### Player (CharacterBody2D)
```gdscript
extends CharacterBody2D
const SPEED = 200.0
const JUMP_VELOCITY = -400.0
const COYOTE_TIME = 0.1
var gravity = ProjectSettings.get_setting("physics/2d/default_gravity")
var coyote_timer := 0.0

func _physics_process(delta):
    if not is_on_floor(): velocity.y += gravity * delta; coyote_timer -= delta
    else: coyote_timer = COYOTE_TIME
    var dir = Input.get_axis("move_left", "move_right")
    velocity.x = dir * SPEED if dir else move_toward(velocity.x, 0, SPEED)
    move_and_slide()
```

### 8-direction movement (Top-Down)
```gdscript
var dir := Vector2(
    Input.get_axis("move_left", "move_right"),
    Input.get_axis("move_up", "move_down")
).normalized()
velocity = dir * SPEED
move_and_slide()
```

### A* grid pathfinding
```gdscript
var astar := AStarGrid2D.new()
func setup_grid(w: int, h: int, cell: Vector2) -> void:
    astar.region = Rect2i(0, 0, w, h); astar.cell_size = cell; astar.update()
func get_path(from: Vector2i, to: Vector2i) -> Array[Vector2i]:
    return astar.get_id_path(from, to)
```

### Top-Down RPG conventions
- CharacterBody2D + move_and_slide()
- Collision layers: world=1, player=2, enemy=3, interactable=4
- TileMapLayer (y_sort_enabled=true) + NavigationRegion2D
- Area2D on interactables, body_entered/exited for proximity
- DialogueManager autoload for conversation state

### Strategy/Sim conventions
- Core loop: what does the player do every 30 seconds?
- Each unit/faction: one clear strength, one exploitable weakness
- Autoloads: ResourceLedger, SettlementManager, FactionManager, ThreatManager
- ENet via MultiplayerAPI (server authority for state, RPCs for input only)
- balance.json for all numeric constants — never hardcode

---

## 3D Patterns

### Player (CharacterBody3D)
```gdscript
extends CharacterBody3D
const SPEED = 5.0
const JUMP_VELOCITY = 4.5
var gravity = ProjectSettings.get_setting("physics/3d/default_gravity")

func _physics_process(delta):
    if not is_on_floor(): velocity.y -= gravity * delta
    if Input.is_action_just_pressed("jump") and is_on_floor(): velocity.y = JUMP_VELOCITY
    var dir = (transform.basis * Vector3(
        Input.get_axis("move_left", "move_right"), 0,
        Input.get_axis("move_forward", "move_back"))).normalized()
    velocity.x = dir.x * SPEED if dir else move_toward(velocity.x, 0, SPEED)
    velocity.z = dir.z * SPEED if dir else move_toward(velocity.z, 0, SPEED)
    move_and_slide()
```

### NavigationAgent3D
```gdscript
var nav_agent := NavigationAgent3D.new()
func _physics_process(delta):
    if nav_agent.is_navigation_finished(): return
    velocity = (nav_agent.get_next_path_position() - global_position).normalized() * SPEED
    move_and_slide()
```

### Scene hierarchy — Exterior
```
World3D (Node3D)
  Environment (WorldEnvironment)     ← ProceduralSkyMaterial, SDFGI on, Glow 0.05
  Sun (DirectionalLight3D)           ← Energy 1.5, PCSS shadow, Angular 0.5
  Level (Node3D)
    Terrain / Props / Architecture
  Player (CharacterBody3D)
  Camera3D
  NavigationRegion3D
```

### Scene hierarchy — Interior
```
World3D (Node3D)
  Environment (WorldEnvironment)     ← Solid color sky, SDFGI off, ReflectionProbe
  AmbientLight (OmniLight3D)         ← Low energy fill
  Room_[name] (Node3D)
    Walls / Floor / Ceiling / Props / Lights
  Player (CharacterBody3D)
  Camera3D
  NavigationRegion3D
```

### CSG blockout rules
- CSGBox3D for walls, floors, platforms, ceilings
- CSGCylinder3D for pillars, trees (placeholder)
- Label: `CSG_[type]_[descriptor]` e.g. `CSG_wall_north`
- All CSG must be replaced with MeshInstance3D + StaticBody3D before export
- Never scaffold: AnimationTree, SDFGI config, custom shaders, final lighting

---

## Blender → Godot Asset Pipeline

### Export settings
```python
bpy.ops.export_scene.gltf(
    filepath=output_path, export_format="GLB",
    export_apply=True, export_animations=True,
    export_skins=True, export_yup=True,
    export_cameras=False, export_lights=False
)
```

### Pipeline QA checklist (run in order)
1. **Mesh** (blender-mcp: validate_mesh) — non-manifold edges, loose verts, zero-area faces
2. **Naming** (blender-mcp: list_objects) — `[type]_[name]_[variant]` with valid prefix: chr\_ prop\_ arch\_ ter\_ veh\_ vfx\_ col\_ lod1\_ lod2\_
3. **Transforms** — scale (1,1,1), rotation (0,0,0) in object mode
4. **Collision** — every non-VFX mesh needs col\_ or UCX\_ collision object
5. **Materials** — no packed textures, PBR Metallic/Roughness workflow
6. **Animations** — `[character]_[state]_[variant]` naming
7. **Y-up** — confirm export_yup=True

FAIL any Critical item (naming, transforms, collision, mesh). Material/animation warnings can pass with noted exceptions.

---

## QA

### Tier 1 — Automated (after every build)
1. `godot-mcp: check_project` — broken refs, missing dirs
2. `godot-mcp: lint_scripts` — gdlint across scripts/
3. `godot-mcp: export_build` — verify each export preset exits cleanly
4. `godot-mcp: run_scene res://tests/run_all_tests.tscn` — parse QA stdout

QA stdout events: PLAYER_SPAWNED, NET_MODE, NET_PEER_CONNECTED, RESOURCE_DEPLETED, HUD_UPDATED, TEST_PASS, TEST_FAIL, SUITE_COMPLETE.
Exit code 0 + no TEST_FAIL = PASS. Otherwise FAIL → open GitHub issue.

### Tier 2 — Manual (multiplayer, UI, visual, input)
Solo mode: host enters world, player spawns correctly, movement works, interaction (F key) works.
Multiplayer: two instances, both visible, independently controllable, state syncs, disconnect handles cleanly.
Build: web + Windows export complete and launch.

---

## Game Design

### GDD authoring
GDD goes in `design/gdd.md` in the game repo. Sections: vision, core loop, mechanics, progression, art direction, audio direction, tech requirements.

### Mechanic design
- Define the mechanic in terms of player verbs (what the player does)
- Specify inputs, outputs, and feedback loops
- Balance: track production/consumption/storage separately
- Threat escalation: discrete tiers with clear visual feedback

### Level design
- Layout doc in `design/levels/` with: room dimensions (meters), grid scale, adjacency, player start, navigation notes
- Block out with CSG first, test navigation, then replace with final art
- Required layout doc fields before scaffolding: dimensions, adjacency, level type, player start

### Balance tables
- All numeric constants in `balance.json` — never hardcode
- Avoid scaling stat growth + equipment + ability unlocks simultaneously
- Win/loss conditions readable at a glance from game state
