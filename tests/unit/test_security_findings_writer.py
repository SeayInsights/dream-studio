"""Phase 18.2.6 — Security findings writer: canonical spool emission tests.

Verifies that:
  1. emit_security_finding() emits security.finding.logged to spool after W25 INSERT.
  2. The spool payload carries required keys and a redacted file_path.
  3. Duplicate findings (same finding_id) do NOT emit to spool.
  4. A spool-write failure does not prevent the SQLite write (fail-open).
  5. emit_security_finding_resolved() emits security.finding.resolved.
  6. emit_security_finding_resolved() returns error for unknown finding_id.
  7. resolve_security_finding() W-writer updates status correctly.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-05-27T00:00:00+00:00"
PROJECT_ID = "proj-sec-findings-18-2-6"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    target = tmp_path / "studio.db"
    bootstrap_database(target)
    conn = sqlite3.connect(str(target))
    try:
        conn.execute(
            "INSERT INTO business_projects"
            " (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (PROJECT_ID, "Security Test Project", "", "active", NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return target


@pytest.fixture
def patched_db(db_path: Path):
    from interfaces.cli.ds import resolve_installed_runtime_paths

    fake = MagicMock()
    fake.sqlite_path = db_path
    fake.source_root = REPO_ROOT
    fake.dream_studio_home = db_path.parent
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake):
        yield fake


# ── emit_security_finding: spool emission ──────────────────────────────────


def test_emit_security_finding_emits_spool_event(patched_db, db_path: Path, tmp_path: Path) -> None:
    """Happy path: emitting a new finding writes to spool as security.finding.logged."""
    from core.telemetry.emitters import emit_security_finding

    captured: list[dict] = []

    def _fake_write_event(envelope_dict, *, root):
        captured.append(envelope_dict)

    with patch("spool.writer.write_event", side_effect=_fake_write_event):
        result = emit_security_finding(
            severity="high",
            description="SQL injection in login handler",
            rule_id="CWE-89",
            file_path="/home/user/builds/dream-studio-clean/src/auth.py",
            start_line=42,
            status="open",
            context={"project_id": PROJECT_ID},
            db_path=db_path,
        )

    assert result.emitted is True
    assert len(captured) == 1
    evt = captured[0]
    assert evt["event_type"] == "security.finding.logged"
    payload = evt["payload"]
    assert payload["finding_id"] == result.record_id
    assert payload["project_id"] == PROJECT_ID
    assert payload["severity"] == "high"
    assert payload["status"] == "open"


def test_emit_security_finding_spool_calls_redact_file_path(patched_db, db_path: Path) -> None:
    """file_path in the spool payload is passed through redact_file_path.

    redact_file_path() is currently a stub (returns the path unchanged) — a
    full implementation is a separate concern. This test asserts that the call
    is wired: when redact_file_path gains a real implementation, personal paths
    will automatically be stripped from spool payloads.
    """
    from core.telemetry.emitters import emit_security_finding

    test_path = "C:\\Users\\Dannis Seay\\builds\\dream-studio-clean\\src\\config.py"

    with (
        patch("spool.writer.write_event"),
        patch(
            "canonical.events.redactor.redact_file_path", return_value="<redacted>"
        ) as mock_redact,
    ):
        emit_security_finding(
            severity="medium",
            description="Hardcoded credentials",
            file_path=test_path,
            start_line=10,
            context={"project_id": PROJECT_ID},
            db_path=db_path,
        )

    # redact_file_path must be called with the raw file path
    mock_redact.assert_called_once_with(test_path)


def test_emit_security_finding_duplicate_does_not_emit_spool(patched_db, db_path: Path) -> None:
    """Duplicate finding (same deterministic ID) skips the spool write."""
    from core.telemetry.emitters import emit_security_finding

    captured: list[dict] = []

    def _fake_write_event(envelope_dict, *, root):
        captured.append(envelope_dict)

    kwargs = dict(
        severity="low",
        description="Insecure cookie flag",
        rule_id="CWE-614",
        file_path="src/session.py",
        start_line=7,
        context={"project_id": PROJECT_ID},
        db_path=db_path,
    )

    with patch("spool.writer.write_event", side_effect=_fake_write_event):
        first = emit_security_finding(**kwargs)
        second = emit_security_finding(**kwargs)

    assert first.emitted is True
    assert second.emitted is False
    assert "duplicate" in (second.error or "")
    assert len(captured) == 1  # spool only fires on first write


def test_emit_security_finding_spool_failure_does_not_block_sqlite(
    patched_db, db_path: Path
) -> None:
    """If the spool write raises, the finding still lands in security_findings."""
    from core.telemetry.emitters import emit_security_finding

    with patch("spool.writer.write_event", side_effect=RuntimeError("spool unavailable")):
        result = emit_security_finding(
            severity="critical",
            description="Remote code execution",
            rule_id="CWE-78",
            context={"project_id": PROJECT_ID},
            db_path=db_path,
        )

    assert result.emitted is True  # SQLite write succeeded despite spool failure
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT finding_id FROM security_findings WHERE finding_id = ?",
            (result.record_id,),
        ).fetchone()
    assert row is not None


# ── resolve_security_finding: W-writer ────────────────────────────────────


def test_resolve_security_finding_updates_status(patched_db, db_path: Path) -> None:
    """resolve_security_finding() returns True and updates status in security_findings."""
    from core.telemetry.emitters import emit_security_finding
    from core.telemetry.execution_spine import resolve_security_finding

    with patch("spool.writer.write_event"):
        result = emit_security_finding(
            severity="high",
            description="Path traversal",
            rule_id="CWE-22",
            context={"project_id": PROJECT_ID},
            db_path=db_path,
        )

    finding_id = result.record_id
    with sqlite3.connect(str(db_path)) as conn:
        updated = resolve_security_finding(conn, finding_id=finding_id, resolution="mitigated")
        status = conn.execute(
            "SELECT status FROM security_findings WHERE finding_id = ?", (finding_id,)
        ).fetchone()[0]

    assert updated is True
    assert status == "mitigated"


def test_resolve_security_finding_returns_false_for_unknown_id(patched_db, db_path: Path) -> None:
    from core.telemetry.execution_spine import resolve_security_finding

    with sqlite3.connect(str(db_path)) as conn:
        updated = resolve_security_finding(conn, finding_id="does-not-exist")
    assert updated is False


# ── emit_security_finding_resolved: emitter ───────────────────────────────


def test_emit_security_finding_resolved_emits_spool_event(patched_db, db_path: Path) -> None:
    """emit_security_finding_resolved() emits security.finding.resolved to spool."""
    from core.telemetry.emitters import emit_security_finding, emit_security_finding_resolved

    with patch("spool.writer.write_event"):
        create_result = emit_security_finding(
            severity="medium",
            description="SSRF vulnerability",
            rule_id="CWE-918",
            context={"project_id": PROJECT_ID},
            db_path=db_path,
        )

    finding_id = create_result.record_id
    captured: list[dict] = []

    def _fake_write_event(envelope_dict, *, root):
        captured.append(envelope_dict)

    with patch("spool.writer.write_event", side_effect=_fake_write_event):
        resolve_result = emit_security_finding_resolved(
            finding_id=finding_id,
            project_id=PROJECT_ID,
            resolution="fixed",
            db_path=db_path,
        )

    assert resolve_result.emitted is True
    assert len(captured) == 1
    evt = captured[0]
    assert evt["event_type"] == "security.finding.resolved"
    assert evt["payload"]["finding_id"] == finding_id
    assert evt["payload"]["project_id"] == PROJECT_ID
    assert evt["payload"]["resolution"] == "fixed"


def test_emit_security_finding_resolved_returns_error_for_unknown(
    patched_db, db_path: Path
) -> None:
    from core.telemetry.emitters import emit_security_finding_resolved

    result = emit_security_finding_resolved(
        finding_id="no-such-finding",
        project_id=PROJECT_ID,
        db_path=db_path,
    )
    assert result.emitted is False
    assert "not found" in (result.error or "")
