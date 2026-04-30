# Tasks: Domain Restructure + Repo Knowledge Extraction

**Plan**: `.planning/specs/domain-restructure-extraction/plan.md`  
**Delivery**: 2 PRs — PR1 (`chore/domain-restructure`) + PR2 (`feat/domain-extractions`)

---

## PR 1 — Domain Restructure

### Phase 1: Branch

- [ ] T001 Create branch `chore/domain-restructure` from main
  - Files: git
  - Depends on: none
  - Acceptance: `git branch --show-current` returns `chore/domain-restructure`

---

### Phase 2: File Moves + Deletes [all parallel after T001]

- [ ] T002 [P] Move `skills/domains/bi/dax-patterns.md` → `skills/domains/powerbi/dax-patterns.md`
  - Files: domains/bi/dax-patterns.md, domains/powerbi/dax-patterns.md
  - Depends on: T001
  - Acceptance: file exists at new path, absent at old path

- [ ] T003 [P] Move `skills/domains/bi/m-query-patterns.md` → `skills/domains/powerbi/m-query-patterns.md`
  - Files: domains/bi/m-query-patterns.md, domains/powerbi/m-query-patterns.md
  - Depends on: T001
  - Acceptance: file exists at new path, absent at old path

- [ ] T004 [P] Move `skills/client-work/powerbi/tmdl-authoring.md` → `skills/domains/powerbi/tmdl-authoring.md`
  - Files: client-work/powerbi/tmdl-authoring.md, domains/powerbi/tmdl-authoring.md
  - Depends on: T001
  - Acceptance: file exists at new path, absent at old path

- [ ] T005 [P] Move `skills/client-work/powerbi/pbip-format.md` → `skills/domains/powerbi/pbip-format.md`
  - Files: client-work/powerbi/pbip-format.md, domains/powerbi/pbip-format.md
  - Depends on: T001
  - Acceptance: file exists at new path, absent at old path

- [ ] T006 [P] Move `skills/client-work/powerbi/design-hacks.yml` → `skills/domains/powerbi/design-hacks.yml`
  - Files: client-work/powerbi/design-hacks.yml, domains/powerbi/design-hacks.yml
  - Depends on: T001
  - Acceptance: file exists at new path, absent at old path

- [ ] T007 [P] Delete `skills/client-work/powerbi/accessibility-checklist.yml` (exact dupe of `domains/powerbi/` copy)
  - Files: client-work/powerbi/accessibility-checklist.yml
  - Depends on: T001
  - Acceptance: file absent from client-work/powerbi/

- [ ] T008 [P] Delete `skills/client-work/powerbi/storytelling-framework.yml`; rename `domains/powerbi/storytelling-patterns.yml` → `domains/powerbi/storytelling-framework.yml`
  - Files: client-work/powerbi/storytelling-framework.yml, domains/powerbi/storytelling-patterns.yml → domains/powerbi/storytelling-framework.yml
  - Depends on: T001
  - Acceptance: `storytelling-framework.yml` exists in `domains/powerbi/`; `storytelling-patterns.yml` and client-work copy are absent

---

### Phase 3: Cleanup + Import Update [sequential after Phase 2]

- [ ] T009 Delete `skills/domains/bi/` directory (empty after T002 + T003)
  - Files: domains/bi/
  - Depends on: T002, T003
  - Acceptance: `domains/bi/` directory does not exist

- [ ] T010 Update `skills/client-work/SKILL.md` — rewrite all imports and "Before you start" file references: `domains/bi/` → `domains/powerbi/`; local `powerbi/` paths → `domains/powerbi/`
  - Files: client-work/SKILL.md
  - Depends on: T002, T003, T004, T005, T006, T007, T008
  - Acceptance: no references to `domains/bi/` remain; no local `powerbi/` relative paths remain; all imports resolve to `domains/powerbi/`

---

### Phase 4: PR 1 Commit + Push

- [ ] T011 Commit all changes on `chore/domain-restructure`; push; open PR titled "chore: consolidate Power BI knowledge into domains/powerbi/"
  - Depends on: T009, T010
  - Acceptance: PR open, CI green

---

## PR 2 — New Domain Files

### Phase 5: Branch [after PR1 merged]

- [ ] T012 Pull latest main; create branch `feat/domain-extractions`
  - Files: git
  - Depends on: T011 (PR1 merged)
  - Acceptance: `git branch --show-current` returns `feat/domain-extractions`

---

### Phase 6: New Files [T013 parallel with T014; T015 sequential after T014]

- [ ] T013 [P] Create `skills/domains/data/data-modeling.md` — dimensional modeling patterns
  - Sections: Inmon vs Kimball, Star schema anatomy, SCD Type 2 + DAX filter, Kimball load order (`staging >> dims >> facts >> aggs`), Snowflake date spine + clustering, Four standard BI query shapes, Anti-patterns
  - Sources: arpit-mittal-ds/Data-Architect + hoangsonww/End-to-End-Data-Pipeline
  - Files: domains/data/data-modeling.md
  - Depends on: T012
  - Acceptance: file exists; all 7 sections present

- [ ] T014 [P] Create `skills/domains/saas-build/component-library.md` (also creates `saas-build/` dir)
  - Sections: UI primitives (accordion, dialog, dropdown, tabs, tooltip, scroll-area), Page layout (site-header, sidebar-nav, footer, pager), Component registry pattern, Utility components (copy-button, command-menu, mode-toggle)
  - Source: ANUXR4G/Mage-UI
  - Files: domains/saas-build/ (new), domains/saas-build/component-library.md
  - Depends on: T012
  - Acceptance: file exists at `domains/saas-build/component-library.md`

- [ ] T015 Create `skills/domains/saas-build/animation-patterns.md`
  - Sections: Text animations (hyper-text, morphing-text, typewriter, gooey-text), Cursor effects (magnetic, pixel-trail, ring), Card/reveal patterns (glow-card, wave-card, morphing-card-stack), GSAP scroll timeline patterns, Framer Motion idioms
  - Sources: meetdarji006/meet-ui + Yashchauhan008/portfolio-3d
  - Files: domains/saas-build/animation-patterns.md
  - Depends on: T014 (T014 creates the saas-build/ directory)
  - Acceptance: file exists at `domains/saas-build/animation-patterns.md`

---

### Phase 7: Registry Update

- [ ] T016 Update `skills/domains/ingest-log.yml` — add entries for all Batch 2+3 repos
  - Repos to register: Data-Architect, End-to-End-Data-Pipeline, Mage-UI, meet-ui, portfolio-3d, data-management (SVG note), Skunkworks-Labs/data-management
  - Files: domains/ingest-log.yml
  - Depends on: T013, T014, T015
  - Acceptance: ingest-log.yml contains a repo entry for each of the 6 newly analyzed repos

---

### Phase 8: PR 2 Commit + Push

- [ ] T017 Commit all changes on `feat/domain-extractions`; push; open PR titled "feat: add data-modeling, component-library, and animation-patterns domain files"
  - Depends on: T013, T014, T015, T016
  - Acceptance: PR open, CI green

---

## Dependencies Summary

| Task | Depends On | Parallel With |
|------|-----------|---------------|
| T001 | none | — |
| T002–T008 | T001 | each other |
| T009 | T002, T003 | T010 blocked |
| T010 | T002–T008 | T009 |
| T011 | T009, T010 | — |
| T012 | T011 merged | — |
| T013 | T012 | T014 |
| T014 | T012 | T013 |
| T015 | T014 | T013 |
| T016 | T013, T014, T015 | — |
| T017 | T013–T016 | — |

## Parallel Execution — PR 1 Wave

```
T001
└── T002 [P] ─┐
└── T003 [P] ─┤ (all in parallel)
└── T004 [P] ─┤
└── T005 [P] ─┤
└── T006 [P] ─┤
└── T007 [P] ─┤
└── T008 [P] ─┘
    ├── T009 (needs T002, T003)
    └── T010 (needs T002–T008)
        └── T011 (PR)
```

## Parallel Execution — PR 2 Wave

```
T012
├── T013 [P] ─────────────────────┐
└── T014 [P] → T015 (same dir) ──┴── T016 → T017 (PR)
```
