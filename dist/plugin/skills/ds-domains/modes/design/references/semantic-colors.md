---
source: https://github.com/shadcn-ui/ui
extracted: 2026-05-02
pattern: semantic-colors
purpose: Semantic color token system with do/don't examples
---

# Semantic Color System

shadcn-ui uses a semantic color token system built on CSS custom properties that automatically adapts to light and dark themes. The system uses **OKLCH color space** for better perceptual uniformity.

## Core Semantic Tokens

### Background & Foreground
- **`--background`** / `bg-background` — Main app background
- **`--foreground`** / `text-foreground` — Main text color
- **`--surface`** / `bg-surface` — Subtle background variations (e.g., code blocks)
- **`--surface-foreground`** / `text-surface-foreground` — Text on surface backgrounds

### Content Containers
- **`--card`** / `bg-card` — Card/panel backgrounds
- **`--card-foreground`** / `text-card-foreground` — Text on cards
- **`--popover`** / `bg-popover` — Popover/dropdown backgrounds
- **`--popover-foreground`** / `text-popover-foreground` — Text in popovers

### Semantic Actions
- **`--primary`** / `bg-primary` — Primary action (CTA buttons, links)
- **`--primary-foreground`** / `text-primary-foreground` — Text on primary backgrounds
- **`--secondary`** / `bg-secondary` — Secondary actions (less prominent)
- **`--secondary-foreground`** / `text-secondary-foreground` — Text on secondary backgrounds
- **`--accent`** / `bg-accent` — Highlighted/featured items
- **`--accent-foreground`** / `text-accent-foreground` — Text on accent backgrounds
- **`--destructive`** / `bg-destructive` — Destructive actions (delete, cancel)
- **`--destructive-foreground`** / `text-destructive-foreground` — Text on destructive backgrounds

### State & Interaction
- **`--muted`** / `bg-muted` — Muted/disabled backgrounds
- **`--muted-foreground`** / `text-muted-foreground` — Muted/helper text
- **`--border`** / `border-border` — Borders and dividers
- **`--input`** / `border-input` — Input field borders
- **`--ring`** / `ring-ring` — Focus ring color
- **`--selection`** / `bg-selection` — Text selection background
- **`--selection-foreground`** / `text-selection-foreground` — Selected text color

### Specialized
- **`--sidebar-*`** — Sidebar-specific semantic tokens (background, foreground, primary, accent, border, ring)
- **`--code-*`** — Code block specific tokens (background, foreground, highlight, number)
- **`--chart-1` through `--chart-5`** — Chart data visualization colors

## CSS Variable Naming Convention

shadcn-ui uses a **two-layer system**:

1. **Base variables** (defined at `:root` and `.dark`):
   ```css
   :root {
     --background: oklch(1 0 0);
     --foreground: oklch(0.145 0 0);
     --primary: oklch(0.205 0 0);
     --primary-foreground: oklch(0.985 0 0);
   }
   ```

2. **Tailwind color mapping** (defined in `@theme inline`):
   ```css
   @theme inline {
     --color-background: var(--background);
     --color-foreground: var(--foreground);
     --color-primary: var(--primary);
     --color-primary-foreground: var(--primary-foreground);
   }
   ```

This allows using Tailwind utilities like `bg-primary`, `text-foreground`, `border-border`.

## Light/Dark Theme Pattern

Each semantic token is redefined in `.dark` for automatic theme switching:

```css
:root {
  --background: oklch(1 0 0);        /* white */
  --foreground: oklch(0.145 0 0);    /* near-black */
  --primary: oklch(0.205 0 0);       /* dark */
  --primary-foreground: oklch(0.985 0 0); /* near-white */
}

.dark {
  --background: oklch(0.145 0 0);    /* near-black */
  --foreground: oklch(0.985 0 0);    /* near-white */
  --primary: oklch(0.922 0 0);       /* light */
  --primary-foreground: oklch(0.205 0 0); /* dark */
}
```

**Pattern**: Light and dark themes **invert** foreground/background pairs but maintain semantic meaning.

## OKLCH Color Format

shadcn-ui v4 uses **OKLCH** instead of HSL:

```css
/* OKLCH format: oklch(lightness chroma hue [/ alpha]) */
--primary: oklch(0.205 0 0);                    /* neutral dark */
--destructive: oklch(0.577 0.245 27.325);       /* red */
--border: oklch(1 0 0 / 10%);                   /* white with 10% opacity */
```

- **Lightness** (0-1): 0 = black, 1 = white
- **Chroma** (0-0.4): 0 = grayscale, higher = more saturated
- **Hue** (0-360): Color angle (0 = red, 120 = green, 240 = blue)

**Why OKLCH?** Better perceptual uniformity than HSL — same chroma/lightness values produce consistent perceived brightness across hues.

## Usage Guidelines

### ✅ DO: Use Semantic Tokens

```tsx
// Good — semantic, adapts to themes
<button className="bg-primary text-primary-foreground">
  Submit
</button>

<div className="bg-card text-card-foreground border border-border">
  Card content
</div>

<p className="text-muted-foreground">Helper text</p>
```

### ❌ DON'T: Hardcode Colors

```tsx
// Bad — breaks in dark mode, not themeable
<button className="bg-blue-600 text-white">
  Submit
</button>

<div className="bg-white text-gray-900 border border-gray-200">
  Card content
</div>

<p className="text-gray-500">Helper text</p>
```

### ✅ DO: Use Foreground Pairs

Always use matching `-foreground` tokens for text on colored backgrounds:

```tsx
// Good — guaranteed contrast
<div className="bg-destructive text-destructive-foreground">Error</div>
<div className="bg-accent text-accent-foreground">Featured</div>
<button className="bg-secondary text-secondary-foreground">Cancel</button>
```

### ❌ DON'T: Mix Mismatched Pairs

```tsx
// Bad — may have contrast issues
<div className="bg-destructive text-foreground">Error</div>
<div className="bg-accent text-primary-foreground">Featured</div>
```

### ✅ DO: Layer Semantic Tokens

Use different semantic backgrounds for visual hierarchy:

```tsx
<div className="bg-background">           {/* Base layer */}
  <div className="bg-card">               {/* Card layer */}
    <div className="bg-muted">            {/* Muted section */}
      <p className="text-muted-foreground">Helper text</p>
    </div>
  </div>
</div>
```

### ❌ DON'T: Use Same Token for Nested Backgrounds

```tsx
// Bad — no visual separation
<div className="bg-card">
  <div className="bg-card">
    {/* Blends into parent */}
  </div>
</div>
```

### ✅ DO: Use Border Tokens Correctly

- `border-border` — General borders and dividers
- `border-input` — Input field borders (may differ for emphasis)

```tsx
<div className="border border-border">Card</div>
<input className="border border-input" />
```

### ✅ DO: Use Ring for Focus States

```tsx
<button className="focus-visible:ring-2 ring-ring ring-offset-2">
  Focus me
</button>
```

## Component Variant Patterns

shadcn-ui components use semantic tokens in variant classes:

```tsx
// Button variants use different semantic tokens
const buttonVariants = cva(
  "base classes",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground",
        secondary: "bg-secondary text-secondary-foreground",
        destructive: "bg-destructive text-destructive-foreground",
        outline: "border border-input bg-background",
        ghost: "hover:bg-accent hover:text-accent-foreground",
      },
    },
  }
)
```

## Theme Customization

To customize colors, override CSS variables in your `globals.css`:

```css
:root {
  --background: oklch(1 0 0);
  --foreground: oklch(0.145 0 0);
  --primary: oklch(0.488 0.243 264.376);        /* Custom purple */
  --primary-foreground: oklch(0.985 0 0);
  --destructive: oklch(0.577 0.245 27.325);     /* Keep destructive red */
  --destructive-foreground: oklch(0.97 0.01 17);
  /* ...other tokens */
}

.dark {
  --background: oklch(0.145 0 0);
  --foreground: oklch(0.985 0 0);
  --primary: oklch(0.63 0.25 270);              /* Lighter purple for dark mode */
  --primary-foreground: oklch(0.985 0 0);
  /* ...other tokens */
}
```

**Pre-built themes** are available (zinc, slate, stone, blue, green, rose, etc.) in `themes.css`.

## Advanced: Dynamic State Classes

Use `data-*` attributes with semantic tokens:

```tsx
<button
  data-active={isActive}
  className="data-[active=true]:bg-primary data-[active=true]:text-primary-foreground"
>
  Toggle
</button>
```

## Migration from HSL

If migrating from shadcn v1-v3 (HSL-based):

```css
/* Old HSL format */
--primary: 221.2 83.2% 53.3%;

/* New OKLCH format */
--primary: oklch(0.63 0.22 250);
```

Use a color converter to maintain visual consistency. OKLCH values are **not** 1:1 with HSL.

## Summary

- **Semantic tokens** abstract color meaning from specific values
- **OKLCH** provides perceptual uniformity across themes
- **Always pair** backgrounds with matching `-foreground` tokens
- **Light/dark themes** redefine the same tokens for automatic adaptation
- **Use Tailwind utilities** like `bg-primary`, `text-foreground`, `border-border`
- **Never hardcode** Tailwind color scales (e.g., `bg-blue-500`) in production components
