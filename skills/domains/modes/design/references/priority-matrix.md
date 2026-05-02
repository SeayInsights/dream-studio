---
source: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
extracted: 2026-05-02
pattern: priority-matrix
purpose: 10-level priority system for design decision ranking
---

# Priority Matrix

A systematic approach to prioritizing UI/UX design decisions by impact and criticality.

## Overview

The priority matrix helps rank design rules and decisions by their impact on user experience, accessibility, and product quality. This ensures critical issues are addressed first while maintaining a holistic view of design quality.

Use this matrix when:
- Planning design work and deciding what to tackle first
- Reviewing UI code or designs for quality
- Allocating time across multiple design improvements
- Making trade-offs between competing design concerns

## Rule Categories by Priority

*Supply for human/AI reference: decide by 1→10 which category of rules to focus on first; query `--domain <Domain>` for specific rules when needed. Scripts do not read this table.*

| Priority | Category | Impact | Domain | Key Checks (Must Have) | Anti-Patterns (Avoid) |
|----------|----------|--------|--------|------------------------|------------------------|
| 1 | Accessibility | CRITICAL | `ux` | Contrast 4.5:1, Alt text, Keyboard nav, Aria-labels | Removing focus rings, Icon-only buttons without labels |
| 2 | Touch & Interaction | CRITICAL | `ux` | Min size 44×44px, 8px+ spacing, Loading feedback | Reliance on hover only, Instant state changes (0ms) |
| 3 | Performance | HIGH | `ux` | WebP/AVIF, Lazy loading, Reserve space (CLS < 0.1) | Layout thrashing, Cumulative Layout Shift |
| 4 | Style Selection | HIGH | `style`, `product` | Match product type, Consistency, SVG icons (no emoji) | Mixing flat & skeuomorphic randomly, Emoji as icons |
| 5 | Layout & Responsive | HIGH | `ux` | Mobile-first breakpoints, Viewport meta, No horizontal scroll | Horizontal scroll, Fixed px container widths, Disable zoom |
| 6 | Typography & Color | MEDIUM | `typography`, `color` | Base 16px, Line-height 1.5, Semantic color tokens | Text < 12px body, Gray-on-gray, Raw hex in components |
| 7 | Animation | MEDIUM | `ux` | Duration 150–300ms, Motion conveys meaning, Spatial continuity | Decorative-only animation, Animating width/height, No reduced-motion |
| 8 | Forms & Feedback | MEDIUM | `ux` | Visible labels, Error near field, Helper text, Progressive disclosure | Placeholder-only label, Errors only at top, Overwhelm upfront |
| 9 | Navigation Patterns | HIGH | `ux` | Predictable back, Bottom nav ≤5, Deep linking | Overloaded nav, Broken back behavior, No deep links |
| 10 | Charts & Data | LOW | `chart` | Legends, Tooltips, Accessible colors | Relying on color alone to convey meaning |

## Priority Levels Explained

### Priority 1: Accessibility (CRITICAL)
**Impact:** Excludes users from accessing the product entirely

Accessibility issues prevent users with disabilities from using the product. These must be fixed first because they represent functional blockers, not just quality improvements.

**Examples:**
- Insufficient color contrast making text unreadable
- Missing alt text on informational images
- Keyboard navigation broken or incomplete
- Screen reader users cannot understand interface

**When to address:** Immediately, before any launch or release

### Priority 2: Touch & Interaction (CRITICAL)
**Impact:** Makes core interactions difficult or impossible on mobile

Touch target sizing and interaction feedback are critical on mobile devices where precision is limited. Poor implementation leads to user frustration and errors.

**Examples:**
- Buttons smaller than 44×44px causing mis-taps
- Touch targets too close together
- No loading feedback during async operations
- Hover-only interactions on touch devices

**When to address:** Immediately for mobile products; before mobile launch

### Priority 3: Performance (HIGH)
**Impact:** Degrades perceived quality and user retention

Performance issues cause slow loads, janky scrolling, and layout shifts that erode user trust and increase bounce rates.

**Examples:**
- Unoptimized images causing slow page loads
- Layout shift (CLS) as content loads
- Font loading causing invisible text (FOIT)
- Bundle too large, blocking initial render

**When to address:** Before launch; monitor and improve continuously

### Priority 4: Style Selection (HIGH)
**Impact:** Misaligned product perception and brand

Choosing the wrong visual style for your product type confuses users and undermines brand credibility. Style must match product category and audience expectations.

**Examples:**
- Using playful claymorphism for enterprise fintech
- Mixing brutalism with soft UI randomly
- Using emoji as functional icons
- Inconsistent style across pages

**When to address:** During initial design; maintain consistency throughout

### Priority 5: Layout & Responsive (HIGH)
**Impact:** Breaks usability on mobile or desktop

Layout and responsive design ensure the product works across devices. Poor implementation creates horizontal scroll, cramped layouts, and broken experiences.

**Examples:**
- Horizontal scroll on mobile
- Fixed-width containers breaking on small screens
- No mobile-first breakpoints
- Disabling zoom on mobile

**When to address:** During layout implementation; test across breakpoints

### Priority 6: Typography & Color (MEDIUM)
**Impact:** Reduces readability and visual clarity

Typography and color choices affect reading comfort, hierarchy, and brand expression. Poor choices make content hard to parse.

**Examples:**
- Body text smaller than 16px
- Low line-height causing cramped reading
- Raw hex codes instead of semantic tokens
- Gray text on gray backgrounds

**When to address:** During visual design; refine before polish phase

### Priority 7: Animation (MEDIUM)
**Impact:** Degrades perceived polish and may cause disorientation

Animation conveys state changes and spatial relationships. Poorly implemented animation distracts, slows interactions, or causes motion sickness.

**Examples:**
- Animations longer than 500ms
- Decorative-only animations without meaning
- Animating width/height causing layout reflow
- No support for reduced-motion preferences

**When to address:** During interaction design; refine before launch

### Priority 8: Forms & Feedback (MEDIUM)
**Impact:** Increases error rates and user frustration

Forms and feedback patterns guide users through complex interactions. Poor implementation increases abandonment and errors.

**Examples:**
- Placeholder-only labels disappearing on focus
- Errors shown only at top of form
- No helper text for complex fields
- Revealing all optional fields upfront

**When to address:** During form design; validate before user testing

### Priority 9: Navigation Patterns (HIGH)
**Impact:** Users get lost or cannot find key features

Navigation structure determines discoverability and orientation. Poor navigation breaks user mental models and hides important features.

**Examples:**
- Bottom nav with more than 5 items
- Broken back button behavior
- No deep linking to key screens
- Overloaded navigation menus

**When to address:** During information architecture; test before launch

### Priority 10: Charts & Data (LOW)
**Impact:** Reduces data comprehension

Charts and data visualization help users understand complex information. Poor implementation makes data harder to interpret.

**Examples:**
- Missing legends or axis labels
- Color-only differentiation (no patterns/shapes)
- No tooltips on hover/tap
- Wrong chart type for data

**When to address:** During data visualization design; refine iteratively

## Usage Guidelines

### When Planning Work
1. Start with Priority 1-2 (CRITICAL) issues - these are blockers
2. Move to Priority 3-5 (HIGH) issues - core quality
3. Address Priority 6-8 (MEDIUM) issues - polish
4. Handle Priority 9-10 last - refinement

### When Reviewing Designs
1. Check each priority level systematically
2. Note all issues found per priority
3. Group fixes into waves: Critical → High → Medium → Low
4. Don't skip lower priorities entirely - they still matter

### When Making Trade-offs
- Never trade off Priority 1-2 issues for features
- Can defer Priority 8-10 issues for shipping pressure
- Re-visit deferred items in next iteration

### When Allocating Time
- 40% on Priority 1-2 (Accessibility, Touch/Interaction)
- 30% on Priority 3-5 (Performance, Style, Layout)
- 20% on Priority 6-8 (Typography, Animation, Forms)
- 10% on Priority 9-10 (Navigation, Data viz)

## Integration with Design Process

### Discovery Phase
- Consider all priorities when researching product type
- Document which categories matter most for this product

### Design Phase
- Start with Priority 4 (Style Selection) to set direction
- Design with Priority 1-2 in mind from the start

### Implementation Phase
- Build Priority 1-2 into every component
- Test Priority 3 (Performance) continuously

### QA Phase
- Audit all 10 priorities systematically
- Fix Critical/High issues before launch
- Log Medium/Low issues for next iteration

### Maintenance Phase
- Monitor Priority 3 (Performance) metrics
- Continuously improve Priority 6-10 based on user feedback

## Related Patterns

- **Style Selection:** See `design-system-selection.md` for choosing appropriate visual styles
- **Accessibility Checklist:** See `accessibility-checklist.md` for detailed WCAG compliance
- **Responsive Breakpoints:** See `responsive-patterns.md` for layout best practices

## References

- Apple Human Interface Guidelines (HIG)
- Material Design 3 Guidelines
- WCAG 2.1 Accessibility Standards
- Core Web Vitals (Google)
