---
name: polish
description: UI quality decision tree — critique seven dimensions (layout, typography, color, animation, copy, responsive, edge cases), score 1-5, fix by priority, re-score. Trigger on `polish ui:`, `critique design:`, `redesign:`, `make it premium:`, or auto after `build page:`/`build component:`.
pack: quality
---

# Polish — UI Quality Decision Tree

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`polish ui:`, `clean up ui:`, `polish site:`, `critique design:`, `audit design:`, `redesign:`, `upgrade ui:`, `make it premium:`, or auto-triggered after `build page:`/`build component:`

## Purpose
Single decision tree replacing individual layout, typography, color, animation, copy, responsive, and edge case skills. One invocation, not fifteen.

## Flow

### Step 1: Critique (score current state)
Open the app in a browser. Score each dimension 1-5:

| Dimension | What to check |
|---|---|
| Layout | Grid alignment, spacing consistency, visual rhythm, whitespace |
| Typography | Hierarchy (H1 > H2 > body clear?), line height, line length (45-75 chars), font pairing |
| Color | Contrast ratios (AA 4.5:1 min), consistent palette usage, dark/light mode, anti-slop check |
| Animation | Meaningful motion (not decoration), timing (200-400ms for UI, 600ms+ for emphasis), easing |
| Copy | Labels clear?, error messages actionable?, CTAs specific (not "Submit")?, empty state guidance? |
| Responsive | 320px, 768px, 1024px, 1440px — layout breaks? Touch targets 44px? Readable? |
| Edge cases | Error states, empty states, loading states, long text overflow, missing images |

Output format:
```
## Critique: [page/component]
Layout: 4/5 — [note]
Typography: 3/5 — [issue]
Color: 5/5
Animation: 2/5 — [issue]
Copy: 3/5 — [issue]
Responsive: 4/5 — [note]
Edge cases: 2/5 — [missing states]
Overall: 3.3/5
Priority fixes: [ranked list]
```

### Step 2: Fix (targeted by dimension)
Work through priority fixes from critique. For each dimension scoring 3 or below:

**Layout** — Fix grid alignment, normalize spacing to 4/8/16/24/32px scale, add whitespace between sections, fix visual rhythm.

**Typography** — Establish clear size scale (1.25 ratio), fix line heights (1.4-1.6 for body, 1.1-1.2 for headings), constrain line length, pair fonts (1 display + 1 body max).

**Color** — Replace failing contrast, apply 60/30/10 rule, check anti-slop list (no purple gradients, no uniform corners, no drop shadows everywhere).

**Animation** — Add entrance animations for content (fade + translate, 200-400ms), add hover/press feedback on interactive elements, remove gratuitous motion.

**Copy** — Rewrite vague labels, make error messages say what went wrong + what to do, make CTAs specific ("Create account" not "Submit"), add empty state messages.

**Responsive** — Fix breakpoint issues starting from smallest screen up, ensure touch targets, test overflow.

**Edge cases** — Add error state UI, empty state UI, loading skeletons, handle long text (truncate or wrap), handle missing images (fallback).

### Step 3: Final pass
After fixes, re-score. All dimensions should be 4+ or have a documented reason for exceptions.

## Output
Updated code with commits per dimension fixed. Final critique score.

## Next in pipeline
→ `verify` (prove the polish looks right in browser)
