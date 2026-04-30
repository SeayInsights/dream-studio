# Design Anti-Patterns — Reference

Banned patterns. If you catch yourself reaching for any of these, stop and use the alternative.

---

## Typography Anti-Patterns

### ❌ Inter-only typography
**What it looks like:** Every heading, body, label, and caption set in Inter with no variation.
**Why it's harmful:** Inter is a fine utility font but it has no personality. Every AI-generated interface defaults to it, making your design invisible.
**Instead:** Pair a display or editorial font for headings with a neutral body font. Even one expressive typeface changes everything.

### ❌ Flat type scale
**What it looks like:** h1 through h4 are all similar sizes, maybe 2–4px apart.
**Why it's harmful:** No hierarchy means the eye doesn't know where to land. The page reads as a wall of text.
**Instead:** Use a minimum 1.25 ratio between type scale steps. Heading levels should feel dramatically different from each other.

### ❌ Body lines longer than 75ch
**What it looks like:** Paragraphs that stretch edge-to-edge on a wide container, making lines 100–120 characters long.
**Why it's harmful:** Long line lengths force the eye to travel far and lose its place on return. Reading speed drops and fatigue increases.
**Instead:** Cap body text containers at 65–75ch. Use max-width on prose containers, not full-width.

### ❌ Gradient text
**What it looks like:** `background-clip: text` + a gradient background on headings to make them glow or shift color.
**Why it's harmful:** Pure decoration with no semantic weight. Screams AI-generated. Fails on some rendering engines and prints badly.
**Instead:** Use a single solid color. Add emphasis through weight, size, or spacing — not color tricks.

### ❌ Low-contrast gray text
**What it looks like:** Body copy or labels in `#999`, `#aaa`, or similar light gray on white backgrounds.
**Why it's harmful:** Fails WCAG AA (4.5:1 minimum for normal text). Unreadable for users with low vision, poor monitors, or bright environments.
**Instead:** Test every text color with a contrast checker. For body text on white, stay at or below `#767676`. For small text, go darker.

---

## Color Anti-Patterns

### ❌ Purple gradients
**What it looks like:** Hero sections, cards, or buttons with purple-to-pink or purple-to-blue gradients.
**Why it's harmful:** Every AI demo from 2023–2025 uses this combination. It signals "AI made this" instantly.
**Instead:** Pick a color strategy first (restrained / committed / full palette / drenched) before picking colors. Derive the palette from a physical scene sentence, not a category reflex.

### ❌ Pure black and pure white
**What it looks like:** `#000000` backgrounds and `#ffffff` text, or vice versa — no tint, no warmth.
**Why it's harmful:** Pure black/white have no personality and produce harsh, sterile contrast with no connection to the brand hue.
**Instead:** Tint every neutral toward the brand hue. A chroma of 0.005–0.01 in OKLCH is invisible but adds life. Use `oklch()` instead of hex for neutrals.

### ❌ Category-reflex color
**What it looks like:** Observability tool → dark blue. Healthcare → white and teal. Finance → navy and gold. Crypto → neon on black.
**Why it's harmful:** If someone can guess your palette from the category name alone, it's the training-data default — not a design decision.
**Instead:** Write a one-sentence physical scene (who uses this, where, under what ambient light, in what mood). If the sentence doesn't force a color answer, make it more specific until it does.

### ❌ High chroma at extremes
**What it looks like:** Saturated colors used at very dark (near black) or very light (near white) lightness values — neon shadows, fluorescent tints.
**Why it's harmful:** In OKLCH, the gamut at extreme lightness values is narrow. Forcing high chroma there produces out-of-gamut colors that shift unpredictably across displays.
**Instead:** Reduce chroma as lightness approaches 0 or 100. Vivid colors live in the middle range of lightness.

### ❌ Platform-default blue for CTAs
**What it looks like:** A "Get Started" or "Submit" button in browser-default `#0066cc` or Bootstrap primary blue.
**Why it's harmful:** It signals no design investment and breaks brand consistency.
**Instead:** Derive CTA color from brand token color, not platform defaults. If there's no brand color yet, pick one deliberately.

---

## Layout Anti-Patterns

### ❌ Centered-everything layouts
**What it looks like:** Every section — hero, features, testimonials, footer — is center-aligned with centered headings and centered body copy.
**Why it's harmful:** Center alignment is appropriate for short, high-impact moments (a single hero stat, a pull quote). Applied everywhere it reads as template-generated and creates awkward ragged edges in paragraphs.
**Instead:** Use left alignment as the default for body content. Reserve center alignment for isolated moments that deserve emphasis.

### ❌ Identical card grids
**What it looks like:** A grid of 3, 6, or 9 cards, all the same size, each with an icon + heading + 2 lines of body text.
**Why it's harmful:** The most clichéd SaaS layout pattern. Every AI-generated features section looks like this. It signals zero design thought.
**Instead:** Vary card sizes, break the grid intentionally, use a different information architecture entirely (timeline, masonry, magazine layout, or feature callouts).

### ❌ Uniform border-radius on every element
**What it looks like:** Every button, card, input, image, and container has the same 8px or 12px border-radius applied.
**Why it's harmful:** Mindless application of a single radius value makes everything look like it came from the same template. Radius should reflect the element's personality and the design system's character.
**Instead:** Decide on a radius language for your design system. Pills for interactive controls, subtle rounding for cards, sharp corners for editorial elements, or a mix with intention.

### ❌ Nesting cards inside cards
**What it looks like:** A card component that contains another card inside it — often seen in dashboards and admin UIs.
**Why it's harmful:** Nested cards create visual clutter, flatten the elevation hierarchy, and signal the layout was not thought through.
**Instead:** Use a different pattern for inner content: a table, a list with dividers, a section with background tint, or inline groups with spacing.

### ❌ Wrapping everything in a container
**What it looks like:** Every element on the page, including full-bleed heroes, background sections, and edge-to-edge images, is wrapped in a `max-width` container div.
**Why it's harmful:** Full-bleed moments add visual impact and breathing room. Constraining everything shrinks the design to feel boxy and safe.
**Instead:** Let backgrounds, images, and decorative elements bleed to the viewport edge. Only constrain text and interactive content where readability requires it.

### ❌ Generic hero section
**What it looks like:** Full-width section with a stock photo or gradient background, centered H1, a supporting paragraph in gray, and a "Get Started" CTA button.
**Why it's harmful:** This pattern is so overused it has become invisible. Users skip past it without reading. It communicates nothing unique about the product.
**Instead:** Make the hero do one specific job. Use the actual product UI, a concrete proof point, a customer result, or an interactive element. The visual should do work, not fill space.

### ❌ Drop shadows on everything
**What it looks like:** Every card, button, modal, image, and text block has a box-shadow applied.
**Why it's harmful:** Drop shadows create elevation cues. When everything is elevated, nothing is. The shadow loses its meaning and the page looks muddy.
**Instead:** Use shadows sparingly and only where elevation is semantically meaningful — floating modals, popovers, active/hover states. Use flat backgrounds, borders, or spacing to separate elements instead.

---

## Motion Anti-Patterns

### ❌ Animating CSS layout properties
**What it looks like:** Transitions or animations on `width`, `height`, `top`, `left`, `margin`, or `padding`.
**Why it's harmful:** Layout property changes trigger browser reflow, which is expensive and produces jank even on capable hardware.
**Instead:** Animate `transform` and `opacity` only. Use `transform: translate()` instead of `top`/`left`, `transform: scale()` instead of `width`/`height`.

### ❌ Bounce and elastic easing
**What it looks like:** UI elements that overshoot their destination and spring back, or that wobble into place.
**Why it's harmful:** Bounce and elastic motion call attention to themselves. They read as playful at best, juvenile at worst, and always slow down perceived interaction time.
**Instead:** Use ease-out-quart, ease-out-quint, or ease-out-expo curves. Motion should decelerate into its final state, not oscillate.

### ❌ Glassmorphism as default
**What it looks like:** Blurred, translucent card panels applied to most or all UI surfaces — navigation, cards, modals, sidebars.
**Why it's harmful:** Glassmorphism became a design trend and then immediately a cliché. Used decoratively it adds visual noise and reduces readability.
**Instead:** Use solid surfaces as the default. Reserve blur and translucency for moments where the layering is semantically meaningful — a true overlay, a tooltip over content, a floating toolbar.

---

## Copy Anti-Patterns

### ❌ Em dashes
**What it looks like:** Sentences that use — em dashes — to insert asides or connect clauses.
**Why it's harmful:** Em dashes are a strong signal of AI-generated prose. They also create rhythm problems in UI copy and vary in rendering across fonts.
**Instead:** Rewrite with commas, colons, semicolons, periods, or parentheses. If a clause needs an em dash to hold together, it probably needs to be its own sentence.

### ❌ Restated headings
**What it looks like:** A section heading that says "Key Features" and the body copy below it begins with "Here are some key features of our product…"
**Why it's harmful:** The heading already did the work. The intro sentence adds zero information and delays the reader from getting to what matters.
**Instead:** The first sentence after a heading should add new information, not repeat the heading. Subheadings should expand on the heading, not mirror it.

### ❌ The hero-metric template
**What it looks like:** A big bold number (10,000+), a small label beneath it (Happy Customers), repeated 3–4 times in a row, often with a gradient accent line.
**Why it's harmful:** The most recognizable SaaS cliché. Every AI-generated landing page uses this exact structure. It signals no design investment.
**Instead:** If metrics matter, make them specific and contextual. Show the number in relation to something real — a chart, a case study stat, a before/after. Give the number a story.

### ❌ Modal as first thought
**What it looks like:** Any user action that needs more information — a form, a confirmation, a settings panel — is immediately put in a modal dialog.
**Why it's harmful:** Modals block the page, trap focus, and interrupt flow. They are often the lazy default rather than the right pattern.
**Instead:** Exhaust inline and progressive alternatives first. Inline expansion, side sheets, drawers, step-by-step flows on the same page, or a dedicated route. Use modals only when interruption is truly warranted (destructive confirmations, critical alerts).

### ❌ Side-stripe borders as decoration
**What it looks like:** Cards, list items, callouts, or alert boxes with a thick colored `border-left` or `border-right` as the primary decorative accent.
**Why it's harmful:** The left-border accent card is one of the most overused patterns in dashboard and admin UI. It reads as a template element, not a design decision.
**Instead:** Use full borders, background tints, leading icons, numbers, or colored headings. If you need to group or call out content, choose a pattern that adds information rather than just visual weight.
