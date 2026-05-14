# Motion Design — Design Reference

Part of the dream-studio design reference library. Consult when adding animations, transitions, or any motion to a design task.

## Duration Guidelines (The 100/300/500 Rule)

Timing is prioritized over easing. Recommended durations:

- **100-150ms**: Instant feedback (buttons, toggles, color changes)
- **200-300ms**: State transitions (menus, tooltips, hover effects)
- **300-500ms**: Layout shifts (accordions, modals, drawers)
- **500-800ms**: Entry animations (page loads, hero reveals)

Key principle: "Exit animations are faster than entrances—use ~75% of enter duration."

## Easing Curves

Avoid the default `ease` function. Instead, select purpose-driven curves:

| Curve | Purpose | CSS Value |
|-------|---------|-----------|
| **ease-out** | Entries | `cubic-bezier(0.16, 1, 0.3, 1)` |
| **ease-in** | Exits | `cubic-bezier(0.7, 0, 0.84, 0)` |
| **ease-in-out** | Toggles | `cubic-bezier(0.65, 0, 0.35, 1)` |

Exponential curves (quart, quint, expo) create natural, physics-based motion. Bounce and elastic effects should be avoided as they appear outdated.

## Animation Materials

Beyond basic transforms and opacity, consider:

- Blur and backdrop-filter for depth effects
- Clip paths and masks for wipes and reveals
- Shadow and glow for emphasis
- Grid-template and FLIP techniques for layout shifts

Guideline: "avoid animating layout-driving properties casually" like width, height, or margins.

## Staggering

Use CSS custom properties: `animation-delay: calc(var(--i, 0) * 50ms)`. Cap total stagger duration around 500ms for 10 items.

## Accessibility

"Vestibular disorders affect ~35% of adults over 40." Always respect `prefers-reduced-motion` by substituting animations (e.g., crossfades instead of slides) rather than removing all motion.

## Perceived Performance

Users judge speed by feel, not actual metrics. Key strategies:

- **80ms threshold**: Micro-interactions below this feel instant
- **Preemptive starts**: Begin transitions while loading
- **Progressive content**: Don't wait for complete data
- **Optimistic UI**: Update interfaces immediately, sync asynchronously

## Performance Best Practices

- Use `will-change` only when animation is imminent
- Replace scroll events with Intersection Observer
- Create motion design tokens for consistency
- Avoid excessive animation (animation fatigue is real)
