"""WO-DASH-DUCKDB-PROJECTION: prove dashboard component reads come from the
DuckDB analytics store (aggregate_metrics.db events_fact projection), not the
SQLite execution_events spine.

Each test seeds a DECOY row into SQLite and the REAL row into DuckDB events_fact,
then asserts the read model surfaces the DuckDB row and never the SQLite decoy —
so the assertions prove provenance, not merely that data is returned.

Repoint scope (this WO): the workflow component and the validation rollup. The
hook/tool/skill/agent components keep reading the SQLite spine until their
capture flows into canonical → events_fact (WO-HOOK-EXEC-STATS emits hook
execution events; WO-AGENT-TELEMETRY emits agent-identified events). Repointing
them now would drop live telemetry (hook.tool_activity has no canonical
equivalent) — a data-loss regression, not a completeness gain. source_tables
therefore still names execution_events for those spine components; it fully
leaves once those WOs land. validation_failures (event.validation.failed —
schema-rejected events) is a different metric and is deliberately NOT read here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.event_store.studio_db import _connect
from core.telemetry.read_models import component_usage_summary, global_telemetry_summary


def _isolate_analytics(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    from core.analytics import duckdb_store

    analytics_db = tmp_path / "aggregate_metrics.db"
    monkeypatch.setattr(duckdb_store, "analytics_db_path", lambda: analytics_db)
    return analytics_db


def _seed_events_fact(analytics_db: Path, rows: list[dict]) -> None:
    from core.analytics import duckdb_store

    conn = duckdb_store.connect_analytics(analytics_db, read_only=False)
    try:
        duckdb_store.ensure_analytics_schema(conn)
        for row in rows:
            conn.execute(
                "INSERT INTO events_fact (event_id, event_type, event_timestamp,"
                " project_id, milestone_id, task_id, workflow_id, status, outcome, payload)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    row["event_id"],
                    row["event_type"],
                    row.get("event_timestamp", "2026-07-08T00:00:00Z"),
                    row.get("project_id"),
                    row.get("milestone_id"),
                    row.get("task_id"),
                    row.get("workflow_id"),
                    row.get("status"),
                    row.get("outcome"),
                    json.dumps(row.get("payload", {})),
                ],
            )
    finally:
        conn.close()


def _seed_sqlite_decoys(db_path: Path) -> None:
    """Seed workflow + validation rows into the SQLite spine that must NEVER
    appear in the repointed reads (they now come from DuckDB)."""
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO execution_events (
                event_id, event_type, event_name, project_id, workflow_id, outcome_status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "decoy-workflow-event",
                "workflow.invocation_recorded",
                "SQLite spine decoy workflow",
                "decoy-project",
                "spine-only-workflow",
                "completed",
            ),
        )
        conn.execute(
            """
            INSERT INTO validation_results (
                validation_id, project_id, event_id, validation_type, status
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "decoy-validation",
                "decoy-project",
                "decoy-workflow-event",
                "spine-only-validation",
                "passed",
            ),
        )
        conn.commit()


def test_workflows_and_validations_from_duckdb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "spine.db"
    _connect(db_path).close()
    analytics_db = _isolate_analytics(monkeypatch, tmp_path)

    _seed_sqlite_decoys(db_path)
    _seed_events_fact(
        analytics_db,
        [
            {
                "event_id": "duck-workflow-1",
                "event_type": "workflow.completed",
                "project_id": "duck-project",
                "workflow_id": "duck-workflow",
                "status": "completed",
            },
            {
                "event_id": "duck-workflow-node-1",
                "event_type": "workflow.node.completed",
                "project_id": "duck-project",
                "workflow_id": "duck-workflow:node-a",
                "status": "failed",
            },
            {
                "event_id": "duck-validation-1",
                "event_type": "validation.result_recorded",
                "project_id": "duck-project",
                "status": "passed",
                "payload": {"validation_type": "pytest_suite"},
            },
        ],
    )

    summary = component_usage_summary(db_path=db_path)

    # Workflow usage comes from DuckDB events_fact (workflow.completed +
    # workflow.node.completed), never the SQLite spine decoy.
    workflow_ids = {row["component_id"] for row in summary["usage"]["workflow"]["rows"]}
    assert workflow_ids == {"duck-workflow", "duck-workflow:node-a"}
    assert "spine-only-workflow" not in workflow_ids

    by_id = {row["component_id"]: row for row in summary["usage"]["workflow"]["rows"]}
    assert by_id["duck-workflow"]["success_count"] == 1
    assert by_id["duck-workflow:node-a"]["failure_count"] == 1

    # Validation outcomes come from DuckDB events_fact (validation.result_recorded),
    # never the SQLite validation_results decoy — and are NOT the validation_failures
    # view (a different, schema-rejection metric).
    validation_types = {row["component_id"] for row in summary["validations"]}
    assert validation_types == {"pytest_suite"}
    assert "spine-only-validation" not in validation_types
    assert summary["validations"][0]["status"] == "passed"


def test_source_tables_are_duckdb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "spine.db"
    _connect(db_path).close()
    _isolate_analytics(monkeypatch, tmp_path)

    summary = component_usage_summary(db_path=db_path)
    source_tables = summary["source_tables"]

    # The DuckDB analytics store (events_fact) is a named source of the /components
    # read model — the all-DuckDB read surface.
    assert "events_fact" in source_tables
    # Token usage already reads the DuckDB view.
    assert "token_usage_records" in source_tables
    # The repointed validation read no longer names the SQLite validation_results
    # table.
    assert "validation_results" not in source_tables


def test_global_summary_validation_outcomes_from_duckdb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The global summary's validation_outcomes rollup also reads DuckDB, and does
    not fall back to the SQLite validation_results decoy."""
    db_path = tmp_path / "spine.db"
    _connect(db_path).close()
    analytics_db = _isolate_analytics(monkeypatch, tmp_path)

    _seed_sqlite_decoys(db_path)
    _seed_events_fact(
        analytics_db,
        [
            {
                "event_id": "duck-validation-2",
                "event_type": "validation.result_recorded",
                "project_id": "duck-project",
                "status": "failed",
                "payload": {"validation_type": "gate_check"},
            }
        ],
    )

    summary = global_telemetry_summary(db_path)
    types = {row["component_id"] for row in summary["validation_outcomes"]}
    assert types == {"gate_check"}
    assert "spine-only-validation" not in types
