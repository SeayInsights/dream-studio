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
