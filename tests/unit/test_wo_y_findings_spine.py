"""WO-Y: findings event-spine correctness (security_events + findings_current_status).

Covers:
- record_finding() writes to security_events spine
- set_finding_status() appends a status-change event
- FindingsProjection.fold_spine() materialises findings_current_status correctly
- fold_spine() is idempotent (no duplicate rows on repeated calls)
- fold_spine() applies status-change events to update current_status
- Migrations 111 / 112 DDL assertions
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
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
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


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


# ── FindingsProjection.fold_spine ─────────────────────────────────────────────


def test_fold_spine_materialises_open_finding(mem_conn):
    from core.projections.findings_projection import FindingsProjection

    eid = str(uuid.uuid4())
    mem_conn.execute(
        """INSERT INTO security_events
           (event_id, event_kind, project_id, severity, title,
            file_path, line_number, scanner_type, created_at)
           VALUES (?, 'finding.recorded', ?, ?, ?, ?, ?, ?, ?)""",
        (eid, "proj-fold-1", "critical", "SQL injection", "db.py", 10, "semgrep", _now()),
    )
    mem_conn.commit()

    n = FindingsProjection().fold_spine(mem_conn)

    assert n == 1
    row = mem_conn.execute(
        "SELECT * FROM findings_current_status WHERE finding_id = ?", (eid,)
    ).fetchone()
    assert row is not None
    assert row["current_status"] == "open"
    assert row["severity"] == "critical"
    assert row["project_id"] == "proj-fold-1"


def test_fold_spine_is_idempotent(mem_conn):
    from core.projections.findings_projection import FindingsProjection

    eid = str(uuid.uuid4())
    mem_conn.execute(
        """INSERT INTO security_events
           (event_id, event_kind, project_id, severity, title, created_at)
           VALUES (?, 'finding.recorded', ?, 'low', 'Info leak', ?)""",
        (eid, "proj-idemp", _now()),
    )
    mem_conn.commit()

    proj = FindingsProjection()
    proj.fold_spine(mem_conn)
    proj.fold_spine(mem_conn)

    count = mem_conn.execute(
        "SELECT COUNT(*) FROM findings_current_status WHERE finding_id = ?", (eid,)
    ).fetchone()[0]
    assert count == 1


def test_fold_spine_applies_status_change_to_read_model(mem_conn):
    from core.projections.findings_projection import FindingsProjection

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

    FindingsProjection().fold_spine(mem_conn)

    row = mem_conn.execute(
        "SELECT current_status, last_status_event_id"
        " FROM findings_current_status WHERE finding_id = ?",
        (fid,),
    ).fetchone()
    assert row["current_status"] == "resolved"
    assert row["last_status_event_id"] == sid


def test_fold_spine_skips_gracefully_when_table_missing():
    from core.projections.findings_projection import FindingsProjection

    empty_conn = sqlite3.connect(":memory:")
    result = FindingsProjection().fold_spine(empty_conn)
    empty_conn.close()

    assert result == 0


# ── end-to-end: record + fold + status ────────────────────────────────────────


def test_end_to_end_record_fold_status(spine_db):
    from core.findings.mutations import record_finding, set_finding_status
    from core.projections.findings_projection import FindingsProjection

    fid = record_finding(
        project_id="proj-e2e",
        severity="high",
        title="Path traversal",
        file_path="upload.py",
        db_path=spine_db,
    )

    conn = sqlite3.connect(str(spine_db))
    conn.row_factory = sqlite3.Row

    FindingsProjection().fold_spine(conn)
    conn.commit()

    row = conn.execute(
        "SELECT current_status FROM findings_current_status WHERE finding_id = ?", (fid,)
    ).fetchone()
    assert row["current_status"] == "open"
    conn.close()

    set_finding_status(fid, "mitigated", reason="WAF rule added", db_path=spine_db)

    conn = sqlite3.connect(str(spine_db))
    conn.row_factory = sqlite3.Row
    FindingsProjection().fold_spine(conn)
    conn.commit()

    row = conn.execute(
        "SELECT current_status FROM findings_current_status WHERE finding_id = ?", (fid,)
    ).fetchone()
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
