---
title: DSAE Phase 1 — Implementation Plan
spec: .planning/specs/ds-analytics/spec.md
status: ready
created: 2026-04-30
phase: 1 — HTML Dashboard only
traceability: active
---

# Dream-Studio Analytics Engine — Phase 1 Plan

## Scope

Phase 1 only. No `.pbip`, no TORII, no PandasAI. Delivers a standalone HTML dashboard
that reads dream-studio's own data (pulse reports, planning specs, git log, skill
telemetry) and renders interactive charts with zero server requirement.

Out of scope for Phase 1: Power BI output, TORII integration, external data feeds,
predictive modeling, lesson draft ingestion.

---

## Architecture

### Runtime Stack

| Layer | Technology | Notes |
|---|---|---|
| Entry point | `scripts/ds_analytics/main.py` | `py scripts/ds_analytics/main.py` or `make analytics` |
| Data layer | SQLite (extend `studio.db`) + file reads | Reuse `hooks/lib/studio_db.py` connection, add 3 new tables |
| ETL | pandas | Parse pulse markdown, spec YAML front matter, git log |
| Analysis | scikit-learn | TF-IDF + k-means for topic clustering; linear regression for trends |
| Output | Jinja2 template + Chart.js (embedded) | Single `.html` file, no CDN at view time |
| Path resolution | `hooks/lib/paths.py` | `state_dir()`, `meta_dir()`, `memory_dir()` |

### Module Layout

```
scripts/ds_analytics/
├── main.py              # Orchestrator: harvest → analyze → render
├── harvester.py         # Reads pulse files, specs, git log, memory index
├── analyzer.py          # pandas ETL + scikit-learn computations
├── renderer.py          # Jinja2 → HTML; embeds Chart.js inline
└── templates/
    └── dashboard.html.j2  # Jinja2 template with Chart.js bundle inline
```

### New SQLite Tables (extend studio.db)

```sql
-- Pulse snapshots parsed from ~/.dream-studio/meta/pulse-*.md
raw_pulse_snapshots (
  id, file_path TEXT, snapshot_date TEXT, health_score INTEGER,
  pr_velocity REAL, draft_backlog INTEGER, parsed_at TEXT
)

-- All planning specs discovered across projects
raw_planning_specs (
  id, spec_path TEXT, project TEXT, title TEXT, status TEXT,
  created_date TEXT, has_build_commit INTEGER, days_to_build INTEGER,
  parsed_at TEXT
)

-- Aggregated analysis results (cache layer)
sum_analytics_run (
  run_id TEXT PRIMARY KEY, ran_at TEXT, spec_count INTEGER,
  orphaned_count INTEGER, conversion_rate REAL,
  dominant_topic TEXT, output_path TEXT
)
```

### Data Flow

```
File System                SQLite (studio.db)         Analysis            Output
─────────────────          ───────────────────         ──────────          ──────
pulse-*.md         →       raw_pulse_snapshots  →      trend line   →
spec.md files      →       raw_planning_specs   →      conversion   →      dashboard.html
git log            →       (existing telemetry) →      skill vel.   →
MEMORY.md files    →       (in-memory only)     →      clustering   →
```

---

## Requirements Traceability

| TR-ID | Requirement | Priority | Source SC | Status | Tasks |
|---|---|---|---|---|---|
| TR-001 | Identify all orphaned specs across all projects | must | SC-001 | planned | T004, T005 |
| TR-002 | Pulse health trend visible over time | must | SC-002 | planned | T003, T007 |
| TR-003 | HTML dashboard is standalone (no server) | must | SC-004 | planned | T009, T010 |
| TR-004 | Skill velocity chart shows over/underused skills | must | SC-005 | planned | T006, T008 |

---

## Technical Decisions

### Why extend studio.db instead of a new database

`studio.db` is already WAL-mode, already has the skill telemetry we need for velocity
charts, and `hooks/lib/studio_db.py` handles connection setup. Adding new tables avoids
a second SQLite file and keeps all analytics in one place for future queries.

### Why Jinja2 for rendering

Chart.js must be embedded (no CDN at view time per spec). A Jinja2 template keeps the
HTML structure readable and separates data from presentation. The renderer passes
serialized JSON data blobs from the analyzer into the template, which Chart.js consumes
inline via `<script>` blocks.

### Why k-means on TF-IDF for orphan clustering

Spec content is short unstructured text. TF-IDF captures keyword weight without needing
a sentence transformer. k-means with k=5 gives readable topic groups. This is fast
enough to run on ~50–200 specs without GPU. If cluster quality is poor at build time,
we can tune `k` or switch to DBSCAN — that decision is deferred to the build phase.

### Orphan detection approach

For each spec, extract its `created` date from YAML front matter. Then run:
```
git log --all --oneline --after="<created_date>" --before="<created_date + 14 days>"
```
and grep for `dream-studio:build` in commit messages. If no match, the spec is orphaned.
This is a conservative heuristic — false negatives possible if build commits don't
follow naming convention, but false positives are worse (marking real builds as orphaned).

### Chart.js bundle size

Chart.js v4 minified is ~200KB. This will be inlined in the HTML file. The output file
will be ~300–400KB total. Acceptable for a local analytics report.

---

## File Ownership Map

| File | Owner task(s) | Notes |
|---|---|---|
| `scripts/ds_analytics/__init__.py` | T001 | Empty init |
| `scripts/ds_analytics/main.py` | T001, T011 | Skeleton in T001, wired in T011 |
| `scripts/ds_analytics/harvester.py` | T002, T003, T004, T005, T006 | Each task adds one harvester function |
| `scripts/ds_analytics/analyzer.py` | T007, T008 | Each task adds one analysis function |
| `scripts/ds_analytics/renderer.py` | T009 | Owns renderer module entirely |
| `scripts/ds_analytics/templates/dashboard.html.j2` | T010 | Owns template entirely |
| `hooks/lib/studio_db.py` | T002 | Adds 3 new table DDL blocks only |
| `requirements.txt` | T001 | Adds pandas, scikit-learn, jinja2 |
| `Makefile` | T001 | Adds `analytics` target |

No two parallel tasks share a file.

---

## Dependency Graph

```
T001 (scaffold)
  └─ T002 (schema) ──┬─ T003 (pulse harvester) [P]
                     ├─ T004 (spec harvester)  [P]
                     ├─ T005 (orphan detect)  ← depends T004
                     └─ T006 (git harvester)  [P]
                           └─ T007, T008 (analysis) ← depends T003,T004,T005,T006
                                  └─ T009 (renderer)
                                       └─ T010 (template)
                                            └─ T011 (wire + smoke test)
```

---

## Success Criteria Coverage

| SC | Description | Covered by |
|---|---|---|
| SC-001 | Orphaned spec detection | T004 + T005 |
| SC-002 | Pulse health trend over time | T003 + T007 |
| SC-004 | Standalone HTML (no server) | T009 + T010 |
| SC-005 | Skill velocity chart | T006 + T008 |

SC-003 (`.pbip`) is Phase 2 — not covered here.

---

## Runtime Deps Added

Add to `requirements.txt`:
```
pandas>=2.2
scikit-learn>=1.4
jinja2>=3.1
```

Chart.js v4 is downloaded at build time and embedded into the template — not a Python dep.

---

## Run Command

```bash
# Direct
py scripts/ds_analytics/main.py

# Via make
make analytics

# Output
~/.dream-studio/analytics/dashboard.html
```
