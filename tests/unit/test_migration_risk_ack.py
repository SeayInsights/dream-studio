"""MIGRATION_RISK_ACKNOWLEDGED acknowledges only when it equals exactly `1` (#927).

The gate used to treat any non-empty value as a yes, so `MIGRATION_RISK_ACKNOWLEDGED=0`
bypassed the matrix-watch block and was recorded as a bypass.
"""

from __future__ import annotations

import pytest

from core.gates import migration_risk

RISK_FILE = "core/event_store/migrations/083_new.sql"


@pytest.fixture
def written(monkeypatch) -> list[dict]:
    """Every envelope the emitter writes to the spool, captured at the writer."""
    events: list[dict] = []
    monkeypatch.setattr("spool.writer.write_event", lambda ev: events.append(ev))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("MIGRATION_RISK_ACKNOWLEDGED", raising=False)
    return events


@pytest.fixture
def migration_gate(written, monkeypatch):
    monkeypatch.setattr(migration_risk, "_changed_files", lambda base_ref: [RISK_FILE])
    # Rollback pairing and DROP safety are not bypassable and have their own tests.
    monkeypatch.setattr(
        "core.gates.migration_rollback_pairing.find_unpaired_migrations", lambda: []
    )
    monkeypatch.setattr(migration_risk, "_changed_forward_migration_drops", lambda files: [])
    return written


def test_the_recorded_reason_is_plain_ascii(migration_gate, monkeypatch):
    """The stored reason carried a mojibake em dash; ASCII leaves nothing to mis-decode."""
    monkeypatch.setenv("MIGRATION_RISK_ACKNOWLEDGED", "1")
    assert migration_risk.main() == 0
    reason = migration_gate[0]["payload"]["reason"]
    assert reason.isascii(), reason
    assert "MIGRATION_RISK_ACKNOWLEDGED=1" in reason


def test_only_exactly_one_acknowledges(migration_gate, monkeypatch, capsys):
    monkeypatch.setenv("MIGRATION_RISK_ACKNOWLEDGED", "1")
    assert migration_risk.main() == 0
    assert len(migration_gate) == 1
    assert "bypassing" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["0", "", "true", "yes", " 1", "1 ", "01", "false", "no"])
def test_anything_else_is_not_an_acknowledgement(migration_gate, monkeypatch, capsys, value):
    monkeypatch.setenv("MIGRATION_RISK_ACKNOWLEDGED", value)
    assert migration_risk.main() == 1
    assert migration_gate == []  # and nothing is recorded as a bypass
    out = capsys.readouterr().out
    assert "bypassing" not in out
    if value:
        assert "is not an acknowledgement" in out
        assert "exactly 1" in out


def test_unset_is_not_an_acknowledgement(migration_gate, capsys):
    assert migration_risk.main() == 1
    assert migration_gate == []
    assert "is not an acknowledgement" not in capsys.readouterr().out
