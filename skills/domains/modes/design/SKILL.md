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

## External References

The following extracted pattern files are available in `skills/domains/modes/design/references/`:

1. **[priority-matrix.md](references/priority-matrix.md)** - 10-level priority system for design decisions (P0 Critical → P9 Future Vision)
2. **[font-pairings.md](references/font-pairings.md)** - 75 curated font pairings with search utility (`search-font-pairings.py`)
3. **[token-architecture.md](references/token-architecture.md)** - 3-layer design token system (base → semantic → component)
4. **[anti-patterns.md](references/anti-patterns.md)** - 99 design anti-patterns with search utility (`search-anti-patterns.py`)
5. **[component-composition.md](references/component-composition.md)** - 14 React component composition patterns
6. **[semantic-colors.md](references/semantic-colors.md)** - 30+ semantic color tokens with usage guidance

### Search Utilities

Two Python utilities provide quick pattern lookups:

**Font Pairing Search:**
```bash
py skills/domains/modes/design/references/search-font-pairings.py "modern professional"
# Returns matching font pairings from 75 curated pairs
```

**Anti-Pattern Search:**
```bash
py skills/domains/modes/design/references/search-anti-patterns.py "color accessibility"
# Returns relevant anti-patterns with severity levels
```

## Mode Routing

### Core Modes

The design skill supports multiple specialized modes. Invoke via `Skill(skill="dream-studio:domains", args="design:<mode>")`.

| Mode | Trigger Keywords | Purpose | Output |
|------|------------------|---------|--------|
| **default** | `design:`, `brand:`, `theme:` | Full design system generation with discovery | Complete design system, components, brand package |
| **design-system** | `design-system:`, `tokens:`, `build design system:` | Generate design systems using token architecture | 3-layer token system, component library, usage guide |
| **banner** | `banner:`, `hero:`, `header design:` | Create banner/hero designs with font pairings | Banner variants with curated font pairings |
| **validate-composition** | `validate:`, `review composition:`, `check patterns:` | Validate React components against composition patterns | Validation report with anti-pattern detection |

### Mode Examples

**Design System Mode:**
```yaml
# User request: "design-system: Build a design system for a fintech dashboard"
# Output: 3-layer token architecture + semantic color palette + component library
```

**Banner Mode:**
```yaml
# User request: "banner: Create a hero section for a SaaS landing page, modern and trustworthy"
# Output: 3 banner variants with font pairings from references/font-pairings.md
```

**Validate Composition Mode:**
```yaml
# User request: "validate-composition: Check my React components for anti-patterns"
# Output: Anti-pattern scan + composition pattern recommendations
```

## Integration Points

### Discovery → Font Pairings
When `discovery-protocol.yml` extraction yields:
- `typography: serif` → Filter font pairings for serif headings
- `mood: professional` → Prioritize "Formal" or "Clean" font pairs
- `mood: playful` → Prioritize "Friendly" or "Warm" font pairs

**Example workflow:**
1. Discovery extracts `mood: professional`, `typography: sans-serif`
2. Run `py references/search-font-pairings.py "professional sans"`
3. Select top 3 pairings for design system

### Token Architecture → Design System
All design system outputs should follow the 3-layer token structure from `token-architecture.md`:
1. **Base tokens** - Raw values (colors, sizes, spacing)
2. **Semantic tokens** - Purpose-based mappings (primary, success, danger)
3. **Component tokens** - Component-specific overrides

### Anti-Pattern Validation
Before finalizing any design output:
1. Run anti-pattern search for relevant categories (e.g., "accessibility", "layout")
2. Cross-check design decisions against flagged anti-patterns
3. Document any intentional exceptions with reasoning

### Priority Matrix Integration
Use the 10-level priority matrix to sequence design work:
- **P0-P2:** Must-have for MVP (core layout, primary actions, critical accessibility)
- **P3-P5:** Important but can be staged (polish, secondary features, edge cases)
- **P6-P9:** Enhancements and future vision (animations, advanced interactions)

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
