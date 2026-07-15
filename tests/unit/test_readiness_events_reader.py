"""WO-SCHEMALEAN: production_readiness_dashboard_summary reads the readiness_events
spine (the normalized production_readiness_* tables were dropped in migration 112;
ds analytics-ingest writes readiness_events, and the reader was repointed to it).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from core.event_store.studio_db import _connect
from core.production_readiness.controls import production_readiness_dashboard_summary


def _seed_assessment(conn: sqlite3.Connection, project_id: str) -> None:
    conn.execute(
        "INSERT INTO readiness_events (event_id, event_kind, project_id, title, body, created_at)"
        " VALUES (?, 'assessment.started', ?, 'test', ?, '2026-07-15T00:00:00Z')",
        (
            "assess-1",
            project_id,
            json.dumps(
                {
                    "status": "partial",
                    "confidence": "medium",
                    "health_score": 82,
                    "readiness_score": 61,
                    "missing_evidence": ["accessibility review"],
                    "blocking_factors": [],
                    "release_readiness_effect": "needs_manual_review",
                }
            ),
        ),
    )
    for cid, result, family in (
        ("a11y", "manual_review", "accessibility"),
        ("sec", "pass", "security"),
    ):
        conn.execute(
            "INSERT INTO readiness_events (event_id, parent_event_id, event_kind, project_id,"
            " control_id, result, title, body, created_at) VALUES (?, 'assess-1',"
            " 'control_result.recorded', ?, ?, ?, ?, ?, '2026-07-15T00:00:01Z')",
            (
                f"ctl-{cid}",
                project_id,
                cid,
                result,
                cid,
                json.dumps({"control_family": family, "severity": "medium"}),
            ),
        )
    conn.commit()


def test_summary_reconstructed_from_readiness_events(tmp_path: Path) -> None:
    db = tmp_path / "studio.db"
    with _connect(db) as conn:
        _seed_assessment(conn, "proj-1")
        summary = production_readiness_dashboard_summary(conn, project_id="proj-1")

    assert summary["assessment_id"] == "assess-1"
    assert summary["status"] == "partial"
    assert summary["source_tables"] == ["readiness_events"]
    assert summary["readiness_score"]["score"] == 61
    assert summary["readiness_score"]["status"] == "partial"
    assert summary["health_score"]["score"] == 82
    assert summary["control_summary"]["total"] == 2
    assert summary["control_summary"]["pass"] == 1
    assert summary["control_summary"]["manual_review"] == 1
    assert {c["control_id"] for c in summary["controls"]} == {"a11y", "sec"}
    assert summary["empty_state"] is None


def test_empty_when_no_assessment(tmp_path: Path) -> None:
    db = tmp_path / "studio.db"
    with _connect(db) as conn:
        # readiness_events exists (migrated) but has no assessment for this project.
        summary = production_readiness_dashboard_summary(conn, project_id="none")
    assert summary["status"] == "unavailable"
    assert summary["readiness_score"]["status"] == "unavailable"
