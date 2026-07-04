"""WO-Y: findings event-spine correctness (security_events spine).

findings_current_status (the materialized projection FindingsProjection used
to fold security_events into) was dropped in migration 140 (WO dff23cb0) —
pure derived state duplicating its source. current_status is now derived at
read time via core.findings.current_status.FINDINGS_CURRENT_STATUS_SQL.

Covers:
- record_finding() writes to security_events spine
- set_finding_status() appends a status-change event
- FINDINGS_CURRENT_STATUS_SQL derives an open finding correctly
- FINDINGS_CURRENT_STATUS_SQL is idempotent/stable across repeated queries
  (no persisted state to duplicate — every call recomputes from security_events)
- FINDINGS_CURRENT_STATUS_SQL applies status-change events to current_status
- FINDINGS_CURRENT_STATUS_SQL degrades gracefully when security_events is missing
- Migrations 111 / 112 DDL assertions
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, UTC
from pathlib import Path

import pytest

pytestmark = pytest.mark.runtime_reliability

# WO-SQUASH-BASELINE (5fd84891, 2026-07-04): migrations 111/112 were collapsed
# into 142_lean_baseline.sql. security_events and readiness_events (the tables
# this file's fixtures need) are still live KEEP tables in the baseline;
# findings_current_status is not (dropped by migration 140, folded into the
# squash). The fixtures below now apply the full baseline via run_migrations()
# instead of hand-executing a specific deleted migration file's DDL text --
# simpler and correct regardless of which migration originally created a table.


def _make_spine_db(path: Path) -> None:
    from core.config.sqlite_bootstrap import run_migrations

    conn = sqlite3.connect(str(path))
    run_migrations(conn, apply_unreleased=True)
    conn.commit()
    conn.close()


@pytest.fixture()
def spine_db(tmp_path):
    """Temp SQLite file with the security-events spine schema. Returns Path."""
    db = tmp_path / "test_spine.db"
    _make_spine_db(db)
    return db


@pytest.fixture()
def mem_conn():
    """In-memory SQLite with the security-events spine schema for projection-level tests."""
    from core.config.sqlite_bootstrap import run_migrations

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn, apply_unreleased=True)
    yield conn
    conn.close()


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


# ── record_finding ─────────────────────────────────────────────────────────────


def test_record_finding_inserts_into_security_events(spine_db):
    from core.findings.mutations import record_finding

    fid = record_finding(
        project_id="p-test",
        work_order_id="wo-test",
        severity="high",
        title="Hardcoded API key",
        body="Remove the secret from source.",
        file_path="app.py",
        line_number=42,
        scanner_type="gitleaks",
        cwe_id="CWE-798",
        owasp_category="A07",
        cve_id=None,
        vuln_class="generic-api-key",
        exploitability="medium",
        correlation_id="scan-001",
        db_path=spine_db,
    )

    conn = sqlite3.connect(str(spine_db))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM security_events WHERE event_id = ?", (fid,)).fetchone()
    conn.close()

    assert row is not None
    assert row["event_kind"] == "finding.recorded"
    assert row["project_id"] == "p-test"
    assert row["severity"] == "high"
    assert row["file_path"] == "app.py"
    assert row["line_number"] == 42
    assert row["vuln_class"] == "generic-api-key"
    assert row["cwe_id"] == "CWE-798"
    assert row["correlation_id"] == "scan-001"


def test_record_finding_returns_valid_uuid(spine_db):
    from core.findings.mutations import record_finding

    fid = record_finding(
        project_id=None,
        work_order_id=None,
        severity="low",
        title="Info disclosure",
        db_path=spine_db,
    )

    assert isinstance(fid, str)
    uuid.UUID(fid)  # raises ValueError if not a valid UUID


def test_record_finding_parent_event_id_is_null(spine_db):
    from core.findings.mutations import record_finding

    fid = record_finding(
        severity="medium",
        title="XSS",
        db_path=spine_db,
    )

    conn = sqlite3.connect(str(spine_db))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT parent_event_id FROM security_events WHERE event_id = ?", (fid,)
    ).fetchone()
    conn.close()

    assert row["parent_event_id"] is None


# ── set_finding_status ─────────────────────────────────────────────────────────


def test_set_finding_status_appends_status_changed_event(spine_db):
    from core.findings.mutations import record_finding, set_finding_status

    fid = record_finding(
        project_id="p-s1",
        severity="medium",
        title="Weak cipher",
        db_path=spine_db,
    )
    set_finding_status(
        fid,
        "false_positive",
        project_id="p-s1",
        reason="Not applicable here",
        db_path=spine_db,
    )

    conn = sqlite3.connect(str(spine_db))
    conn.row_factory = sqlite3.Row
    events = conn.execute(
        "SELECT event_kind, parent_event_id, body"
        " FROM security_events WHERE parent_event_id = ?",
        (fid,),
    ).fetchall()
    conn.close()

    assert len(events) == 1
    assert events[0]["event_kind"] == "finding.status_changed"
    assert events[0]["parent_event_id"] == fid
    assert "false_positive" in events[0]["body"]


def test_set_finding_status_multiple_transitions(spine_db):
    from core.findings.mutations import record_finding, set_finding_status

    fid = record_finding(severity="high", title="SSRF", db_path=spine_db)
    set_finding_status(fid, "mitigated", db_path=spine_db)
    set_finding_status(fid, "resolved", db_path=spine_db)

    conn = sqlite3.connect(str(spine_db))
    rows = conn.execute(
        "SELECT COUNT(*) FROM security_events WHERE parent_event_id = ?", (fid,)
    ).fetchone()
    conn.close()

    assert rows[0] == 2


# ── FINDINGS_CURRENT_STATUS_SQL (read-time derivation, migration 140) ─────────


def _current_status_row(conn: sqlite3.Connection, finding_id: str) -> sqlite3.Row | None:
    from core.findings.current_status import FINDINGS_CURRENT_STATUS_SQL

    return conn.execute(
        f"SELECT * FROM ({FINDINGS_CURRENT_STATUS_SQL}) WHERE finding_id = ?",
        (finding_id,),
    ).fetchone()


def test_derivation_computes_open_finding(mem_conn):
    eid = str(uuid.uuid4())
    mem_conn.execute(
        """INSERT INTO security_events
           (event_id, event_kind, project_id, severity, title,
            file_path, line_number, scanner_type, created_at)
           VALUES (?, 'finding.recorded', ?, ?, ?, ?, ?, ?, ?)""",
        (eid, "proj-fold-1", "critical", "SQL injection", "db.py", 10, "semgrep", _now()),
    )
    mem_conn.commit()

    row = _current_status_row(mem_conn, eid)

    assert row is not None
    assert row["current_status"] == "open"
    assert row["severity"] == "critical"
    assert row["project_id"] == "proj-fold-1"


def test_derivation_is_stable_across_repeated_queries(mem_conn):
    eid = str(uuid.uuid4())
    mem_conn.execute(
        """INSERT INTO security_events
           (event_id, event_kind, project_id, severity, title, created_at)
           VALUES (?, 'finding.recorded', ?, 'low', 'Info leak', ?)""",
        (eid, "proj-idemp", _now()),
    )
    mem_conn.commit()

    first = _current_status_row(mem_conn, eid)
    second = _current_status_row(mem_conn, eid)

    assert dict(first) == dict(second)


def test_derivation_applies_status_change(mem_conn):
    fid = str(uuid.uuid4())
    sid = str(uuid.uuid4())
    now = _now()

    mem_conn.execute(
        """INSERT INTO security_events
           (event_id, event_kind, project_id, severity, title, created_at)
           VALUES (?, 'finding.recorded', 'proj-sc', 'medium', 'XSS', ?)""",
        (fid, now),
    )
    mem_conn.execute(
        """INSERT INTO security_events
           (event_id, parent_event_id, event_kind, project_id, body, created_at)
           VALUES (?, ?, 'finding.status_changed', 'proj-sc', 'resolved: fixed in PR #9', ?)""",
        (sid, fid, _now()),
    )
    mem_conn.commit()

    row = _current_status_row(mem_conn, fid)
    assert row["current_status"] == "resolved"
    assert row["last_status_event_id"] == sid


def test_derivation_returns_nothing_when_security_events_missing():
    from core.findings.current_status import FINDINGS_CURRENT_STATUS_SQL

    empty_conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises(sqlite3.OperationalError):
            empty_conn.execute(f"SELECT * FROM ({FINDINGS_CURRENT_STATUS_SQL})").fetchall()
    finally:
        empty_conn.close()


# ── end-to-end: record + derive + status ──────────────────────────────────────


def test_end_to_end_record_derive_status(spine_db):
    from core.findings.mutations import record_finding, set_finding_status

    fid = record_finding(
        project_id="proj-e2e",
        severity="high",
        title="Path traversal",
        file_path="upload.py",
        db_path=spine_db,
    )

    conn = sqlite3.connect(str(spine_db))
    conn.row_factory = sqlite3.Row
    row = _current_status_row(conn, fid)
    assert row["current_status"] == "open"
    conn.close()

    set_finding_status(fid, "mitigated", reason="WAF rule added", db_path=spine_db)

    conn = sqlite3.connect(str(spine_db))
    conn.row_factory = sqlite3.Row
    row = _current_status_row(conn, fid)
    assert row["current_status"] == "mitigated"
    conn.close()


# ── Fresh-schema DDL assertions ─────────────────────────────────────────────────
# WO-SQUASH-BASELINE (5fd84891, 2026-07-04): migrations 111 (created
# security_events/readiness_events/findings_current_status) and 112 (retired
# the sec_sarif_findings/sec_cve_matches/sec_manual_reviews cluster) were
# collapsed into 142_lean_baseline.sql. findings_current_status was itself
# later dropped (migration 140); its DDL-content assertion is removed rather
# than adapted since the table has no live schema to check. The remaining
# assertions are rewritten against the live fresh-chain schema (ground truth
# that survives regardless of which now-deleted migration file originally
# introduced or retired an object) instead of grepping specific migration
# file text.


def test_fresh_schema_has_security_and_readiness_events_tables(mem_conn):
    for table in ("security_events", "readiness_events"):
        row = mem_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)
        ).fetchone()
        assert row is not None, f"{table} missing from the fresh baseline schema"


def test_security_events_has_required_columns(mem_conn):
    cols = {row["name"] for row in mem_conn.execute("PRAGMA table_info(security_events)")}
    for col in (
        "event_id",
        "parent_event_id",
        "event_kind",
        "severity",
        "vuln_class",
        "created_at",
    ):
        assert col in cols, f"security_events missing column {col}"


def test_findings_current_status_dropped_and_retired_cluster_absent(mem_conn):
    """findings_current_status (migration 140) and the sec_sarif_findings/
    sec_cve_matches/sec_manual_reviews cluster (migration 112) must not exist
    in the fresh baseline schema; vw_security_summary must still exist,
    rebuilt to read security_events directly (migration 140)."""
    for table in (
        "findings_current_status",
        "sec_sarif_findings",
        "sec_cve_matches",
        "sec_manual_reviews",
    ):
        row = mem_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)
        ).fetchone()
        assert row is None, f"{table} should not exist in the fresh baseline schema"

    view_row = mem_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name = 'vw_security_summary'"
    ).fetchone()
    assert view_row is not None, "vw_security_summary should survive in the fresh baseline schema"
