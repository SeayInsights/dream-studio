---
name: design
description: Visual design capability — brand tokens, anti-slop rules, visual hierarchy, generative art (p5.js), theme application to projects, and ad-creative guidance. Trigger on `design art:`, `design poster:`, `canvas:`, `generative art:`, `apply theme:`, `brand:`, `ad creative:`, and related commands.
pack: domains
---

# Design — Visual Design Capability

## Trigger
`design art:`, `design poster:`, `canvas:`, `design gen:`, `generative art:`, `algorithmic art:`, `apply theme:`, `theme:`, `brand:`, `apply brand:`, `ad creative:`, `ad copy:`, `generate ads:`

## Fact Verification First (Principle #0)

Before working on any brand/product design task, verify facts first:

**Trigger:** Any specific product name, version number, or release timeline claim

**Hard requirement:**
1. `WebSearch` product name + "2026 latest" or "launch date" to confirm existence/status/version
2. Document findings in `product-facts.md` (never rely on memory or training data)
3. If search is uncertain or ambiguous → ask user, don't assume

**Why:** Assumptions cost hours in rework. Search costs 10 seconds.

**Banned phrases (stop and search instead):**
- ❌ "I recall X hasn't launched yet"
- ❌ "X is currently version N" (without verification)
- ❌ "This product may not exist"
- ✅ "Let me verify X's current status" → WebSearch

**Example cost:** Assuming DJI Pocket 4 unreleased when actually launched 4 days prior = 2 hours of rework on wrong assumptions. WebSearch would have prevented this.

## Brand Asset Protocol (Mandatory for Brand Work)

When task mentions specific brand/product name, run this 5-step protocol:

### Step 1: Ask (Complete Asset Checklist)
Don't ask "got brand guidelines?" — too vague. Ask by category:
1. **Logo** (SVG/PNG) — any brand MUST have
2. **Product images/renders** — physical products MUST have  
3. **UI screenshots** — digital products (App/SaaS/website) MUST have
4. Color values (HEX/RGB)
5. Font stack
6. Brand guidelines PDF / design system URL

### Step 2: Search Official Channels

| Asset | Search Path |
|-------|-------------|
| Logo | `<brand>.com/press`, `<brand>.com/brand`, homepage inline SVG |
| Product images | Product page hero, press kit, YouTube launch video screenshots |
| UI screenshots | App Store listings, product demos, official screenshots section |
| Colors | CSS inspection, brand guidelines PDF |

Fallback: `WebSearch` "<brand> logo download SVG", "<brand> <product> official renders"

### Step 3: Download Assets

**Quality threshold ("5-10-2-8 rule"):**
- Search **5 rounds** across different channels
- Collect **10 candidates**
- Select **2 best**
- Each must score **8/10+** on: resolution (2000px+ for images), copyright clarity, brand fit, composition, narrative value
- **Exception:** Logo always required if found (not subject to 5-10-2-8)

**Download commands:**
```bash
# Logo
curl -o assets/<brand>/logo.svg https://<brand>.com/logo.svg
# Or extract inline SVG from homepage HTML
curl -A "Mozilla/5.0" -L https://<brand>.com -o assets/<brand>/homepage.html
# grep '<svg' to extract

# Product images (2000px+ minimum)
curl -A "Mozilla/5.0" -L "<hero-image-url>" -o assets/<brand>/product-hero.png
```

### Step 4: Verify + Extract

- **Logo:** File exists, opens, has light/dark variants, transparent background
- **Product images:** 2000px+, clean background, multiple angles preferred
- **UI screenshots:** Current version, native resolution (1x/2x), no user data pollution
- **Colors:** `grep -hoE '#[0-9A-Fa-f]{6}' assets/<brand>/*.{svg,html,css} | sort | uniq -c | sort -rn | head -20`, filter black/white/gray

### Step 5: Document in brand-spec.md

Create `assets/<brand>/brand-spec.md`:

```markdown
# <Brand> · Brand Spec
> Acquired: YYYY-MM-DD
> Sources: <list download sources>

## Core Assets
### Logo
- Main: `assets/<brand>/logo.svg`
- Light variant: `assets/<brand>/logo-white.svg`
- Usage: <placement guidelines>

### Product Images (physical products)
- Hero: `assets/<brand>/product-hero.png` (2000×1500)
- Detail: `assets/<brand>/product-detail-1.png`

### UI Screenshots (digital products)
- Home: `assets/<brand>/ui-home.png`
- Feature: `assets/<brand>/ui-feature-<name>.png`

## Supporting Assets
### Color Palette
- Primary: #XXXXXX <source>
- Background: #XXXXXX
- Accent: #XXXXXX

### Typography
- Display: <font stack>
- Body: <font stack>

### Tone Keywords
- <3-5 adjectives describing brand essence>
```

**Execution discipline:** All designs MUST reference real asset file paths from brand-spec.md. Never use CSS silhouettes or hand-drawn SVG as substitutes for actual product images/logos.

**Failure fallback:**
- Logo not found → **stop and ask user** (logo is recognition foundation)
- Product images not found → AI generation with official reference as base, then ask user, then honest placeholder
- Colors not found → Design Direction Advisor mode (see below)

**Why this matters:** Brand recognition hierarchy is Logo > Product images/UI > Colors > Fonts. Only extracting colors produces generic 40-point work. Real assets produce 90-point work.

## Design Direction Advisor (Vague Brief Fallback)

**Trigger:** User gives vague brief without specific context — "make it look good", "design something", "I don't know what style", or can't provide design system/references

**Process:**
1. Acknowledge lack of context: "Without existing design context, I'll offer 3 differentiated directions for you to choose from."
2. Select 3 philosophies from the 20-school library that fit the project type (web/print/motion/data)
3. For each direction, explain:
   - Philosophy core
   - Visual characteristics  
   - Why it fits this project
   - Trade-offs vs other directions
4. Generate quick visual sketch/mockup for each direction
5. User picks one → proceed with full design

**20 Design Philosophy Library:**

| School | Best For | Characteristics |
|--------|----------|-----------------|
| Pentagram (Info Architecture) | Corporate, B2B, data-heavy | Extreme grid, black/white + 1 color, 60%+ whitespace |
| Stamen Design (Data Poetics) | Data viz, maps, analytics | Warm palette, organic patterns, layered information |
| Information Architects | Content-first, editorial | System fonts, blue links, reading-optimized, zero decoration |
| Fathom (Scientific Narrative) | Reports, research, science | Journal aesthetic, precise charts, navy + grays |
| Locomotive (Scroll Storytelling) | Marketing sites, campaigns | Cinematic parallax, dark mode, bold emerging typography |
| Active Theory (WebGL Poetry) | Tech demos, 3D experiences | Particle systems, neon gradients, mouse-reactive |
| Field.io (Algorithmic Aesthetics) | Generative, creative tech | Algorithm-driven patterns, abstract geometry |
| Resn (Motion Design) | Animations, video, interactive | Smooth transitions, physics-based motion |
| Experimental Jetset | Avant-garde, cultural | Typographic experimentation, conceptual layouts |
| Müller-Brockmann (Swiss Grid) | Traditional print, precision | Mathematical grid, ultra-clean, functional |
| Build (Contemporary Minimal) | Modern brands, portfolios | Refined simplicity, subtle details |
| Sagmeister & Walsh (Experimental Bold) | Creative agencies, culture | Provocative, handmade elements, unexpected |
| Zach Lieberman (Creative Code) | Art installations, exhibitions | Interactive code art, playful algorithms |
| Raven Kwok (Generative Patterns) | Backgrounds, textures | Computational patterns, black/white contrast |
| Ash Thorp (Cinematic Futurism) | Sci-fi, product launches | Cinematic grade, futuristic UI, deep blacks |
| Territory Studio (UI Sci-Fi) | Film UI, product vision | Screen graphics, HUD elements, data overlays |
| Takram (Design Engineering) | Product design, innovation | Form + function unity, thoughtful restraint |
| Kenya Hara (Eastern Minimalism) | Luxury, contemplative | Vast whitespace, subtle textures, profound simplicity |
| Irma Boom (Editorial Craft) | Books, publications, print | Material craft, unconventional binding, tactile |
| Neo Shen (Neo-Chinese Aesthetics) | Cultural fusion, contemporary | Traditional motifs + modern execution |

See `references/design-philosophies.md` for full details on each school.

**Example response:**
```
I'll recommend 3 differentiated directions:

**Option A: Pentagram (Info Architecture)**
- Philosophy: Typography as primary language, extreme grid discipline
- Visuals: Black/white + 1 brand color, 60%+ whitespace, Helvetica family
- Fits because: Your project is information-dense, needs clarity over decoration
- Trade-off: Conservative, won't surprise anyone

**Option B: Field.io (Algorithmic Aesthetics)**  
- Philosophy: Generative systems create unique instances
- Visuals: Abstract geometry, particle systems, dynamic composition
- Fits because: Your project is tech-forward, can benefit from motion
- Trade-off: Requires WebGL/canvas, heavier performance cost

**Option C: Kenya Hara (Eastern Minimalism)**
- Philosophy: Emptiness as substance, profound simplicity
- Visuals: Vast whitespace, subtle textures, muted palette
- Fits because: Your project values contemplation over urgency
- Trade-off: Risk of appearing 'too quiet' to Western audiences

Which direction resonates?
```

## Junior Designer Workflow

You're the user's junior designer. The user is your manager. **Never dive into execution without showing your thinking first.**

### Pass 1: Assumptions + Placeholders (5-15 min)
Start every design file with a comment block stating:
- Your understanding of the goal
- Target audience assumption
- Tone/style interpretation
- Planned approach
- Unresolved questions
- Placeholders for missing assets

**Example:**
```html
<!--
ASSUMPTIONS (review before I proceed):
- Target: B2B SaaS buyers (based on "professional" keyword)
- Tone: Trustworthy but approachable (not corporate-stiff)
- Flow: Hero → Features → Pricing → CTA
- Colors: Using brand blue + neutral grays (no accent color confirmed yet)

UNRESOLVED:
- Section 3 data source? (using placeholder for now)
- Background: abstract geometry or real photos?
- CTA copy: "Get Started" or "Start Free Trial"?

If direction looks wrong, NOW is cheapest time to redirect.
-->
```

**Show this to user → wait for feedback before proceeding to Pass 2**

### Pass 2: Real Components + Variations
After user approves direction:
- Replace placeholders with real components
- Build variations if requested
- **Show again midway through** — don't wait until 100% done

### Pass 3: Polish
User satisfied with overall → refine details:
- Typography scale, spacing, contrast
- Animation timing
- Edge cases
- Parameter controls (if applicable)

### Pass 4: Verify + Deliver
- Run verification (link checks, responsive test, accessibility audit)
- Export deliverables
- Document handoff notes

**Why:** Fixing misunderstanding early is 100× cheaper than late. Junior designers show work-in-progress, not just final deliverables.

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
