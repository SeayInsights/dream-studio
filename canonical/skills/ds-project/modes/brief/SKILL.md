---
dream_studio:
  skill_id: ds-project
  pack: project
  mode: brief
  mode_type: wizard
  inputs: [project_id]
  outputs: [design_brief_locked]
  capabilities_required: [Read, Bash]
  model_preference: sonnet
  estimated_duration: 5min
---

# Design Brief Wizard

Walks the user through filling a project design brief one question at a time.
Resolves the `design_brief_locked` gate without requiring manual `design-brief update` calls.

## Before you start

Call `get_design_brief(project_id=..., source_root=..., dream_studio_home=...)`.

If no brief exists yet, call `create_design_brief(project_id=..., source_root=..., dream_studio_home=...)`.

Capture the `brief_id` from the returned dict — all updates use it.

## Rules

1. One question at a time — never present two fields in the same message.
2. For bounded fields (design_system), always present numbered choices.
3. Never guess or pre-fill. Every field requires an explicit answer from the user.
4. After all fields are filled, show a summary and ask for confirmation before locking.

## Fields to fill (in order)

### 1 — Purpose
Ask: "What is this project for? Describe it in 1–2 sentences."

Call `update_design_brief_field(brief_id=..., field="purpose", value="<answer>", source_root=..., dream_studio_home=...)`

### 2 — Audience
Ask: "Who will use this? (e.g., internal team, external customers, executives)"

Call `update_design_brief_field(brief_id=..., field="audience", value="<answer>", source_root=..., dream_studio_home=...)`

### 3 — Tone
Ask: "What tone should the UI have? (e.g., professional, playful, technical, minimal)"

Call `update_design_brief_field(brief_id=..., field="tone", value="<answer>", source_root=..., dream_studio_home=...)`

### 4 — Design System
Ask: "Pick a design system:
1. brutalist-bold — raw, high-contrast, editorial weight
2. editorial-modern — clean type-led layouts, generous whitespace
3. executive-clean — polished, corporate, high information density
4. playful-rounded — friendly, colorful, consumer-facing
5. tech-minimal — dark mode, monospace accents, developer tooling feel"

Call `set_design_system(brief_id=..., system_name="<system_name>", source_root=..., dream_studio_home=...)`.

`<system_name>` must be exactly one of: `brutalist-bold`, `editorial-modern`,
`executive-clean`, `playful-rounded`, `tech-minimal`.

### 5 — Font Pairing
Ask: "What font pairing? Give a primary and secondary font, or say 'use system defaults'."

Call `update_design_brief_field(brief_id=..., field="font_pairing", value="<answer>", source_root=..., dream_studio_home=...)`

### 6 — Brand Tokens
Ask: "Any key colors, spacing scale, or brand tokens to enforce?
(e.g., 'primary #1A1A2E, accent #E94560, 8px base unit' — or 'none, use the design system defaults')"

Call `update_design_brief_field(brief_id=..., field="brand_tokens", value="<answer>", source_root=..., dream_studio_home=...)`

## Confirmation and lock

After all 6 fields are filled, call `get_design_brief(project_id=..., source_root=..., dream_studio_home=...)` to verify,
then present a summary:

> "Here's your design brief:
> - **Purpose:** [value]
> - **Audience:** [value]
> - **Tone:** [value]
> - **Design system:** [value]
> - **Font pairing:** [value]
> - **Brand tokens:** [value]
>
> Lock this brief? (1) Yes, lock it. (2) Change [field]."

When confirmed: call `lock_design_brief(brief_id=..., source_root=..., dream_studio_home=...)`.

Then: "Brief locked. The `design_brief_locked` gate is now satisfied.
Invoke `ds-project:resume` and type **start** to begin the work order."
