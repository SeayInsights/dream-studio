---
ds:
  pack: domains
  mode: website/deck
  mode_type: build
  inputs: [direction_lock, content_brief, deck_type]
  outputs: [html_deck]
  capabilities_required: [Read, Write]
  model_preference: sonnet
  estimated_duration: 20-40min
---

# Deck — HTML Presentation Builder

Builds complete, single-file HTML presentations from a locked direction and the Duarte Sparkline narrative methodology.

## Pre-requisites

- **Direction lock REQUIRED.** If no lock file exists, stop and tell the user: "Run `direction:` first to lock your visual direction."
- **Content brief REQUIRED.** Collect before building (Step 1 below).

## FROZEN FRAMEWORK — Critical Rule

`assets/deck-framework.html` contains locked JavaScript and CSS for:
- Keyboard navigation (← →, space, enter)
- Scale-to-fit viewport
- Print/PDF CSS
- Speaker notes toggle (press S)
- Slide counter and progress bar

**NEVER modify the framework `<script>` or `<style>` blocks.** Only insert content into `<!-- SLOT:slide-N -->` markers.

## Duarte Sparkline Methodology

Reference `references/slide-strategies.md` for full methodology. Core concept:

- **What Is** — current state, the problem, context (low/tension)
- **What Could Be** — the vision, the opportunity, the contrast (high/resolution)
- **Call to Action** — specific, concrete next steps

The emotional arc oscillates between "what is" and "what could be," building toward the final CTA.

## Build Process

### Step 1 — Content Brief

Collect from the user before writing a single slide:

| Field | Example |
|-------|---------|
| Topic / title | "Q3 Product Roadmap" |
| Audience | Engineering leads, exec team |
| Duration | 5 min / 10 min / 20 min |
| Key messages | 3–5 bullet points |
| Data / evidence | Charts, stats, quotes |
| Desired outcome | Inform / persuade / sell / teach |

### Step 2 — Narrative Arc

Map content to Sparkline structure:
- **Opening:** Hook with "what is" — current state or the problem
- **Body:** Alternate "what is" (tension) with "what could be" (resolution)
- **Closing:** "Call to action" — specific next steps, owners, dates

Target slide count: 1 slide/min + title + CTA (10-min talk ≤ 12 slides).

### Step 3 — Slide Inventory

Plan slides by type before building. Present the list to the user and confirm.

| Slide Type | Purpose | Layout |
|------------|---------|--------|
| title | Opening slide | Large heading, subtitle, optional image |
| section | Section divider | Full-bleed heading |
| content | Text + bullets | Heading + body text (max 5 bullets) |
| data-viz | Chart/graph | Heading + visualization area |
| comparison | Side-by-side | Two columns |
| quote | Testimonial/pullquote | Large centered text + attribution |
| image | Full-bleed image | Image with optional overlay text |
| cta | Closing CTA | Action heading + contact/links |

### Step 4 — Fill Framework

1. Read `assets/deck-framework.html`
2. For each slide, insert content into `<!-- SLOT:slide-N -->` markers only
3. Apply direction lock palette and fonts to all content styles
4. Add speaker notes via `data-notes` attribute (see below)
5. **Do not touch** any `<script>` block or framework `<style>` block

### Step 5 — Anti-Slop Lint + Deliver

```bash
py scripts/lint-artifact.py <output.html>
```

Fix ALL violations before delivering. Follow with: "Run `critique:` to get a 5-dimension quality score."

---

## Slide Content Rules

- Max 5 bullet points per slide — fewer is better
- Max 25 words per bullet
- One idea per slide
- Data-viz slides: one chart, one clear takeaway in the heading
- No paragraph text on slides — put detail in speaker notes
- Heading font for all titles; body font for bullet/content text only
- All colors from the direction lock palette — no ad-hoc values

## Speaker Notes

```html
<div class="slide" data-notes="Speak to the 18% YoY gap here. Emphasize this was pre-initiative data.">
  <!-- visible slide content -->
</div>
```

Notes appear when the presenter presses S. Write notes as spoken sentences, not bullets.

## Anti-patterns

- Modifying framework JavaScript or framework CSS
- Adding slide-specific CSS outside slot areas
- More than 20 slides for a 10-minute talk
- Wall-of-text slides — move detail to `data-notes`
- Charts without a clear single takeaway in the heading
- No CTA slide at the end
- Colors or fonts not in the direction lock
- Skipping the lint step
