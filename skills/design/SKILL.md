---
name: design
description: Visual design capability — brand tokens, anti-slop rules, visual hierarchy, generative art (p5.js), theme application to projects, and ad-creative guidance. Trigger on `design art:`, `design poster:`, `canvas:`, `generative art:`, `apply theme:`, `brand:`, `ad creative:`, and related commands.
pack: domains
---

# Design — Visual Design Capability

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`design art:`, `design poster:`, `canvas:`, `design gen:`, `generative art:`, `algorithmic art:`, `apply theme:`, `theme:`, `brand:`, `apply brand:`, `ad creative:`, `ad copy:`, `generate ads:`

## Fact Verification First

**Trigger:** Any product name, version, or release timeline claim

**Process:**
1. `WebSearch` product + "2026 latest" to confirm existence/status/version
2. Document in `product-facts.md`, never rely on memory
3. If unclear → ask user, don't assume

**Why:** Search 10 seconds << rework 2 hours

## Brand Asset Protocol

**Trigger:** Task mentions specific brand/product name

**5-step workflow:**

### 1. Ask (Asset Checklist)
Ask by category (not "got brand guidelines?"):
- Logo (SVG/PNG) — required for any brand
- Product images — required for physical products
- UI screenshots — required for digital products
- Colors (HEX/RGB), fonts, brand guidelines URL

### 2. Search
- Logo: `<brand>.com/press`, `/brand`, homepage inline SVG
- Product images: product page, press kit, YouTube screenshots
- UI: App Store, product demos, official screenshots
- Colors: CSS inspect, brand guidelines

### 3. Download ("5-10-2-8 rule")
- Search 5 rounds, collect 10 candidates, select 2 best, each 8/10+ quality
- Minimum: 2000px for images, transparent background for logos
- Exception: Logo always required if found

### 4. Verify
- Logo: exists, light/dark variants, transparent
- Images: 2000px+, clean background
- UI: current version, no user data
- Colors: `grep -hoE '#[0-9A-Fa-f]{6}'` from files, filter black/white/gray

### 5. Document brand-spec.md
Create `assets/<brand>/brand-spec.md` with logo paths, image paths, color palette, fonts, tone keywords.

**Execution:** All designs reference real asset paths. Never substitute with CSS silhouettes.

**Fallback:** Logo not found → ask user. Product images not found → AI generation or placeholder. Colors not found → Design Direction Advisor.

**Why:** Logo > Product images/UI > Colors > Fonts for brand recognition.

## Design Direction Advisor

**Trigger:** Vague brief without context — "make it look good", "design something", no style reference

**Process:**
1. Acknowledge: "I'll offer 3 differentiated directions"
2. Select 3 from 20-school library matching project type
3. For each: philosophy, characteristics, fit, trade-offs
4. Generate quick mockup for each
5. User picks → proceed

**20 Design Schools:** See `references/design-philosophies.md` for full catalog.

Quick reference:
- **Info Architecture:** Pentagram, Stamen, Information Architects, Fathom
- **Motion:** Locomotive, Active Theory, Field.io, Resn
- **Experimental:** Experimental Jetset, MÃ¼ller-Brockmann, Build, Sagmeister
- **Computational:** Zach Lieberman, Raven Kwok, Ash Thorp, Territory Studio
- **Material:** Takram, Kenya Hara, Irma Boom, Neo Shen

**Response format:** 3 options with philosophy + visuals + why + trade-off for each.

## Junior Designer Workflow

**Never execute without showing thinking first.**

### Pass 1: Assumptions + Placeholders
Start with comment block: goal, audience, tone, approach, unresolved questions, placeholders. Show → get feedback.

### Pass 2: Real Components
After approval: replace placeholders, build variations. Show midway, don't wait for 100%.

### Pass 3: Polish
When approved: refine typography, spacing, contrast, timing, edges.

### Pass 4: Verify + Deliver
Verify (links, responsive, a11y), export, document handoff.

**Why:** Fix misunderstandings early (100Ã— cheaper than late).

## Brand tokens
Define your own brand tokens at the top of the project's design config. Example template:

| Token | Value | Usage |
|---|---|---|
| Dark | `{{brand_dark}}` | Backgrounds, primary surfaces |
| Accent | `{{brand_accent}}` | CTAs, highlights |
| Secondary | `{{brand_secondary}}` | Secondary accents, links, success states |
| Light | `{{brand_light}}` | Text on dark, light backgrounds |

Fill these in per project. Once set, treat them as the single source of truth — replace hardcoded colors with token references.

## Anti-slop rules
These are banned patterns. If you catch yourself reaching for any of these, stop:
- No purple gradients (every AI demo uses them)
- No centered-everything layouts
- No uniform border-radius on every element
- No Inter-only typography (pair a display font with a body font)
- No generic hero sections with stock photo + centered H1 + "Get Started" CTA
- No drop shadows on everything
- No low-contrast gray text

## Visual design principles
- **Contrast** — Create visual hierarchy through size, weight, and color contrast
- **Whitespace** — Let elements breathe. Dense ≠ professional.
- **Alignment** — Grid-based. Irregular alignment needs to be intentional.
- **Typography** — Max 2 typefaces. Clear size scale (e.g., 1.25 ratio).
- **Color** — 60/30/10 rule. Primary/secondary/accent.

## Generative art patterns
- p5.js for canvas-based generative work
- Seeded randomness: always use a seed so outputs are reproducible
- HTML viewer template: self-contained single-file with embedded p5.js
- Parameter controls: expose key variables (seed, density, palette) as UI sliders
- Export: save as PNG at 2x resolution for print quality

## Theme application
When applying a theme to an existing project:
1. Map brand tokens to CSS custom properties
2. Replace hardcoded colors with token references
3. Update typography scale to match brand
4. Verify contrast ratios (WCAG AA minimum: 4.5:1 for text)
5. Test dark/light mode if applicable

## Ad creative
- Platform-specific dimensions (feed: 1080x1080, story: 1080x1920, banner: varies)
- Visual hierarchy: hook → value prop → CTA (3-second test)
- Text overlay: max 20% of image area for social platforms
- Brand consistency: use token colors, not platform-default blue
