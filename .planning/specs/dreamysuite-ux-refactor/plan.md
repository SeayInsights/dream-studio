# Implementation Plan: DreamySuite UX & Architecture Refactor

**Date**: 2026-04-27 | **Spec**: `.planning/specs/dreamysuite-ux-refactor/spec.md`  
**Input**: Feature specification addressing 8 critical UX/architecture issues in dreamysuite editor

## Summary

Refactor dreamysuite editor to fix critical UX issues and align with modern visual editor patterns (Wix Studio, Framer). Approved approach: Incremental refactor in 3 independently shippable phases addressing 8 user stories (P1-P3 priority) covering canvas bounds, breakpoint consistency, inspector consolidation, sidebar reorganization, and interaction polish.

## Technical Context

**Language/Version**: TypeScript 5.x (Next.js/React 19 app)  
**Primary Dependencies**: React 19, Next.js, Zustand (state), motion/mini (animations), Cloudflare Workers  
**Storage**: D1 (Cloudflare SQL), element config in JSON  
**Testing**: Manual testing + browser verification (no automated tests specified)  
**Target Platform**: Browser (Chrome, Safari, Firefox)  
**Project Type**: Web app - visual wedding site editor  
**Performance Goals**: <100ms selection/resize render overhead, 60fps interactions  
**Constraints**: Backward compatible with existing user data, zero-downtime migration  
**Scale/Scope**: 8 user stories, 32 functional requirements, 27-36 files modified across 3 phases

## Constitution Check

*GATE: Must pass before implementation.*

✅ **Follows dream-studio principles**:
- Incremental delivery (3 phases)
- No premature abstractions (fixing real bugs, not hypothetical)
- Evidence-based design (research from Wix Studio, Webflow, Framer)
- Backward compatible (migration for existing data)

✅ **Project-specific (dreamysuite CLAUDE.md)**:
- Uses 'Tile' not 'Block' in user-facing text (retained internal 'Block' in code)
- Builder preview rendering aware (`$slug.tsx` for preview bugs)
- Responsive breakpoint verification after CSS/layout changes

## Project Structure

### Documentation (this feature)

```text
.planning/specs/dreamysuite-ux-refactor/
├── spec.md              # User stories, requirements (dream-studio:think output)
├── plan.md              # This file (dream-studio:plan output)
├── tasks.md             # Task breakdown (dream-studio:plan output)
└── traceability.yaml    # Requirements tracking registry
```

### Source Code (DreamySuite)

```text
C:\Users\Dannis Seay\builds\dreamysuite/
├── src/app/(dashboard)/sites/[id]/editor-v2/
│   ├── Canvas.tsx                    # Main canvas component
│   ├── EditorShell.tsx               # Editor layout shell
│   ├── Inspector.tsx                 # Right-side inspector panel (5 tabs → 2 tabs)
│   ├── IconRail.tsx                  # Left sidebar (10 items → 4 sections with nesting)
│   ├── SlideTray.tsx                 # Slide-out tray panels
│   ├── SelectionLayer.tsx            # Selection/hover outlines
│   ├── BreakpointFrame.tsx           # Responsive breakpoint wrapper
│   ├── editing/
│   │   ├── DragHandles.tsx           # Resize handles (8 positions)
│   │   ├── BlockEditPanel.tsx        # Floating toolbar for block editing
│   │   └── SectionToolbar.tsx        # Section-level toolbar
│   ├── inspector/
│   │   ├── ContentTab.tsx            # Current "Info" tab → merge to Design
│   │   ├── LayoutTab.tsx             # Current "Layout" tab → merge to Advanced
│   │   ├── StyleTab.tsx              # Current "Style" tab → merge to Design
│   │   ├── MotionTab.tsx             # Current "Motion" tab → merge to Advanced
│   │   ├── AssistantTab.tsx          # Current "AI" tab → merge to Advanced
│   │   └── [NEW] DesignTab.tsx       # New consolidated Design tab
│   │   └── [NEW] AdvancedTab.tsx     # New consolidated Advanced tab
│   ├── hooks/
│   │   ├── useDrag.ts                # Drag/resize logic (bounds checking added)
│   │   └── useSelection.ts           # Selection state management
│   └── lib/
│       ├── [NEW] boundsCalculator.ts # Canvas bounds constraint utilities
│       └── cascadeConfig.ts          # Breakpoint config cascade (order fix added)
├── src/app/stores/
│   └── editorStore.ts                # Zustand state (EditorState, SelectionState updates)
└── [NEW] src/lib/migrations/
    └── migrateOutOfBoundsElements.ts # Data migration for existing bad data
```

**Structure Decision**: Keep existing `editor-v2` structure. Create new components alongside old (InspectorV2, SidebarNav), route via feature flag initially, then deprecate old components after validation. No parallel `editor-v3` directory (too risky for big-bang approach).

## Complexity Tracking

No complexity concerns requiring justification. This is a refactor of existing functionality with well-understood patterns from industry research.

## Requirements Traceability

<!--
  Link implementation tasks (from tasks.md) to functional requirements (from spec.md)
-->

| Requirement ID | Description | Implemented By |
|---------------|-------------|----------------|
| **FR-001** | System MUST constrain elements within canvas bounds during move/resize | T001, T002, T003 |
| **FR-002** | System MUST auto-scroll canvas when dragging near edges | T002 |
| **FR-003** | System MUST migrate existing out-of-bounds elements on editor load | T004 |
| **FR-004** | System MUST prevent negative coordinates relative to page origin | T001, T002 |
| **FR-005** | System MUST preserve element order across breakpoints unless overridden | T005, T006 |
| **FR-006** | System MUST cascade breakpoint overrides (mobile←tablet←desktop) | T005 |
| **FR-007** | System MUST visually indicate breakpoint-specific overrides | T007 |
| **FR-008** | Users MUST be able to reset breakpoint overrides | T007 |
| **FR-009** | System MUST consolidate inspector from 5 tabs to 2 tabs | T008, T009, T010 |
| **FR-010** | Design tab MUST contain visual properties (colors, typography, spacing, etc.) | T009 |
| **FR-011** | Advanced tab MUST contain layout/behavior (position, size, animations, etc.) | T010 |
| **FR-012** | System MUST auto-switch to relevant tab on user actions | T011 |
| **FR-013** | System MUST reduce sidebar from 10 items to 4 sections | T012, T013 |
| **FR-014** | "Add" section MUST group Elements, Media, Effects | T013 |
| **FR-015** | "Pages" section MUST group Pages, Navigation, Layers | T013 |
| **FR-016** | "Site" section MUST group Theme, Language, Music, Settings | T013 |
| **FR-017** | System MUST render selection outline as 2px solid with high contrast | T014, T015 |
| **FR-018** | System MUST render hover outline as 1px dashed with 50% opacity | T014, T015 |
| **FR-019** | System MUST show element label badge on selection | T015 |
| **FR-020** | System MUST support selection cycling for overlapped elements | T014 (already exists) |
| **FR-021** | System MUST render 8 resize handles (4 corners + 4 edges) | T016 (already exists, refine) |
| **FR-022** | Resize handles MUST have 10px visual + 44px touch target | T016 |
| **FR-023** | Resize handles MUST scale 1.2x on hover with cursor change | T016 |
| **FR-024** | System MUST maintain aspect ratio with shift-key during resize | T016 |
| **FR-025** | System MUST show contextual toolbar on double-click | T017, T018 |
| **FR-026** | Toolbar MUST reposition to remain within viewport bounds | T017 |
| **FR-027** | Toolbar MUST close on outside click or Escape | T018 (already exists, verify) |
| **FR-028** | System MUST prevent toolbar overlap with inspector | T017 |
| **FR-029** | Inspector MUST show page settings when no element selected | T019 |
| **FR-030** | Inspector MUST show element settings when element selected | T019 (already exists, verify) |
| **FR-031** | System MUST provide breadcrumb navigation for page hierarchy | T020 (already exists, verify) |
| **FR-032** | Top bar MUST provide quick access to page-level settings | T020 (already exists, verify) |

## Dependencies

### External Dependencies
- No new npm packages required
- All dependencies already in package.json (React 19, Zustand, motion/mini)

### Internal Dependencies
- Existing dreamysuite editor-v2 architecture
- Zustand editorStore state management
- Existing block data structure with `overrides` property
- CSS utility library (Tailwind via `cn()`)

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Breaking existing user sites with data migration | **High** | Test migration on clone of production DB first; rollback script ready; gradual rollout (10% → 50% → 100%) |
| Users confused by sudden UI change | **Medium** | Feature flag for gradual rollout; in-app tooltip tour on first load; changelog announcement |
| Performance regression from bounds checking | **Low** | Bounds calc is O(1); use RAF for updates; measure before/after with Chrome DevTools |
| Inspector tab migration loses property discoverability | **Medium** | A/B test with 5 power users before full rollout; heatmap tracking to find missing properties |
| Sidebar consolidation breaks muscle memory | **Low** | Keep keyboard shortcuts unchanged; add search to sidebar panels |
| Breakpoint order fix breaks sites that rely on current buggy behavior | **Medium** | Add opt-out flag `legacyBreakpointOrder` in site settings (deprecated in 3 months) |

## Success Metrics

- [ ] All 32 functional requirements (FR-001 through FR-032) implemented
- [ ] All 8 user stories (US1-US8) testable independently
- [ ] Performance: <100ms overhead for selection/resize rendering (measured via Chrome Performance tab)
- [ ] Code quality: Inspector code LOC reduced by 40% (current ~800 LOC → target ~480 LOC)
- [ ] User validation: 5/5 beta testers successfully complete common tasks with new UI
- [ ] Zero regressions: Existing element types (video, countdown, gallery, etc.) work unchanged
- [ ] Migration: 100% of existing out-of-bounds elements auto-corrected on first editor load

## Phase Breakdown

### Phase 1: Canvas Bounds + Breakpoint Order (Days 1-3) — P1

**Goal**: Fix critical bugs blocking users (elements outside canvas, layout order inconsistency)

**Deliverables**:
- Bounds constraint system (`boundsCalculator.ts` utility)
- Bounds checking in drag/resize operations
- Migration for existing out-of-bounds elements
- Breakpoint order cascade logic with inheritance
- Visual indicator for breakpoint overrides

**Validation**: 
- Add element, drag to edge → stays within bounds
- Switch breakpoints → order preserved
- Load old site with out-of-bounds elements → auto-corrected

**Shipping**: Independent PR, can ship without Phase 2/3

---

### Phase 2: Inspector + Sidebar Consolidation (Days 4-8) — P1-P2

**Goal**: Streamline editor UI to match industry standards (Wix Studio 2-tab pattern)

**Deliverables**:
- New 2-tab inspector (Design + Advanced)
- Property migration to new tab groups
- Sidebar reduced from 10 → 4 sections with nesting
- Feature flag for gradual rollout

**Validation**:
- Select element → see 2 tabs with all properties accessible
- Click sidebar "Add" → see nested panels (Elements, Media, Effects)
- Property coverage test: verify all old properties exist in new tabs

**Shipping**: Independent PR with feature flag, can ship without Phase 3

---

### Phase 3: Interaction Polish (Days 9-11) — P2-P3

**Goal**: Professional, delightful interaction quality

**Deliverables**:
- Enhanced selection outlines (2px solid, high contrast)
- Improved resize handles (44px touch targets, 1.2x hover scale)
- Smart floating toolbar positioning (viewport-aware)
- Page vs element clarity improvements

**Validation**:
- Select element → clear 2px outline visible
- Hover over element → 1px dashed outline appears
- Double-click element → toolbar appears, stays in viewport
- No element selected → inspector shows page settings

**Shipping**: Independent PR, polish improvements

## Implementation Notes

### Backward Compatibility Strategy
1. **Data migration**: Auto-run on editor load (no user action required)
2. **Feature flags**: `useInspectorV2`, `useSidebarV2` in user preferences
3. **Graceful degradation**: Old data structure still valid, new code adds to it
4. **Rollback plan**: Feature flags can disable new UI, revert to V1 instantly

### Testing Strategy
1. **Manual verification** after each task (no automated tests requested)
2. **Browser matrix**: Chrome (primary), Safari, Firefox
3. **Breakpoint verification**: Test desktop, tablet, mobile views
4. **Data migration test**: Clone production DB, run migration, verify no data loss
5. **Performance benchmarking**: Chrome DevTools Performance tab, compare before/after

### Commit Strategy
- One task = one logical commit
- Commit message format: `[Phase N] Task TXX: <description>`
- Example: `[Phase 1] Task T001: Add bounds calculator utility`

### Rollout Strategy
1. **Phase 1**: Ship to 10% canary → 50% → 100% (2-3 days)
2. **Phase 2**: Beta opt-in for power users (1 week) → 25% → 50% → 100%
3. **Phase 3**: Ship to 100% (polish, low risk)

## dream-studio Integration

**Skill Flow**: think → **plan** → build → review → verify → ship

**Output Location**: `.planning/specs/dreamysuite-ux-refactor/plan.md` and `tasks.md`

**Next Steps**: 
1. Review this plan with user for approval ✅ (APPROVED: Approach 1)
2. Run `dream-studio:build` with the tasks.md file
3. Execute tasks in dependency order, commit after each logical group
4. Pause at each phase checkpoint to validate independently
5. Ship each phase independently via feature flag rollout
