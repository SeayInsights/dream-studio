# Color & Contrast — Design Reference

Part of the dream-studio design reference library. Consult when making color and contrast decisions in any design task.

## Color Spaces: Use OKLCH

Replace HSL with OKLCH/LCH for perceptually uniform colors. Equal steps in lightness *look* equal—unlike HSL where 50% lightness in yellow looks bright while 50% in blue looks dark.

OKLCH uses three components: `oklch(lightness chroma hue)` with lightness 0-100%, chroma approximately 0-0.4, and hue 0-360. Build primary color variants by maintaining consistent chroma and hue while adjusting lightness, but reduce chroma near white or black to avoid garish results.

Brand hue selection should be intentional, not reflexive. Avoid defaulting to blue (250°) or warm orange (60°)—these represent common AI-design patterns rather than strategic choices for specific brands.

## Building Functional Palettes

### Tinted Neutrals

Move beyond lifeless pure grays. Add subtle chroma (0.005-0.015) to neutrals, matching your brand's hue direction. This chroma level remains subconsciously cohesive without appearing deliberately tinted.

Your tint direction must align with the project's brand identity. If your brand is teal, neutrals lean teal; if amber, they lean amber. Avoid the lazy defaults of always warming toward orange or cooling toward blue—these create visual monotony across projects.

### Palette Structure

A complete system includes:

- **Primary**: Brand identity, CTAs, key actions (1 color, 3-5 shades)
- **Neutral**: Text, backgrounds, borders (9-11 shade scale)
- **Semantic**: Success, error, warning, info (4 colors, 2-3 shades each)
- **Surface**: Cards, modals, elevation levels (2-3 variations)

Omit secondary/tertiary colors unless necessary. Most applications function well with a single accent, as additional colors introduce decision fatigue.

### The 60-30-10 Rule

This principle addresses visual weight distribution:

- **60%**: Neutral backgrounds, white space, base surfaces
- **30%**: Secondary colors for text, borders, inactive states
- **10%**: Accent colors for CTAs, highlights, focus states

The frequent error involves overusing accent colors because they represent brand identity. Accent effectiveness stems from scarcity—excessive use diminishes their impact.

## Contrast & Accessibility

### WCAG Requirements

| Content Type | AA Minimum | AAA Target |
|--------------|------------|-----------|
| Body text | 4.5:1 | 7:1 |
| Large text (18px+ or 14px bold) | 3:1 | 4.5:1 |
| UI components, icons | 3:1 | 4.5:1 |
| Non-essential decorations | None | None |

**Note**: Placeholder text still needs 4.5:1 contrast—commonly overlooked light gray placeholders frequently violate accessibility standards.

### Dangerous Color Combinations

Avoid these problematic pairings:

- Light gray on white (most common accessibility failure)
- Gray text on colored backgrounds (appears washed out; use darker background shades or transparency instead)
- Red on green or vice versa (affects approximately 8% of men)
- Blue text on red (visual vibration)
- Yellow on white (typically fails contrast)
- Thin light text over images (unpredictable contrast results)

### Never Use Pure Gray or Pure Black

Pure gray (`oklch(50% 0 0)`) and pure black (`#000`) lack natural appearance. Real shadows and surfaces always contain color casts. Even minimal chroma (0.005-0.01) achieves natural appearance without obvious tinting.

### Testing Tools

Verify contrast through objective testing:

- WebAIM Contrast Checker
- Browser DevTools → Rendering → Vision deficiency emulation
- Polypane for real-time accessibility assessment

## Theming: Light & Dark Mode

### Dark Mode Strategy

Dark mode isn't simply inverted light mode. Key distinctions:

| Light Mode | Dark Mode |
|------------|-----------|
| Shadows create depth | Lighter surfaces create depth (no shadows) |
| Dark text on light backgrounds | Light text on dark backgrounds (reduced weight) |
| Vibrant accents | Slightly desaturated accents |
| White backgrounds | Dark gray surfaces (oklch 12-18%), never pure black |

Dark mode depth emerges from surface lightness variations, not shadows. Create a three-step surface scale where higher elevations appear lighter (e.g., 15% / 20% / 25% lightness). Apply consistent brand hue and chroma, varying only lightness. Reduce body text weight slightly in dark mode (e.g., 350 instead of 400) since light text naturally appears heavier against dark backgrounds.

### Token Hierarchy

Implement two layers: primitive tokens (`--blue-500`) and semantic tokens (`--color-primary: var(--blue-500)`). Dark mode redefines only the semantic layer; primitives remain unchanged.

## Alpha Is A Design Smell

Extensive transparency use (rgba, hsla) typically signals incomplete palette design. Transparency creates unpredictable contrast, performance costs, and inconsistency. Instead, define explicit overlay colors for specific contexts. Exception: focus rings and interactive states legitimately require transparency.

## What to Avoid

- Relying solely on color to convey information
- Creating palettes without clearly defined color roles
- Using pure black for expansive areas
- Skipping color blindness testing (affects 8% of men)
- Inverting light mode as dark mode solution
- Defaulting to common "safe" hues rather than brand-specific choices
- Overusing accent colors due to brand prominence
- Implementing heavy alpha/transparency without explicit overlay definitions
