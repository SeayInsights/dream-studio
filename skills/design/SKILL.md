---
name: design
description: Visual design capability — brand tokens, anti-slop rules, visual hierarchy, generative art (p5.js), theme application to projects, and ad-creative guidance. Trigger on `design art:`, `design poster:`, `canvas:`, `generative art:`, `apply theme:`, `brand:`, `ad creative:`, and related commands.
pack: domains
---

# Design — Visual Design Capability

## Trigger
`design art:`, `design poster:`, `canvas:`, `design gen:`, `generative art:`, `algorithmic art:`, `apply theme:`, `theme:`, `brand:`, `apply brand:`, `ad creative:`, `ad copy:`, `generate ads:`

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
