# TA0c — activity_log Write-Site Inventory

Generated: 2026-05-21 during TA0c reconnaissance.
Scope: All INSERT and SELECT sites for `activity_log` across production code.
Purpose: Spec for what canonical event types are needed and how each write site maps.

---

## Schema

```sql
CREATE TABLE IF NOT EXISTS activity_log (
    activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_type TEXT NOT NULL,
    stream_id TEXT,
    stream_type TEXT,
    event_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    event_data TEXT,  -- JSON blob
    prd_id TEXT,
    task_id TEXT,
    session_id TEXT,
    workflow_run_key TEXT,
    skill_id TEXT,
    status TEXT CHECK(status IN ('pending','in_progress','completed','failed','cancelled')),
    severity TEXT CHECK(severity IN ('info','warning','error','critical')),
    duration_ms INTEGER,
    is_anomaly BOOLEAN DEFAULT 0,
    anomaly_score REAL DEFAULT 0.0,
    FOREIGN KEY (prd_id) REFERENCES prd_documents(prd_id) ON DELETE SET NULL,
    FOREIGN KEY (task_id) REFERENCES prd_tasks(task_id) ON DELETE SET NULL,
    FOREIGN KEY (session_id) REFERENCES prd_sessions(session_id) ON DELETE SET NULL,
    FOREIGN KEY (workflow_run_key) REFERENCES raw_workflow_runs(run_key) ON DELETE SET NULL,
    FOREIGN KEY (skill_id) REFERENCES reg_skills(skill_id) ON DELETE SET NULL
);
```

Row count at audit time: 156 rows (all get backfilled in migration 062).

---

## FK Dependencies (child tables that reference activity_log.activity_id)

These tables have an `activity_id INTEGER` column linking to `activity_log`:
- `raw_workflow_runs.activity_id`
- `raw_workflow_nodes.activity_id`
- `raw_lessons.activity_id`
- `raw_research.activity_id`
- `research_cache.activity_id`

**Migration decision:** Set `activity_id = NULL` in all new inserts going forward.
The FK column is nullable in all five tables. The column itself stays until a future cleanup PR
removes it — this PR only stops writing to it.

---

## Write Sites

### W1 — control/analysis/engine.py:193
- **Function:** `analyze_project()` — start of analysis run
- **activity_type:** `"analysis.started"`
- **Columns:** `activity_type, stream_id, stream_type, event_timestamp, event_data, status, severity`
- **Pattern:** Inside `if _NORMALIZER_AVAILABLE:` block inside `with transaction() as conn:`
- **Canonical already emitted:** YES — `write_envelopes([CanonicalEventEnvelope(ANALYSIS_STARTED)])` at line 147–162, before the `if _NORMALIZER_AVAILABLE:` block
- **Canonical EventType:** `EventType.ANALYSIS_STARTED` ("analysis.started") — **already exists**
- **Migration:** DELETE the `if _NORMALIZER_AVAILABLE:` block (lines 176–206). The `with transaction()` block remains for the `pi_analysis_runs` INSERT.

### W2 — control/analysis/engine.py:259
- **Function:** `analyze_project()` — Phase 1 (discovery) completion
- **activity_type:** `"analysis.phase.completed"` with `phase="discovery"` in event_data
- **Pattern:** Same as W1 — `if _NORMALIZER_AVAILABLE:` inside `with transaction()`
- **Canonical already emitted:** YES — `write_envelopes([ANALYSIS_DISCOVERY_COMPLETED])` at lines 215–230
- **Canonical EventType:** `EventType.ANALYSIS_DISCOVERY_COMPLETED` — **already exists**
- **Migration:** DELETE the `if _NORMALIZER_AVAILABLE:` block (lines 242–272).

### W3 — control/analysis/engine.py:328
- **Function:** `analyze_project()` — Phase 2 (research) completion
- **activity_type:** `"analysis.phase.completed"` with `phase="research"`
- **Canonical already emitted:** YES — `write_envelopes([ANALYSIS_RESEARCH_COMPLETED])` before the block
- **Canonical EventType:** `EventType.ANALYSIS_RESEARCH_COMPLETED` — **already exists**
- **Migration:** DELETE the `if _NORMALIZER_AVAILABLE:` block.

### W4 — control/analysis/engine.py:405
- **Function:** `analyze_project()` — Phase 3 (audit) completion
- **activity_type:** `"analysis.phase.completed"` with `phase="audit"`
- **Canonical already emitted:** YES — `write_envelopes([ANALYSIS_AUDIT_COMPLETED])` before the block
- **Canonical EventType:** `EventType.ANALYSIS_AUDIT_COMPLETED` — **already exists**
- **Migration:** DELETE the `if _NORMALIZER_AVAILABLE:` block.

### W5 — control/analysis/engine.py:475
- **Function:** `analyze_project()` — Phase 4 (bug analysis) completion
- **activity_type:** `"analysis.phase.completed"` with `phase="bug_analysis"`
- **Canonical already emitted:** YES — `write_envelopes([ANALYSIS_BUG_ANALYSIS_COMPLETED])` before the block
- **Canonical EventType:** `EventType.ANALYSIS_BUG_ANALYSIS_COMPLETED` — **already exists**
- **Migration:** DELETE the `if _NORMALIZER_AVAILABLE:` block.

### W6 — control/analysis/engine.py:545
- **Function:** `analyze_project()` — Phase 5 (synthesis) completion
- **activity_type:** `"analysis.phase.completed"` with `phase="synthesis"`
- **Canonical already emitted:** YES — `write_envelopes([ANALYSIS_SYNTHESIS_COMPLETED])` before the block
- **Canonical EventType:** `EventType.ANALYSIS_SYNTHESIS_COMPLETED` — **already exists**
- **Migration:** DELETE the `if _NORMALIZER_AVAILABLE:` block.

### W7 — control/analysis/engine.py:621
- **Function:** `analyze_project()` — overall analysis completion
- **activity_type:** `"analysis.completed"`
- **Canonical already emitted:** YES — `write_envelopes([ANALYSIS_COMPLETED])` at lines 569–587, before the block
- **Canonical EventType:** `EventType.ANALYSIS_COMPLETED` — **already exists**
- **Migration:** DELETE the `if _NORMALIZER_AVAILABLE:` block (lines 602–635).

---

### W8/W9 — core/event_store/studio_db.py:313, 338 (_insert_activity_log hub)

The `_insert_activity_log()` function has two internal code paths:
- **W8 (line 313):** INSERT when called with an existing `conn` (pass-through)
- **W9 (line 338):** INSERT via a new `_db_transaction()` when `conn` is None

This function is the central hub — it is NOT a standalone call site. Its callers (W11, W13, W14, W15, W16, W17) are the logical write sites. After all callers are replaced with `write_envelopes()`, this function must be deleted entirely.

The function also calls `bridge.emit_from_legacy()` after the INSERT — this bridge-based canonical emission is also superseded by direct `write_envelopes()` in the callers after migration.

### W10 — core/event_store/studio_db.py:459 (archive_workflow — normalizer path)
- **Function:** `archive_workflow()` — workflow run completion (normalizer-available path)
- **activity_type:** `"workflow_run"`
- **Columns:** All 13 columns including `prd_id, task_id, session_id, duration_ms`
- **activity_id used as FK:** YES — `raw_workflow_runs.activity_id = cur.lastrowid`
- **Canonical already emitted:** NO — this path only writes to activity_log; no prior write_envelopes call
- **Canonical EventType:** `EventType.WORKFLOW_COMPLETED` ("workflow.completed") — **NEW**
- **Migration:** Replace with `write_envelopes()` for WORKFLOW_COMPLETED; set `activity_id = None` for the raw_workflow_runs INSERT.

### W11 — core/event_store/studio_db.py:492 (archive_workflow — fallback path)
- **Function:** `archive_workflow()` — workflow run (fallback when normalizer unavailable)
- **activity_type:** `"workflow_run"` via `_insert_activity_log()`
- **Migration:** This is the `else:` branch of W10. Both branches collapse into a single `write_envelopes()` call after migration.

### W12 — core/event_store/studio_db.py:572 (archive_workflow — workflow node, normalizer path)
- **Function:** `archive_workflow()` — each workflow DAG node completion
- **activity_type:** `"workflow_node"`
- **activity_id used as FK:** YES — `raw_workflow_nodes.activity_id = cur.lastrowid`
- **Canonical already emitted:** NO — only activity_log written in this path
- **Canonical EventType:** `EventType.WORKFLOW_NODE_COMPLETED` ("workflow.node.completed") — **already exists**
- **Migration:** Replace with `write_envelopes()` for WORKFLOW_NODE_COMPLETED; set `node_activity_id = None`.

### W13 — core/event_store/studio_db.py:596 (archive_workflow — workflow node, fallback)
- **activity_type:** `"workflow_node"` via `_insert_activity_log()`
- **Migration:** Collapses into W12's single write_envelopes() call.

### W14 — core/event_store/studio_db.py:2404 (capture_lesson — fallback)
- **Function:** `capture_lesson()` — lesson learned captured
- **activity_type:** `"lesson_captured"` via `_insert_activity_log()`
- **Payload:** `source, title, confidence`
- **activity_id used as FK:** YES — `raw_lessons.activity_id`
- **Canonical already emitted:** YES via normalizer path (lines before 2402 INSERT INTO activity_log directly, not shown in W14 context — but follows same if/else pattern as W10/W11)
- **Canonical EventType:** `EventType.LESSON_CAPTURED` ("system.lesson.captured") — **NEW**
- **Migration:** Both branches (normalizer INSERT + fallback _insert_activity_log) → single `write_envelopes()` for LESSON_CAPTURED; set `activity_id = None`.

### W15 — core/event_store/studio_db.py:2582 (store_research — fallback)
- **Function:** `store_research()` — research query completed
- **activity_type:** `"research_completed"` via `_insert_activity_log()`
- **Payload:** `query, source_type, source_url, confidence_score`
- **activity_id used as FK:** YES — `raw_research.activity_id`
- **Canonical EventType:** `EventType.RESEARCH_COMPLETED` ("research.completed") — **already exists**
- **Migration:** Both branches → single `write_envelopes()` for RESEARCH_COMPLETED; set `activity_id = None`.

### W16 — core/event_store/studio_db.py:2711 (cache_research — fallback)
- **Function:** `cache_research()` — research result cached
- **activity_type:** `"research_cached"` via `_insert_activity_log()`
- **Payload:** `topic, source_count, confidence_score, triangulation_score`
- **activity_id used as FK:** YES — `research_cache.activity_id`
- **Canonical EventType:** `EventType.RESEARCH_CACHE_STORED` ("research.cache_stored") — **already exists**
- **Migration:** Both branches → single `write_envelopes()` for RESEARCH_CACHE_STORED; set `activity_id = None`.

### W17 — core/event_store/studio_db.py:3237 (log_skill_execution)
- **Function:** `log_skill_execution()` — skill execution telemetry
- **activity_type:** `"skill_execution"` via `_insert_activity_log()`
- **Payload:** `skill_name, skill_args, status, model, duration_ms, error_message`
- **activity_id used as FK:** NO — return value only used as boolean success check
- **Canonical already emitted:** NO — only `_insert_activity_log()` call; no normalizer path
- **Canonical EventType:** `EventType.SKILL_EXECUTED` ("skill.executed") — **NEW**
- **Migration:** Replace `_insert_activity_log()` call with `write_envelopes()`; return value becomes True if envelopes written without exception.

### W18 — projections/scoring/engine.py:202 (emit_enriched_event)
- **Function:** `ScoringEngine.emit_enriched_event()` — risk score written back to activity_log
- **activity_type:** `"risk_score.computed"`
- **Payload:** `source_event_id, source_type, risk_score, computed_at, components`
- **Note:** activity_id column is being set to a non-integer string (`f"risk-{...}"`) — bug in existing code; SQLite stores as TEXT
- **Canonical EventType:** `EventType.RISK_SCORE_COMPUTED` ("risk.score.computed") — **NEW**
- **Migration:** Replace INSERT with `write_envelopes()` for RISK_SCORE_COMPUTED. source_event_id in payload changes from `event['activity_id']` to the canonical `event_id` (UUID).

### W19 — projections/parsers/sarif_parser.py:275 (import_findings)
- **Function:** `SarifParser.import_findings()` — security finding from SARIF tool
- **activity_type:** `"security_finding"`
- **Payload:** `file_path, line_number, rule_id, severity, message`
- **Canonical EventType:** `EventType.SECURITY_FINDING_RECORDED` ("security.finding.recorded") — **NEW**
- **Migration:** Replace INSERT with `write_envelopes()` for SECURITY_FINDING_RECORDED.

---

## Read Sites (Production)

These sites query activity_log in production code. All must be migrated to canonical_events before the table is dropped.

### R1 — projections/scoring/engine.py:91
- **Query:** `SELECT ... FROM activity_log WHERE activity_type LIKE 'security.%' AND activity_id NOT IN (subquery for risk_score.computed)`
- **Purpose:** Fetch unscored security events for risk scoring
- **Migration:** `WHERE event_type LIKE 'security.%' AND event_id NOT IN (SELECT json_extract(payload, '$.source_event_id') FROM canonical_events WHERE event_type = 'risk.score.computed' ...)`

### R2 — projections/scoring/engine.py:95
- **Query:** Anti-join subquery inside R1
- **Migration:** Part of R1 migration above.

### R3 — guardrails/evaluator.py:157
- **Query:** `SELECT event_data FROM activity_log WHERE {where_clause}` (dynamic)
- **Purpose:** Guardrail trigger evaluation — checks file patterns in event_data
- **Migration:** `SELECT payload FROM canonical_events WHERE {equivalent_where_clause}` (column rename: event_data → payload)

### R4 — guardrails/evaluator.py:164
- **Query:** `SELECT COUNT(*) FROM activity_log WHERE {where_clause}` (dynamic)
- **Migration:** Same as R3 with COUNT(*).

### R5 — projections/api/routes/intelligence.py:266
- **Query:** `SELECT COUNT(*) FROM activity_log al WHERE al.event_timestamp > datetime('now', '-7 days') {filter}`
- **Purpose:** Project intelligence dashboard — recent activity count
- **Migration:** `SELECT COUNT(*) FROM canonical_events ce WHERE ce.timestamp > datetime('now', '-7 days') {filter}` (column rename: event_timestamp → timestamp)

### R6 — projections/api/routes/intelligence.py:383
- **Query:** `FROM activity_log al` in larger JOIN query
- **Purpose:** Dashboard activity metrics
- **Migration:** `FROM canonical_events ce` with column renames (event_timestamp→timestamp, event_data→payload, activity_type→event_type)

### R7 — interfaces/cli/benchmark_queries.py:54
- **Query:** `SELECT * FROM activity_log ORDER BY timestamp DESC LIMIT 100`
- **Purpose:** Benchmark only — not in production serving path
- **Migration:** Update to query canonical_events or remove.

### R8 — interfaces/cli/benchmark_queries.py:55
- **Query:** `SELECT COUNT(*) FROM activity_log`
- **Migration:** Update to query canonical_events or remove.

### R9 — core/event_store/studio_db.py:3010
- **Query:** `SELECT is_anomaly FROM activity_log WHERE activity_id = ?`
- **Purpose:** Anomaly detection — retrieve anomaly flag for a specific activity
- **Migration:** Anomaly scores are not in canonical_events schema. Options: (a) return False/None since anomaly detection against activity_log ceases to function after drop, (b) migrate anomaly data separately. **Decision: return None and log a deprecation warning** — anomaly detection against activity_log is legacy functionality.

---

## Read Sites (Tests)

These are in test files. Tests that set up activity_log for test isolation purposes may stay; assertions against production writes must be updated.

- `tests/unit/test_skill_execution_logging.py:94,122,151,177,204` — verify skill execution is logged; need to update to check canonical_events
- `tests/runtime_verification/test_write_paths.py:216,247` — runtime verification of write paths
- `tests/core/test_dual_write.py:67` — verifies dual-write; needs update to verify canonical_events only after drop
- `tests/unit/test_governance_privacy_boundaries.py:409,414` — verifies security findings are logged

---

## Canonical Event Types: New Registrations Required

Add to `canonical/events/types.py` (EventType enum + EVENT_TYPE_REGISTRY):

| Constant | Value | activity_type Source | Domain |
|---|---|---|---|
| `WORKFLOW_COMPLETED` | `"workflow.completed"` | `workflow_run` | `telemetry` |
| `LESSON_CAPTURED` | `"system.lesson.captured"` | `lesson_captured` | `telemetry` |
| `SKILL_EXECUTED` | `"skill.executed"` | `skill_execution` | `telemetry` |
| `RISK_SCORE_COMPUTED` | `"risk.score.computed"` | `risk_score.computed` | `telemetry` |
| `SECURITY_FINDING_RECORDED` | `"security.finding.recorded"` | `security_finding` | `telemetry` |

Already exists (no action needed):
- `ANALYSIS_STARTED`, `ANALYSIS_DISCOVERY_COMPLETED`, `ANALYSIS_RESEARCH_COMPLETED`, `ANALYSIS_AUDIT_COMPLETED`, `ANALYSIS_BUG_ANALYSIS_COMPLETED`, `ANALYSIS_SYNTHESIS_COMPLETED`, `ANALYSIS_COMPLETED`
- `WORKFLOW_NODE_COMPLETED`
- `RESEARCH_COMPLETED`, `RESEARCH_CACHE_STORED`

---

## Migration Numbering

- Migration 061: `061_backfill_sdlc_creation_events.sql` (latest)
- Migration 062: `062_backfill_activity_log_to_canonical.sql` (backfill 156 rows)
- Migration 063: `063_drop_activity_log.sql` (drop table + verify count)

---

## Audit vs Actual Count

User's pre-audit estimate: 8 write sites (7 in engine.py + 1 in studio_db.py)
Actual write sites found: 19 (7 in engine.py + 10 in studio_db.py + 1 in scoring/engine.py + 1 in sarif_parser.py)
Production read sites found: 9 (R1-R9)
Test read sites found: 10 (informational — some may stay as test setup)

All 19 write sites and 9 production read sites are in scope for this PR.
