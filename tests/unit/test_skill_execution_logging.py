"""Unit tests for skill execution logging via canonical event spool (TC-007).

activity_log was dropped in migration 063. log_skill_execution() now emits
canonical events via _write_envelopes. These tests verify the emitted envelope.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.event_store import studio_db  # noqa: E402
from core.event_store import connection  # noqa: E402


def _get_envelope(mock_write):
    """Extract the first CanonicalEventEnvelope from a write_envelopes mock call."""
    assert mock_write.called, "_write_envelopes was never called"
    envelopes = mock_write.call_args[0][0]
    assert len(envelopes) == 1
    return envelopes[0]


def test_log_skill_execution_basic(tmp_path):
    """Test basic skill execution logging emits correct canonical event."""
    db_path = tmp_path / "test.db"
    with patch("core.event_store.connection._write_envelopes") as mock_write:
        result = studio_db.log_skill_execution(
            skill_name="ds-core",
            skill_args="build",
            status="success",
            model="claude",
            session_id="test-session-123",
            project_id="test-project",
            db_path=db_path,
        )

    assert result is True
    env = _get_envelope(mock_write)
    assert env.event_type == "skill.executed"
    assert env.session_id == "test-session-123"
    assert env.payload["skill_name"] == "ds-core"
    assert env.payload["status"] == "completed"  # "success" → "completed"


def test_log_skill_execution_default_model_is_provider_neutral(tmp_path):
    """Default skill metadata should not make any provider canonical."""
    db_path = tmp_path / "test.db"
    with patch("core.event_store.connection._write_envelopes") as mock_write:
        result = studio_db.log_skill_execution(
            skill_name="ds-core",
            skill_args="build",
            status="success",
            session_id="test-session-123",
            project_id="test-project",
            db_path=db_path,
        )

    assert result is True
    env = _get_envelope(mock_write)
    assert env.payload["model"] == "unspecified"


def test_log_skill_execution_with_duration(tmp_path):
    """Test skill execution logging with duration and token counts."""
    db_path = tmp_path / "test.db"
    with patch("core.event_store.connection._write_envelopes") as mock_write:
        result = studio_db.log_skill_execution(
            skill_name="ds-quality",
            skill_args="debug",
            status="success",
            model="claude",
            session_id="test-session-456",
            project_id="test-project",
            duration_ms=1500,
            input_tokens=1000,
            output_tokens=500,
            db_path=db_path,
        )

    assert result is True
    env = _get_envelope(mock_write)
    assert env.payload["duration_ms"] == 1500
    assert env.payload["skill_name"] == "ds-quality"
    assert env.payload["input_tokens"] == 1000
    assert env.payload["output_tokens"] == 500


def test_log_skill_execution_failed_status(tmp_path):
    """Test skill execution logging with failed status."""
    db_path = tmp_path / "test.db"
    with patch("core.event_store.connection._write_envelopes") as mock_write:
        result = studio_db.log_skill_execution(
            skill_name="ds-security",
            skill_args="scan",
            status="failed",
            model="claude",
            session_id="test-session-789",
            project_id="test-project",
            error_message="Network timeout during scan",
            db_path=db_path,
        )

    assert result is True
    env = _get_envelope(mock_write)
    assert env.payload["status"] == "failed"
    assert env.payload["error_message"] == "Network timeout during scan"


def test_log_skill_execution_with_trace_linkage(tmp_path):
    """Test skill execution logging with PRD/task linkage."""
    db_path = tmp_path / "test.db"
    with patch("core.event_store.connection._write_envelopes") as mock_write:
        result = studio_db.log_skill_execution(
            skill_name="ds-domains",
            skill_args="saas-build",
            status="success",
            model="claude",
            session_id="test-session-xyz",
            project_id="test-project",
            prd_id="PRD-2024-001",
            task_id="TC-007",
            db_path=db_path,
        )

    assert result is True
    assert mock_write.called
    env = _get_envelope(mock_write)
    assert env.event_type == "skill.executed"
    assert env.session_id == "test-session-xyz"


def test_normalizer_integration():
    """Test that EventNormalizer is available and registered."""
    from core.event_store import studio_db

    assert connection._NORMALIZER_AVAILABLE is True
    assert connection._event_normalizer.is_registered("claude") is True
