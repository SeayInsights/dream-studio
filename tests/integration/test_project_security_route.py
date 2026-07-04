"""Integration tests for WO-DASH-ATTRIBUTION-SURFACES T4/T5: project security route."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.config.sqlite_bootstrap import bootstrap_database

# ── Shared helpers ─────────────────────────────────────────────────────────────

DS_UUID = "29ff0914-b15a-4a84-8bc7-5619cc5240f6"


def _client(db_path: Path, monkeypatch) -> TestClient:
    from projections.api.main import app

    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    return TestClient(app)


def _seed_project(conn: sqlite3.Connection) -> None:
    """Insert the canonical Dream Studio project row."""
    conn.execute(
        "INSERT OR IGNORE INTO business_projects"
        " (project_id, name, project_path, status, created_at, updated_at)"
        " VALUES (?, ?, ?, 'active', datetime('now'), datetime('now'))",
        (DS_UUID, "Dream Studio", "/builds/dream-studio-clean"),
    )
    conn.commit()


# ── T4: test_security_renders_or_honest_empty ──────────────────────────────────


def test_security_renders_or_honest_empty(tmp_path: Path, monkeypatch) -> None:
    """T4: /api/v1/projects/{uuid}/security returns honest empty state or live findings.

    findings_current_status (a materialized projection over security_events)
    was dropped in migration 140 (WO dff23cb0) — current status is now derived
    from security_events at read time (core/findings/current_status.py).

    Scenario A — no finding.recorded events on the spine:
    Route derives zero findings from the (empty) security_events spine and
    returns honest empty state with count == 0. This is by-design behaviour,
    not a bug.

    Scenario B — security_events has 2 finding.recorded events (both 'open',
    the default status with no finding.status_changed event) for DS_UUID:
    Route derives them, excludes none, returns count == 2.
    """

    # ── Scenario A: no findings on the spine ─────────────────────────────────
    db_path_a = tmp_path / "empty.db"
    bootstrap_database(db_path_a)
    conn_a = sqlite3.connect(str(db_path_a))
    conn_a.row_factory = sqlite3.Row
    try:
        _seed_project(conn_a)
    finally:
        conn_a.close()

    client_a = _client(db_path_a, monkeypatch)
    resp_a = client_a.get(f"/api/v1/projects/{DS_UUID}/security")
    assert (
        resp_a.status_code == 200
    ), f"Expected 200 (honest empty state), got {resp_a.status_code}: {resp_a.text}"
    data_a = resp_a.json()
    assert "findings" in data_a, f"Missing 'findings' key in response: {data_a}"
    assert data_a["count"] == 0, (
        f"Expected count == 0 for a project with no findings table, got {data_a['count']}. "
        f"Full response: {data_a}"
    )

    # ── Scenario B: findings table with 2 open findings ───────────────────────
    db_path_b = tmp_path / "with_findings.db"
    bootstrap_database(db_path_b)
    conn_b = sqlite3.connect(str(db_path_b))
    conn_b.row_factory = sqlite3.Row
    try:
        _seed_project(conn_b)

        # security_events already created by bootstrap_database (migration 111).
        # Both findings stay 'open' (the CTE default) — no status_changed event.
        conn_b.executemany(
            "INSERT INTO security_events"
            " (event_id, event_kind, project_id, title, severity, file_path, line_number,"
            "  scanner_type, created_at)"
            " VALUES (?, 'finding.recorded', ?, ?, ?, ?, ?, ?, datetime('now'))",
            [
                (
                    "fnd-1",
                    DS_UUID,
                    "SQL injection risk",
                    "high",
                    "core/db.py",
                    42,
                    "static_analysis",
                ),
                (
                    "fnd-2",
                    DS_UUID,
                    "Hardcoded secret",
                    "critical",
                    "config.py",
                    10,
                    "secret_scan",
                ),
            ],
        )
        conn_b.commit()
    finally:
        conn_b.close()

    client_b = _client(db_path_b, monkeypatch)
    resp_b = client_b.get(f"/api/v1/projects/{DS_UUID}/security")
    assert resp_b.status_code == 200, f"Expected 200, got {resp_b.status_code}: {resp_b.text}"
    data_b = resp_b.json()
    assert data_b["count"] == 2, f"Expected count == 2, got {data_b['count']}. Response: {data_b}"
    for finding in data_b["findings"]:
        assert "severity" in finding, f"Finding missing 'severity': {finding}"
        assert "title" in finding, f"Finding missing 'title': {finding}"

    titles = {f["title"] for f in data_b["findings"]}
    assert (
        "Hardcoded secret" in titles
    ), f"Critical finding 'Hardcoded secret' not in response titles: {titles}"
    severities = {f["severity"] for f in data_b["findings"]}
    assert "critical" in severities, f"Expected 'critical' severity in findings, got: {severities}"


# ── T5: test_end_to_end ────────────────────────────────────────────────────────


def test_end_to_end(tmp_path: Path, monkeypatch) -> None:
    """T5 (end-to-end): security route filters resolved findings and surface availability agrees.

    findings_current_status (dropped migration 140, WO dff23cb0) used to carry
    current_status as a column; current status is now derived from the latest
    finding.status_changed event on the security_events spine (or 'open' if
    none — see core/findings/current_status.py).

    1. Bootstrap a DB, seed business_projects and security_events with
       1 open high finding and 1 resolved medium finding (resolved via a
       finding.status_changed event).
    2. Call GET /api/v1/projects/{uuid}/security.
    3. Assert status 200, count == 1 (resolved is excluded), the high finding present.
    4. Verify _project_surface_availability returns security=True when security_events exists.
    """
    db_path = tmp_path / "e2e.db"
    bootstrap_database(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        _seed_project(conn)

        # security_events already created by bootstrap_database (migration 111)
        conn.executemany(
            "INSERT INTO security_events"
            " (event_id, event_kind, project_id, title, severity, file_path, line_number,"
            "  scanner_type, created_at)"
            " VALUES (?, 'finding.recorded', ?, ?, ?, ?, ?, ?, datetime('now'))",
            [
                (
                    "fnd-open-1",
                    DS_UUID,
                    "Unsafe deserialization",
                    "high",
                    "core/loader.py",
                    88,
                    "static_analysis",
                ),
                (
                    "fnd-resolved-1",
                    DS_UUID,
                    "Outdated dependency",
                    "medium",
                    "requirements.txt",
                    5,
                    "dependency_scan",
                ),
            ],
        )
        conn.execute(
            "INSERT INTO security_events"
            " (event_id, parent_event_id, event_kind, project_id, body, created_at)"
            " VALUES ('fnd-resolved-1-status', 'fnd-resolved-1', 'finding.status_changed',"
            "  ?, 'resolved', datetime('now'))",
            (DS_UUID,),
        )
        conn.commit()

        # Verify surface availability while connection is open (same DB state)
        from projections.api.lib.project_helpers import _project_surface_availability

        availability = _project_surface_availability(conn)
        assert availability["security"] is True, (
            f"_project_surface_availability should return security=True when "
            f"security_events exists, got: {availability}"
        )
    finally:
        conn.close()

    client = _client(db_path, monkeypatch)
    resp = client.get(f"/api/v1/projects/{DS_UUID}/security")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert (
        data["count"] == 1
    ), f"Expected count == 1 (resolved excluded), got {data['count']}. Response: {data}"

    assert (
        len(data["findings"]) == 1
    ), f"Expected 1 finding in list, got {len(data['findings'])}. Response: {data}"
    open_finding = data["findings"][0]
    assert (
        open_finding["severity"] == "high"
    ), f"Expected 'high' severity for the open finding, got: {open_finding['severity']}"
    assert (
        open_finding["title"] == "Unsafe deserialization"
    ), f"Expected title 'Unsafe deserialization', got: {open_finding['title']}"
    assert (
        open_finding["status"] == "open"
    ), f"Expected status 'open', got: {open_finding['status']}"
