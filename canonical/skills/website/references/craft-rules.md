# Craft Rules — Universal Design Quality Standards

These principles govern every design decision made during a website build. The anti-slop linter catches specific mechanical violations; these rules govern the reasoning behind every choice. When in doubt about a decision, return here.

---

## Rule 1: Specificity Over Generic

**Principle:** Every element must earn its place with real, specific content. Generic copy and stock imagery signal low effort and destroy trust.

| Do | Don't |
|---|---|
| "Cut deploy time from 45 minutes to 3" | "Revolutionize Your Workflow" |
| Photo of the actual product dashboard | Stock photo of people pointing at a laptop |
| "3,200 teams ship faster with Relay" | "Trusted by teams worldwide" |

- Headlines must make a falsifiable claim or deliver a specific benefit.
- Feature cards require real features — label, description, and a concrete outcome.
- Images must show the actual product, team, or result. If you don't have it, use a labeled placeholder (see Rule 2).

---

## Rule 2: Real Content Over Placeholders

**Principle:** Placeholder content makes it impossible to validate layout, hierarchy, or readability. Draft realistic content instead.

| Do | Don't |
|---|---|
| Write plausible copy at realistic length (e.g., a 12-word headline, a 2-sentence subhead) | Leave "Heading goes here" or "Lorem ipsum dolor sit amet" |
| Label images: `PLACEHOLDER — replace with: product screenshot showing dashboard filters` | Insert any stock photo without a label |
| Draft realistic pricing tiers with plausible names and feature lists | Leave blank pricing columns |

- If real content is unavailable, write draft content that matches the expected length and tone.
- Placeholder images must always be labeled with what should replace them and why that specific image matters.
- Never ship a page where the content skeleton is visible.

---

## Rule 3: Restraint Over Decoration

**Principle:** Every visual element must serve hierarchy, readability, or navigation. Decoration for its own sake is noise that competes with content.

| Do | Don't |
|---|---|
| A gradient that marks a section boundary or draws attention to a CTA | A gradient on a body text card "because it looks cool" |
| A shadow that communicates z-level (card floating above surface) | A shadow on a flat element with no spatial meaning |
| One decorative illustration per section that reinforces the message | Floating blobs, random geometric shapes, or abstract "tech" textures |

- Ask of every decoration: "What does this communicate?" If the answer is "nothing," remove it.
- Gradients require a stated functional purpose: depth cue, section separator, attention gradient.
- Shadows must simulate real lighting. The shadow direction must be consistent across the page.

---

## Rule 4: Hierarchy Over Uniformity

**Principle:** The eye must know where to look first, second, and third. If everything competes, nothing wins.

| Do | Don't |
|---|---|
| h1: 56px, h2: 40px, h3: 28px — visually distinct levels | h1: 24px, h2: 22px, h3: 20px — nearly identical |
| One primary CTA per viewport (filled button, high contrast) | Three equally prominent buttons side by side |
| Secondary actions use ghost or text button style | Secondary links styled identically to the primary CTA |

- Size contrast between adjacent heading levels must be at least 1.25x.
- One primary CTA per viewport. Everything else is secondary and must look secondary.
- Don't bold entire paragraphs. Bold is a contrast tool — it loses meaning if overused.

---

## Rule 5: Typography Is Architecture

**Principle:** Type choices determine how content is consumed. Poor type makes readable content unreadable.

| Do | Don't |
|---|---|
| Body line height: 1.6, max line length: 70ch | Body line height: 1.2, full-width text spanning 120ch |
| Display font for hero headline only; system or neutral font for all body copy | Display font used for body paragraphs |
| Heading line height: 1.15 for tight, impactful display | Heading line height: 1.8, making it look like a paragraph |

- Display/decorative fonts: maximum 3 uses per page (hero, section headline, one emphasis moment).
- Body font line height: 1.5–1.75. Heading line height: 1.1–1.3.
- Maximum line length: 65–75 characters. Apply `max-width` to text containers, not the full layout column.

---

## Rule 6: Color Communicates Meaning

**Principle:** Every color in the palette has a job. Random accents create visual chaos and undermine brand coherence.

| Do | Don't |
|---|---|
| Primary blue for CTAs and links; amber only for warnings/alerts; neutrals for body text | Four different accent colors used interchangeably across the page |
| Foreground on background: 4.5:1 contrast ratio for body text | Light gray text on white background (common contrast failure) |
| 1 primary + 1 accent + 2–3 neutrals | 6 brand colors all used at equal weight |

- Assign semantic roles before applying color: primary action, secondary action, success, warning, error, neutral.
- Check contrast ratios before finalizing: 4.5:1 for body text (WCAG AA), 3:1 for large text (≥18px bold or ≥24px regular).
- If you're tempted to add a new color, define its semantic role first. If you can't, don't add it.

---

## Rule 7: Motion Serves Comprehension

**Principle:** Animation must communicate something. Unexplained motion is distraction.

| Do | Don't |
|---|---|
| Fade-in on scroll for new content sections (communicates: this is new) | Spinning logo or parallax star field with no informational purpose |
| Button press feedback with a 100ms scale transform (communicates: registered) | Every element bouncing in on load simultaneously |
| Slide-out for a dismissed toast (communicates: gone) | Decorative hover animations on non-interactive elements |

- Before adding any animation, state its purpose: state change, spatial relationship, or user feedback.
- Entrance animations: use for content that is genuinely new to the viewport. Not for decorative flair.
- Always implement `prefers-reduced-motion` — wrap motion in `@media (prefers-reduced-motion: no-preference)` or check in JS.

---

## Rule 8: Whitespace Is Structural

**Principle:** Whitespace is not empty space — it is the mechanism that groups, separates, and creates rhythm. Cramped layouts feel untrustworthy.

| Do | Don't |
|---|---|
| Section padding: 96px top/bottom; internal element gap: 32px | Equal padding inside and between sections (destroys grouping) |
| Spacing scale based on 8px base: 8, 16, 24, 32, 48, 64, 96 | Random padding values: 14px, 23px, 37px |
| Cards with 24px internal padding, 16px gap between cards | Cards with 8px padding and 32px gap (gap larger than breathing room inside) |

- Section padding should be 2–3x the internal element spacing.
- Stick to a spacing scale. Pick 8px as the base unit and only use multiples.
- More whitespace around important elements signals importance. Cramped = low status.

---

## Rule 9: Components Must Be Self-Evident

**Principle:** If a user needs to read instructions to operate a component, the component is broken. Affordances communicate interaction without words.

| Do | Don't |
|---|---|
| Buttons with hover state, active state, focus ring, and cursor: pointer | Div styled as a button with no focus ring, no hover change |
| Form field with visible label above, placeholder as example only | Input with placeholder-only label that disappears on focus |
| Accordion with a chevron icon that rotates on open/close | Accordion with no visual indicator that it is expandable |

- Every interactive element must visually change on hover, focus, and active states.
- Labels are always visible above or beside their field — never placeholder-only.
- If a component is novel or non-standard, it needs a stronger affordance signal, not a tooltip.

---

## Rule 10: Ship What You'd Screenshot

**Principle:** Every page must be portfolio-quality at any viewport. "It'll look better with real content" is a red flag, not a plan.

| Do | Don't |
|---|---|
| Test at 320px, 768px, 1280px, 1920px before delivering | Deliver at one viewport and assume it's fine |
| Fill every section with realistic draft content before review | Leave skeleton sections and say "client will fill this in" |
| Include a hero image or labeled placeholder before shipping | Ship with a broken image or empty hero |

- Screenshot the page mentally at every breakpoint. If you wouldn't put it in a portfolio, fix it first.
- Mobile is not an afterthought. Responsive layout must be validated, not assumed.
- The standard is: would this pass a design review with a senior designer looking over your shoulder? If not, it's not done.
