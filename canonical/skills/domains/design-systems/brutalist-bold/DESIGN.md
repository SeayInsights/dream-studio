# Brutalist Bold Design System

**Purpose:** High-impact visual system for brands that demand attention. Inspired by Neobrutalism, Wired magazine, and early web aesthetics. Unapologetically bold, experimental, and functional.

**Best For:** Tech startups, creative agencies, indie SaaS, developer tools, experimental brands, counterculture products

**Inspiration Sources:** Wired magazine, Gumroad, Neobrutalism movement, early web brutalism

---

## 1. Visual Theme

### Core Philosophy
- **Raw & Unpolished:** Embrace imperfection, expose structure
- **Maximum Contrast:** Black on white, no subtlety
- **Functional First:** Form follows function, no decoration for decoration's sake
- **Asymmetric Energy:** Break grids intentionally, create tension
- **Bold Typography:** Text as visual element, not just content

### Brand Personality
- Confident, rebellious, experimental
- Authentic, transparent, no-BS
- Tech-forward but human
- Playful chaos within functional constraints

### Visual Principles
1. **High Contrast Always:** Black/white/primary only
2. **Thick Borders Everywhere:** 2-4px minimum
3. **Heavy Shadows:** Hard shadows for depth, no gradients
4. **Asymmetric Layouts:** Intentional imbalance
5. **Exposed Grid:** Show the structure

---

## 2. Colors

### Primary Palette
```css
/* Core System */
--black: #000000;          /* Primary text, borders, shadows */
--white: #FFFFFF;          /* Backgrounds, negative space */
--accent: #FF0055;         /* Primary CTAs, highlights */
--accent-alt: #00FF94;     /* Secondary actions, success */

/* Supporting */
--gray: #808080;           /* Disabled states only */
--yellow: #FFFF00;         /* Warnings, highlights */
--cyan: #00FFFF;           /* Links, info states */
```

### Color Usage Rules
- **80% Black/White:** Most of interface is pure B&W
- **15% Accent:** Primary brand color for CTAs
- **5% Alt Colors:** Sparingly for emphasis
- **No Gradients:** Ever
- **No Opacity:** Use solid colors only

### Contrast Requirements
- Text on background: 21:1 (black on white)
- Interactive elements: Full saturation accent on white
- Disabled: Pure gray (#808080)

### Color Combinations
```
Primary CTA:     black text + accent background + 3px black border
Secondary CTA:   black text + white background + 3px black border
Destructive:     white text + black background + 3px accent border
Success:         black text + accent-alt background + 3px black border
Warning:         black text + yellow background + 3px black border
Info:            black text + cyan background + 3px black border
```

---

## 3. Typography

### Font Stack
```css
/* Primary: Brutal Grotesque */
font-family: 'Space Grotesk', 'Archivo Black', 'Arial Black', sans-serif;

/* Mono: For code/data */
font-family: 'Space Mono', 'Courier New', monospace;
```

### Type Scale (Aggressive Jumps)
```css
--h1: 72px / 1.0;      /* Hero headlines */
--h2: 48px / 1.1;      /* Section headers */
--h3: 32px / 1.2;      /* Card titles */
--h4: 24px / 1.3;      /* Subsections */
--body: 18px / 1.5;    /* Primary text */
--small: 14px / 1.4;   /* Labels, captions */
--tiny: 12px / 1.3;    /* Legal, footnotes */
```

### Weight System
- **900 (Black):** All headlines, CTAs
- **700 (Bold):** Subheads, emphasis
- **400 (Regular):** Body text only
- **No other weights**

### Typography Rules
1. **All Caps for Headlines:** H1-H3 always uppercase
2. **High Contrast Sizing:** 2x jump between levels minimum
3. **Tight Leading on Headlines:** 1.0-1.2 line-height
4. **Generous Body Spacing:** 1.5 line-height minimum
5. **No Italic:** Use weight/color for emphasis

### Text Treatments
```css
/* Headline */
text-transform: uppercase;
font-weight: 900;
letter-spacing: -0.02em;

/* Label */
text-transform: uppercase;
font-weight: 700;
letter-spacing: 0.1em;
font-size: 12px;

/* Body */
font-weight: 400;
letter-spacing: 0;
```

---

## 4. Components

### Buttons
```css
/* Primary */
background: var(--accent);
color: #000;
border: 3px solid #000;
padding: 16px 32px;
font-weight: 900;
text-transform: uppercase;
box-shadow: 6px 6px 0 #000;
transition: none;

/* Hover */
transform: translate(3px, 3px);
box-shadow: 3px 3px 0 #000;

/* Secondary */
background: #fff;
color: #000;
border: 3px solid #000;
```

### Input Fields
```css
border: 3px solid #000;
background: #fff;
padding: 16px;
font-size: 18px;
font-weight: 700;

/* Focus */
outline: 3px solid var(--accent);
outline-offset: 3px;
```

### Cards
```css
background: #fff;
border: 4px solid #000;
padding: 32px;
box-shadow: 12px 12px 0 #000;

/* Hover */
transform: translate(-4px, -4px);
box-shadow: 16px 16px 0 #000;
```

### Navigation
- Thick top/bottom borders (4px)
- All caps labels
- High contrast hover states (background flip)
- No dropdowns, expose all options

### Modals/Overlays
```css
background: #fff;
border: 6px solid #000;
box-shadow: 20px 20px 0 rgba(0,0,0,0.5);
position: fixed;
top: 50%;
left: 50%;
transform: translate(-50%, -50%) rotate(-1deg); /* Slight tilt */
```

### Icons
- Line icons only, 3px stroke
- Or solid black geometric shapes
- Large sizes (24px minimum)
- No icon fonts, inline SVG only

---

## 5. Layout & Grid

### Grid System
```css
/* Intentionally Broken Grid */
display: grid;
grid-template-columns: repeat(12, 1fr);
gap: 24px;

/* Asymmetric Sections */
.hero { grid-column: 1 / 8; }
.sidebar { grid-column: 9 / 13; }
```

### Layout Principles
1. **Asymmetry is Key:** Avoid centered, balanced layouts
2. **Overlap Elements:** Layer cards, text, images
3. **Expose Grid Lines:** Show column/row markers
4. **Tight Gutters:** 16-24px spacing
5. **Edge Bleeding:** Break container bounds intentionally

### Spacing Scale
```css
--xs: 8px;
--sm: 16px;
--md: 24px;
--lg: 48px;
--xl: 96px;
```

### Container Rules
- **Max Width:** 1400px (wide)
- **Padding:** 48px
- **No Centering:** Align left or right
- **Full Bleed Sections:** Break containers frequently

### Z-Index Strategy
```css
--z-base: 0;
--z-card: 10;
--z-overlay: 100;
--z-modal: 1000;
```

---

## 6. Depth & Elevation

### Shadow System (Hard Shadows Only)
```css
--shadow-sm: 4px 4px 0 #000;
--shadow-md: 8px 8px 0 #000;
--shadow-lg: 12px 12px 0 #000;
--shadow-xl: 20px 20px 0 #000;

/* Colored Shadows */
--shadow-accent: 8px 8px 0 var(--accent);
--shadow-dual: 8px 8px 0 var(--accent), 16px 16px 0 #000;
```

### Elevation Layers
1. **Base (0):** Page background, flat text
2. **Card (1):** 8px shadow, 3px border
3. **Interactive (2):** 12px shadow, hover states
4. **Modal (3):** 20px shadow, 6px border
5. **Tooltip (4):** 6px shadow, 2px border

### Border System
```css
--border-thin: 2px solid #000;
--border-base: 3px solid #000;
--border-thick: 4px solid #000;
--border-heavy: 6px solid #000;
```

### Depth Rules
- **No Blur:** All shadows 100% opacity, hard edges
- **Direction Consistency:** Shadows always bottom-right
- **Stackable:** Layer multiple shadows for depth
- **Interactive Shift:** Reduce shadow on press (translate toward shadow)

---

## 7. Do's and Don'ts

### DO
- Use maximum contrast (black on white)
- Add thick borders to everything
- Make buttons feel chunky and tactile
- Break grids intentionally for energy
- Use all caps for headlines
- Expose UI structure (show the grid)
- Stack hard shadows for depth
- Make text huge or tiny, no middle ground
- Use asymmetric layouts
- Let elements overlap and collide

### DON'T
- Use gradients (ever)
- Add rounded corners (0px radius always)
- Use subtle colors or pastels
- Center everything symmetrically
- Use opacity for hierarchy
- Add blur or soft shadows
- Use more than 3-4 colors per page
- Make everything the same size
- Hide borders or structure
- Use decorative fonts

### Brutalist-Specific Guidelines
- **Embrace Ugliness:** If it feels too polished, push harder
- **Function Over Form:** Every element must serve a purpose
- **No Decoration:** No flourishes, ornaments, or embellishments
- **Honest Materials:** Expose HTML structure, show the code
- **Tension is Good:** Uncomfortable spacing creates energy

---

## 8. Responsive Behavior

### Breakpoints
```css
--mobile: 0-640px;
--tablet: 641-1024px;
--desktop: 1025px+;
```

### Mobile Strategy
- **Stack Everything:** No side-by-side on mobile
- **Bigger Touch Targets:** 56px minimum
- **Reduce Shadows:** 4px max on mobile
- **Thinner Borders:** 2px on mobile (3-4px desktop)
- **Maintain Asymmetry:** Keep bold layouts, don't center

### Responsive Type Scale
```css
/* Mobile */
--h1: 48px;
--h2: 32px;
--body: 16px;

/* Desktop */
--h1: 72px;
--h2: 48px;
--body: 18px;
```

### Layout Shifts
- Desktop: Asymmetric multi-column
- Tablet: 2-column max, maintain overlaps
- Mobile: Single column, vertical rhythm

### Touch Interactions
```css
/* Mobile Buttons */
min-height: 56px;
padding: 16px 24px;
font-size: 16px;
border: 2px solid #000;
box-shadow: 4px 4px 0 #000;
```

---

## 9. Agent Prompt Guide

### System Context
```
You are designing with a brutalist/neobrutalism aesthetic. 
Reference: Wired magazine, Gumroad, early web brutalism.

Core principles:
- Maximum contrast (black/white/accent)
- Thick borders (3-4px)
- Hard shadows (no blur)
- Asymmetric layouts
- Bold typography (900 weight, all caps headlines)
- No gradients, rounded corners, or subtle effects
- Functional over decorative
```

### Component Prompts

**Button:**
```
Create a brutalist button:
- Background: [accent color or white]
- Text: black, 900 weight, uppercase
- Border: 3px solid black
- Shadow: 6px 6px 0 black
- Hover: translate(3px, 3px), shadow reduces to 3px 3px 0
- Padding: 16px 32px
- No border-radius
```

**Card:**
```
Design a brutalist card:
- White background
- 4px solid black border
- 12px 12px 0 black shadow
- 32px padding
- Asymmetric content layout
- Hover: shift up/left (-4px), increase shadow to 16px
```

**Hero Section:**
```
Build a brutalist hero:
- Asymmetric 2-column grid (5/7 or 7/5 split)
- Headline: 72px, 900 weight, all caps, black
- Accent color background block behind CTA
- Overlapping elements (image bleeds into text column)
- Thick borders separating sections
- Hard shadow on CTA: 8px 8px 0 black
```

### Color Selection Prompts
```
Primary CTA: Use accent color (#FF0055) with black text and border
Secondary action: White background, black text/border
Success state: Accent-alt (#00FF94) background
Warning: Yellow (#FFFF00) background
Error: Black background, white text, accent border
```

### Layout Prompts
```
Create asymmetric brutalist layout:
- 12-column grid, intentional imbalance (e.g., 7/5, 8/4, 9/3)
- Expose grid with visible borders
- Overlap sections by -24px
- Alternate left/right alignment per section
- No centered content blocks
- 48px section padding, 24px gap
```

### Typography Prompts
```
Brutalist type hierarchy:
- H1: 72px, 900 weight, uppercase, line-height 1.0, -0.02em tracking
- H2: 48px, 900 weight, uppercase
- Body: 18px, 400 weight, 1.5 line-height
- Labels: 12px, 700 weight, uppercase, 0.1em tracking
- No italic, use weight/color for emphasis
```

### Accessibility Requirements
```
Maintain brutalist aesthetic while ensuring:
- 21:1 contrast ratio (black on white)
- 56px touch targets on mobile
- 3px focus outlines (accent color)
- Screen reader labels on all interactive elements
- Semantic HTML structure exposed
```

### Anti-Patterns to Avoid
```
NEVER in brutalist design:
- Rounded corners (border-radius: 0 always)
- Gradients (solid colors only)
- Soft shadows (no blur, hard edges only)
- Opacity for hierarchy (use color/weight)
- Subtle color palettes (high contrast only)
- Centered symmetric layouts (asymmetry required)
- Decorative elements (functional only)
```

---

## Quick Reference Card

**Colors:** Black, White, Accent (#FF0055)
**Borders:** 3-4px solid black
**Shadows:** 6-12px hard shadows, no blur
**Type:** Space Grotesk, 900 weight headlines, all caps
**Layout:** Asymmetric grids, overlap elements
**Spacing:** 8/16/24/48/96px scale
**Radius:** 0px always
**Philosophy:** Raw, bold, functional, unapologetic

