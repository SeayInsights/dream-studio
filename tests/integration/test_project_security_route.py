"""Integration tests for WO-DASH-ATTRIBUTION-SURFACES T4/T5: project security route."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
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

    Scenario A — no findings_current_status table exists:
    Route falls through to pi_violations (also absent) and returns honest empty
    state with count == 0. This is by-design behaviour, not a bug.

    Scenario B — findings_current_status exists with 2 open findings for DS_UUID:
    Route reads them, excludes none (both are 'open'), returns count == 2.
    """

    # ── Scenario A: no findings table ────────────────────────────────────────
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

        # findings_current_status already created by bootstrap_database (migration 111)
        conn_b.executemany(
            "INSERT INTO findings_current_status"
            " (finding_id, project_id, title, severity, file_path, line_number,"
            "  current_status, scanner_type, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            [
                (
                    "fnd-1",
                    DS_UUID,
                    "SQL injection risk",
                    "high",
                    "core/db.py",
                    42,
                    "open",
                    "static_analysis",
                ),
                (
                    "fnd-2",
                    DS_UUID,
                    "Hardcoded secret",
                    "critical",
                    "config.py",
                    10,
                    "open",
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

    1. Bootstrap a DB, seed business_projects and findings_current_status with
       1 open high finding and 1 resolved medium finding.
    2. Call GET /api/v1/projects/{uuid}/security.
    3. Assert status 200, count == 1 (resolved is excluded), the high finding present.
    4. Verify _project_surface_availability returns security=True when the table exists.
    """
    db_path = tmp_path / "e2e.db"
    bootstrap_database(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        _seed_project(conn)

        # findings_current_status already created by bootstrap_database (migration 111)
        conn.executemany(
            "INSERT INTO findings_current_status"
            " (finding_id, project_id, title, severity, file_path, line_number,"
            "  current_status, scanner_type, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            [
                (
                    "fnd-open-1",
                    DS_UUID,
                    "Unsafe deserialization",
                    "high",
                    "core/loader.py",
                    88,
                    "open",
                    "static_analysis",
                ),
                (
                    "fnd-resolved-1",
                    DS_UUID,
                    "Outdated dependency",
                    "medium",
                    "requirements.txt",
                    5,
                    "resolved",
                    "dependency_scan",
                ),
            ],
        )
        conn.commit()

        # Verify surface availability while connection is open (same DB state)
        from projections.api.routes.project_intelligence import _project_surface_availability

        availability = _project_surface_availability(conn)
        assert availability["security"] is True, (
            f"_project_surface_availability should return security=True when "
            f"findings_current_status exists, got: {availability}"
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
