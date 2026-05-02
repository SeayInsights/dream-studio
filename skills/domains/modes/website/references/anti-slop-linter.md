# Anti-Slop Linter — Rule Catalog

## Purpose

The anti-slop linter catches the visual and copy patterns that AI-generated websites default to when not given strong brand direction. Left unchecked, these patterns produce sites that look identical: purple gradients, Inter everywhere, invented social proof, emoji bullets, and vague filler headings. This linter makes those defaults visible so they can be intentionally replaced or intentionally kept (with bypass).

The linter does not enforce taste. It enforces intentionality. Every flagged pattern has a legitimate use — the point is that it must be a deliberate choice, not an unexamined default.

---

## Invocation

```bash
py scripts/lint-artifact.py <file.html>
py scripts/lint-artifact.py <file.html> --severity critical    # only critical rules
py scripts/lint-artifact.py <file.html> --fix-hints            # include inline fix suggestions
py scripts/lint-artifact.py <file.html> --json                 # machine-readable output
```

Exit codes: `0` = clean, `1` = warnings only, `2` = critical violations found.

---

## Bypass Syntax

Any rule can be silenced for a single line by placing a bypass comment on the line **directly above** the violation:

```html
<!-- lint-disable purple-gradient -->
background: linear-gradient(135deg, #7c3aed, #4f46e5);
```

For multi-line blocks, wrap with open/close:

```html
<!-- lint-disable purple-gradient -->
.hero {
  background: linear-gradient(135deg, #7c3aed, #4f46e5);
}
<!-- lint-enable purple-gradient -->
```

Use bypass sparingly. If a client's brand IS purple, that is a valid bypass — add a comment explaining why (`<!-- lint-disable purple-gradient: Acme brand color, see brand-guide.pdf -->`).

---

## Severity Levels

| Level | Meaning | Action |
|---|---|---|
| **critical** | Definitively marks the site as AI-generated or untrustworthy. Ship-blocking. | Must fix or explicitly bypass before delivery. |
| **high** | Strong AI default signal. Visible to trained eyes. | Fix unless client brief overrides. |
| **medium** | Lazy shortcut, not a red flag on its own. Adds up. | Review and decide; note if keeping. |

---

## Rule Catalog

---

### purple-gradient
**Severity**: critical
**Pattern**: Any of `#7c3aed`, `#8b5cf6`, `#a78bfa`, `#6d28d9`, `purple`, `violet` appearing inside a `linear-gradient()`, `radial-gradient()`, or `conic-gradient()` call; also catches Tailwind utility classes `from-purple-*`, `to-purple-*`, `via-purple-*`, `from-violet-*`, `to-violet-*` on gradient containers.

**Example (bad)**:
```css
.hero {
  background: linear-gradient(135deg, #7c3aed 0%, #8b5cf6 100%);
}
```

**Fix**:
```css
/* Use brand colors sourced from the brief. If no brief exists, pause and ask. */
.hero {
  background: linear-gradient(135deg, var(--brand-primary) 0%, var(--brand-secondary) 100%);
}
```

**Bypass**: `<!-- lint-disable purple-gradient -->` on the line above

---

### indigo-default
**Severity**: critical
**Pattern**: Any of `#6366f1`, `#4f46e5`, `#818cf8`, `#4338ca`, `indigo` appearing as a value for `color`, `background-color`, `background`, `border-color`, `fill`, `stroke`, or `--color-primary` / `--color-accent` CSS custom properties. Also catches Tailwind classes `bg-indigo-*`, `text-indigo-*`, `border-indigo-*` used on interactive elements (buttons, links, badges).

**Example (bad)**:
```html
<button class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded">
  Get Started
</button>
```

**Fix**:
```html
<!-- Use a brand color token, not Tailwind's default indigo -->
<button class="btn-primary">
  Get Started
</button>
```
```css
.btn-primary {
  background-color: var(--brand-action);
  color: var(--brand-action-text);
}
```

**Bypass**: `<!-- lint-disable indigo-default -->` on the line above

---

### emoji-as-icon
**Severity**: high
**Pattern**: Unicode codepoints in emoji ranges (`\u{1F300}–\u{1FAFF}`, `\u{2600}–\u{26FF}`, `\u{2700}–\u{27BF}`) appearing inside `<button>`, `<a>`, `<li>`, `<td>`, `<th>`, or as the first/only child of a `<span>` or `<div>` acting as a UI control. Also catches emoji in heading text (h1–h4).

**Example (bad)**:
```html
<ul>
  <li>⚡ Blazing fast performance</li>
  <li>🔒 Bank-level security</li>
  <li>📊 Real-time analytics</li>
</ul>
```

**Fix**:
```html
<!-- Use inline SVG or an icon component with accessible aria-label -->
<ul>
  <li>
    <svg aria-hidden="true" class="icon icon-bolt"><use href="#bolt"/></svg>
    Blazing fast performance
  </li>
</ul>
```

**Bypass**: `<!-- lint-disable emoji-as-icon -->` on the line above

---

### inter-as-display
**Severity**: high
**Pattern**: `font-family` values containing `Inter`, `system-ui`, `-apple-system`, or `BlinkMacSystemFont` applied to elements with `font-size` >= 24px, or applied to `h1`, `h2`, `h3` selectors, or applied to a class that includes `heading`, `display`, `title`, or `hero` in its name.

**Example (bad)**:
```css
h1, h2 {
  font-family: 'Inter', system-ui, sans-serif;
  font-size: 3rem;
}
```

**Fix**:
```css
/* Display type needs personality. Inter is a UI workhorse, not a headline font. */
h1, h2 {
  font-family: var(--font-display); /* e.g. Fraunces, Playfair, Syne, Neue Haas */
}
body {
  font-family: 'Inter', system-ui, sans-serif; /* Inter is fine here */
}
```

**Bypass**: `<!-- lint-disable inter-as-display -->` on the line above

---

### lorem-ipsum
**Severity**: critical
**Pattern**: Case-insensitive match for `lorem ipsum`, `dolor sit amet`, `consectetur adipiscing`, `sed do eiusmod`, `ut labore et dolore`, or `[PLACEHOLDER]`, `[INSERT TEXT]`, `[CONTENT HERE]`, `[COPY TBD]` in any text node or attribute value.

**Example (bad)**:
```html
<p>
  Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod
  tempor incididunt ut labore et dolore magna aliqua.
</p>
```

**Fix**:
```html
<!-- Write real copy. If copy isn't ready, mark it clearly and block delivery. -->
<p>
  <!-- COPY NEEDED: 2–3 sentences describing [feature]. Block delivery until filled. -->
</p>
```

**Bypass**: `<!-- lint-disable lorem-ipsum -->` on the line above (for actual Latin text quotations, not placeholder copy)

---

### invented-metrics
**Severity**: high
**Pattern**: Regex matching common fabricated social-proof patterns in text nodes:
- `\d+[xX]\s*(faster|better|more|less|cheaper)`
- `\d+\.?\d*%\s*(uptime|accuracy|faster|reduction|increase|improvement|satisfaction)`
- `\d+[KkMmBb\+]?\s*\+?\s*(users|clients|customers|companies|teams|businesses|downloads|installs)`
- `#1\s+(in|for|rated|ranked|trusted)`
- `trusted by \d+`

Unless immediately followed by a citation element (`<cite>`, `<sup>`, footnote link, or `data-source` attribute).

**Example (bad)**:
```html
<div class="stats">
  <span>10x faster</span>
  <span>99.9% uptime</span>
  <span>1M+ users</span>
</div>
```

**Fix**:
```html
<!-- Option A: add real citations -->
<div class="stats">
  <span>10x faster <cite><a href="/methodology">see methodology</a></cite></span>
  <span>99.9% uptime <sup data-source="status-page-2024">†</sup></span>
  <span>1M+ users <cite>as of Q4 2024</cite></span>
</div>

<!-- Option B: replace with verifiable, specific claims -->
<div class="stats">
  <span>Reduced build time from 8 min to 45 sec in our own CI</span>
  <span>Status page history available at status.example.com</span>
  <span>47,000 active workspaces — updated monthly</span>
</div>
```

**Bypass**: `<!-- lint-disable invented-metrics -->` on the line above

---

### left-accent-card
**Severity**: medium
**Pattern**: `border-left` with a width of `3px`, `4px`, `0.25rem`, `0.1875rem` and a solid color value on an element that also has `padding`, `background`, or `border-radius` (i.e., a card-like container). Also catches Tailwind `border-l-4` or `border-l-[3px]` combined with `bg-*` and `p-*`.

**Example (bad)**:
```css
.feature-card {
  border-left: 4px solid #6366f1;
  padding: 1.5rem;
  background: #f8f9fa;
  border-radius: 0.5rem;
}
```

**Fix**:
```css
/* Choose a card treatment that fits the brand: full border, top accent,
   background tint, elevation, or icon-led. Left border = AI tells. */
.feature-card {
  border: 1px solid var(--color-border);
  padding: 1.5rem;
  border-radius: 0.5rem;
}
/* Or: top accent if deliberate */
.feature-card--accented {
  border-top: 3px solid var(--brand-primary);
  padding: 1.5rem;
  border-radius: 0 0 0.5rem 0.5rem;
}
```

**Bypass**: `<!-- lint-disable left-accent-card -->` on the line above

---

### stock-alt-text
**Severity**: medium
**Pattern**: `alt` attribute values matching (case-insensitive): empty string `""`, `"image"`, `"photo"`, `"picture"`, `"img"`, `"icon"`, `"logo"` (standalone), `"banner"`, `"thumbnail"`, `"screenshot"`, or any alt text that is a single generic noun without context. Also catches `alt` attributes containing only whitespace.

**Example (bad)**:
```html
<img src="hero.jpg" alt="image">
<img src="team-photo.jpg" alt="photo">
<img src="logo.svg" alt="">
```

**Fix**:
```html
<!-- Describe what the image communicates, not what it is. -->
<img src="hero.jpg" alt="Aerial view of downtown Portland at dusk, with the Willamette River reflecting city lights">
<img src="team-photo.jpg" alt="The Acme founding team of five people standing outside their first office in Austin, 2019">
<!-- Decorative images: use empty alt with role presentation -->
<img src="logo.svg" alt="Acme Inc." role="img">
<!-- Pure decoration: empty alt is correct -->
<img src="divider-wave.svg" alt="" role="presentation">
```

**Bypass**: `<!-- lint-disable stock-alt-text -->` on the line above

---

### excessive-shadow
**Severity**: medium
**Pattern**: A single `box-shadow` property value containing more than two comma-separated shadow layers on the same element. Also catches Tailwind's `shadow-2xl` and `shadow-3xl` combined with any other shadow utility on the same element.

**Example (bad)**:
```css
.card {
  box-shadow:
    0 1px 2px rgba(0,0,0,0.04),
    0 4px 8px rgba(0,0,0,0.08),
    0 12px 24px rgba(0,0,0,0.12),
    0 24px 48px rgba(0,0,0,0.06);
}
```

**Fix**:
```css
/* Two layers maximum. A base shadow + an ambient shadow is almost always enough. */
.card {
  box-shadow:
    0 1px 3px rgba(0,0,0,0.08),
    0 8px 24px rgba(0,0,0,0.10);
}
```

**Bypass**: `<!-- lint-disable excessive-shadow -->` on the line above

---

### gratuitous-blur
**Severity**: medium
**Pattern**: `backdrop-filter: blur()` or `-webkit-backdrop-filter: blur()` on any element that is not:
- A `<dialog>` or `[role="dialog"]`
- A `[role="alertdialog"]`
- An element with class containing `modal`, `overlay`, `drawer`, `sheet`, or `lightbox`
- An element with `position: fixed` and a high `z-index` (>= 100)

Also catches CSS `filter: blur()` on decorative blobs (elements with class containing `blob`, `glow`, `orb`, `bg-blur`, `blur-shape`).

**Example (bad)**:
```css
.feature-card:hover {
  backdrop-filter: blur(12px);
}
.hero::before {
  content: '';
  filter: blur(80px);
  background: #7c3aed;
  border-radius: 9999px;
}
```

**Fix**:
```css
/* Blur on hover cards: use a subtle background tint instead */
.feature-card:hover {
  background-color: var(--color-surface-hover);
}
/* Purple blob: if decorative elements are needed, use opacity and shape instead */
.hero::before {
  content: '';
  background: radial-gradient(var(--brand-primary-subtle) 0%, transparent 70%);
}
```

**Bypass**: `<!-- lint-disable gratuitous-blur -->` on the line above

---

### rainbow-gradient
**Severity**: high
**Pattern**: `linear-gradient()`, `radial-gradient()`, or `conic-gradient()` containing three or more color stops that span more than 180 degrees of the HSL hue wheel (i.e., the colors are not analogous — they read as rainbow or carnival). Detection approximates hue spread from hex/rgb values at stop positions.

**Example (bad)**:
```css
.cta-button {
  background: linear-gradient(90deg, #f97316, #eab308, #22c55e, #3b82f6, #a855f7);
}
.badge {
  background: linear-gradient(135deg, #ff0080, #7928ca, #0070f3);
}
```

**Fix**:
```css
/* Restrict gradients to analogous colors (within ~60° of hue wheel) or
   neutral-to-color fades. More than two hues = art project, not UI. */
.cta-button {
  background: linear-gradient(90deg, var(--brand-primary), var(--brand-secondary));
}
/* If a vibrant accent is needed, use a single bold color */
.badge {
  background: var(--brand-accent);
  color: var(--brand-accent-text);
}
```

**Bypass**: `<!-- lint-disable rainbow-gradient -->` on the line above

---

### default-rounded
**Severity**: medium
**Pattern**: `border-radius: 9999px`, `border-radius: 50%` (on non-circular elements), or Tailwind `rounded-full` on elements that are not:
- `<button>` elements with explicit pill intent
- Avatar/profile image containers
- Tags or badges (short single-line text chips)
- Elements with `aspect-ratio: 1` (circles)

Catches it on `<div>`, `<section>`, `<article>`, `<input>`, and card containers where full-round implies pill shape on a non-pill element.

**Example (bad)**:
```html
<div class="bg-white shadow-lg p-8 rounded-full">
  <h3>Feature Title</h3>
  <p>Feature description text goes here.</p>
</div>
```

**Fix**:
```html
<!-- Use a purposeful radius. Cards typically want 8–16px. -->
<div class="bg-white shadow-lg p-8 rounded-xl">
  <h3>Feature Title</h3>
  <p>Feature description text goes here.</p>
</div>
```

**Bypass**: `<!-- lint-disable default-rounded -->` on the line above

---

### ai-testimonial
**Severity**: critical
**Pattern**: Regex matching in `<blockquote>`, `[class*="testimonial"]`, `[class*="quote"]`, `[class*="review"]` text nodes:
- `"(I\s+love|I\s+really\s+love|absolutely\s+love)\s+this\s+(product|tool|app|platform|service)"`
- `"best\s+(tool|product|app|software|platform)\s+I('ve|\s+have)\s+ever\s+used"`
- `"changed\s+my\s+(life|business|workflow|everything)"`
- `"game.?changer"`
- `"(5\s+stars|five\s+stars|⭐{4,5})"`
- Any testimonial where the cited person has no last name, no role, no company, or only initials (e.g., "— John D." or "— Sarah, Happy Customer")

**Example (bad)**:
```html
<blockquote>
  "This tool changed my life. Best product I've ever used. A true game changer!"
  <cite>— Michael S., Business Owner</cite>
</blockquote>
```

**Fix**:
```html
<!-- Use real quotes from real people with full attribution.
     If you don't have real testimonials yet, omit the section entirely. -->
<blockquote>
  "We cut our monthly reporting time from 6 hours to 40 minutes in the first week."
  <cite>— Priya Mehta, Director of Operations, Clearline Logistics</cite>
</blockquote>
```

**Bypass**: `<!-- lint-disable ai-testimonial -->` on the line above (requires a comment explaining the source)

---

### filler-section
**Severity**: high
**Pattern**: Heading elements (h1–h4) or elements with `aria-label` matching (case-insensitive):
- `"why choose us"`
- `"our features"` / `"key features"` / `"core features"`
- `"get started today"` / `"get started"`
- `"meet our team"` / `"our team"`
- `"what we offer"` / `"what we do"`
- `"how it works"` (acceptable only when followed by ≥ 3 distinct steps with real content)
- `"about us"` (acceptable only when followed by > 100 words of body text)
- `"contact us"` (flagged only when it is the only heading in a `<section>`)
- `"our mission"` / `"our vision"` / `"our values"` without substantive body copy below

**Example (bad)**:
```html
<section>
  <h2>Why Choose Us</h2>
  <p>We are dedicated to providing the best possible experience for our customers.</p>
</section>

<section>
  <h2>Our Features</h2>
  <!-- three emoji-icon cards with one-line descriptions -->
</section>
```

**Fix**:
```html
<!-- Make the heading specific to the actual claim or benefit -->
<section>
  <h2>Built for teams that ship weekly, not quarterly</h2>
  <p>Our review queue processes 200 PRs/day without slowing down. Here's how.</p>
</section>

<section aria-label="Integration capabilities">
  <h2>Connects to the tools you already use</h2>
  <!-- specific integration list with logos -->
</section>
```

**Bypass**: `<!-- lint-disable filler-section -->` on the line above

---

### dark-mode-afterthought
**Severity**: medium
**Pattern**: A `@media (prefers-color-scheme: dark)` block that contains **only** `background-color`, `background`, `color`, and `border-color` property overrides, with no changes to:
- Shadows (`box-shadow`, `filter: drop-shadow`)
- Opacity values
- Image sources or filters
- Custom property redefinitions at `:root` or `[data-theme]` level
- Border thickness or style changes

Also flags a `prefers-color-scheme: dark` block where the number of overridden properties is fewer than 30% of the total light-mode declaration count for the same selectors.

**Example (bad)**:
```css
/* Light mode: rich shadows, warm tints, detailed card styles */
.card {
  background: #ffffff;
  color: #111827;
  box-shadow: 0 2px 8px rgba(0,0,0,0.12);
  border: 1px solid rgba(0,0,0,0.08);
}

@media (prefers-color-scheme: dark) {
  /* Just flip bg/text, ignore everything else */
  .card {
    background: #1f2937;
    color: #f9fafb;
  }
}
```

**Fix**:
```css
/* Use semantic tokens — redefine them in dark mode, let components inherit */
:root {
  --color-surface: #ffffff;
  --color-text: #111827;
  --color-shadow: rgba(0, 0, 0, 0.12);
  --color-border: rgba(0, 0, 0, 0.08);
}

@media (prefers-color-scheme: dark) {
  :root {
    --color-surface: #1f2937;
    --color-text: #f9fafb;
    --color-shadow: rgba(0, 0, 0, 0.40); /* shadows need to be stronger in dark mode */
    --color-border: rgba(255, 255, 255, 0.08);
  }
}

.card {
  background: var(--color-surface);
  color: var(--color-text);
  box-shadow: 0 2px 8px var(--color-shadow);
  border: 1px solid var(--color-border);
}
```

**Bypass**: `<!-- lint-disable dark-mode-afterthought -->` on the line above

---

## Quick Reference Table

| Rule ID | Severity | What it catches |
|---|---|---|
| `purple-gradient` | critical | #7c3aed / #8b5cf6 / violet in gradients |
| `indigo-default` | critical | #6366f1 / #4f46e5 / Tailwind indigo as primary |
| `lorem-ipsum` | critical | Placeholder copy, lorem ipsum text |
| `ai-testimonial` | critical | Fabricated or unattributed social proof quotes |
| `emoji-as-icon` | high | Unicode emoji used as UI icons |
| `inter-as-display` | high | Inter/system-ui on display/heading type |
| `invented-metrics` | high | Uncited performance claims and user counts |
| `rainbow-gradient` | high | 3+ hue-spanning color stops in gradients |
| `filler-section` | high | Generic section headings without specific claims |
| `left-accent-card` | medium | 3-4px left border on card containers |
| `stock-alt-text` | medium | Generic or empty alt attributes |
| `excessive-shadow` | medium | More than 2 box-shadow layers on one element |
| `gratuitous-blur` | medium | backdrop-filter/blob blur used decoratively |
| `default-rounded` | medium | border-radius: 9999px on non-pill elements |
| `dark-mode-afterthought` | medium | Dark mode that only swaps bg/text colors |
