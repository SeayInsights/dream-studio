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

**Purpose:** Translate user intent into structured design system parameters.

**Three Input Modes:**

**Mode A: I-Lang (Structured)** — User provides YAML/JSON with dimensions from `discovery-protocol.yml`
**Mode B: Natural Language** — Extract dimensions from prose using `nlp_mappings`
**Mode C: Interactive** — Ask targeted questions for missing critical dimensions (mood, density, layout)

**Output:** Minimum `mood`, `density`, `layout` dimensions. Proceed to Design System Selection.

**Reference:** `discovery-protocol.yml` — all dimension definitions, valid values, NLP mappings

See `examples.md` for detailed Mode A/B/C workflows and extraction examples.

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

| Mode | Trigger | Output |
|------|---------|--------|
| **default** | `design:`, `brand:`, `theme:` | Complete design system, components, brand package |
| **design-system** | `design-system:`, `tokens:` | 3-layer token system, component library |
| **banner** | `banner:`, `hero:` | Banner variants with curated font pairings |
| **validate-composition** | `validate:`, `review composition:` | Validation report with anti-pattern detection |

See `examples.md` for mode examples and detailed workflows.

## Integration Points

- **Discovery → Font Pairings:** Use `search-font-pairings.py` to match mood/typography dimensions
- **Token Architecture:** 3-layer structure (base → semantic → component) from `token-architecture.md`
- **Anti-Pattern Validation:** Run anti-pattern search before finalizing output
- **Priority Matrix:** P0-P2 (MVP) → P3-P5 (staged) → P6-P9 (enhancements)

See `examples.md` for detailed integration workflows.

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
