# UAT Checklist - Phase 6 Discovery System

**Task**: T128 - User Acceptance Testing  
**Status**: ⏳ Pending Director Approval

## Test Plan

### 1. Component Extraction
- [ ] Extract components from dream-studio project
- [ ] Verify `pi_components` table populated (expect 3,408+ components)
- [ ] Check `pi_dependencies` table (expect 83,272+ edges)

### 2. Graph Visualization
- [ ] Open dashboard → Project Graph tab
- [ ] Verify nodes and edges render without freezing
- [ ] Test performance: Should render <5s for 1k+ nodes

### 3. Component Metadata
- [ ] Click a component node in graph
- [ ] Verify metadata panel shows:
  - Component name
  - File path
  - Type (function/class/module)
  - Line count

### 4. Impact Analysis
- [ ] Select critical component: `core/event_store/studio_db.py`
- [ ] Run impact analysis
- [ ] Verify blast radius visualization
- [ ] Check risk score calculation (affected/total)

### 5. Tool Search
- [ ] Search for "database" tools
- [ ] Verify results include: SQLite, Supabase, PostgreSQL
- [ ] Check confidence scores >0.7
- [ ] Test category filtering

### 6. Graph Filtering
- [ ] Filter by component type (function/class/module)
- [ ] Verify graph updates dynamically
- [ ] Test search within graph

## Acceptance Criteria

- ✅ All 3 dashboard tabs functional
- ✅ No critical bugs
- ✅ Performance feels snappy (<2s for all actions)
- ✅ Director approves UX

## Performance Targets

- Graph render: <5s for 10k nodes
- API queries: <500ms (p95)
- Pan/zoom: 60fps smooth

## Notes

Director must manually test and approve before Phase 6 completion.
