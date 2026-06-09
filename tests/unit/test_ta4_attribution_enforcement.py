"""TA4: attribution_status enforcement on SDLC-domain events."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest import mock

import pytest

from canonical.events.envelope import (
    CanonicalEventEnvelope,
    _validate_sdlc_event,
)
from core.config.sqlite_bootstrap import bootstrap_database

# ── shared fixture IDs ────────────────────────────────────────────────────────

PROJECT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
WO_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
NOW = "2026-05-22T00:00:00+00:00"


# ── unit: _validate_sdlc_event ────────────────────────────────────────────────


class TestValidateSdlcEvent:
    def test_non_sdlc_event_passes(self):
        for domain in ("telemetry", "system", None):
            trace = {"domain": domain} if domain else {}
            d = {"trace": trace}
            assert _validate_sdlc_event(d) is None

    def test_sdlc_missing_attribution_status_fails(self):
        d = {"trace": {"domain": "sdlc", "project_id": PROJECT_ID}}
        err = _validate_sdlc_event(d)
        assert err is not None
        assert "attribution_status" in err

    def test_sdlc_invalid_attribution_status_fails(self):
        d = {"trace": {"domain": "sdlc", "attribution_status": "unknown_value"}}
        err = _validate_sdlc_event(d)
        assert err is not None
        assert "unknown_value" in err

    @pytest.mark.parametrize(
        "status",
        ["fully_attributed", "partial", "orphan", "backfill"],
    )
    def test_sdlc_valid_attribution_statuses_pass(self, status: str):
        d = {"trace": {"domain": "sdlc", "attribution_status": status}}
        assert _validate_sdlc_event(d) is None

    def test_empty_trace_non_sdlc_passes(self):
        assert _validate_sdlc_event({"trace": {}}) is None

    def test_missing_trace_key_passes(self):
        assert _validate_sdlc_event({}) is None


# ── unit: envelope serialization continues on validation failure ──────────────


class TestEnvelopeSerializationContinues:
    def test_invalid_sdlc_still_returns_dict(self):
        """Validation failure must not prevent to_dict() from returning the event."""
        env = CanonicalEventEnvelope(
            event_type="work_order.started",
            session_id=None,
            payload={"title": "test"},
            trace={"domain": "sdlc"},  # missing attribution_status
        )
        with mock.patch("core.telemetry.diagnostics.log_diagnostic") as mock_log:
            result = env.to_dict()

        assert result["event_type"] == "work_order.started"
        assert result["trace"] == {"domain": "sdlc"}
        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs.kwargs["category"] == "failure"
        assert call_kwargs.kwargs["source"] == "canonical.events.envelope.validate"

    def test_valid_sdlc_produces_no_diagnostic(self):
        env = CanonicalEventEnvelope(
            event_type="work_order.started",
            session_id=None,
            payload={"title": "test"},
            trace={"domain": "sdlc", "attribution_status": "fully_attributed"},
        )
        with mock.patch("core.telemetry.diagnostics.log_diagnostic") as mock_log:
            result = env.to_dict()

        assert result["event_type"] == "work_order.started"
        mock_log.assert_not_called()

    def test_non_sdlc_produces_no_diagnostic(self):
        env = CanonicalEventEnvelope(
            event_type="token.consumed",
            session_id=None,
            payload={"input_tokens": 100},
            trace={"domain": "telemetry"},
        )
        with mock.patch("core.telemetry.diagnostics.log_diagnostic") as mock_log:
            env.to_dict()

        mock_log.assert_not_called()

    def test_diagnostic_failure_does_not_propagate(self):
        """If diagnostics itself throws, to_dict() must still succeed."""
        env = CanonicalEventEnvelope(
            event_type="work_order.started",
            session_id=None,
            payload={},
            trace={"domain": "sdlc"},  # missing attribution_status
        )
        with mock.patch(
            "core.telemetry.diagnostics.log_diagnostic", side_effect=RuntimeError("boom")
        ):
            result = env.to_dict()

        assert result["event_type"] == "work_order.started"


# ── integration: SDLC event without attribution_status lands + diagnostic written ─


@pytest.fixture
def diag_dir(tmp_path):
    return tmp_path / "diagnostics"


@pytest.fixture
def spool_root(tmp_path):
    root = tmp_path / "spool"
    root.mkdir()
    return root


class TestIntegrationAttributionEnforcement:
    def test_sdlc_event_without_attribution_lands_and_diagnostic_written(
        self, diag_dir, spool_root, monkeypatch
    ):
        monkeypatch.setenv("DS_DIAGNOSTICS_DIR", str(diag_dir))

        env = CanonicalEventEnvelope(
            event_type="work_order.started",
            session_id=None,
            payload={"title": "test"},
            trace={"domain": "sdlc"},  # missing attribution_status
        )
        d = env.to_dict()

        # Event dict is still produced (visibility over correctness)
        assert d["event_type"] == "work_order.started"

        # Diagnostic entry was written
        assert diag_dir.exists(), "diagnostic dir should have been created"
        jsonl_files = list(diag_dir.glob("*.jsonl"))
        assert jsonl_files, "at least one diagnostic JSONL file expected"

        entries = [
            json.loads(line)
            for f in jsonl_files
            for line in f.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        failure_entries = [e for e in entries if e.get("category") == "failure"]
        assert failure_entries, "expected at least one failure diagnostic entry"
        assert any(
            "attribution_status" in e.get("details", {}).get("error_message", "")
            for e in failure_entries
        )

    def test_sdlc_event_with_valid_attribution_no_diagnostic(
        self, diag_dir, spool_root, monkeypatch
    ):
        monkeypatch.setenv("DS_DIAGNOSTICS_DIR", str(diag_dir))

        env = CanonicalEventEnvelope(
            event_type="work_order.started",
            session_id=None,
            payload={"title": "test"},
            trace={"domain": "sdlc", "attribution_status": "fully_attributed"},
        )
        env.to_dict()

        if diag_dir.exists():
            entries = [
                json.loads(line)
                for f in diag_dir.glob("*.jsonl")
                for line in f.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            failure_entries = [e for e in entries if e.get("category") == "failure"]
            assert not failure_entries, "no failure diagnostics expected for valid SDLC event"


# ── integration: block_work_order emits attribution_status ───────────────────


@pytest.fixture
def db_home(tmp_path):
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True)
    bootstrap_database(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?, 'Test Project', 'desc', 'active', ?, ?)",
            (PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, NULL, 'WO1', '', 'in_progress', 'documentation', ?, ?)",
            (WO_ID, PROJECT_ID, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return tmp_path


class TestBlockWorkOrderAttribution:
    def test_block_work_order_event_has_attribution_status(self, db_home, tmp_path):
        """block_work_order must emit work_order.blocked with attribution_status."""
        source_root = tmp_path / "source"
        source_root.mkdir()

        emitted: list[dict] = []

        def fake_write_event(d):
            emitted.append(d)

        with (
            mock.patch(
                "core.work_orders.mutations._require_db",
                return_value=db_home / "state" / "studio.db",
            ),
            mock.patch("spool.writer.write_event", side_effect=fake_write_event),
        ):
            from core.work_orders.mutations import block_work_order

            result = block_work_order(
                work_order_id=WO_ID,
                reason="testing",
                source_root=source_root,
            )

        assert result["ok"] is True
        assert emitted, "expected a spool event to be emitted"
        evt = emitted[0]
        assert evt["event_type"] == "work_order.blocked"
        assert evt["trace"]["domain"] == "sdlc"
        assert (
            "attribution_status" in evt["trace"]
        ), "work_order.blocked must have attribution_status in trace"
        assert evt["trace"]["attribution_status"] == "fully_attributed"
