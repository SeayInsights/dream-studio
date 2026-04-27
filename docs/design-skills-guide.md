# Design Skills Guide

Two design skills now available: dream-studio:design and huashu-design. Each has distinct strengths and use cases.

---

## dream-studio:design

**Strengths:**
- Brand asset acquisition (Fact Verification + Brand Asset Protocol)
- Design direction advisory (20 design philosophies)
- Visual identity and theme application
- Generative art (p5.js)
- Ad creative generation
- Anti-slop discipline

**Triggers:** `design art:`, `brand:`, `apply theme:`, `ad creative:`, `design direction:`, `visual identity:`

**When to use:**
- Starting a new design project without existing brand assets
- Need design direction recommendations for vague briefs
- Applying brand themes to existing projects
- Creating generative art or p5.js sketches
- Producing ad creative for social platforms
- Auditing designs for AI slop patterns

**Output:**
- `assets/<brand>/brand-spec.md` — Documented brand assets (logo, colors, fonts, product images, UI screenshots)
- `product-facts.md` — Verified facts about products/technologies
- Design direction recommendations (3 options from 20 philosophies)
- Visual designs with established brand consistency

**Key workflows:**

### Brand Asset Protocol
1. Fact Verification — WebSearch to confirm product/brand exists and current status
2. Ask for assets — Logo, product images, UI screenshots, colors, fonts
3. Search official channels — Brand site, press kit, App Store
4. Download with quality threshold — 5-10-2-8 rule (5 rounds, 10 candidates, 2 selected, 8/10+ quality)
5. Document in brand-spec.md — Single source of truth for all brand assets

### Design Direction Advisor
When brief is vague:
1. Acknowledge lack of context
2. Select 3 philosophies from 20-school library matching project type
3. Explain each: philosophy, characteristics, fit, trade-offs
4. Generate quick mockup for each direction
5. User picks → proceed with full design

### Junior Designer Workflow
1. **Pass 1:** Show assumptions + placeholders, get feedback
2. **Pass 2:** Build real components after approval
3. **Pass 3:** Polish details
4. **Pass 4:** Verify and deliver

---

## huashu-design

**Strengths:**
- Interactive prototypes (iOS/Android with clickable navigation)
- Slide decks (HTML presentations + editable PPTX export)
- Motion design (MP4/GIF with 60fps interpolation)
- Design variations with live Tweaks
- Infographics (PDF/PNG/SVG export)
- Expert 5-dimension critique

**Triggers:** `prototype:`, `mockup:`, `slides:`, `deck:`, `animate:`, `motion:`, `export pptx:`, `export mp4:`

**When to use:**
- Building interactive app prototypes (iOS/Android mockups)
- Creating presentation decks (need PPTX export)
- Producing motion design videos (product launches, explainers)
- Exploring design variations with parameter controls
- Creating print-quality infographics
- Getting expert design critique (5-dimension review)

**Output:**
- Interactive HTML prototypes with device bezels
- HTML slide decks + editable PowerPoint files
- MP4/GIF animations with 60fps interpolation
- Side-by-side design variations with Tweaks panel
- Vector PDFs, high-res PNGs, SVG exports
- 5-dimension design review with actionable feedback

**Key capabilities:**

### Interactive Prototypes
- Pixel-accurate device bezels (iPhone, Android)
- Multi-screen navigation with state management
- Real images from Wikimedia/Met/Unsplash
- Playwright verification before delivery

### Slide Decks
- HTML presentation (browser-based)
- Exports to editable PPTX (real text frames, not images)
- Speaker notes support
- Professional layouts

### Motion Design
- Stage + Sprite animation model
- 25fps base + 60fps interpolation
- GIF with palette optimization
- BGM integration (6 scene-specific tracks)
- MP4/GIF/video exports

### Tweaks System
- Live parameter switching (colors, typography, density)
- Side panel controls
- localStorage persistence
- Survives page reload

---

## Workflow: dream-studio:design → huashu-design

**Ideal pattern for brand projects:**

### Step 1: Establish Brand Assets (dream-studio:design)
```
User: "brand: Linear"

dream-studio:design runs:
- Fact Verification → WebSearch confirms Linear exists, current status
- Brand Asset Protocol → downloads logo, UI screenshots, extracts colors
- Creates assets/linear/brand-spec.md with all assets documented
```

**Output:** `assets/linear/brand-spec.md`
```markdown
# Linear · Brand Spec
> Acquired: 2026-04-26

## Core Assets
### Logo
- Main: assets/linear/logo.svg
- Dark variant: assets/linear/logo-white.svg

### UI Screenshots
- Home: assets/linear/ui-home.png
- Issues: assets/linear/ui-issues.png

## Color Palette
- Primary: #5E6AD2
- Background: #FFFFFF
- Text: #1F2128

## Typography
- Display: Inter
- Body: Inter
```

### Step 2: Produce Deliverables (huashu-design)
```
User: "animate: product launch video using brand-spec.md"

huashu-design runs:
- Reads assets/linear/brand-spec.md
- References real logo from assets/linear/logo.svg
- Uses color palette from brand-spec
- Creates motion design with brand consistency
- Exports MP4/GIF with 60fps
```

**Output:** Product launch video with Linear's actual logo, colors, UI screenshots — not generic "tech company" animation.

**Why this matters:**
- brand-spec.md becomes single source of truth
- huashu-design deliverables stay brand-consistent
- No guessing colors or hand-drawing logos
- Professional output, not AI slop

---

## Quick Reference

| Task | Use This Skill | Example Trigger |
|------|----------------|-----------------|
| Get brand assets | dream-studio:design | `brand: Stripe` |
| Need design direction | dream-studio:design | `design direction: landing page` |
| Apply theme to project | dream-studio:design | `apply theme: dark mode` |
| Create generative art | dream-studio:design | `generative art: particle system` |
| Make ad creative | dream-studio:design | `ad creative: Instagram feed 1080x1080` |
| Build iOS prototype | huashu-design | `prototype: iOS onboarding flow` |
| Create slide deck | huashu-design | `slides: product pitch deck` |
| Make launch video | huashu-design | `animate: 60s product launch` |
| Export to PowerPoint | huashu-design | `export pptx: this presentation` |
| Design variations | huashu-design | `mockup: 3 color scheme variations` |
| Get design critique | huashu-design | `review: this design 5-dimension` |

---

## Common Patterns

### Pattern 1: New Product Launch
1. `brand: <product>` — dream-studio:design establishes assets
2. `animate: launch video` — huashu-design creates 60s MP4 using brand-spec.md
3. `slides: investor deck` — huashu-design creates HTML + PPTX using brand-spec.md

### Pattern 2: Vague Brief
1. `design direction: make a landing page` — dream-studio:design offers 3 philosophy options
2. User picks "Pentagram (Info Architecture)"
3. `prototype: landing page in Pentagram style` — huashu-design builds interactive mockup

### Pattern 3: Rebrand Existing Project
1. `brand: <new brand>` — dream-studio:design acquires new assets
2. `apply theme: new brand to this codebase` — dream-studio:design maps tokens to CSS
3. `verify: brand consistency` — Check all references point to brand-spec.md

### Pattern 4: Presentation for Client
1. `brand: <client name>` — dream-studio:design gets client logo/colors
2. `slides: project proposal deck` — huashu-design creates presentation
3. `export pptx: editable for client review` — huashu-design outputs PowerPoint file

---

## Tips

### For dream-studio:design
- **Always run Fact Verification first** — Never assume product exists/status without WebSearch
- **5-10-2-8 quality rule** — Search 5 rounds, collect 10 candidates, select 2 best, each 8/10+
- **Logo is non-negotiable** — If logo not found, stop and ask user (never substitute with CSS)
- **Show assumptions first** — Junior Designer Workflow: placeholders → feedback → execution

### For huashu-design
- **Reference brand-spec.md** — Always use real assets from dream-studio's brand-spec.md
- **Export capabilities** — Leverage PPTX, MP4, GIF, PDF exports (dream-studio can't do these)
- **Tweaks for exploration** — Use Tweaks system for live parameter variations
- **Playwright verification** — huashu runs tests before delivery (trust but verify)

### Cross-skill
- **dream-studio establishes, huashu produces** — Use dream-studio to create brand-spec.md, huashu to make deliverables
- **Don't duplicate asset acquisition** — If dream-studio already created brand-spec.md, huashu reads it (don't re-download)
- **Consistent file paths** — Both skills use `assets/<brand>/` convention

---

## Troubleshooting

**Q: Which skill for "design a landing page"?**  
A: Depends on context:
- Need brand assets first? → dream-studio:design
- Have brand assets, need interactive prototype? → huashu-design
- Vague brief, need direction? → dream-studio:design (Design Direction Advisor)

**Q: Can huashu-design get brand assets?**  
A: huashu-design has its own Brand Asset Protocol, but dream-studio's version is more thoroughly documented and integrated with Fact Verification. Recommended: use dream-studio for asset acquisition, huashu for deliverables.

**Q: I already have brand guidelines PDF. Which skill?**  
A: dream-studio:design — it will extract assets from PDF and create brand-spec.md. Then huashu-design can use that brand-spec for deliverables.

**Q: Need a quick mockup without brand assets?**  
A: huashu-design — it can work standalone with its Design Direction Advisor fallback. But quality will be higher if you run dream-studio:design brand: first.

**Q: Both skills have "Junior Designer Workflow" and "Design Direction Advisor"?**  
A: Yes, huashu-design pioneered these patterns and dream-studio:design extracted them. Both implement the same philosophy. Use whichever skill you're already working with.

**Q: Generative art / p5.js — which skill?**  
A: dream-studio:design — huashu-design doesn't cover generative/computational art.

**Q: MP4/GIF/PPTX exports — which skill?**  
A: huashu-design — dream-studio:design doesn't have export infrastructure.

---

## Version History

- **2026-04-26** — Initial integration. dream-studio:design enhanced with huashu patterns (Fact Verification, Brand Asset Protocol, Design Direction Advisor, Junior Designer Workflow). huashu-design installed as complementary skill for specialized deliverables.
