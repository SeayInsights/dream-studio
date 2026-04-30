# Feature Specification: DreamySuite UX & Architecture Refactor

**Topic Directory**: `.planning/specs/dreamysuite-ux-refactor/`  
**Created**: 2026-04-27  
**Status**: Draft  
**Input**: User description: "Address 8 critical UX/architecture issues in dreamysuite editor"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Element Visibility & Canvas Bounds (Priority: P1)

A user adds a video element to their wedding site homepage. The element should always remain visible and movable within the canvas bounds, never rendering outside where it becomes inaccessible.

**Why this priority**: P1 - This is a critical bug blocking users from editing their sites. Elements rendering outside the canvas make the editor unusable.

**Independent Test**: Can be fully tested by adding elements to a page, resizing/moving them, and verifying they remain visible and accessible within the canvas viewport. Delivers immediate value by making the editor functional.

**Acceptance Scenarios**:

1. **Given** a user adds any element to the canvas, **When** they resize or move it, **Then** the element remains within visible canvas bounds
2. **Given** an element is positioned near canvas edge, **When** user switches breakpoints, **Then** the element adjusts but remains visible and selectable
3. **Given** elements exist from previous sessions, **When** user opens the editor, **Then** all elements are visible and within canvas bounds

---

### User Story 2 - Consistent Breakpoint Layout (Priority: P1)

A user designs their homepage on desktop with a video element above a countdown element. When they preview on tablet or mobile, the layout order should remain consistent unless they explicitly override it.

**Why this priority**: P1 - Layout inconsistency across breakpoints breaks the user's design intent and creates confusion. This is core to responsive design functionality.

**Independent Test**: Can be tested by creating a page with multiple elements on desktop, then switching breakpoints and verifying element order is preserved. Delivers value by ensuring design intent transfers across devices.

**Acceptance Scenarios**:

1. **Given** a user arranges elements A-B-C on desktop, **When** they switch to tablet breakpoint, **Then** elements remain in A-B-C order unless overridden
2. **Given** a user explicitly reorders elements on mobile, **When** they switch back to desktop, **Then** desktop layout is unchanged
3. **Given** a user adds a new element on tablet, **When** they switch to desktop, **Then** the new element appears in the same relative position

---

### User Story 3 - Streamlined Inspector (Priority: P1)

A user selects a video element and wants to adjust its styling and layout. They should find all properties organized in 2 intuitive tabs: Design (visual properties) and Advanced (layout/behavior).

**Why this priority**: P1 - The current 5-tab inspector creates cognitive overload. Consolidating to 2 tabs (like Wix Studio, Framer) dramatically improves usability and matches industry standards.

**Independent Test**: Can be tested by selecting any element and verifying all properties are accessible in 2 clearly labeled tabs. Delivers value by reducing friction and improving discoverability.

**Acceptance Scenarios**:

1. **Given** a user selects any element, **When** they open the inspector, **Then** they see exactly 2 tabs: "Design" and "Advanced"
2. **Given** a user wants to change colors/fonts/spacing, **When** they click the Design tab, **Then** all visual properties are grouped logically
3. **Given** a user wants to change position/size/animations, **When** they click the Advanced tab, **Then** all layout/behavior properties are grouped logically

---

### User Story 4 - Consolidated Left Sidebar (Priority: P2)

A user wants to navigate between pages, add elements, and adjust theme settings. They should find these organized in logical groups in the left sidebar, not scattered across 10+ separate icons.

**Why this priority**: P2 - The current 10-item sidebar is too fragmented. Consolidation improves navigation efficiency, but the editor is still usable with current structure.

**Independent Test**: Can be tested by accessing all core functions (pages, elements, layers, theme, media) through the reorganized sidebar. Delivers value by reducing visual clutter and improving information architecture.

**Acceptance Scenarios**:

1. **Given** a user clicks "Add" in the sidebar, **When** the panel opens, **Then** they see elements, media, and effects grouped in sections
2. **Given** a user clicks "Pages" in the sidebar, **When** the panel opens, **Then** they see pages, navigation, and layers grouped together
3. **Given** a user clicks "Site" in the sidebar, **When** the panel opens, **Then** they see theme, settings, language, and music grouped together

---

### User Story 5 - Improved Selection Highlights (Priority: P2)

A user selects an element on the canvas. The selection should show a clear, prominent outline that doesn't obscure the content, with visible handles for resize/move operations.

**Why this priority**: P2 - Better visual feedback improves editing confidence and reduces errors, but current selection works functionally.

**Independent Test**: Can be tested by selecting elements and verifying the highlight is visible, clear, and doesn't interfere with content visibility. Delivers value through improved UX polish.

**Acceptance Scenarios**:

1. **Given** a user selects an element, **When** the selection renders, **Then** a 2px solid outline appears with contrasting color
2. **Given** a user hovers over an unselected element, **When** the hover state renders, **Then** a 1px dashed outline appears
3. **Given** multiple elements overlap, **When** a user selects the top element, **Then** the selection outline is visible above other elements

---

### User Story 6 - Enhanced Resize Handles (Priority: P2)

A user wants to resize an element. They should see clear, touch-friendly handles on all 8 positions (corners and edges) with proper visual hierarchy.

**Why this priority**: P2 - Better resize handles improve precision and reduce frustration, but current handles work functionally.

**Independent Test**: Can be tested by selecting an element and verifying 8 handles are visible and usable for resizing. Delivers value through improved interaction quality.

**Acceptance Scenarios**:

1. **Given** a user selects an element, **When** the resize handles render, **Then** 8 handles appear at corners and edge midpoints
2. **Given** a user hovers over a resize handle, **When** the hover state activates, **Then** the handle scales 1.2x and cursor changes appropriately
3. **Given** a user drags a resize handle, **When** resizing, **Then** the element resizes smoothly with live preview

---

### User Story 7 - Refined Floating Toolbars (Priority: P3)

A user double-clicks an element to edit its content. A floating toolbar should appear with contextual actions, positioned intelligently to avoid obscuring content.

**Why this priority**: P3 - Floating toolbar improvements enhance workflow efficiency but are not blocking core functionality.

**Independent Test**: Can be tested by double-clicking elements and verifying toolbars appear with relevant actions. Delivers value through workflow optimization.

**Acceptance Scenarios**:

1. **Given** a user double-clicks a text element, **When** the toolbar appears, **Then** it shows text formatting actions (bold, italic, alignment)
2. **Given** a user double-clicks a video element, **When** the toolbar appears, **Then** it shows media-specific actions (replace, crop, effects)
3. **Given** a toolbar would render off-screen, **When** it calculates position, **Then** it repositions to remain fully visible

---

### User Story 8 - Page vs Element Control Clarity (Priority: P3)

A user wants to change the page background color. They should understand that page-level properties are in the top bar or page panel, not the element inspector.

**Why this priority**: P3 - Clearer separation improves discoverability but doesn't block current workflows.

**Independent Test**: Can be tested by accessing page settings through dedicated UI and verifying element inspector only shows element properties. Delivers value through improved mental model.

**Acceptance Scenarios**:

1. **Given** no element is selected, **When** user opens inspector, **Then** it shows page-level settings (background, effects, SEO)
2. **Given** an element is selected, **When** user opens inspector, **Then** it shows only element-level properties
3. **Given** a user wants page navigation settings, **When** they click breadcrumb or page icon, **Then** page settings panel opens

---

### Edge Cases

- What happens when an element is positioned outside canvas during data migration from old version?
- How does the system handle custom CSS that conflicts with new layout constraints?
- What happens when a user has 50+ elements on a page and selects overlapping elements?
- How do breakpoint overrides work when the base element is deleted?
- What happens to floating toolbars when canvas zoom level changes?
- How are keyboard shortcuts handled when both inspector tabs support similar properties?
- What happens to elements with manual z-index when new stacking context is introduced?

## Requirements *(mandatory)*

### Functional Requirements

**Canvas & Element Positioning:**
- **FR-001**: System MUST constrain all elements within canvas bounds during move/resize operations
- **FR-002**: System MUST auto-scroll canvas when dragging elements near viewport edges
- **FR-003**: System MUST migrate existing out-of-bounds elements to visible positions on editor load
- **FR-004**: System MUST prevent elements from being positioned with negative coordinates relative to page origin

**Responsive Breakpoint System:**
- **FR-005**: System MUST preserve element order across breakpoints unless explicitly overridden
- **FR-006**: System MUST cascade breakpoint overrides: mobile inherits from tablet, tablet inherits from desktop
- **FR-007**: System MUST visually indicate when an element has breakpoint-specific overrides
- **FR-008**: Users MUST be able to reset breakpoint overrides to inherit from parent breakpoint

**Inspector Redesign:**
- **FR-009**: System MUST consolidate inspector from 5 tabs to 2 tabs: "Design" and "Advanced"
- **FR-010**: Design tab MUST contain: colors, typography, spacing, borders, shadows, backgrounds
- **FR-011**: Advanced tab MUST contain: layout, position, size, animations, effects, custom CSS
- **FR-012**: System MUST auto-switch to relevant tab when user performs related action (e.g., drag → Advanced tab)

**Left Sidebar Consolidation:**
- **FR-013**: System MUST reduce left sidebar from 10 items to 4 primary sections: "Add", "Pages", "Site", "Settings"
- **FR-014**: "Add" section MUST group: Elements, Media, Effects sub-panels
- **FR-015**: "Pages" section MUST group: Page list, Navigation config, Layers view
- **FR-016**: "Site" section MUST group: Theme, Language, Music, Global settings

**Selection & Interaction:**
- **FR-017**: System MUST render selection outline as 2px solid line with high contrast color
- **FR-018**: System MUST render hover outline as 1px dashed line with 50% opacity
- **FR-019**: System MUST show element label badge on selection outline top-left
- **FR-020**: System MUST support selection cycling when clicking overlapped elements

**Resize Handles:**
- **FR-021**: System MUST render 8 resize handles (4 corners + 4 edges) on selected elements
- **FR-022**: Resize handles MUST have 10px visual size and 44px touch target for accessibility
- **FR-023**: Resize handles MUST scale 1.2x on hover and show appropriate cursor
- **FR-024**: System MUST maintain aspect ratio when shift-key held during corner resize

**Floating Toolbars:**
- **FR-025**: System MUST show contextual toolbar on double-click with element-specific actions
- **FR-026**: Toolbar MUST reposition to remain within viewport bounds
- **FR-027**: Toolbar MUST close when clicking outside or pressing Escape
- **FR-028**: System MUST prevent toolbar overlap with inspector panel

**Page vs Element Separation:**
- **FR-029**: Inspector MUST show page settings when no element is selected
- **FR-030**: Inspector MUST show element settings when element is selected
- **FR-031**: System MUST provide breadcrumb navigation for page hierarchy
- **FR-032**: Top bar MUST provide quick access to page-level settings (publish, preview, SEO)

### Key Entities

- **EditorState**: Manages canvas viewport, zoom level, scroll position, out-of-bounds detection
- **InspectorConfig**: Defines tab structure, property groups, conditional visibility rules
- **SidebarSection**: Defines sidebar items, nesting structure, panel routing
- **SelectionState**: Manages selected/hovered elements, outline rendering, handle positions
- **BreakpointOverride**: Tracks element property overrides per breakpoint with inheritance chain
- **ToolbarContext**: Defines toolbar content based on element type and current editing mode

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of elements remain within canvas bounds after move/resize operations (0 out-of-bounds elements)
- **SC-002**: Element order consistency: 100% match between desktop layout order and tablet/mobile (unless overridden)
- **SC-003**: Inspector tab reduction: 60% fewer tabs (5 → 2) with 100% property coverage
- **SC-004**: Sidebar consolidation: 60% fewer top-level items (10 → 4) with <3 clicks to any feature
- **SC-005**: Selection visibility: 95%+ users successfully identify selected element in user testing
- **SC-006**: Resize accuracy: 90%+ users successfully resize elements to target dimensions within 2 attempts
- **SC-007**: Page load performance: <100ms overhead from new selection/resize rendering system
- **SC-008**: Code maintainability: Inspector code LOC reduced by 40% through consolidation

## Assumptions

- Canvas rendering uses absolute positioning within a scrollable container (verified in current code)
- Breakpoint system already supports overrides via `overrides` property on blocks (verified in document store)
- Element data structure supports adding new metadata fields without schema migration
- Users have modern browsers with ResizeObserver and pointer events support
- Existing element types (video, countdown, gallery, etc.) will work with new inspector structure
- Current Zustand store architecture (editorStore) supports new state requirements
- Designer has capacity to create new selection/handle graphics if needed

## Research: Visual Editor Best Practices Analysis

### Industry Patterns (Wix Studio, Webflow, Framer)

**Wix Studio Approach:**
- Inspector panel is the "control center" for each element
- Primary "Design" tab for visual properties (size, colors, borders, shadows)
- Secondary tabs for Layout, Position, and CMS integration
- Consolidated approach: everything for an element in one place
- Responsive behavior controls integrated into Design tab

**Webflow Approach:**
- Interface mirrors CSS box model directly
- Right-side properties panel with CSS-like controls
- Separate panels for Structure, Classes, and Settings
- More technical, developer-oriented interface
- Strong separation between structure (left) and properties (right)

**Framer Approach:**
- Minimalist interface inspired by Figma
- Single right-side panel with property sections
- Auto-layout handles responsive behavior
- Real-time collaboration support
- Drag-and-drop canvas with live preview

**Key Takeaways:**
1. **2-tab pattern wins**: All modern editors use 1-2 primary tabs for properties, not 5+
2. **Design-first hierarchy**: Visual properties (Design) always come before technical properties (Advanced/Layout)
3. **Contextual property groups**: Properties grouped by function, not by implementation
4. **Left = navigation, Right = properties**: Clear spatial separation of concerns
5. **Inline editing + inspector**: Floating toolbars for quick edits, inspector for deep configuration

### Selection & Manipulation Patterns

**Figma/Framer Standard:**
- 2px solid outline for selection
- 8 resize handles (corners + edges)
- Blue/purple accent color for handles
- Label badge top-left corner
- Hover state with dashed outline

**Webflow Approach:**
- Colored outline with element type indicator
- Click-through to parent elements
- Breadcrumb navigation in selection

**Best Practice Synthesis:**
- Use high-contrast, solid outline (2-3px)
- 8 handles with large touch targets (44px minimum)
- Clear visual hierarchy: selection > hover > default
- Label badges for context
- Support for nested selection cycling

## Approach Analysis

### Approach 1: Incremental Refactor (Recommended)

**Description**: Address issues in 3 phases over multiple PRs, maintaining backward compatibility.

**Phase 1 - Canvas Fixes (P1):**
- Fix out-of-bounds rendering via CSS containment and bounds checking
- Implement breakpoint order preservation in cascade logic
- Add migration script for existing out-of-bounds elements
- Estimated: 2-3 days, 4-6 files modified

**Phase 2 - Inspector & Sidebar Consolidation (P1-P2):**
- Create new 2-tab inspector structure
- Migrate property components to new tab groups
- Consolidate sidebar to 4 sections with nested panels
- Add feature flag for gradual rollout
- Estimated: 4-5 days, 15-20 files modified

**Phase 3 - Interaction Polish (P2-P3):**
- Enhanced selection highlights
- Improved resize handles
- Refined floating toolbars
- Page vs element clarity improvements
- Estimated: 2-3 days, 8-10 files modified

**Pros:**
- Lower risk: each phase independently testable
- Faster time-to-value: P1 issues fixed first
- Easier code review: smaller, focused PRs
- Backward compatible: old data works with new code
- Team can learn and adapt between phases

**Cons:**
- Longer total timeline: 8-11 days vs. 5-7 days big-bang
- Temporary inconsistency: mixed old/new UI during transition
- Requires feature flags and migration logic
- More PRs to manage (6-9 PRs vs. 2-3)

**Technical Approach:**
- Use CSS containment (`contain: layout`) for canvas bounds
- Implement `getEffectiveOrder()` function for breakpoint inheritance
- Create new `InspectorV2.tsx` component, feature-flagged
- Refactor `IconRail` to `SidebarNav` with nested panels
- Enhance `SelectionLayer` and `DragHandles` rendering

**Migration Strategy:**
- Add `editorVersion: 2` flag to user preferences
- Run migration on editor load to fix out-of-bounds elements
- Support both inspector versions during transition
- Analytics to track adoption and issues

---

### Approach 2: Big-Bang Refactor

**Description**: Rewrite the entire editor UI in one large effort, shipping all improvements together.

**Implementation:**
- Create parallel `editor-v3` directory
- Rebuild inspector, sidebar, canvas, selection from scratch
- Single cutover moment for all users
- Estimated: 5-7 days, 40-60 files modified

**Pros:**
- Cleaner codebase: no legacy support code
- Consistent UX: all improvements land together
- Simpler mental model: one version, no flags
- Opportunity to fix technical debt holistically

**Cons:**
- High risk: massive PR, hard to review thoroughly
- Longer wait for fixes: users suffer with bugs until full ship
- Harder to test: integration testing surface is huge
- Difficult to isolate regressions when they occur
- Higher chance of scope creep and delays

**Technical Approach:**
- Copy `editor-v2` to `editor-v3`
- Rewrite components in dependency order
- Create comprehensive test suite before cutover
- Dark launch to beta users first

---

### Approach 3: Hybrid (New Components, Gradual Migration)

**Description**: Build new components alongside old ones, migrate individual features piecemeal using a "strangler fig" pattern.

**Implementation:**
- Create `InspectorV2.tsx`, `SidebarNavV2.tsx` as separate components
- Route to V2 components via feature flags or user preference
- Migrate users gradually via A/B test or opt-in
- Eventually deprecate V1 components
- Estimated: 6-9 days, 25-35 files modified

**Pros:**
- Lower risk than big-bang: failures isolated to V2 components
- A/B testable: measure impact on user behavior
- Allows for user feedback before full rollout
- Old and new can coexist during validation

**Cons:**
- Code duplication: maintaining two versions
- Complexity: routing logic, feature flags, state sync
- Delayed cleanup: old code lingers for months
- Requires more coordination across team

**Technical Approach:**
- Build V2 components with clean interfaces
- Share state via Zustand store
- Use feature flag system (e.g., `useEditorV2: boolean`)
- Analytics to compare V1 vs V2 metrics

---

## Recommendation: Approach 1 (Incremental Refactor)

**Rationale:**

1. **Risk mitigation**: Breaking the work into 3 phases allows us to validate each change independently. If Phase 1 introduces a regression, we catch it before building Phase 2 on top.

2. **Faster time-to-value**: The P1 issues (out-of-bounds elements, breakpoint consistency) are blocking users *today*. Approach 1 lets us ship fixes in 2-3 days instead of waiting 5-7 days for the full refactor.

3. **Code review quality**: Smaller PRs (4-6 files vs 40-60 files) are easier to review thoroughly, reducing the chance of bugs slipping through.

4. **Maintainability**: The incremental approach forces us to think about backward compatibility and migration, which are valuable long-term. Approach 2's big-bang could leave us with data migration issues we didn't foresee.

5. **Team learning**: Each phase provides feedback that informs the next phase. For example, if Phase 2 reveals that users struggle with the 2-tab inspector, we can adjust Phase 3's toolbar design accordingly.

**Why not Approach 2?** Too risky for a production editor with existing user data. A 40-60 file PR is nearly impossible to review thoroughly, and any regressions will affect all users simultaneously.

**Why not Approach 3?** The overhead of maintaining two versions outweighs the benefits. Feature flags are valuable, but full component duplication leads to code rot and confusion.

**Implementation Plan:**

Phase 1 (Week 1): Canvas bounds + breakpoint order → immediate user relief  
Phase 2 (Week 2): Inspector + sidebar consolidation → improved daily workflow  
Phase 3 (Week 3): Interaction polish → professional, delightful experience  

Each phase is independently shippable and testable, de-risking the overall project.

---

## Technical Architecture Details

### Canvas Bounds Constraint System

**Problem**: Elements can be positioned with negative coordinates or beyond canvas width, making them invisible and inaccessible.

**Solution**: Implement bounds checking in drag/resize operations with auto-correction.

**Key Components:**

1. **BoundsCalculator** (new utility):
```typescript
// Pseudo-code
interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

function getCanvasBounds(canvasRef: HTMLElement): Bounds {
  const { width, height } = canvasRef.getBoundingClientRect();
  return {
    minX: 0,
    minY: 0,
    maxX: width,
    maxY: height - FOOTER_BUFFER
  };
}

function constrainToBounds(element: Rect, bounds: Bounds): Rect {
  // Ensure element stays within bounds
  // Priority: keep top-left visible, then clamp size if needed
}
```

2. **Migration Hook** (runs on editor load):
```typescript
// Pseudo-code
function migrateOutOfBoundsElements(blocks: Block[]): Block[] {
  const bounds = getCanvasBounds();
  return blocks.map(block => {
    if (isOutOfBounds(block.config, bounds)) {
      return {
        ...block,
        config: constrainToBounds(block.config, bounds)
      };
    }
    return block;
  });
}
```

3. **Drag/Resize Interceptor** (in `useDrag` hook):
```typescript
// Intercept position updates
function onDragMove(delta: Point) {
  const newPosition = calculateNewPosition(currentPosition, delta);
  const constrained = constrainToBounds(newPosition, canvasBounds);
  applyPosition(constrained);
}
```

### Breakpoint Order Preservation

**Problem**: Element order changes between breakpoints because overrides don't preserve order.

**Solution**: Implement explicit order tracking with cascade inheritance.

**Key Components:**

1. **Order Cascade Logic**:
```typescript
// Pseudo-code
function getEffectiveOrder(block: Block, breakpoint: Breakpoint): number {
  // Check for explicit override at current breakpoint
  if (block.overrides?.[breakpoint]?.order !== undefined) {
    return block.overrides[breakpoint].order;
  }
  
  // Cascade: mobile → tablet → desktop
  if (breakpoint === 'mobile' && block.overrides?.tablet?.order !== undefined) {
    return block.overrides.tablet.order;
  }
  
  // Fall back to base order
  return block.order ?? block.config.order ?? 0;
}
```

2. **Visual Indicator** (when order is overridden):
```typescript
// Show badge in inspector when element has breakpoint-specific order
{hasOrderOverride && (
  <Badge variant="info">
    Custom order on {breakpoint}
    <Button onClick={() => resetOrderOverride()}>Reset</Button>
  </Badge>
)}
```

### Inspector Tab Consolidation

**Current Structure**:
- Info (block type, label, visibility)
- Layout (width, height, position, spacing)
- Style (colors, typography, borders)
- Motion (animations, transitions)
- AI (assistant features)

**New Structure**:

**Design Tab** (visual properties):
- Colors & Backgrounds
- Typography
- Spacing (padding, margin)
- Borders & Shadows
- Visibility & Opacity

**Advanced Tab** (layout & behavior):
- Size & Position
- Layout (flex, grid)
- Responsive Overrides
- Animations & Effects
- Custom CSS
- AI Assistant

**Implementation**:
```typescript
// New component structure
<Inspector>
  <TabList>
    <Tab id="design">Design</Tab>
    <Tab id="advanced">Advanced</Tab>
  </TabList>
  
  <TabPanel id="design">
    <PropertyGroup label="Colors & Backgrounds">
      <ColorInput prop="backgroundColor" />
      <ColorInput prop="textColor" />
      <BackgroundPicker />
    </PropertyGroup>
    
    <PropertyGroup label="Typography">
      <FontPicker />
      <FontSizeInput />
      <TextAlignButtons />
    </PropertyGroup>
    
    {/* ... more groups */}
  </TabPanel>
  
  <TabPanel id="advanced">
    <PropertyGroup label="Size & Position">
      <DimensionInput prop="width" />
      <DimensionInput prop="height" />
      <PositionControls />
    </PropertyGroup>
    
    {/* ... more groups */}
  </TabPanel>
</Inspector>
```

### Sidebar Consolidation

**Current**: 10 flat items  
**New**: 4 sections with nested panels

**Structure**:
```typescript
const SIDEBAR_SECTIONS = [
  {
    id: 'add',
    label: 'Add',
    icon: Plus,
    panels: [
      { id: 'elements', label: 'Elements', icon: Square },
      { id: 'media', label: 'Media', icon: Image },
      { id: 'effects', label: 'Effects', icon: Sparkles }
    ]
  },
  {
    id: 'pages',
    label: 'Pages',
    icon: FileText,
    panels: [
      { id: 'page-list', label: 'Pages', icon: FileText },
      { id: 'navigation', label: 'Navigation', icon: PanelTop },
      { id: 'layers', label: 'Layers', icon: Layers }
    ]
  },
  {
    id: 'site',
    label: 'Site',
    icon: Globe,
    panels: [
      { id: 'theme', label: 'Theme', icon: Palette },
      { id: 'language', label: 'Language', icon: Languages },
      { id: 'music', label: 'Music', icon: Music }
    ]
  },
  {
    id: 'settings',
    label: 'Settings',
    icon: Settings,
    panel: 'site-settings' // Single panel, no nesting
  }
];
```

**UI Pattern**: Click section → slide-out panel with nested options

### Selection Highlight Improvements

**Current**: 1px ring with label  
**New**: 2px solid outline with enhanced visual hierarchy

**CSS Updates**:
```css
/* Selected element */
.selection-outline--selected {
  outline: 2px solid var(--primary);
  outline-offset: -1px;
  position: relative;
  z-index: 60;
}

/* Hovered element */
.selection-outline--hover {
  outline: 1px dashed var(--primary);
  outline-offset: -1px;
  opacity: 0.5;
}

/* Collision warning */
.selection-outline--collision {
  outline: 2px solid var(--destructive);
  animation: pulse-outline 1s ease-in-out infinite;
}

/* Label badge */
.selection-label {
  position: absolute;
  top: -20px;
  left: -2px;
  background: var(--primary);
  color: var(--primary-foreground);
  padding: 2px 6px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  border-radius: 3px 3px 0 0;
}
```

### Resize Handle Enhancements

**Current**: 10px visual handles  
**New**: 10px visual + 44px touch target

**Implementation**:
```typescript
// DragHandles.tsx updates
const HANDLE_VISUAL_SIZE = 10; // Visible square
const HANDLE_TOUCH_TARGET = 44; // Clickable area (WCAG compliant)

<div 
  className="resize-handle"
  style={{
    // Visual appearance
    width: HANDLE_VISUAL_SIZE,
    height: HANDLE_VISUAL_SIZE,
    
    // Touch target (invisible padding)
    padding: (HANDLE_TOUCH_TARGET - HANDLE_VISUAL_SIZE) / 2
  }}
  onPointerEnter={() => setHovered(true)}
/>

// CSS
.resize-handle {
  background: white;
  border: 2px solid var(--primary);
  border-radius: 2px;
  cursor: nw-resize; /* Changes per handle */
  transition: transform 0.15s ease;
}

.resize-handle:hover {
  transform: scale(1.2);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}
```

### Floating Toolbar Positioning

**Problem**: Toolbars render off-screen or overlap inspector

**Solution**: Smart positioning with viewport bounds detection

```typescript
function calculateToolbarPosition(
  elementRect: Rect,
  toolbarSize: Size,
  viewport: Rect,
  inspectorWidth: number
): Point {
  const availableRight = viewport.width - inspectorWidth;
  
  // Try above element
  let x = elementRect.left + elementRect.width / 2 - toolbarSize.width / 2;
  let y = elementRect.top - toolbarSize.height - 8;
  
  // If above is off-screen, try below
  if (y < viewport.top) {
    y = elementRect.bottom + 8;
  }
  
  // If below is off-screen, try inline
  if (y + toolbarSize.height > viewport.bottom) {
    y = elementRect.top + 8;
  }
  
  // Clamp X to avoid inspector overlap
  x = Math.max(8, Math.min(x, availableRight - toolbarSize.width - 8));
  
  return { x, y };
}
```

## Migration & Rollout Plan

### Phase 1: Canvas Fixes (Days 1-3)

**Tasks:**
1. Implement `BoundsCalculator` utility
2. Add bounds checking to `useDrag` hook
3. Create migration function for out-of-bounds elements
4. Fix breakpoint order cascade in `getEffectiveConfig`
5. Add analytics events for migration triggers

**Testing:**
- Unit tests for bounds calculation
- Integration test: drag element to edge, verify constraint
- Migration test: load site with out-of-bounds elements, verify correction
- Breakpoint test: verify order preserved across device changes

**Rollout:**
- Ship to 10% of users (canary)
- Monitor error rates and analytics
- Expand to 50%, then 100%

### Phase 2: Inspector & Sidebar (Days 4-8)

**Tasks:**
1. Create `InspectorV2.tsx` with 2-tab structure
2. Migrate property components to new tab groups
3. Refactor `IconRail` to `SidebarNav` with sections
4. Create nested panel routing logic
5. Add feature flag `useInspectorV2`

**Testing:**
- Visual regression tests for new inspector
- Accessibility audit (keyboard nav, ARIA labels)
- Property coverage test: verify all properties accessible
- User testing: 5 users complete common tasks

**Rollout:**
- Beta opt-in for power users (1 week)
- Collect feedback, iterate
- Ship to 25%, 50%, 100%

### Phase 3: Interaction Polish (Days 9-11)

**Tasks:**
1. Update `SelectionLayer` with enhanced outlines
2. Improve `DragHandles` visual and touch targets
3. Implement smart toolbar positioning
4. Add page vs element context clarity

**Testing:**
- Visual QA: selection highlights on various elements
- Touch target testing on mobile breakpoint
- Toolbar positioning edge cases

**Rollout:**
- Ship to 100% (low-risk polish improvements)

### Analytics & Success Tracking

**Metrics to Monitor:**

1. **Canvas bounds violations**: Track how often migration runs (should decrease to 0)
2. **Breakpoint order consistency**: % of sites with order mismatches (target: <5%)
3. **Inspector tab clicks**: Measure if 2 tabs reduce friction vs 5 tabs
4. **Sidebar navigation efficiency**: Avg clicks to reach feature (target: <3)
5. **Selection errors**: % of clicks that miss intended element (target: <10%)
6. **Resize accuracy**: % of resize operations completed successfully (target: >90%)
7. **Performance**: P95 render time for selection/handles (target: <50ms)

**Events to Track:**
- `editor.canvas.bounds_violation`
- `editor.breakpoint.order_override`
- `editor.inspector.tab_switch`
- `editor.sidebar.section_open`
- `editor.selection.cycle_attempt`
- `editor.resize.handle_drag`
- `editor.toolbar.position_adjusted`

---

## Open Questions & Decisions Needed

1. **Inspector transition**: Feature flag with gradual rollout, or hard cutover?
   - **Recommendation**: Feature flag for 2 weeks, then cutover
   
2. **Old data migration**: Auto-migrate on load, or show migration prompt?
   - **Recommendation**: Auto-migrate silently, log to analytics
   
3. **Keyboard shortcuts**: Do we need new shortcuts for 2-tab inspector?
   - **Recommendation**: Keep existing shortcuts, map to new tabs
   
4. **Mobile breakpoint editing**: Should we restrict certain properties on mobile?
   - **Recommendation**: No restrictions, but add warnings for problematic values
   
5. **Undo/redo**: Do bounds constraints go in undo history?
   - **Recommendation**: No, constraints are automatic corrections, not user actions

---

## Next Steps (After Director Approval)

1. Create GitHub issues for each phase
2. Design review: Share Figma mockups of new inspector/sidebar
3. Technical spec review: Validate bounds calculation approach with team
4. Set up feature flags in dashboard settings
5. Create test data set with known edge cases
6. Schedule user testing sessions for Phase 2

---

## dream-studio Integration

**Skill Flow**: think → plan → build → review → verify → ship

**Output Location**: `.planning/specs/dreamysuite-ux-refactor/spec.md`

**Next Steps**: 
1. Get Director (user) approval on recommended Approach 1
2. Run `dream-studio:plan` to break this spec into implementation tasks
3. Output will be `.planning/specs/dreamysuite-ux-refactor/plan.md` and `tasks.md`

---

## Sources

Research references used in this specification:

- [Studio Editor: Using the Inspector Panel | Wix.com](https://support.wix.com/en/article/studio-editor-using-the-inspector-panel)
- [Studio Editor: A Guided Tour | Wix.com](https://support.wix.com/en/article/studio-editor-a-guided-tour)
- [Inspector Panel Video Tutorial | Editor X](https://www.wix.com/studio-tech-design/academyx3/lessons/inspector-panel)
- [UI Inspector - Visual CSS Editor](https://www.ui-inspector.com/)
- [The Ultimate Guide to UI Design in 2026 | Medium](https://medium.com/@WebdesignerDepot/the-ultimate-guide-to-ui-design-in-2026-d9a6ef5a93bd)
- [Framer vs Webflow: key differences that matter most](https://www.sommo.io/blog/framer-vs-webflow)
- [Webflow vs Framer: Design Tool Showdown (2026)](https://designrevision.com/blog/framer-vs-webflow)
