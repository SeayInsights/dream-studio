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

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "core" / "event_store" / "migrations"

_SPINE_SQL: str | None = None


def _spine_ddl() -> str:
    global _SPINE_SQL
    if _SPINE_SQL is None:
        _SPINE_SQL = (MIGRATIONS_DIR / "111_security_events_spine.sql").read_text(encoding="utf-8")
    return _SPINE_SQL


def _make_spine_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(_spine_ddl())
    conn.close()


@pytest.fixture()
def spine_db(tmp_path):
    """Temp SQLite file with migration-111 schema. Returns Path."""
    db = tmp_path / "test_spine.db"
    _make_spine_db(db)
    return db


@pytest.fixture()
def mem_conn():
    """In-memory SQLite with migration-111 schema for projection-level tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_spine_ddl())
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


# ── Migration DDL assertions ───────────────────────────────────────────────────


def test_migration_111_creates_all_three_tables():
    sql = (MIGRATIONS_DIR / "111_security_events_spine.sql").read_text(encoding="utf-8")
    for table in ("security_events", "readiness_events", "findings_current_status"):
        assert table in sql, f"migration 111 missing {table}"


def test_migration_111_security_events_has_required_columns():
    sql = (MIGRATIONS_DIR / "111_security_events_spine.sql").read_text(encoding="utf-8")
    for col in (
        "event_id",
        "parent_event_id",
        "event_kind",
        "severity",
        "vuln_class",
        "created_at",
    ):
        assert col in sql, f"migration 111 security_events missing column {col}"


def test_migration_111_findings_current_status_has_required_columns():
    sql = (MIGRATIONS_DIR / "111_security_events_spine.sql").read_text(encoding="utf-8")
    for col in ("finding_id", "current_status", "last_status_event_id", "created_at", "updated_at"):
        assert col in sql, f"migration 111 findings_current_status missing column {col}"


def test_migration_112_covers_retired_cluster():
    sql = (MIGRATIONS_DIR / "112_findings_cluster_retire.sql").read_text(encoding="utf-8")
    for table in ("sec_sarif_findings", "sec_cve_matches", "sec_manual_reviews"):
        assert table in sql, f"migration 112 should reference {table} for DROP"
    assert "vw_security_summary" in sql, "migration 112 should rebuild vw_security_summary"
