---
name: accessibility-expert
description: Audit and remediate WCAG 2.2 accessibility issues in web interfaces using automated tools and manual testing procedures.
---

## Patterns

- Use semantic HTML before ARIA. Native elements carry implicit roles, keyboard behavior, and focus management.
- Focus management: trap focus in modals; restore to trigger on close; move focus to page heading on route change.
- Keyboard navigation order must match the visual reading order (DOM order drives tab sequence).
- Color contrast: 4.5:1 minimum for normal text, 3:1 for large text (18pt / 14pt bold), 3:1 for UI components.
- Touch targets: minimum 44x44 CSS pixels (WCAG 2.2 SC 2.5.8). Use padding to expand without changing visual size.
- Alt text: decorative = `alt=""`, informative = describe content, functional = describe the action.
- Form labels: explicit `<label for>` preferred; `aria-label` when no visible text needed; `aria-labelledby` to reuse existing text.
- Skip navigation: first focusable element on page, visually hidden until focused, points to `#main-content`.
- Live regions: `aria-live="polite"` for status/results; `role="alert"` for critical errors. Keep injected text concise.

## Anti-Patterns

- Color alone to convey state or error -- always pair with icon, pattern, or text label.
- Placeholder text as the only label for an input -- placeholder disappears on type.
- `tabindex` values greater than 0 -- breaks the natural tab order and creates a parallel focus sequence.
- `display:none` or `visibility:hidden` on content that screen readers should reach -- use sr-only CSS instead.
- Overriding correct implicit HTML semantics with ARIA roles (e.g., `role="presentation"` on a semantic element, `role="button"` on `<a>`).

## Gotchas

- NVDA+Chrome and JAWS+Edge expose ARIA differently. Test both before calling a component accessible.
- VoiceOver on iOS uses swipe navigation and does not fire keydown events. Desktop-passing components can fail on iPhone.
- Dynamic content injected into the DOM after a user action is invisible to screen readers unless a live region or focus move is in place.
- Modal dialogs without a focus trap allow Tab to cycle into the obscured background. Apply `inert` to background content.
- Custom comboboxes need the full ARIA combobox keyboard pattern: arrows, Enter, Escape, Home, End, type-ahead.
- Toggle buttons need `aria-pressed`; disclosure widgets need `aria-expanded`; tabbed UIs need `aria-selected`. Missing required ARIA states fail axe-core.

## Checklist

### Automated audit (run first)
- [ ] Run axe-core: `npx axe-cli https://localhost:3000 --include main`
- [ ] Run Lighthouse accessibility audit in Chrome DevTools (score 90+ before manual review)
- [ ] Run `npx accessibility-checker` if IBM checker is available

### Keyboard audit
- [ ] Tab through every interactive element -- confirm logical order
- [ ] Every action reachable and operable without a mouse
- [ ] Modals trap focus and restore on close
- [ ] Skip link appears on first Tab press and works
- [ ] Custom components (dropdowns, date pickers) pass full ARIA keyboard spec

### Screen reader audit
- [ ] NVDA + Chrome: heading structure, form labels, live regions, modal behavior
- [ ] VoiceOver + Safari (macOS): same flow
- [ ] VoiceOver + iOS (iPhone): key interactive components
- [ ] All images have appropriate alt text (decorative vs informative vs functional)

### Visual audit
- [ ] Check contrast ratios with browser DevTools or https://webaim.org/resources/contrastchecker/
- [ ] Information is not conveyed by color alone
- [ ] Touch targets are at least 44x44px on mobile viewport
- [ ] Focus indicator is visible and has 3:1 contrast against adjacent colors (WCAG 2.2 SC 2.4.11)

### Remediation priority framework
1. Critical (block release): missing keyboard access, missing form labels, broken focus trap in modal
2. High (fix in current sprint): contrast failures, missing alt text on functional images, dynamic content not announced
3. Medium (fix in next sprint): touch target too small, missing skip link, ARIA required attributes absent
4. Low (track and improve): non-critical ARIA enhancements, improved screen reader verbosity

## Tools / Commands

```bash
# Install and run axe CLI against a local dev server
npm install -g @axe-core/cli
axe http://localhost:3000 --include main --reporter html > axe-report.html

# Lighthouse CLI accessibility audit
npx lighthouse http://localhost:3000 --only-categories=accessibility --output html --output-path ./lighthouse-a11y.html

# Check for missing alt attributes across the codebase
grep -rn 'img ' src/ | grep -v 'alt='

# Find tabindex > 0 usage
grep -rn 'tabindex="[1-9]' src/

# Run markuplint with a11y rules (if configured)
npx markuplint "src/**/*.html" "src/**/*.tsx"

# Color contrast check via CLI (requires contrast-ratio package)
npx color-contrast "#1a1a1a" "#ffffff"
```
