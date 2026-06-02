# Architecture — Module/Layer/Coupling Quality Audit

## Mode dispatch

0. Apply portable skill contract.
1. Parse mode from argument (first word).
2. Default to `audit` if no mode given.
3. Read `modes/<mode>/SKILL.md` completely.
4. If `gotchas.yml` exists, read it before executing.

| Mode | File | Keywords |
|------|------|---------|
| audit | audit/SKILL.md | audit:, architecture audit:, arch audit:, coupling audit: |

## What This Skill Does

`audit` — automated review of module structure, layer relationships, and coupling patterns.
Static detection (AST-based) for structural rules (god class/module, import count, nesting depth,
premature abstraction). LLM detection for semantic rules (cohesion, layer leakage, abstraction quality).
Never fixes — classifies and reports only.

## Source Authority

Rules defined in `rules.yml`. Stack-aware thresholds in `config.yml` (overridable per project).

## Supported Languages (Phase 1)

**Python:** All 13 rules (primary proving ground: dream-studio-clean)
**TypeScript / JavaScript:** All 13 rules (primary proving ground: DreamySuite Next.js)
**Go:** All 13 rules (static analysis; proving ground: TBD Phase 2)
**Rust:** All 13 rules (static analysis; proving ground: TBD Phase 2)

## Phase 2 Rules (Deferred)

**arch-007** (module-level circular deps): requires full import graph + SCC algorithm
(Tarjan/Kosaraju). dep-007 in types-deps skill covers direct import-level cycles today.
arch-007 covers transitive paths invisible to dep-007. Implement when
`canonical/skills/quality/shared/dependency_graph.py` exists.

**arch-008** (high afferent coupling): requires in-degree computation on full import graph.
Implement alongside arch-007 using the same graph builder.

## Skill Boundary

**Architecture skill owns:** module/class/layer structure — god objects, layer inversions,
cross-layer leakage, coupling/cohesion at module level, abstraction quality.

**Cross-references:**
- `arch-001` ↔ `cq-002` (class aggregate vs function LOC — dual-angle)
- `arch-001` ↔ `ux-007` (structural LOC vs reuse intent — dual-angle)
- `arch-007` (Phase 2) ↔ `dep-007` (transitive cycles vs direct import cycles — dual-angle)

## Stack-Aware Calibration

Thresholds in `config.yml` differ by stack family:
- **Frontend SPA:** god_class_loc=300, max_import_count=8 (components are small by design)
- **Backend service:** god_class_loc=500, max_import_count=15 (services coordinate many concerns)
- **Library:** god_class_loc=200, max_import_count=5 (narrow scope; reuse premium)

Projects override thresholds and layer_map via `architecture_config.yml` at project root.
