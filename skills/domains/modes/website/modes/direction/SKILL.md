---
ds:
  pack: domains
  mode: website/direction
  mode_type: creative
  inputs: [discovery_brief]
  outputs: [direction_lock]
  capabilities_required: [Read, Write]
  model_preference: sonnet
  estimated_duration: 10-20min
---

# Direction — Deterministic Visual Direction

Second mandatory stage of the website pipeline. Takes the discovery brief and produces 3 differentiated visual directions. User picks one. That pick becomes the **direction lock** — immutable for all downstream modes.

---

## Step 1: Analyze Discovery Brief

Read the discovery brief and extract these signals:

| Signal | Extracts To |
|--------|-------------|
| Purpose | Narrows to 3–4 applicable philosophy schools |
| Audience | Constrains tone and density |
| Tone | Maps to specific schools |
| Existing brand? | If yes, directions must harmonize — not reinvent |

---

## Step 2: Cross-Reference Design Philosophies

Read: `skills/domains/modes/design/references/design-philosophies.md`

Match brief signals to the **3 most appropriate schools**. Each direction maps to ONE school. No blending.

---

## Step 3: Generate 3 Directions

Each direction MUST include ALL fields. No partial directions.

```markdown
## Direction [A/B/C]: [Name]

**Philosophy**: [School name] — [1-line philosophy summary]

**Palette** (OKLch locked — 5 colors, no improvisation):
| Role | OKLch | Hex | Usage |
|------|-------|-----|-------|
| Primary | oklch(...) | #... | Buttons, links, primary actions |
| Secondary | oklch(...) | #... | Secondary elements, hover states |
| Accent | oklch(...) | #... | Highlights, badges, callouts |
| Surface | oklch(...) | #... | Backgrounds, cards |
| Text | oklch(...) | #... | Body text, headings |

**Typography**:
- Display: [Font Name] — [weight, usage]
- Body: [Font Name] — [weight, usage]
- Source: skills/domains/modes/design/references/font-pairings.md, pairing #[N]

**Layout Strategy**: [grid type, density, whitespace approach]

**Mood Board**: [3–5 sentences — what this direction FEELS like. Specific, not vibes.]
```

---

## Step 4: Present for Selection

Show all 3 directions. Ask: **"Which direction: A, B, or C?"**

Do not suggest a preferred option. Do not offer a fourth.

---

## Step 5: Lock Direction

When user responds with A, B, or C:

1. Write the direction lock JSON to `.planning/direction-lock.json`
2. Output: `Direction locked: [Direction Name]. All subsequent builds will use this palette and typography.`
3. Output: `To change direction, start a new pipeline with discover:`

**Direction Lock Format:**
```json
{
  "direction_locked": true,
  "name": "Direction A: Modern Authority",
  "philosophy": "Pentagram — Michael Bierut Style",
  "palette": {
    "primary": {"oklch": "oklch(0.55 0.15 250)", "hex": "#2563eb"},
    "secondary": {"oklch": "oklch(0.70 0.08 250)", "hex": "#7c9cc7"},
    "accent": {"oklch": "oklch(0.75 0.12 80)", "hex": "#c9a84c"},
    "surface": {"oklch": "oklch(0.97 0.005 250)", "hex": "#f8f9fc"},
    "text": {"oklch": "oklch(0.25 0.02 250)", "hex": "#1e293b"}
  },
  "typography": {
    "display": {"font": "Playfair Display", "weight": "700"},
    "body": {"font": "Source Sans 3", "weight": "400"}
  },
  "layout": "editorial grid, medium density, generous section padding"
}
```

---

## OKLch Palette Rules

- Define all colors in OKLch **first**, then convert to hex
- Primary and Text must have >= 4.5:1 contrast against Surface (WCAG AA)
- Accent must have >= 3:1 contrast against Surface (WCAG AA large text)
- No two colors closer than ΔE < 20 in OKLch space (perceptual distinctness)
- **NEVER use**: `#7c3aed` (purple), `#6366f1` (indigo), `#ec4899` (pink) — AI defaults, banned

---

## 5 Pre-Locked Palette Families (fallback)

Use when OKLch generation is uncertain. Customize lightness/chroma, but keep hue anchors fixed.

| Family | Mood | Primary | Accent | Surface | Hue Anchor |
|--------|------|---------|--------|---------|------------|
| Maritime Authority | Professional, trustworthy | oklch(0.35 0.13 255) #1e3a5f | oklch(0.72 0.14 75) #c49a28 | oklch(0.97 0.005 255) #f7f9fc | Navy + Gold |
| Forest Craft | Organic, premium | oklch(0.38 0.12 155) #1a5c3a | oklch(0.78 0.10 95) #c8b560 | oklch(0.96 0.01 100) #f5f2ea | Green + Cream |
| Ember Precision | Bold, editorial | oklch(0.28 0.02 30) #2e2420 | oklch(0.60 0.18 35) #b8472a | oklch(0.97 0.005 30) #faf8f7 | Charcoal + Rust |
| Arctic Focus | Clean, technical | oklch(0.40 0.10 240) #2d5080 | oklch(0.82 0.07 210) #9ac8e0 | oklch(0.98 0.004 240) #f6f8fb | Slate + Ice |
| Terra Heritage | Grounded, authentic | oklch(0.38 0.08 50) #5c3d1e | oklch(0.65 0.09 145) #5a8c6a | oklch(0.96 0.01 60) #f5f0e8 | Brown + Sage |

Derive Secondary (primary hue, higher lightness) and Text (primary hue, L ≈ 0.22) from Primary.

---

## Anti-Patterns

- Generating colors without defining OKLch first
- Using AI-default purple/indigo as any role
- Offering more than 3 directions (choice paralysis)
- Incomplete directions — all 5 fields required
- Suggesting "you could also try..." after lock — **lock means locked**
- Blending two philosophy schools into one direction
