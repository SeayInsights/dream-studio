# Interaction Design — Design Reference

Part of the dream-studio design reference library. Consult when designing forms, interactive elements, states, and user feedback patterns.

## Essential Interactive States

Every interactive element requires eight core states:

1. **Default** — Element at rest
2. **Hover** — Cursor over element (desktop/pointer devices only)
3. **Focus** — Element receives keyboard focus (visible to keyboard users)
4. **Active** — Element is being clicked or pressed
5. **Disabled** — Element cannot be interacted with
6. **Loading** — Async operation in progress
7. **Error** — Invalid state or failed operation
8. **Success** — Operation completed successfully

**Critical principle:** Hover and focus serve different users. Keyboard navigators never see hover states. Design both states independently—never assume focus implies hover or vice versa.

## Focus Management

### Focus Visibility

- **Never use `outline: none` without replacement.** This breaks keyboard accessibility for users relying on visible focus indicators.
- Use `:focus-visible` to show focus rings only for keyboard users (maintains visual clarity for pointer users).
- Focus ring requirements:
  - **Minimum contrast:** 3:1 against background
  - **Thickness:** 2–3px
  - **Placement:** Offset from element boundary (2–4px), not embedded
  - **Color:** High contrast (typically white or brand color on dark, or dark on light)

### Form Focus & Validation

- **Placeholders are not labels.** Placeholder text disappears on input and is not accessible. Always pair a visible `<label>` element with form fields.
- **Validate on blur, not keystroke.** Real-time keystroke validation creates excessive error noise. Validate when user leaves the field.
- **Show error states clearly:** Use red text, icons, or borders; never rely on color alone.

## Modern Interactive APIs

### Native `<dialog>` Element

```html
<dialog id="modal">
  <form method="dialog">
    <h2>Confirm Action</h2>
    <p>Are you sure?</p>
    <button type="submit" value="cancel">Cancel</button>
    <button type="submit" value="confirm">Confirm</button>
  </form>
</dialog>
```

Benefits:
- Automatic focus trapping within modal
- Escape key closes modal
- Backdrop overlay applied automatically
- Semantically correct

### Popover API

Use for tooltips, dropdowns, and light-dismiss overlays (feature support: Chrome 114+, Firefox 114+, Safari 17.4+):

```html
<button popovertarget="dropdown">Open Menu</button>
<div id="dropdown" popover>
  <button>Option 1</button>
  <button>Option 2</button>
</div>
```

Benefits:
- Built-in light-dismiss (click outside closes)
- Automatic z-index stacking (no z-index wars)
- Escape key closes
- Positioned on top layer

### CSS Anchor Positioning

Position overlays relative to triggers without JavaScript (Chrome 125+, Edge 125+):

```css
button {
  anchor-name: --trigger;
}

dropdown {
  position: fixed;
  top: calc(anchor(bottom) + 8px);
  left: anchor(left);
}
```

## Common Anti-Patterns

### Dropdown Clipping Bug

**Problem:** `position: absolute` dropdowns within `overflow: hidden` containers get clipped.

**Solutions:**
- Use `position: fixed` with calculated positioning
- Use Popover API (top layer escapes overflow)
- Use framework portals (React: `createPortal`, Vue: `<Teleport>`)

### Over-Confirmation

**Problem:** "Are you sure?" confirmation dialogs. Users click through them mindlessly without reading.

**Better pattern:**
1. Delete the item immediately
2. Show an undo button in a toast notification (5–8 second window)
3. Only use confirmation dialogs for truly irreversible actions (e.g., account deletion)

### Missing Skip Links

For keyboard navigation efficiency, always include skip links at the top of pages:

```html
<a href="#main" class="skip-link">Skip to main content</a>
```

Style to be invisible until focused (not `display: none`).

## Form Patterns

### Accessible Form Fields

- Always pair `<label>` with `<input>` using `for` attribute or nesting
- Use semantic HTML: `<input type="email">`, `<input type="tel">`, etc.
- Group related fields with `<fieldset>` and `<legend>`
- Provide helpful error messages next to fields, not in modals

### Loading States

- Show inline spinners or skeleton loaders for form submissions
- Disable the submit button during submission with aria-busy
- Display progress for long operations (>1 second)

### Error States

- Display validation errors on blur, not submit
- Show field-level errors inline, not in a summary dialog
- Use color + icon + text (never color alone for accessibility)
- Preserve filled values when showing errors (don't clear the form)

### Success States

- Brief confirmation message or toast (not required for every action)
- Redirect or state update after successful form submission
- Clear any error states once the user corrects input

## Keyboard Navigation

### Roving Tabindex Pattern

For lists or menus where only one item is in tab order:

```html
<div role="list">
  <button role="listitem" tabindex="0">First</button>
  <button role="listitem" tabindex="-1">Second</button>
  <button role="listitem" tabindex="-1">Third</button>
</div>
```

- Use Arrow keys to navigate
- Only one item has `tabindex="0"` at a time
- Pressing Tab moves focus out of the list entirely

### Skip Links

Place at the top of the page:

```html
<a href="#main" class="sr-only">Skip to main content</a>
```

When focused, reveals full text and jumps to main content region.

## Loading & Async Patterns

- **Inline spinners:** Prefer within the component needing data
- **Skeleton loaders:** Preview layout while data loads (better perceived performance)
- **Timeout messaging:** If async > 3–5 seconds, show user a message ("This is taking longer than usual...")
- **Error recovery:** Provide retry button if async operation fails

## Empty States

When a container or list has no content:

1. **Empty container message:** Brief, friendly explanation
2. **Optional call-to-action:** "Create your first item" or "Import data"
3. **Icon or illustration:** Visual anchor (optional but recommended)

Avoid: Leaving empty containers completely blank or showing an error

## Design Checklist

- [ ] All interactive elements have default, hover, focus, and active states
- [ ] Focus ring is visible, contrasts at 3:1 minimum, and is 2–3px thick
- [ ] Form labels are always visible (not placeholder text alone)
- [ ] Form validation occurs on blur, not keystroke
- [ ] Errors are shown inline with field, not in modal
- [ ] Dropdowns use fixed positioning or Popover API (not absolute within overflow:hidden)
- [ ] Confirmation dialogs only used for irreversible actions
- [ ] Successful operations have clear feedback (toast, state update)
- [ ] Keyboard navigation is efficient (roving tabindex, skip links)
- [ ] Loading states are shown for async > 1 second
- [ ] Empty states explain what to do next
- [ ] All color signals include text or icon fallbacks
