---
source: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
extracted: 2026-05-02
pattern: token-architecture
purpose: 3-layer design token system (primitive→semantic→component)
---

# Token Architecture

Three-layer token system for scalable, themeable design systems.

## Layer Overview

```
┌─────────────────────────────────────────┐
│  Component Tokens                       │  Per-component overrides
│  --button-bg, --card-padding            │
├─────────────────────────────────────────┤
│  Semantic Tokens                        │  Purpose-based aliases
│  --color-primary, --spacing-section     │
├─────────────────────────────────────────┤
│  Primitive Tokens                       │  Raw design values
│  --color-blue-600, --space-4            │
└─────────────────────────────────────────┘
```

## Why Three Layers?

| Layer | Purpose | When to Change |
|-------|---------|----------------|
| Primitive | Base values (colors, sizes) | Rarely - foundational |
| Semantic | Meaning assignment | Theme switching |
| Component | Component customization | Per-component needs |

## Layer 1: Primitive Tokens

Raw design values without semantic meaning.

### Color Scales

```css
:root {
  /* Gray Scale */
  --color-gray-50:  #F9FAFB;
  --color-gray-100: #F3F4F6;
  --color-gray-200: #E5E7EB;
  --color-gray-300: #D1D5DB;
  --color-gray-500: #6B7280;
  --color-gray-900: #111827;
  --color-gray-950: #030712;

  /* Primary Colors (Blue) */
  --color-blue-500: #3B82F6;
  --color-blue-600: #2563EB;
  --color-blue-700: #1D4ED8;

  /* Status Colors */
  --color-green-600: #16A34A;
  --color-yellow-500: #EAB308;
  --color-red-600: #DC2626;
}
```

### Spacing Scale

4px base unit system.

```css
:root {
  --space-0:   0;
  --space-1:   0.25rem;   /* 4px */
  --space-2:   0.5rem;    /* 8px */
  --space-3:   0.75rem;   /* 12px */
  --space-4:   1rem;      /* 16px */
  --space-6:   1.5rem;    /* 24px */
  --space-8:   2rem;      /* 32px */
  --space-12:  3rem;      /* 48px */
  --space-16:  4rem;      /* 64px */
}
```

### Typography

```css
:root {
  /* Font Sizes */
  --font-size-xs:   0.75rem;   /* 12px */
  --font-size-sm:   0.875rem;  /* 14px */
  --font-size-base: 1rem;      /* 16px */
  --font-size-lg:   1.125rem;  /* 18px */
  --font-size-2xl:  1.5rem;    /* 24px */
  --font-size-4xl:  2.25rem;   /* 36px */

  /* Font Weights */
  --font-weight-normal:   400;
  --font-weight-medium:   500;
  --font-weight-semibold: 600;
  --font-weight-bold:     700;

  /* Line Heights */
  --leading-tight:  1.25;
  --leading-normal: 1.5;
  --leading-relaxed: 1.625;
}
```

### Other Primitives

```css
:root {
  /* Border Radius */
  --radius-sm:      0.125rem;  /* 2px */
  --radius-md:      0.375rem;  /* 6px */
  --radius-lg:      0.5rem;    /* 8px */
  --radius-xl:      0.75rem;   /* 12px */
  --radius-full:    9999px;

  /* Shadows */
  --shadow-sm:   0 1px 2px 0 rgb(0 0 0 / 0.05);
  --shadow-default: 0 1px 3px 0 rgb(0 0 0 / 0.1);
  --shadow-md:   0 4px 6px -1px rgb(0 0 0 / 0.1);
  --shadow-lg:   0 10px 15px -3px rgb(0 0 0 / 0.1);

  /* Duration */
  --duration-150: 150ms;
  --duration-200: 200ms;
  --duration-300: 300ms;
}
```

## Layer 2: Semantic Tokens

Purpose-based aliases that reference primitives.

### Background & Foreground

```css
:root {
  /* Page background */
  --color-background: var(--color-gray-50);
  --color-foreground: var(--color-gray-900);

  /* Card/surface background */
  --color-card: white;
  --color-card-foreground: var(--color-gray-900);
}
```

### Primary & Secondary

```css
:root {
  /* Primary */
  --color-primary: var(--color-blue-600);
  --color-primary-hover: var(--color-blue-700);
  --color-primary-foreground: white;

  /* Secondary */
  --color-secondary: var(--color-gray-100);
  --color-secondary-hover: var(--color-gray-200);
  --color-secondary-foreground: var(--color-gray-900);
}
```

### Status & Utility

```css
:root {
  /* Muted */
  --color-muted: var(--color-gray-100);
  --color-muted-foreground: var(--color-gray-500);

  /* Destructive */
  --color-destructive: var(--color-red-600);
  --color-destructive-foreground: white;

  /* Status */
  --color-success: var(--color-green-600);
  --color-warning: var(--color-yellow-500);
  --color-error: var(--color-red-600);

  /* Border & Focus */
  --color-border: var(--color-gray-200);
  --color-ring: var(--color-blue-500);
}
```

### Spacing Semantics

```css
:root {
  /* Component internal spacing */
  --spacing-component-xs: var(--space-1);
  --spacing-component-sm: var(--space-2);
  --spacing-component: var(--space-3);
  --spacing-component-lg: var(--space-4);

  /* Section spacing */
  --spacing-section-sm: var(--space-8);
  --spacing-section: var(--space-12);
  --spacing-section-lg: var(--space-16);
}
```

### Dark Mode Overrides

```css
.dark {
  --color-background: var(--color-gray-950);
  --color-foreground: var(--color-gray-50);

  --color-card: var(--color-gray-900);
  --color-card-foreground: var(--color-gray-50);

  --color-muted: var(--color-gray-800);
  --color-muted-foreground: var(--color-gray-400);

  --color-border: var(--color-gray-800);
}
```

## Layer 3: Component Tokens

Component-specific tokens referencing semantic layer.

### Button

```css
:root {
  /* Default (Primary) */
  --button-bg: var(--color-primary);
  --button-fg: var(--color-primary-foreground);
  --button-hover-bg: var(--color-primary-hover);

  /* Secondary */
  --button-secondary-bg: var(--color-secondary);
  --button-secondary-fg: var(--color-secondary-foreground);
  --button-secondary-hover-bg: var(--color-secondary-hover);

  /* Destructive */
  --button-destructive-bg: var(--color-destructive);
  --button-destructive-fg: var(--color-destructive-foreground);

  /* Sizing */
  --button-padding-x: var(--space-4);
  --button-padding-y: var(--space-2);
  --button-radius: var(--radius-md);
  --button-font-size: var(--font-size-sm);
  --button-font-weight: var(--font-weight-medium);
}
```

### Input

```css
:root {
  /* Background & Border */
  --input-bg: var(--color-background);
  --input-border: var(--color-border);
  --input-fg: var(--color-foreground);
  --input-placeholder: var(--color-muted-foreground);

  /* Focus */
  --input-focus-border: var(--color-ring);
  --input-focus-ring: var(--color-ring);

  /* Sizing */
  --input-padding-x: var(--space-3);
  --input-padding-y: var(--space-2);
  --input-radius: var(--radius-md);
  --input-font-size: var(--font-size-sm);
}
```

### Card

```css
:root {
  /* Background & Border */
  --card-bg: var(--color-card);
  --card-fg: var(--color-card-foreground);
  --card-border: var(--color-border);
  --card-shadow: var(--shadow-default);

  /* Spacing */
  --card-padding: var(--space-6);
  --card-padding-sm: var(--space-4);
  --card-gap: var(--space-4);

  /* Shape */
  --card-radius: var(--radius-lg);
}
```

### Badge

```css
:root {
  /* Default */
  --badge-bg: var(--color-primary);
  --badge-fg: var(--color-primary-foreground);

  /* Sizing */
  --badge-padding-x: var(--space-2-5);
  --badge-padding-y: var(--space-0-5);
  --badge-radius: var(--radius-full);
  --badge-font-size: var(--font-size-xs);
}
```

### Dialog/Modal

```css
:root {
  /* Overlay */
  --dialog-overlay-bg: rgb(0 0 0 / 0.5);

  /* Content */
  --dialog-bg: var(--color-background);
  --dialog-fg: var(--color-foreground);
  --dialog-shadow: var(--shadow-lg);

  /* Spacing */
  --dialog-padding: var(--space-6);
  --dialog-radius: var(--radius-lg);
  --dialog-max-width: 32rem;
}
```

## Naming Convention

```
--{category}-{item}-{variant}-{state}

Examples:
--color-primary           # category-item
--color-primary-hover     # category-item-state
--button-bg-hover         # component-property-state
--space-section-sm        # category-semantic-variant
```

## Usage Patterns

### Good: Uses semantic tokens

```css
.card {
  background: var(--color-card);
  color: var(--color-card-foreground);
  border: 1px solid var(--color-border);
}
```

### Bad: Uses primitive tokens directly

```css
.card {
  background: var(--color-gray-50);
  color: var(--color-gray-900);
}
```

### Component Usage

```css
.button {
  background: var(--button-bg);
  color: var(--button-fg);
  padding: var(--button-padding-y) var(--button-padding-x);
  border-radius: var(--button-radius);
  font-size: var(--button-font-size);
  font-weight: var(--button-font-weight);
  transition: background var(--duration-150);
}

.button:hover {
  background: var(--button-hover-bg);
}

.button.secondary {
  background: var(--button-secondary-bg);
  color: var(--button-secondary-fg);
}
```

## File Organization

### Option 1: Separate files

```
tokens/
├── primitives.css     # Raw values
├── semantic.css       # Purpose aliases
├── components.css     # Component tokens
└── index.css          # Imports all
```

### Option 2: Single file with sections

```css
/* === PRIMITIVES === */
:root { ... }

/* === SEMANTIC === */
:root { ... }

/* === COMPONENTS === */
:root { ... }

/* === DARK MODE === */
.dark { ... }
```

## Migration from Flat Tokens

### Before (flat):

```css
--button-primary-bg: #2563EB;
--button-secondary-bg: #F3F4F6;
```

### After (three-layer):

```css
/* Primitive */
--color-blue-600: #2563EB;
--color-gray-100: #F3F4F6;

/* Semantic */
--color-primary: var(--color-blue-600);
--color-secondary: var(--color-gray-100);

/* Component */
--button-bg: var(--color-primary);
--button-secondary-bg: var(--color-secondary);
```

## Benefits

1. **Theming**: Change semantic layer for instant theme switching
2. **Consistency**: Components reference same semantic tokens
3. **Maintenance**: Update primitives once, cascade everywhere
4. **Dark Mode**: Override semantic tokens, primitives stay the same
5. **Scale**: Add new components without touching foundation

## W3C DTCG Alignment

Token JSON format (W3C Design Tokens Community Group):

```json
{
  "color": {
    "blue": {
      "600": {
        "$value": "#2563EB",
        "$type": "color"
      }
    }
  },
  "semantic": {
    "primary": {
      "$value": "{color.blue.600}",
      "$type": "color"
    }
  }
}
```
