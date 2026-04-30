---
title: DSAE Phase 1 — Task Breakdown
plan: .planning/specs/ds-analytics/plan.md
spec: .planning/specs/ds-analytics/spec.md
created: 2026-04-30
traceability: active
total_tasks: 11
---

# DSAE Phase 1 — Tasks

Traceability: ACTIVE (4 requirements, 11 tasks, 4 success criteria)

---

## Phase A — Scaffold

### T001 — Project scaffold and deps
- **Implements:** (infrastructure — no TR-ID)
- **Files:**
  - `scripts/ds_analytics/__init__.py` (create, empty)
  - `scripts/ds_analytics/main.py` (create, skeleton only — arg parse + placeholder calls)
  - `requirements.txt` (edit — add pandas, scikit-learn, jinja2)
  - `Makefile` (edit — add `analytics` target: `py scripts/ds_analytics/main.py`)
- **Depends on:** none
- **Acceptance:** `py scripts/ds_analytics/main.py` runs without ImportError and prints "DSAE: no data yet"

---

## Phase B — Data Harvesting

*All Phase B tasks depend on T001. T002 must complete before T003, T004, T006 can start. T005 depends on T004.*

### T002 — Extend studio.db schema with analytics tables
- **Implements:** (infrastructure for TR-001, TR-002, TR-004)
- **Files:**
  - `hooks/lib/studio_db.py` (edit — append DDL for `raw_pulse_snapshots`, `raw_planning_specs`, `sum_analytics_run`)
- **Depends on:** T001
- **Acceptance:** `py hooks/lib/studio_db.py status` lists all three new tables with 0 rows and no error

### T003 [P] — Pulse file harvester
- **Implements:** TR-002
- **Files:**
  - `scripts/ds_analytics/harvester.py` (create / edit — add `harvest_pulse()` function)
- **Depends on:** T002
- **Acceptance:** `harvest_pulse()` reads all `~/.dream-studio/meta/pulse-*.md` files, inserts rows into `raw_pulse_snapshots`, and returns a non-empty list of dicts with keys `snapshot_date`, `health_score`

### T004 [P] — Planning spec harvester
- **Implements:** TR-001
- **Files:**
  - `scripts/ds_analytics/harvester.py` (edit — add `harvest_specs()` function)
- **Depends on:** T002
- **Acceptance:** `harvest_specs()` walks `.planning/specs/**/spec.md` across all known project paths, parses YAML front matter, and inserts rows into `raw_planning_specs`; returns count >= 1 for the ds-analytics spec itself

### T005 — Orphan detection
- **Implements:** TR-001
- **Files:**
  - `scripts/ds_analytics/harvester.py` (edit — add `detect_orphans()` function)
- **Depends on:** T004
- **Acceptance:** `detect_orphans()` sets `has_build_commit=0` for any spec with no `dream-studio:build` commit within 14 days of `created_date` in git history; result persists to `raw_planning_specs` and function returns a list of orphaned spec titles

### T006 [P] — Skill telemetry harvester
- **Implements:** TR-004
- **Files:**
  - `scripts/ds_analytics/harvester.py` (edit — add `harvest_skill_velocity()` function)
- **Depends on:** T002
- **Acceptance:** `harvest_skill_velocity()` queries `effective_skill_runs` from `studio.db` and returns a DataFrame with columns `skill_name`, `week`, `invocation_count`, `success_rate`; no error if table is empty (returns empty DataFrame)

---

## Phase C — Analysis

*All Phase C tasks depend on T003, T004, T005, T006 all being complete.*

### T007 — Pulse trend analysis
- **Implements:** TR-002
- **Files:**
  - `scripts/ds_analytics/analyzer.py` (create / edit — add `compute_pulse_trend()` function)
- **Depends on:** T003, T004, T005, T006
- **Acceptance:** `compute_pulse_trend()` reads `raw_pulse_snapshots`, fits a linear regression on health_score over time, and returns a dict with keys `dates`, `scores`, `trend_slope`, `trend_direction` ("improving" / "degrading" / "stable")

### T008 — Skill velocity + spec conversion analysis
- **Implements:** TR-004, TR-001
- **Files:**
  - `scripts/ds_analytics/analyzer.py` (edit — add `compute_skill_velocity()` and `compute_conversion_rate()` functions)
- **Depends on:** T003, T004, T005, T006
- **Acceptance:** `compute_skill_velocity()` returns a DataFrame sorted by invocation_count descending; `compute_conversion_rate()` returns `{"total": N, "orphaned": M, "rate": float}` where rate = (total - orphaned) / total

---

## Phase D — Rendering

*Rendering depends on all analysis tasks completing. T009 and T010 are sequential (renderer loads the template).*

### T009 — HTML renderer module
- **Implements:** TR-003
- **Files:**
  - `scripts/ds_analytics/renderer.py` (create — `render_dashboard(data: dict, output_path: Path)` function)
- **Depends on:** T007, T008
- **Acceptance:** `render_dashboard()` accepts the merged analysis dict and writes a file to the given path; calling it with fixture data produces a file that `open` can read without error and that contains the string `"Chart.js"` (confirming Chart.js is embedded)

### T010 — Dashboard Jinja2 template
- **Implements:** TR-003
- **Files:**
  - `scripts/ds_analytics/templates/dashboard.html.j2` (create — full HTML template with Chart.js bundle inline, 4 chart blocks)
- **Depends on:** T009
- **Acceptance:** Template renders to valid HTML with exactly 4 `<canvas>` elements (pulse trend, skill velocity, conversion rate donut, orphaned specs bar); Chart.js bundle present in `<script>` tag without any CDN URL

### T011 — Wire main.py and smoke test
- **Implements:** TR-001, TR-002, TR-003, TR-004
- **Files:**
  - `scripts/ds_analytics/main.py` (edit — replace placeholder with full orchestration: harvest → analyze → render → print output path)
- **Depends on:** T010
- **Acceptance:** `py scripts/ds_analytics/main.py` completes without error, prints the path to `~/.dream-studio/analytics/dashboard.html`, and the file exists on disk and opens in a browser without a server

---

## Summary

| Task | Description | Parallel | Depends On | Implements |
|---|---|---|---|---|
| T001 | Project scaffold and deps | — | none | infra |
| T002 | Extend studio.db schema | — | T001 | infra |
| T003 | Pulse file harvester | [P] | T002 | TR-002 |
| T004 | Planning spec harvester | [P] | T002 | TR-001 |
| T005 | Orphan detection | — | T004 | TR-001 |
| T006 | Skill telemetry harvester | [P] | T002 | TR-004 |
| T007 | Pulse trend analysis | — | T003,T004,T005,T006 | TR-002 |
| T008 | Skill velocity + conversion | — | T003,T004,T005,T006 | TR-004,TR-001 |
| T009 | HTML renderer module | — | T007,T008 | TR-003 |
| T010 | Dashboard Jinja2 template | — | T009 | TR-003 |
| T011 | Wire main.py + smoke test | — | T010 | TR-001,TR-002,TR-003,TR-004 |

**Total tasks:** 11
**Parallel waves:** T003, T004, T006 can run simultaneously after T002
**Critical path:** T001 → T002 → T004 → T005 → T007 → T009 → T010 → T011

---

## Traceability Summary

| TR-ID | Description | Priority | Status | Tasks |
|---|---|---|---|---|
| TR-001 | Identify all orphaned specs | must | planned | T004, T005, T008, T011 |
| TR-002 | Pulse health trend over time | must | planned | T003, T007, T011 |
| TR-003 | Standalone HTML dashboard | must | planned | T009, T010, T011 |
| TR-004 | Skill velocity chart | must | planned | T006, T008, T011 |
