# Tasks: DreamySuite UX & Architecture Refactor

**Input**: Design documents from `.planning/specs/dreamysuite-ux-refactor/`
**Prerequisites**: plan.md (required), spec.md (required for user stories)

**Organization**: Tasks grouped by phase (3 phases) and user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Path Conventions

All paths relative to: `C:\Users\Dannis Seay\builds\dreamysuite/`

---

## Phase 1: Canvas Bounds + Breakpoint Order (Days 1-3, P1 Priority)

**Purpose**: Fix critical bugs - elements outside canvas, layout order inconsistency

**⚠️ CRITICAL**: These are blocking bugs affecting user ability to edit sites

---

### User Story 1 - Element Visibility & Canvas Bounds (Priority: P1) 🎯 Critical Fix

**Goal**: Ensure all elements remain visible and accessible within canvas bounds

**Independent Test**: Add elements, resize/move them, switch breakpoints → verify all stay visible and accessible

---

#### Implementation for User Story 1

- [ ] **T001** [P] [US1] Create bounds calculator utility
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/lib/boundsCalculator.ts`
  - **Implements**: TR-001, TR-004
  - **Depends on**: None
  - **Acceptance**: 
    - Utility exports `getCanvasBounds(container: HTMLElement): Bounds` returning `{minX, minY, maxX, maxY}`
    - Utility exports `constrainToBounds(element: Rect, bounds: Bounds): Rect` constraining element to bounds
    - Logic prioritizes keeping top-left visible, then clamps size if needed
    - Unit test: element at (-100, 50) gets constrained to (0, 50)
    - Unit test: element extending beyond maxX gets width clamped

- [ ] **T002** [US1] Add bounds checking to drag and resize operations
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/hooks/useDrag.ts`
  - **Implements**: TR-001, TR-002, TR-004
  - **Depends on**: T001
  - **Acceptance**:
    - Import `boundsCalculator` utility
    - In `onDragMove` function, calculate `newPosition` then pass through `constrainToBounds`
    - In `onResizeMove` function, calculate `newSize` then pass through `constrainToBounds`
    - Auto-scroll canvas when dragging within 50px of viewport edges (FR-002)
    - Manual test: Drag element to canvas edge → stops at boundary, doesn't go off-screen
    - Manual test: Resize element beyond canvas → width/height clamps to fit

- [ ] **T003** [P] [US1] Add CSS containment to canvas component
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/Canvas.tsx`
  - **Implements**: TR-001
  - **Depends on**: None
  - **Acceptance**:
    - Add `contain: layout` CSS property to canvas container div
    - Add `overflow: clip` or `overflow: hidden` to prevent visual overflow
    - Verify elements cannot visually render outside canvas bounds
    - Manual test: Load editor → no elements visible outside canvas scroll area

- [ ] **T004** [US1] Create migration for existing out-of-bounds elements
  - **File**: `src/lib/migrations/migrateOutOfBoundsElements.ts`
  - **Implements**: TR-003
  - **Depends on**: T001
  - **Acceptance**:
    - Export function `migrateOutOfBoundsElements(blocks: Block[]): Block[]`
    - For each block, check if position/size is out-of-bounds using `boundsCalculator`
    - If out-of-bounds, update `config` with constrained position/size
    - Track analytics event `editor.migration.bounds_fix` with count
    - Integrate into `Canvas.tsx` `useEffect` on initial blocks load
    - Manual test: Create site with element at position (-200, 100) in DB → after load, element at (0, 100)
    - Manual test: Check analytics dashboard for migration events

**Checkpoint**: At this point, User Story 1 complete - all elements constrained within canvas bounds

---

### User Story 2 - Consistent Breakpoint Layout (Priority: P1) 🎯 Critical Fix

**Goal**: Preserve element order across breakpoints unless explicitly overridden

**Independent Test**: Arrange elements A-B-C on desktop → switch to tablet/mobile → verify order preserved

---

#### Implementation for User Story 2

- [ ] **T005** [P] [US2] Implement breakpoint order cascade logic
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/lib/cascadeConfig.ts`
  - **Implements**: TR-005, TR-006
  - **Depends on**: None
  - **Acceptance**:
    - Create or update `getEffectiveOrder(block: Block, breakpoint: Breakpoint): number` function
    - Logic: Check `block.overrides?.[breakpoint]?.order` first (explicit override)
    - If not found and breakpoint is mobile, check `block.overrides?.tablet?.order` (cascade)
    - If not found and breakpoint is tablet, check base `block.order` or `block.config.order`
    - Fall back to index in blocks array if no order specified
    - Unit test: Desktop order=1 → Tablet (no override) → should return 1
    - Unit test: Desktop order=1, Tablet order=2 → Mobile (no override) → should return 2
    - Unit test: Desktop order=1, Tablet order=2, Mobile order=3 → should return 3

- [ ] **T006** [US2] Apply order cascade in block rendering
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/Canvas.tsx`
  - **Implements**: TR-005
  - **Depends on**: T005
  - **Acceptance**:
    - Import `getEffectiveOrder` from cascadeConfig
    - Before rendering blocks, sort by `getEffectiveOrder(block, currentBreakpoint)`
    - Verify blocks render in correct order for desktop, tablet, mobile
    - Manual test: Create 3 elements on desktop → switch to tablet → order unchanged (no overrides)
    - Manual test: Reorder elements on mobile → switch to tablet → mobile order different, tablet unchanged
    - Manual test: Switch back to desktop → desktop order unchanged

- [ ] **T007** [P] [US2] Add visual indicator for breakpoint overrides in inspector
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/inspector/LayoutTab.tsx` (or new AdvancedTab in Phase 2)
  - **Implements**: TR-007, TR-008
  - **Depends on**: T005
  - **Acceptance**:
    - Check if current block has `overrides?.[currentBreakpoint]?.order !== undefined`
    - If true, show Badge component: "Custom order on {breakpoint}"
    - Add "Reset" button next to badge
    - On reset click, delete `overrides[breakpoint].order` and re-save block
    - Manual test: Reorder element on tablet → switch to desktop → no badge shows
    - Manual test: Reorder element on tablet → stay on tablet → badge shows "Custom order on tablet"
    - Manual test: Click reset → badge disappears, order reverts to desktop order

**Checkpoint**: At this point, User Story 2 complete - breakpoint order preserved with cascade inheritance

---

**Phase 1 Complete**: Canvas bounds + breakpoint order fixed. Can ship independently.

---

## Phase 2: Inspector + Sidebar Consolidation (Days 4-8, P1-P2 Priority)

**Purpose**: Streamline editor UI to match industry standards (Wix Studio 2-tab pattern)

**⚠️ NOTE**: Feature-flagged rollout - old and new UI will coexist during transition

---

### User Story 3 - Streamlined Inspector (Priority: P1) 🎯 MVP

**Goal**: Consolidate inspector from 5 tabs to 2 intuitive tabs (Design + Advanced)

**Independent Test**: Select any element → verify all properties accessible in 2 clearly labeled tabs

---

#### Implementation for User Story 3

- [ ] **T008** [P] [US3] Create new 2-tab inspector shell component
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/InspectorV2.tsx`
  - **Implements**: TR-009
  - **Depends on**: None
  - **Acceptance**:
    - Copy structure from existing `Inspector.tsx`
    - Define 2 tabs: `{ id: "design", label: "Design" }` and `{ id: "advanced", label: "Advanced" }`
    - Remove old tab IDs: "info", "layout", "style", "motion", "assistant"
    - Tab switching logic (active state) same as current Inspector
    - Slide-in/slide-out animation preserved
    - Manual test: Open inspector → see exactly 2 tabs labeled "Design" and "Advanced"
    - Manual test: Click tabs → switch between Design and Advanced panels

- [ ] **T009** [P] [US3] Create Design tab with consolidated property groups
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/inspector/DesignTab.tsx`
  - **Implements**: TR-010
  - **Depends on**: None (can build in parallel with T008)
  - **Acceptance**:
    - Create `PropertyGroup` sections:
      - "Colors & Backgrounds" (from old StyleTab)
      - "Typography" (from old StyleTab, ContentTab)
      - "Spacing" (from old StyleTab, LayoutTab)
      - "Borders & Shadows" (from old StyleTab)
      - "Visibility & Opacity" (from old ContentTab)
    - Migrate components from `ContentTab.tsx`, `StyleTab.tsx`:
      - `ColorInput`, `BackgroundPicker`, `FontPicker`, `FontSizeInput`, `TextAlignButtons`
      - `SpacingControls` (padding, margin), `BorderInput`, `ShadowPicker`
      - `VisibilityToggle`, `OpacitySlider`
    - All property inputs connect to `useEditorStore` and `updateBlock` same as before
    - Manual test: Select text element → Design tab shows typography controls
    - Manual test: Select video element → Design tab shows background, spacing, visibility
    - Manual test: Change color → verify block updates and re-renders

- [ ] **T010** [P] [US3] Create Advanced tab with layout/behavior properties
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/inspector/AdvancedTab.tsx`
  - **Implements**: TR-011
  - **Depends on**: None (can build in parallel with T008, T009)
  - **Acceptance**:
    - Create `PropertyGroup` sections:
      - "Size & Position" (from old LayoutTab)
      - "Layout" (flex, grid from old LayoutTab)
      - "Responsive Overrides" (breakpoint-specific settings from old LayoutTab)
      - "Animations & Effects" (from old MotionTab)
      - "Custom CSS" (from old CustomCssPanel)
      - "AI Assistant" (from old AssistantTab)
    - Migrate components from `LayoutTab.tsx`, `MotionTab.tsx`, `AssistantTab.tsx`, `CustomCssPanel.tsx`:
      - `DimensionInput` (width, height), `PositionControls`
      - `LayoutControls` (flexbox, grid), `BreakpointOverridePanel`
      - `AnimationPresetPicker`, `EffectPresetPicker`
      - `CustomCssPanel` component (embedded)
      - `AssistantTab` component (embedded)
    - Manual test: Select element → Advanced tab shows size, position controls
    - Manual test: Drag element → Advanced tab auto-opens (if FR-012 implemented)
    - Manual test: Apply animation → verify effect renders on canvas

- [ ] **T011** [US3] Implement auto-tab-switch on user actions
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/InspectorV2.tsx` and `hooks/useDrag.ts`
  - **Implements**: TR-012
  - **Depends on**: T008, T009, T010
  - **Acceptance**:
    - Add `setInspectorTab(tabId: string)` to editorStore
    - In `useDrag.ts`, on drag start, call `setInspectorTab("advanced")`
    - In `InspectorV2.tsx`, on color picker open, call `setInspectorTab("design")`
    - Add debounce (500ms) to avoid rapid tab switching
    - Manual test: Drag element → Advanced tab opens automatically
    - Manual test: Click color input → Design tab opens automatically (if on Advanced)
    - Manual test: Rapid actions → tab doesn't flicker, settles after debounce

**Checkpoint**: At this point, User Story 3 complete - inspector consolidated to 2 tabs with all properties accessible

---

### User Story 4 - Consolidated Left Sidebar (Priority: P2)

**Goal**: Reduce left sidebar from 10 items to 4 sections with nested panels

**Independent Test**: Access all core functions (pages, elements, theme) through reorganized sidebar in <3 clicks

---

#### Implementation for User Story 4

- [ ] **T012** [P] [US4] Define new sidebar section structure
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/lib/sidebarConfig.ts` (new file)
  - **Implements**: TR-013
  - **Depends on**: None
  - **Acceptance**:
    - Export constant `SIDEBAR_SECTIONS` array with 4 sections:
      - `{ id: 'add', label: 'Add', icon: Plus, panels: ['elements', 'media', 'effects'] }`
      - `{ id: 'pages', label: 'Pages', icon: FileText, panels: ['page-list', 'navigation', 'layers'] }`
      - `{ id: 'site', label: 'Site', icon: Globe, panels: ['theme', 'language', 'music'] }`
      - `{ id: 'settings', label: 'Settings', icon: Settings, panel: 'site-settings' }`
    - Each panel maps to existing tray component (e.g., 'elements' → ElementsTray)
    - TypeScript types: `SidebarSection`, `PanelId`
    - Unit test: Verify SIDEBAR_SECTIONS has exactly 4 top-level items
    - Unit test: Verify total panel count matches old sidebar (10 panels → 10 nested panels)

- [ ] **T013** [US4] Refactor IconRail to SidebarNav with nested panel routing
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/SidebarNav.tsx` (rename from IconRail.tsx)
  - **Implements**: TR-013, TR-014, TR-015, TR-016
  - **Depends on**: T012
  - **Acceptance**:
    - Import `SIDEBAR_SECTIONS` from sidebarConfig
    - Render 4 top-level section buttons (no longer 10 flat items)
    - On section click, open slide-out panel showing nested sub-panels
    - Sub-panel click opens corresponding tray (existing `SlideTray` component)
    - Preserve keyboard navigation and animations from old IconRail
    - Update `EditorShell.tsx` to use `<SidebarNav />` instead of `<IconRail />`
    - Manual test: Click "Add" → see nested buttons for Elements, Media, Effects
    - Manual test: Click "Elements" → ElementsTray opens with element picker
    - Manual test: Click "Pages" → see nested buttons for Pages, Navigation, Layers
    - Manual test: Click "Site" → see nested buttons for Theme, Language, Music
    - Manual test: Click "Settings" → site settings panel opens (no nesting)
    - Manual test: All 10 original functions accessible within 2-3 clicks

**Checkpoint**: At this point, User Story 4 complete - sidebar consolidated to 4 sections with all functions accessible

---

**Phase 2 Complete**: Inspector + sidebar streamlined. Can ship independently via feature flag.

---

## Phase 3: Interaction Polish (Days 9-11, P2-P3 Priority)

**Purpose**: Professional, delightful interaction quality - selection highlights, resize handles, toolbars

**⚠️ NOTE**: Lower priority polish - can ship after Phase 1 & 2 if needed

---

### User Story 5 - Improved Selection Highlights (Priority: P2)

**Goal**: Clear, prominent selection outlines that don't obscure content

**Independent Test**: Select elements → verify highlight visible, clear, doesn't interfere with content

---

#### Implementation for User Story 5

- [ ] **T014** [P] [US5] Update selection outline rendering logic
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/SelectionLayer.tsx`
  - **Implements**: TR-017, TR-018, TR-020
  - **Depends on**: None
  - **Acceptance**:
    - Update `Outline` component CSS:
      - Selected: `outline: 2px solid var(--primary)` (upgrade from 1px)
      - Hover: `outline: 1px dashed var(--primary)`, `opacity: 0.5`
    - Ensure z-index layering: selected > hover > default
    - Selection cycling already implemented (FR-020), verify still works
    - Manual test: Select element → 2px solid outline appears, clearly visible
    - Manual test: Hover over element → 1px dashed outline appears at 50% opacity
    - Manual test: Click overlapping elements multiple times → cycles through stack (z-order)

- [ ] **T015** [P] [US5] Enhance selection label badge styling
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/SelectionLayer.tsx`
  - **Implements**: TR-019
  - **Depends on**: None
  - **Acceptance**:
    - Update label badge CSS in `Outline` component:
      - Increase font weight: `font-weight: 600`
      - Add subtle shadow: `box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1)`
      - Ensure high contrast: background uses `--primary`, text uses `--primary-foreground`
    - Label always positioned top-left of selection outline
    - Manual test: Select element → label badge clearly readable with high contrast
    - Manual test: Select element near top edge → label doesn't get cut off (may need to reposition)

**Checkpoint**: At this point, User Story 5 complete - selection highlights enhanced for clarity

---

### User Story 6 - Enhanced Resize Handles (Priority: P2)

**Goal**: Clear, touch-friendly resize handles with proper visual hierarchy

**Independent Test**: Select element → verify 8 handles visible, usable, hover effects work

---

#### Implementation for User Story 6

- [ ] **T016** [US6] Improve resize handle visuals and touch targets
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/editing/DragHandles.tsx`
  - **Implements**: TR-021, TR-022, TR-023, TR-024
  - **Depends on**: None
  - **Acceptance**:
    - 8 handles already exist (4 corners + 4 edges), verify all rendering
    - Update `HANDLE_VISUAL` constant to 10px (visual square size)
    - Update `TOUCH_TARGET` constant to 44px (clickable area - WCAG compliant)
    - Add CSS: `.resize-handle { transition: transform 0.15s ease; }`
    - Add CSS: `.resize-handle:hover { transform: scale(1.2); box-shadow: 0 2px 8px rgba(0,0,0,0.15); }`
    - Update cursor styles per handle (nw-resize, n-resize, ne-resize, etc.)
    - Add shift-key aspect ratio lock logic in `useDrag.ts` (FR-024)
    - Manual test: Select element → all 8 handles visible at corners and edges
    - Manual test: Hover over handle → handle scales 1.2x, shadow appears
    - Manual test: Drag handle → element resizes smoothly, live preview
    - Manual test: Hold shift while dragging corner → aspect ratio maintained
    - Manual test: Touch target (on mobile breakpoint) → 44px clickable area works

**Checkpoint**: At this point, User Story 6 complete - resize handles enhanced for precision and accessibility

---

### User Story 7 - Refined Floating Toolbars (Priority: P3)

**Goal**: Contextual floating toolbars positioned intelligently, never off-screen or overlapping inspector

**Independent Test**: Double-click elements → verify toolbar appears with relevant actions, stays in viewport

---

#### Implementation for User Story 7

- [ ] **T017** [P] [US7] Implement smart toolbar positioning algorithm
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/editing/BlockEditPanel.tsx`
  - **Implements**: TR-025, TR-026, TR-028
  - **Depends on**: None
  - **Acceptance**:
    - Create `calculateToolbarPosition(elementRect, toolbarSize, viewport, inspectorWidth): Point` function
    - Logic:
      - Try position: above element, centered horizontally
      - If above is off-screen, try below element
      - If below is off-screen, try inline (top-left of element + 8px offset)
      - Clamp X to avoid inspector overlap: `Math.min(x, availableRight - toolbarSize.width - 8)`
    - Apply calculated position to toolbar portal
    - Manual test: Double-click element near top edge → toolbar appears below element
    - Manual test: Double-click element near bottom edge → toolbar appears above element
    - Manual test: Double-click element near right edge (with inspector open) → toolbar shifts left to avoid overlap
    - Manual test: All toolbar positions keep full toolbar visible within viewport

- [ ] **T018** [P] [US7] Verify toolbar close behavior
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/editing/BlockEditPanel.tsx`
  - **Implements**: TR-027
  - **Depends on**: None (verify existing behavior)
  - **Acceptance**:
    - Verify Escape key closes toolbar (should already exist)
    - Verify clicking outside toolbar closes it (should already exist)
    - If missing, add event listeners:
      - `document.addEventListener('keydown', (e) => e.key === 'Escape' && closeToolbar())`
      - `document.addEventListener('click', (e) => !toolbar.contains(e.target) && closeToolbar())`
    - Manual test: Double-click element → toolbar opens
    - Manual test: Press Escape → toolbar closes
    - Manual test: Click outside toolbar → toolbar closes
    - Manual test: Click inside toolbar → toolbar stays open

**Checkpoint**: At this point, User Story 7 complete - floating toolbars refined for better positioning and UX

---

### User Story 8 - Page vs Element Control Clarity (Priority: P3)

**Goal**: Clear separation between page-level and element-level properties in UI

**Independent Test**: Verify page settings accessible when no element selected, element settings when element selected

---

#### Implementation for User Story 8

- [ ] **T019** [P] [US8] Update inspector to show page settings when no element selected
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/InspectorV2.tsx` (or Inspector.tsx)
  - **Implements**: TR-029, TR-030
  - **Depends on**: None (may depend on T008 if InspectorV2 used)
  - **Acceptance**:
    - In Inspector component, check `selectedBlockId` from editorStore
    - If `selectedBlockId === null`, render `PageSettingsPanel` component
    - If `selectedBlockId !== null`, render Design/Advanced tabs (element properties)
    - Manual test: Deselect all elements (click canvas background) → inspector shows page settings
    - Manual test: Select element → inspector switches to element properties (Design/Advanced tabs)
    - Manual test: Page settings show: background, effects, SEO, metadata
    - Manual test: Element settings show: properties specific to that element type

- [ ] **T020** [P] [US8] Verify breadcrumb and top bar page-level access
  - **File**: `src/app/(dashboard)/sites/[id]/editor-v2/Breadcrumb.tsx` and `TopBar.tsx`
  - **Implements**: TR-031, TR-032
  - **Depends on**: None (verify existing behavior)
  - **Acceptance**:
    - Verify `Breadcrumb` component exists and shows page hierarchy
    - Verify clicking breadcrumb opens page settings panel
    - Verify `TopBar` component has Publish, Preview, Settings buttons
    - If missing, add page settings button to TopBar
    - Manual test: Click breadcrumb → page settings panel opens
    - Manual test: Click page icon in breadcrumb → page list or page settings opens
    - Manual test: TopBar has quick access to Publish, Preview, SEO settings

**Checkpoint**: At this point, User Story 8 complete - page vs element separation clarified in UI

---

**Phase 3 Complete**: Interaction polish done. All 8 user stories implemented.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Canvas Bounds + Breakpoint Order)**: No dependencies - can start immediately
- **Phase 2 (Inspector + Sidebar)**: Independent of Phase 1 - can run in parallel if team capacity
- **Phase 3 (Interaction Polish)**: Independent of Phase 1 & 2 - can run in parallel if team capacity

### Within Phase 1

- T001 must complete before T002, T004 (bounds calculator used by drag logic and migration)
- T003 can run in parallel with T001
- T005 must complete before T006 (cascade logic used in rendering)
- T007 can run in parallel with T005, T006

### Within Phase 2

- T008, T009, T010 can all run in parallel (separate files)
- T011 depends on T008, T009, T010 (requires all tabs to exist)
- T012 can run in parallel with T008-T011
- T013 depends on T012 (uses sidebar config)

### Within Phase 3

- All tasks (T014-T020) are independent and can run in parallel

### Parallel Opportunities

**Phase 1 Parallelization:**
```bash
# Can run simultaneously:
T001 (boundsCalculator.ts) + T003 (Canvas.tsx CSS) + T005 (cascadeConfig.ts)
# Then run:
T002 (useDrag.ts) + T007 (LayoutTab.tsx)
# Then run:
T004 (migration) + T006 (Canvas.tsx rendering)
```

**Phase 2 Parallelization:**
```bash
# Can run simultaneously:
T008 (InspectorV2.tsx) + T009 (DesignTab.tsx) + T010 (AdvancedTab.tsx) + T012 (sidebarConfig.ts)
# Then run:
T011 (auto-tab-switch) + T013 (SidebarNav.tsx)
```

**Phase 3 Parallelization:**
```bash
# All can run simultaneously:
T014 (SelectionLayer.tsx) + T015 (SelectionLayer.tsx labels) + T016 (DragHandles.tsx) + T017 (BlockEditPanel.tsx) + T018 (BlockEditPanel.tsx verify) + T019 (Inspector.tsx) + T020 (Breadcrumb/TopBar verify)
```

---

## Implementation Strategy

### Incremental Delivery (Recommended)

1. **Complete Phase 1** (Days 1-3):
   - Tasks T001-T007
   - **STOP and VALIDATE**: Test canvas bounds and breakpoint order fixes
   - Commit, create PR, ship to 10% canary
   
2. **Complete Phase 2** (Days 4-8):
   - Tasks T008-T013
   - **STOP and VALIDATE**: Test new inspector and sidebar with beta users
   - Feature flag enabled for opt-in testers (1 week feedback period)
   - Commit, create PR, ship to 25% → 50% → 100%

3. **Complete Phase 3** (Days 9-11):
   - Tasks T014-T020
   - **STOP and VALIDATE**: Visual QA on selection highlights, resize handles, toolbars
   - Commit, create PR, ship to 100% (low-risk polish)

Each phase independently shippable and testable.

### Parallel Team Strategy

With 2 developers:
1. **Week 1**: Dev A does Phase 1 (T001-T007), Dev B starts Phase 2 (T008-T012)
2. **Week 2**: Dev A does Phase 2 (T011, T013), Dev B does Phase 3 (T014-T020)
3. Phases ship as they complete (not waiting for all phases)

---

## dream-studio Integration

**Execution via**: `dream-studio:build` skill

**Task Tracking**: Use TaskCreate/TaskUpdate to track progress (20 tasks total)

**Checkpoints**: Pause after each user story to verify independently

**Commit Strategy**: Commit after each task or logical group (prefix with `[Phase N]`)

**Branch Strategy**: 
- `feat/dreamysuite-phase1-canvas-bounds`
- `feat/dreamysuite-phase2-inspector-sidebar`
- `feat/dreamysuite-phase3-interaction-polish`

---

## Summary Table

| Phase | Tasks | User Stories | Days | LOC Changed | Risk | Ship Independently? |
|-------|-------|--------------|------|-------------|------|---------------------|
| Phase 1 | T001-T007 | US1, US2 | 2-3 | ~200 (4-6 files) | Medium | ✅ Yes |
| Phase 2 | T008-T013 | US3, US4 | 4-5 | ~800 (15-20 files) | Medium-High | ✅ Yes (feature flag) |
| Phase 3 | T014-T020 | US5-US8 | 2-3 | ~300 (8-10 files) | Low | ✅ Yes |
| **Total** | **20 tasks** | **8 stories** | **8-11 days** | **~1300 LOC** | **Medium** | **3 independent PRs** |

---

## Notes

- All tasks include exact file paths relative to dreamysuite project root
- [P] tasks can be parallelized to speed up development
- Each user story checkpoint validates story independently before moving to next
- Feature flags used for gradual rollout of Phase 2 (inspector/sidebar changes)
- Phase 1 and Phase 3 can ship without feature flags (direct fixes and polish)
- Commit after each logical task group, use `[Phase N] Task TXX:` prefix
- Manual testing required after each task (no automated tests specified in requirements)
