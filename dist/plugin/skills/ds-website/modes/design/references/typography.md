# Typography — Design Reference

Part of the dream-studio design reference library. Consult when making typography decisions in any design task.

## Core Principles

### Vertical Rhythm & Spacing

Line-height serves as the foundational unit for all vertical spacing. If body text uses `line-height: 1.5` on 16px type (24px total), spacing should be multiples of 24px to create visual harmony.

This creates predictable, cohesive layouts where whitespace feels intentional rather than arbitrary.

### Modular Scale

Use **fewer sizes with more contrast** rather than many similar sizes. A 5-tier system works for most projects:

- Small (e.g., 14px) — captions, helper text
- Base (e.g., 16px) — body text
- Medium (e.g., 20px) — subheadings
- Large (e.g., 24px) — section headings
- Extra Large (e.g., 32px) — page headings

Employ popular ratios like 1.25 (major third) or 1.5 (perfect fifth) for consistent stepping.

### Readability Measure

Use character-based widths (`max-width: 65ch`) to optimize readability. This ensures lines aren't too long (fatiguing to read) or too short (forcing excessive breaks).

#### Dark Mode Compensation

Light text on dark backgrounds requires adjustment across three axes:
- **Line-height**: Increase by 0.05–0.1 (e.g., from 1.5 to 1.6)
- **Letter-spacing**: Add 0.01–0.02em subtle tracking
- **Weight**: Consider one weight step heavier for legibility

## Font Selection & Pairing

### Anti-Reflexes to Defend

Avoid these common but unfounded assumptions:

- Technical briefs don't need serifs "for warmth"
- Editorial work doesn't require trendy expressive serifs
- Children's products don't need rounded display fonts
- "Modern" doesn't automatically mean geometric sans-serif

Choose fonts for **function and context**, not for vague stylistic associations.

### Single-Family Hierarchy

One well-chosen font family in multiple weights creates cleaner hierarchy than two competing typefaces. Add a second font **only for genuine contrast needs** — most projects thrive with a single versatile family.

## Web Font Optimization

### Font Loading Strategy

Choose the right `font-display` descriptor for your context:

- **`swap`**: Immediate text visibility with potential layout shifts. Good for content where readability matters more than perfect stability.
- **`optional`**: Zero-shift guarantees on slower networks. Use when layout stability is critical (dashboards, data-heavy apps).

Match fallback metrics using `size-adjust`, `ascent-override`, `descent-override`, and `line-gap-override` to minimize layout shifts during font swap.

### Variable Fonts

Preload only critical weights. Consider variable fonts when deploying 3+ weights to reduce network payload and improve performance.

## Modern Web Typography

### Fluid Type

Use `clamp()` for headings on marketing pages to scale responsively:

```css
font-size: clamp(1.5rem, 4vw, 3rem);
```

**Keep fixed scales for app UIs and dashboards** — predictable sizing ensures stable spacing and grid alignment.

### OpenType Features

Apply selectively for improved readability and professionalism:

- **`font-variant-numeric: tabular-nums`** — data tables (monospace digit width)
- **`font-variant-caps: small-caps`** — abbreviations and acronyms
- **`font-feature-settings: 'liga' 0`** — disable ligatures in code blocks

### ALL-CAPS Tracking

Add 5–12% letter-spacing to capital-only labels and headings to prevent visual cramping:

```css
text-transform: uppercase;
letter-spacing: 0.08em;
```

## Accessibility

### Core Requirements

Never disable user zoom. Design for users with low vision who may rely on it:

```css
/* Good */
html {
  zoom: 100%;
}

/* Bad */
html {
  -webkit-user-select: none;
  zoom: 50%;
  user-zoom: fixed;
}
```

### Font Sizing for Preference Respect

Use `rem` or `em` units for font sizes to respect user browser/OS font-size preferences:

```css
/* Good */
body { font-size: 1rem; }
h1 { font-size: 2rem; }

/* Bad */
body { font-size: 16px; }
h1 { font-size: 32px; }
```

### Minimum Body Text Size

Maintain minimum 16px body text. Smaller sizes strain readers, especially those with low vision or reading disabilities.

### Touch Targets

Ensure 44px+ hit areas for interactive text (links, buttons). This accommodates thumb-sized interaction on mobile and assistive device users.

### Color Contrast

Maintain WCAG AA contrast (4.5:1 for normal text, 3:1 for large text) for legibility across vision types. Test against deuteranopia and protanopia (colorblind variants) not just brightness.

## Common Patterns

### Headings with Subheadings

Stack with consistent vertical rhythm:

```
H1: 32px, line-height 1.2, margin-bottom 24px
Subtitle: 18px, margin-bottom 32px
Body: 16px, line-height 1.5, margin-bottom 24px
```

### Caption & Meta Text

Keep slightly reduced size but maintain rhythm:

```
Caption: 14px, line-height 1.4
Meta (dates, bylines): 14px, letter-spacing 0.02em
```

### Inline Emphasis

Prefer weight over italics for better contrast in digital:

```
/* Preferred */
<strong>Important</strong>  /* 600+ weight */

/* Fallback */
<em>Emphasis</em>  /* 400 italic */
```

## Testing & Iteration

- **Test at actual sizes** — don't design typography in 200% zoom
- **Test across devices** — phone, tablet, desktop with real content length
- **Check at minimum contrast** — view against lightest and darkest backgrounds you'll use
- **Validate with screen readers** — ensure semantic markup, not just visual styling
- **Measure actual line lengths** — use browser dev tools, not assumptions
