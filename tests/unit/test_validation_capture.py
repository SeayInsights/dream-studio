"""WO-VALIDATION-CAPTURE: executable-check outcomes are captured as
validation.result_recorded canonical events.

The validations dashboard component reads events_fact validation.result_recorded
(WO-DASH-DUCKDB-PROJECTION repoint), which was empty because nothing emitted that
event. run_executable_checks — where the WO's SQL/TEST/API-CHECKs run — now emits
one per check, best-effort. This is a capture gap fix, distinct from
event.validation.failed (schema-rejected events).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.event_store.studio_db import _connect
from core.work_orders import verify


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "studio.db"
    _connect(db).close()
    return db


def test_validation_result_captured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each executable check emits a validation.result_recorded event carrying its
    type, outcome, and command — passing and failing checks both captured."""
    captured: list = []
    monkeypatch.setattr(
        "emitters.shared.spool_writer.write_envelopes", lambda envs: captured.extend(envs)
    )
    db = _db(tmp_path)
    tasks = [
        {"title": "pass-task", "acceptance_criteria": "SQL-CHECK: SELECT 1"},
        {"title": "fail-task", "acceptance_criteria": "SQL-CHECK: SELECT 1 WHERE 1=0"},
    ]

    results = verify.run_executable_checks(tasks, db)
    assert set(results) == {"pass-task", "fail-task"}  # the checks still ran

    events = [e for e in captured if e.event_type == "validation.result_recorded"]
    assert len(events) == 2
    by_status = {e.payload["status"]: e for e in events}
    assert set(by_status) == {"passed", "failed"}
    for e in events:
        assert e.payload["validation_type"] == "SQL-CHECK"
        assert e.payload["status"] == e.payload["outcome_status"]
        assert "command" in e.payload
    assert by_status["passed"].payload["command"] == "SELECT 1"


def test_capture_is_best_effort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A spool-write failure must never break the check run (best-effort telemetry)."""

    def _boom(_envs: object) -> None:
        raise RuntimeError("spool down")

    monkeypatch.setattr("emitters.shared.spool_writer.write_envelopes", _boom)
    db = _db(tmp_path)
    tasks = [{"title": "t", "acceptance_criteria": "SQL-CHECK: SELECT 1"}]

    # Must not raise, and the check result is still returned to the caller.
    results = verify.run_executable_checks(tasks, db)
    assert results["t"][0]["passed"] is True


def test_no_event_without_checks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A task with no *-CHECK line emits nothing (no spurious validation events)."""
    captured: list = []
    monkeypatch.setattr(
        "emitters.shared.spool_writer.write_envelopes", lambda envs: captured.extend(envs)
    )
    db = _db(tmp_path)
    verify.run_executable_checks(
        [{"title": "t", "acceptance_criteria": "just prose, no checks"}], db
    )
    assert captured == []
