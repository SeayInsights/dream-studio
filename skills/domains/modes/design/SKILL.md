---
ds:
  pack: domains
  mode: design
  mode_type: build
  inputs: [design_intent, brand_guidelines, content, target_audience]
  outputs: [design_system, components, assets, brand_package]
  capabilities_required: [Read, Write, WebSearch, Skill]
  model_preference: sonnet
  estimated_duration: 30-90min
---

# Design — Visual Design Capability

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Step 1: Discovery (MANDATORY) {#discovery}

**Purpose:** Translate user intent into structured design system parameters before any design work begins.

**This step CANNOT be skipped.** Discovery establishes the design foundation and prevents misalignment. Every design request must begin with discovery.

### Three Input Modes

#### Mode A: I-Lang Format (Structured Input)
User provides structured YAML/JSON with dimension values from the discovery protocol.

**Example:**
```yaml
palette: monochrome
mood: professional
density: spacious
typography: sans-serif
layout: centered
responsive: mobile-first
exclude: [animations, gradients]
```

**Process:**
1. Parse input against `discovery-protocol.yml` schema
2. Validate dimension values (reject invalid options)
3. Flag missing critical dimensions: `mood`, `density`, `layout`
4. Proceed to design system selection with validated intent

#### Mode B: Natural Language (Prose Description)
User describes intent in natural language without structure.

**Example:**
"I want a clean, professional design with lots of space and no animations. Should work well on mobile."

**Process:**
1. Extract phrases and map to dimensions using `nlp_mappings` from `discovery-protocol.yml`
   - "clean, professional" → `mood: professional`, `typography: sans-serif`
   - "lots of space" → `density: spacious`
   - "no animations" → `exclude: [animations]`
   - "work well on mobile" → `responsive: mobile-first`
2. Document mapped dimensions
3. If critical dimensions missing (`mood`, `density`, `layout`), switch to Mode C for targeted questions
4. Proceed to design system selection

#### Mode C: Interactive Prompting (Minimal Input)
User gives minimal input or Mode B extraction yields insufficient data.

**Process:**
1. Ask targeted questions for missing critical dimensions
2. Minimum viable set (in priority order):
   - **Mood:** "What feeling should this design convey?" (professional / playful / minimal / bold / elegant / modern)
   - **Density:** "How much information needs to fit?" (spacious / balanced / compact / data-heavy)
   - **Layout:** "What's the main content structure?" (centered / sidebar / full-width / multi-column / asymmetric)
3. Optional follow-up for refinement:
   - **Palette:** "Any color preference?" (monochrome / vibrant / warm / cool / pastel / high-contrast)
   - **Accent:** "Primary accent color?" (blue / green / purple / red / orange / none)
4. Document responses as structured intent
5. Proceed to design system selection

### Discovery Output

At the end of discovery, you must have:
- **Minimum:** `mood`, `density`, `layout`
- **Recommended:** All 8 dimensions defined or explicitly defaulted
- **Format:** Structured dimension map (YAML/JSON or documented prose)

### Reference

All dimension definitions, valid values, and NLP mappings are defined in `discovery-protocol.yml`. Consult this file when:
- Validating I-Lang input
- Mapping natural language phrases
- Designing interactive prompts
- Adding new dimension values

**Discovery checkpoint:** Once intent is captured, proceed to Design System Selection.

---

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

## Design System Selection {#system-selection}

**Purpose:** Match user intent and project context to the appropriate design system preset.

**Decision Table:**

| User Intent / Project Type | Design System | Characteristics | Best For |
|----------------------------|---------------|-----------------|----------|
| Tech/SaaS product | `tech-minimal` | Clean typography, muted palette, generous whitespace, subtle shadows | Developer tools, B2B SaaS, productivity apps (Stripe/Linear inspired) |
| Content/editorial | `editorial-modern` | Strong typographic hierarchy, serif headings, focused reading experience | Blogs, publications, documentation sites (Notion/Substack inspired) |
| Bold/experimental | `brutalist-bold` | High contrast, chunky borders, raw grid, bold colors, unapologetic layout | Creative agencies, portfolios, art projects (Wired/Neo-brutalism inspired) |
| Friendly/accessible | `playful-rounded` | Rounded corners, bright colors, approachable copy, clear CTAs | Consumer apps, onboarding flows, community products (Airbnb/Duolingo inspired) |
| Enterprise/dashboard | `executive-clean` | Data-first layout, structured grids, professional palette, chart-ready | Analytics dashboards, admin panels, reporting tools (IBM/Salesforce inspired) |

**Selection Guidance:**

1. **Match context first:** If the user mentions a specific product type (e.g., "dashboard for executives"), prioritize context over aesthetic preference.
2. **Brand alignment:** If brand guidelines are available, choose the system with the closest visual language, then customize.
3. **Audience matters:** B2B products lean toward `tech-minimal` or `executive-clean`; consumer products toward `playful-rounded` or `editorial-modern`.
4. **When in doubt:** Default to `tech-minimal` for technical products, `editorial-modern` for content-heavy sites.
5. **Mixing systems:** Do NOT blend systems within a single project. Pick one, commit, then customize within that system's constraints.

**Integration with Phase 3:**
This table will power automated design system selection when curated presets are integrated in Phase 3. Each system name maps to a preset bundle (tokens, components, templates).

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
