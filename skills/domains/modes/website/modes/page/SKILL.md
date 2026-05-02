---
ds:
  pack: domains
  mode: website/page
  mode_type: build
  inputs: [direction_lock, brand_tokens, page_type, content]
  outputs: [html_page]
  capabilities_required: [Read, Write, Bash]
  model_preference: sonnet
  estimated_duration: 15-45min
---

# Page — Full-Fidelity HTML Builder

Builds complete, single-file HTML pages from a locked direction and brand tokens.

## Pre-requisites

- **Direction lock REQUIRED.** If no lock file exists, stop and tell the user: "Run `direction:` first to lock your visual direction."
- **Brand tokens RECOMMENDED** but not required — the direction lock palette is sufficient.

## Page Types

| Type | Trigger | Typical Sections |
|------|---------|-----------------|
| landing | "landing page", "homepage" | Hero, features, social proof, CTA, footer |
| pricing | "pricing page" | Header, plan comparison, FAQ, CTA |
| portfolio | "portfolio", "showcase" | Hero, project grid, about, contact |
| blog | "blog page", "article" | Header, article body, sidebar, related posts |
| dashboard | "dashboard page" | Nav, stat cards, data tables, charts |
| documentation | "docs page" | Sidebar nav, content area, table of contents |
| app-shell | "app layout" | Top bar, sidebar, main content area |
| about | "about page" | Hero, team, mission, timeline |

## Build Process

### Step 1 — Determine Page Type
Match the user request to a page type from the table above. If ambiguous, ask.

### Step 2 — Load Direction Lock
Read the lock file. Extract palette, typography pairing, and layout strategy. ALL colors, fonts, and spacing derive from this lock — no ad-hoc values.

### Step 3 — Section Inventory
List the sections for the selected page type. Present the list to the user and confirm before building. Allow reordering or dropping sections.

### Step 4 — Content Strategy
For each section, resolve content in priority order:
1. User-provided content → use as-is
2. Extractable content (URL, document) → extract it
3. No content → write plausible draft copy. Mark every draft element with `data-placeholder="true"`. Follow craft-rules.md Rule 2: real, specific copy even for placeholders — no "Lorem ipsum", no "Heading Here".

### Step 5 — Build HTML
Single-file HTML. Nothing external except Google Fonts.

Required:
- `<style>` block using CSS custom properties from `brand.css` or the direction lock palette
- Semantic HTML: `<header>`, `<main>`, `<section>`, `<article>`, `<footer>`, `<nav>`
- Mobile-first responsive design with fluid typography via `clamp()`
- Accessibility: `aria-label`, proper heading hierarchy (one `<h1>` per page), skip-to-content link, visible focus styles
- Google Fonts `<link>` for the locked font pairing
- **No CSS frameworks** — no Tailwind, Bootstrap, or utility classes. Custom CSS only
- **No JavaScript** unless the component is interactive by nature (carousel, modal, accordion)

### Step 6 — Apply Craft Rules
Before finalizing, verify against `references/craft-rules.md`:
- **Specificity:** every heading says something concrete, not generic
- **Hierarchy:** each section has a clear focal point
- **Restraint:** every decorative element earns its place
- **Typography:** display font used ≤ 3 times; body `line-height` 1.5–1.75
- **Whitespace:** consistent vertical spacing rhythm

### Step 7 — Anti-Slop Lint
```bash
py scripts/lint-artifact.py <output.html>
```
Fix ALL violations before delivering. Do not skip this step.

### Step 8 — Deliver
Output the HTML file. Follow with: "Run `critique:` to get a 5-dimension quality score."

---

## HTML Skeleton

Every page starts from this structure:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>[Page Title]</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="[Google Fonts URL]" rel="stylesheet">
  <style>
    /* Brand tokens */
    :root { /* from direction lock or brand.css */ }

    /* Reset */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    /* Base typography */
    body { font-family: var(--font-body); line-height: 1.6; color: var(--color-text); background: var(--color-surface); }
    h1, h2, h3 { font-family: var(--font-display); line-height: 1.2; }

    /* Skip link */
    .skip-link { position: absolute; top: -100%; left: 1rem; background: var(--color-accent); color: #fff; padding: 0.5rem 1rem; }
    .skip-link:focus { top: 1rem; }

    /* Focus styles */
    :focus-visible { outline: 2px solid var(--color-accent); outline-offset: 3px; }

    /* Sections — page-type-specific styles */

    /* Responsive */
    @media (max-width: 768px) { /* mobile overrides */ }
    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: 0.01ms !important; } }
  </style>
</head>
<body>
  <a href="#main" class="skip-link">Skip to content</a>
  <main id="main">
    <!-- Sections -->
  </main>
</body>
</html>
```

## Responsive Strategy

- **Base styles = mobile.** Enhance upward.
- Breakpoints: `640px` (sm) · `768px` (md) · `1024px` (lg) · `1280px` (xl)
- Fluid type: `font-size: clamp(1rem, 0.5rem + 2vw, 1.5rem)`
- Images: `max-width: 100%; height: auto;`
- Layout: CSS Grid for page structure, Flexbox for component-level alignment

## Anti-patterns

- Colors not in the direction lock palette
- Fonts not in the locked pairing
- Placeholder content missing `data-placeholder="true"`
- Tailwind/Bootstrap classes instead of custom CSS
- Skipping the lint step
- Building without a direction lock
- Splitting CSS or JS into separate files — one HTML file only
- `!important` anywhere except the reduced-motion media query
