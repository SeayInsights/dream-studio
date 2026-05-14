# DreamySuite Canvas Patterns

Visual builder architecture patterns extracted from production open-source builders.
Referenced by: dashboard-dev

Sources: Webstudio (inflator.ts), GrapesJS (canvas/, undo_manager/), Frappe Builder (block.ts, canvasStore.ts, AIPageGeneratorModal.vue), VvvebJs (components-*.js)

---

## 1. Zero-Size Inflation (Webstudio inflator pattern)

**Problem:** Empty container components collapse to 0×0px and become unselectable, undeletable, and invisible to the user.

**Solution:** Use a `MutationObserver` watching the canvas subtree. On each mutation batch (debounced via `requestAnimationFrame`), check all elements for zero bounding rect. For elements where both width and height are 0:
- Add a `data-ds-inflated` attribute
- Apply synthetic `min-height` and `min-width` (e.g., 75px) via inline style override
- For grid containers, inflate collapsed tracks using `minmax(75px, 0px)` on individual track definitions

**Critical distinction:** Distinguish "empty" (should inflate) from "intentionally zero" (user set height: 0 explicitly — do NOT inflate). Check whether the element has user-authored style declarations before inflating.

**When to remove inflation:** Remove the synthetic padding immediately when the element receives content (child elements or text). Re-check on every MutationObserver callback.

---

## 2. Canvas Overlay Pattern (GrapesJS CanvasSpots)

**Problem:** Selection handles, resize grips, hover outlines, and floating toolbars placed inside the canvas DOM fight with page layout and z-index stacking.

**Solution:** Maintain a separate overlay `<div>` positioned absolutely above the canvas iframe. ALL builder chrome (selection boxes, handles, toolbars, hover rings) renders in this overlay — never injected into the page DOM inside the iframe.

**Coordinate translation:**
1. Get the element's bounding rect in iframe space: `iframe.contentDocument.getElementById(id).getBoundingClientRect()`
2. Get the iframe's offset in host space: `iframeEl.getBoundingClientRect()`
3. Translate: `hostX = iframeRect.left + elementRect.left * zoomFactor`
4. Apply to the overlay element: `overlayEl.style.left = hostX + 'px'`

**Benefits:**
- Overlay chrome doesn't affect page layout or trigger reflows in the iframe
- Overlay can extend beyond iframe bounds (e.g., a toolbar that overlaps the panel)
- z-index battles are structurally eliminated — overlay is always on top

---

## 3. Four-Tier Responsive Style Cascade (Frappe Builder block.ts)

**Problem:** Naive inline-style editing doesn't support per-breakpoint overrides cleanly.

**Solution:** Store styles in four separate maps per component instance:

```javascript
{
  baseStyles: {},      // default styles (desktop)
  tabletStyles: {},    // tablet overrides
  mobileStyles: {},    // mobile overrides
  rawStyles: {}        // styles that bypass cascade (layout calculations)
}
```

**Write routing:** When the canvas is in a breakpoint mode, write style changes to the correct tier only:
- Desktop mode → write to `baseStyles`
- Tablet mode → write to `tabletStyles`
- Mobile mode → write to `mobileStyles`

**Read cascade:** `getStyle(breakpoint)` merges tiers in order (mobile overrides tablet overrides base):
```javascript
function getStyle(breakpoint) {
  const base = { ...component.baseStyles };
  if (breakpoint <= TABLET) Object.assign(base, component.tabletStyles);
  if (breakpoint <= MOBILE) Object.assign(base, component.mobileStyles);
  return base;
}
```

**Override detection:** `hasOverrides(breakpoint)` returns true if the component has breakpoint-specific styles diverging from base — use this to show a "reset to base" button in the UI.

---

## 4. Drag Placeholder as Raw DOM (Frappe canvasStore)

**Problem:** Showing a drop placeholder via reactive state (React/Vue state) triggers a full component re-render on every `dragover` event, causing jank and performance issues.

**Solution:** Inject the drop placeholder as a raw DOM element — completely outside the framework's reactive system:

```javascript
function insertDropPlaceholder(targetEl, position) {
  const placeholder = document.createElement('div');
  placeholder.id = 'ds-drop-placeholder';
  placeholder.style.cssText = 'height: 4px; background: #6366f1; border-radius: 2px; margin: 2px 0;';
  targetEl.insertAdjacentElement(position, placeholder);
}

function removeDropPlaceholder() {
  document.getElementById('ds-drop-placeholder')?.remove();
}
```

Call `insertDropPlaceholder` in `dragover`, `removeDropPlaceholder` in `dragleave` and `drop`. Only update reactive state in the `drop` handler — after the placeholder is removed.

---

## 5. Grouped Undo (GrapesJS magicFusionIndex)

**Problem:** Operations that set multiple properties simultaneously (e.g., applying a style preset, pasting a component) create dozens of separate undo entries, requiring dozens of Ctrl+Z presses to undo one user action.

**Solution:** Group related mutations into a single undo step:

```javascript
// Open a group before batch operations
undoManager.startGroup();

// All mutations within the group are fused
component.setStyle({ color: 'red', fontSize: '16px', fontWeight: 'bold' });
component.setAttribute('data-theme', 'primary');

// Close the group — everything above = ONE undo step
undoManager.stopGroup();
```

**Implementation:** Track a `groupActive` flag and a `groupedMutations[]` buffer. When `stopGroup()` is called, push the entire buffer as a single entry on the undo stack. On undo, replay all mutations in the group in reverse.

**When to use:** Any operation that sets more than 2 properties atomically — style preset application, component duplication, paste from clipboard, AI-generated content insertion.

---

## 6. Declarative Property Panel (VvvebJs properties[] pattern)

**Problem:** Each component type requires hand-coded property panel UI, causing duplication and inconsistency.

**Solution:** Components expose a `properties[]` array in their definition. The property panel renders automatically from this array — no per-component panel code needed:

```javascript
{
  name: 'Hero Section',
  html: '<section class="hero">...</section>',
  properties: [
    {
      key: 'background-color',
      inputtype: 'color',
      label: 'Background Color',
      defaultValue: '#ffffff'
    },
    {
      key: 'data-layout',
      inputtype: 'select',
      label: 'Layout',
      options: ['left', 'center', 'right'],
      defaultValue: 'center'
    },
    {
      key: 'padding',
      inputtype: 'range',
      label: 'Padding',
      min: 0, max: 120, unit: 'px',
      defaultValue: 60
    }
  ]
}
```

The panel iterates `properties[]`, renders the appropriate input for each `inputtype`, and calls `onChange` when the user edits a value. Adding a new configurable property = adding one object to the array.

**Input type registry:** Register input types globally (`colorpicker`, `fontFamily`, `googleFont`, `slider`, `select`, `text`, `toggle`). Any component can reference any registered type by name.

---

## 7. AI → Canvas Pipeline (Frappe AIPageGeneratorModal pattern)

**Problem:** AI-generated content needs to be deserialized into the canvas's component tree format, not just rendered as raw HTML.

**Solution:** Full pipeline from prompt to canvas:

1. **Prompt construction:** Send user's natural language prompt to the AI endpoint. System prompt must include the exact JSON schema for components — the AI must know the exact shape to output.

2. **AI response:** AI returns a JSON array of block objects matching the component schema:
```json
[
  {
    "type": "hero",
    "props": { "layout": "center", "background-color": "#1a1a2e" },
    "children": [
      { "type": "heading", "props": { "level": 1 }, "content": "Welcome" },
      { "type": "button", "props": { "variant": "primary" }, "content": "Get Started" }
    ]
  }
]
```

3. **Deserialization:** Iterate the JSON, construct component instances from the type registry, set props, wire parent-child relationships.

4. **Canvas insertion:** Insert the root components at the current drop target or replace the selected region.

**Key requirement:** The AI system prompt MUST specify the exact JSON schema with field names, types, allowed values for each `type`, and the children array structure. Without this, the AI produces incompatible JSON that fails deserialization.

**Error handling:** Validate each block's `type` against the component registry before inserting. Unknown types get replaced with a "Unknown Component" placeholder that is visible on canvas but doesn't break the tree.
