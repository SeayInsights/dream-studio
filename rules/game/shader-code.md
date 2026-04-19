---
description: Rules for shader code — visual effects, materials, post-processing
globs:
  - "**/shaders/**"
  - "**/assets/shaders/**"
  - "**/materials/**"
  - "**/*.gdshader"
  - "**/src/shaders/**"
  - "**/vfx/**/*.gdshader"
---

# Shader Code Rules

## Performance
- Target 60fps on mid-range hardware. Profile with Godot's built-in GPU profiler.
- Avoid branching in fragment shaders — use `mix()`, `step()`, `smoothstep()` instead.
- Minimize texture lookups per fragment. Pack related data into RGBA channels of a single texture.
- Use `hint_default_white`, `hint_default_black` on uniform samplers for unused slots.

## Portability
- Write for Vulkan (Godot 4 default) but avoid Vulkan-only features if targeting web export.
- Test shaders on both desktop and mobile renderers if cross-platform.
- Use `render_mode` declarations explicitly — don't rely on defaults.

## Uniforms
- All tunable values as `uniform` with `hint_range()` — never hardcode visual parameters.
- Group related uniforms with `group_uniforms` for Inspector organization.
- Name uniforms descriptively: `edge_thickness`, not `val1`.

## Structure
- One visual effect per shader. Don't combine outline + dissolve + glow in one file.
- Comment the visual intent at the top: "Dissolve effect with edge glow for death animation."
- Vertex and fragment functions stay under 50 lines each. Extract to functions if longer.
