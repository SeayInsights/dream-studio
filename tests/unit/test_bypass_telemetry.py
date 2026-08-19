"""WO-BYPASS-TELEMETRY: every enforcement bypass and fail-open leaves a mark.

The 2026-08-18 audit found the escape hatches were invisible: DS_ENFORCE=0
exited before any telemetry ran, all hook fail-open paths allowed silently,
and MIGRATION_RISK_ACKNOWLEDGED recorded nothing. Fail-open stays (a broken
DB must never brick editing) — invisibility is the defect these tests pin.
"""

from __future__ import annotations

import io
import json
import runpy
import sqlite3
import sys
import uuid
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EDIT_HOOK = REPO_ROOT / "runtime" / "hooks" / "meta" / "on-edit-enforce.py"
STOP_HOOK = REPO_ROOT / "runtime" / "hooks" / "meta" / "on-stop-enforce.py"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config.sqlite_bootstrap import bootstrap_database  # noqa: E402
from core.health.doctor_bypass import bypass_audit  # noqa: E402
from runtime.lib import enforcement  # noqa: E402

NOW = datetime.now(UTC).isoformat()


@pytest.fixture
def captured(monkeypatch):
    """Capture — never really emit — the bypass/observation telemetry."""
    calls: list[dict] = []
    monkeypatch.setattr(
        "core.event_store.event_writer.insert_hook_execution",
        lambda **kw: calls.append(kw),
    )
    return calls


@pytest.fixture
def hermetic(tmp_path, monkeypatch):
    """Point the enforcement lib at temp stores so no real DB is touched."""
    monkeypatch.setattr(enforcement, "AUTHORITY_DB", tmp_path / "missing-studio.db")
    monkeypatch.setattr(enforcement, "FILES_DB", tmp_path / "missing-files.db")
    monkeypatch.setattr(enforcement, "SESSION_DIR", tmp_path / "enforce")
    monkeypatch.setattr(enforcement, "TEMP_ROOT", tmp_path / "nonexistent-temp")
    monkeypatch.setattr(enforcement, "DS_HOME", tmp_path / "nonexistent-ds-home")
    monkeypatch.delenv("DS_ENFORCE", raising=False)
    monkeypatch.delenv("DS_ENFORCE_TIER", raising=False)
    return tmp_path


def _run_hook(hook: Path, payload: dict) -> str:
    stdin, out = sys.stdin, io.StringIO()
    sys.stdin = io.StringIO(json.dumps(payload))
    try:
        with redirect_stdout(out):
            runpy.run_path(str(hook), run_name="__main__")
    finally:
        sys.stdin = stdin
    return out.getvalue().strip()


def _bypass_calls(calls: list[dict]) -> list[dict]:
    return [c for c in calls if (c.get("trigger_context") or {}).get("decision") == "bypass"]


# ── DS_ENFORCE=0 leaves a mark ──────────────────────────────────────────────────


def test_ds_enforce_off_emits_event(hermetic, captured, monkeypatch, tmp_path):
    """The escape hatch still works (no deny output) but is recorded."""
    monkeypatch.setenv("DS_ENFORCE", "0")
    out = _run_hook(
        EDIT_HOOK,
        {
            "session_id": "s1",
            "tool_name": "Edit",
            "tool_input": {"file_path": str(tmp_path / "x.py")},
        },
    )
    assert out == ""  # allowed — the hatch is intact
    bypasses = _bypass_calls(captured)
    assert bypasses, "DS_ENFORCE=0 short-circuit must be recorded"
    assert bypasses[0]["trigger_context"]["rule"] == "enforcement_disabled"

    captured.clear()
    out = _run_hook(STOP_HOOK, {"session_id": "s1", "stop_hook_active": False})
    assert out == ""
    stop_bypasses = _bypass_calls(captured)
    assert stop_bypasses and stop_bypasses[0]["trigger_context"]["rule"] == "enforcement_disabled"


def test_fail_open_authority_db_recorded(hermetic, captured, tmp_path):
    """A missing authority DB still fails open — visibly, not silently."""
    out = _run_hook(
        EDIT_HOOK,
        {
            "session_id": "s2",
            "tool_name": "Edit",
            "tool_input": {"file_path": str(tmp_path / "some" / "src.py")},
        },
    )
    assert out == ""  # fail-open preserved
    bypasses = _bypass_calls(captured)
    assert any(
        c["trigger_context"]["rule"] == "fail_open_authority_db" for c in bypasses
    ), f"missing-DB fail-open must be recorded, got: {[c['trigger_context'] for c in bypasses]}"


# ── Gate acknowledgment leaves a mark ───────────────────────────────────────────


def test_migration_ack_recorded(monkeypatch):
    """MIGRATION_RISK_ACKNOWLEDGED=1 bypasses the block AND records it."""
    from core.gates import migration_risk

    oldest = sorted((REPO_ROOT / "core" / "event_store" / "migrations").glob("*.sql"))[0]
    rel = oldest.relative_to(REPO_ROOT).as_posix()

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("MIGRATION_RISK_ACKNOWLEDGED", "1")
    monkeypatch.setattr(migration_risk, "_changed_files", lambda base_ref: [rel])
    # The rollback-pairing and DROP-safety checks are deliberately NOT bypassable
    # and carry their own tests — neutralize them so this test pins only the
    # ack-recording behavior of the matrix-watch branch.
    monkeypatch.setattr(
        "core.gates.migration_rollback_pairing.find_unpaired_migrations", lambda: []
    )
    monkeypatch.setattr(migration_risk, "_changed_forward_migration_drops", lambda files: [])

    recorded: list[tuple] = []
    monkeypatch.setattr(
        "core.gates.bypass_event.record_gate_bypass",
        lambda gate, reason, extra=None: recorded.append((gate, reason, extra)),
    )
    rc = migration_risk.main()
    assert rc == 0  # the hatch is intact
    assert recorded and recorded[0][0] == "migration_risk"
    assert rel in (recorded[0][2] or {}).get("risk_files", [])


# ── The emitters themselves execute (gap WO 08298665) ──────────────────────────


def test_record_gate_bypass_writes_spool_event(monkeypatch):
    """Run record_gate_bypass's REAL body: envelope construction + spool write
    (previously only ever monkeypatched, so the path never executed under test)."""
    written: list[dict] = []
    monkeypatch.setattr("spool.writer.write_event", lambda ev: written.append(ev))

    from core.gates.bypass_event import record_gate_bypass

    record_gate_bypass(
        "migration_risk",
        "MIGRATION_RISK_ACKNOWLEDGED=1",
        extra={"risk_files": ["core/event_store/migrations/x.sql"]},
    )
    assert len(written) == 1
    ev = written[0]
    assert ev["event_type"] == "gate.bypassed"
    assert ev["payload"]["gate"] == "migration_risk"
    assert ev["payload"]["risk_files"] == ["core/event_store/migrations/x.sql"]
    assert ev["severity"] == "warning"
    assert ev["trace"]["domain"] == "sdlc"


def test_trailer_consumption_records_bypass(monkeypatch, capsys):
    """The docs-drift gate records which domains a Docs-Reviewed-No-Change
    trailer actually cleared — and stays silent when none were cleared."""
    from interfaces.cli import contract_docs_drift_gate as gate

    def _fake_report(cleared: bool) -> dict:
        status = "docs_reviewed_no_change_needed" if cleared else "docs_current"
        return {
            "status": "pass",
            "domains": [{"domain_id": "release_publication_gate", "status": status}],
        }

    recorded: list[tuple] = []
    monkeypatch.setattr(
        "core.gates.bypass_event.record_gate_bypass",
        lambda g, reason, extra=None: recorded.append((g, extra)),
    )
    monkeypatch.setattr(gate, "validate_contract_registry", lambda reg: [])
    monkeypatch.setattr(gate, "contract_registry", lambda: {})
    monkeypatch.setattr(
        gate, "_gather_reviewed_no_change", lambda **kw: {"release_publication_gate"}
    )
    monkeypatch.setattr(gate, "_changed_files", lambda args: ["core/gates/x.py"])
    monkeypatch.setattr(sys, "argv", ["contract_docs_drift_gate.py"])

    # Trailer cleared a domain: recorded with the domain ids.
    monkeypatch.setattr(gate, "change_impact_report", lambda *a, **kw: _fake_report(True))
    with pytest.raises(SystemExit) as exc:
        gate.main()
    assert exc.value.code == 0
    capsys.readouterr()
    assert recorded == [
        ("docs_drift_reviewed_no_change", {"domains": ["release_publication_gate"]})
    ]

    # No domain cleared: nothing recorded.
    recorded.clear()
    monkeypatch.setattr(gate, "change_impact_report", lambda *a, **kw: _fake_report(False))
    with pytest.raises(SystemExit) as exc:
        gate.main()
    assert exc.value.code == 0
    capsys.readouterr()
    assert recorded == []


# ── The surfaces read the marks ─────────────────────────────────────────────────


def _seed_bypass_events(db: Path) -> None:
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO ai_canonical_events"
        " (event_id, received_at, event_type, event_timestamp, schema_version,"
        "  trace, payload, severity, source)"
        " VALUES (?, ?, 'system.hook.execution.logged', ?, '1', '{}', ?, 'info', 'test')",
        (
            str(uuid.uuid4()),
            NOW,
            NOW,
            json.dumps(
                {
                    "hook_name": "on_edit_enforce",
                    "trigger_context": {
                        "decision": "bypass",
                        "rule": "enforcement_disabled",
                        "detail": "DS_ENFORCE=0",
                    },
                }
            ),
        ),
    )
    conn.execute(
        "INSERT INTO business_canonical_events"
        " (event_id, received_at, event_type, event_timestamp, schema_version,"
        "  trace, payload, severity, source)"
        " VALUES (?, ?, 'gate.bypassed', ?, '1', '{}', ?, 'warning', 'test')",
        (
            str(uuid.uuid4()),
            NOW,
            NOW,
            json.dumps({"gate": "migration_risk", "reason": "MIGRATION_RISK_ACKNOWLEDGED=1"}),
        ),
    )
    conn.commit()
    conn.close()


def test_bypass_audit_aggregates_both_families(tmp_path):
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    _seed_bypass_events(db)

    report = bypass_audit(db)
    assert report["total"] == 2
    assert report["by_rule"]["enforcement_disabled"]["count"] == 1
    assert report["gate_bypasses"]["migration_risk"]["count"] == 1


def test_project_state_surfaces_bypasses(tmp_path):
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    _seed_bypass_events(db)

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        from core.projects.queries import get_project_state

        state = get_project_state(source_root=tmp_path, dream_studio_home=tmp_path)
    assert state["ok"] is True
    assert state["bypass_summary"]["last_7d_total"] == 2
    assert state["bypass_summary"]["rules"] == {"enforcement_disabled": 1}
    assert state["bypass_summary"]["gates"] == {"migration_risk": 1}
