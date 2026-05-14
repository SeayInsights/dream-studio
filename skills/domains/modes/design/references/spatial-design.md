# Spatial Design — Design Reference

Part of the dream-studio design reference library. Consult when making spacing, layout, and grid decisions in any design task.

## Spacing Systems

**Base Unit Recommendation**: Use a 4pt base rather than 8pt. The rationale: "8pt systems are too coarse—you'll frequently need 12px (between 8 and 16)." This produces the scale: 4, 8, 12, 16, 24, 32, 48, 64, 96px.

**Token Naming**: Use semantic names reflecting relationships (`--space-sm`, `--space-lg`) instead of literal values. Leverage `gap` for sibling spacing to prevent margin collapse issues.

## Grid Systems

**Self-Adjusting Approach**: Use `repeat(auto-fit, minmax(280px, 1fr))` for responsive behavior without breakpoints. This ensures columns maintain minimum width while expanding to available space. For intricate layouts, named grid areas allow flexible redefinition across breakpoints.

## Visual Hierarchy

**The Squint Test**: Blur your view and verify the most prominent element, secondary elements, and logical groupings remain identifiable. Uniform visual weight when blurred indicates hierarchy problems.

**Multi-Dimensional Approach**: Effective hierarchy combines multiple tools—size (3:1+ ratio), weight contrast, color differentiation, strategic positioning, and spacing. The strongest designs employ 2-3 dimensions simultaneously.

**Card Usage**: Cards shouldn't be default. Reserve them for truly distinct, actionable content or grid comparisons requiring visual boundaries. Avoid nested cards; use spacing and typography instead.

## Advanced Techniques

**Container Queries**: Apply responsive behavior at component level rather than viewport level, enabling the same component to adapt across different container sizes.

**Optical Adjustments**: Compensate for letterform whitespace with negative margins and adjust icon positioning for visual centering.

**Touch Targets**: Maintain 44px minimum interactive areas while controlling visual size through padding or pseudo-elements.

**Depth & Elevation**: Establish semantic z-index hierarchies and subtle shadow scales rather than arbitrary values.
