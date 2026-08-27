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
Invoke `ds-project:resume` to pick up the work order."

## Locked is not current {#brief-currency}

**DO** treat a lock as having an expiry driven by work, not by time. `design_brief_locked` used to ask only whether a locked row existed, so a brief locked in May satisfied it in August after months of UI work had moved the surfaces it described (WO-BRIEF-CURRENCY). It now also asks whether the brief is **current**.

A brief goes stale when a **UI-class work order closes** after it was locked — `ui_component`, `ui_page`, or `saas_feature`. Backend-only work (`api_endpoint`, `data_pipeline`, `infrastructure`, `deployment`, `documentation`) does **not** stale it: a brief that still describes the UI is still true, and crying wolf would train operators to re-lock reflexively.

| Gate says | Meaning | Do this |
|---|---|---|
| `no locked design brief` | none exists | fill and lock one (this mode) |
| `existence but not currency` | locked, but UI work closed since | re-lock, **or** declare reviewed-no-change |
| passes | current | proceed |

**Two remedies, and they are not interchangeable:**

- **Re-lock** when the design language actually changed. Re-locking does not require re-running the whole wizard — update what moved and lock again.
- **Declare reviewed-no-change** when the surface moved but the brief genuinely still holds (a new button reusing existing tokens, say). This is the same idiom the docs-drift gates use, and it is **recorded with its own timestamp and a note** — so it ages exactly like a lock. Work closing *after* the declaration stales the brief again.

**DON'T** reach for reviewed-no-change to skip a real re-lock. A declaration that says "still holds" about a brief that no longer does is worse than a stale lock, because it looks like someone checked.

**DON'T** ask for a brief per work order. `business_design_briefs` is project-scoped deliberately: a brief per WO would proliferate near-duplicates and destroy the shared design language that is the whole point of having one. One current project brief satisfies every UI work order in the project.
