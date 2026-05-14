"""Unit tests for skill execution logging with EventNormalizer (TC-007)."""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

# Add repo root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.event_store import studio_db


@pytest.fixture
def test_db(tmp_path):
    """Create a migrated temporary test database."""
    db_path = tmp_path / "test_studio.db"

    conn = studio_db._connect(db_path)
    for prd_id in ("test-prd", "PRD-2024-001"):
        conn.execute(
            """INSERT OR REPLACE INTO prd_documents
               (prd_id, title, file_path, status, created_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            (prd_id, prd_id, f"prd/{prd_id}.md", "in-progress"),
        )
    conn.execute(
        """INSERT OR REPLACE INTO prd_plans
           (plan_id, prd_id, phase_name, file_path, created_at)
           VALUES (?, ?, ?, ?, datetime('now'))""",
        ("plan-test-prd", "test-prd", "Phase 6D", "prd/test-prd/plan.md"),
    )
    conn.execute(
        """INSERT OR REPLACE INTO prd_plans
           (plan_id, prd_id, phase_name, file_path, created_at)
           VALUES (?, ?, ?, ?, datetime('now'))""",
        ("plan-prd-2024-001", "PRD-2024-001", "Phase 6D", "prd/PRD-2024-001/plan.md"),
    )
    conn.execute(
        """INSERT OR REPLACE INTO prd_tasks
           (task_id, plan_id, prd_id, task_name, status, created_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))""",
        ("TC-007", "plan-prd-2024-001", "PRD-2024-001", "Skill execution logging", "in_progress"),
    )
    for session_id in (
        "test-session-123",
        "test-session-456",
        "test-session-789",
        "test-session-xyz",
    ):
        conn.execute(
            """INSERT OR REPLACE INTO prd_sessions
               (session_id, prd_id, plan_id, started_at)
               VALUES (?, ?, ?, datetime('now'))""",
            (session_id, "test-prd", "plan-test-prd"),
        )
    for skill_id, pack, mode in [
        ("ds-core", "core", "build"),
        ("ds-quality", "quality", "debug"),
        ("ds-security", "security", "scan"),
        ("ds-domains", "domains", "saas-build"),
    ]:
        conn.execute(
            """INSERT OR REPLACE INTO reg_skills
               (skill_id, pack, mode, description, triggers, skill_path, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            (skill_id, pack, mode, "test skill", "", f"skills/{skill_id}.md"),
        )
    conn.commit()
    conn.close()

    return db_path


def test_log_skill_execution_basic(test_db):
    """Test basic skill execution logging."""
    result = studio_db.log_skill_execution(
        skill_name="ds-core",
        skill_args="build",
        status="success",
        model="claude",
        session_id="test-session-123",
        project_id="test-project",
        db_path=test_db,
    )

    assert result is True

    conn = sqlite3.connect(str(test_db))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM activity_log WHERE activity_type='skill_execution'"
    ).fetchone()

    assert row is not None
    assert row["stream_type"] == "skill"
    assert row["session_id"] == "test-session-123"
    assert row["skill_id"] == "ds-core"
    assert row["status"] == "completed"  # "success" mapped to "completed" (DB schema constraint)

    conn.close()


def test_log_skill_execution_default_model_is_provider_neutral(test_db):
    """Default skill metadata should not make any provider canonical."""
    result = studio_db.log_skill_execution(
        skill_name="ds-core",
        skill_args="build",
        status="success",
        session_id="test-session-123",
        project_id="test-project",
        db_path=test_db,
    )

    assert result is True

    conn = sqlite3.connect(str(test_db))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT event_data FROM activity_log WHERE activity_type='skill_execution'"
    ).fetchone()

    assert row is not None
    event_data = json.loads(row["event_data"])
    assert event_data["model"] == "unspecified"

    conn.close()


def test_log_skill_execution_with_duration(test_db):
    """Test skill execution logging with duration and token counts."""
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
        db_path=test_db,
    )

    assert result is True

    conn = sqlite3.connect(str(test_db))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM activity_log WHERE session_id='test-session-456'").fetchone()

    assert row is not None
    assert row["duration_ms"] == 1500
    assert row["skill_id"] == "ds-quality"

    conn.close()


def test_log_skill_execution_failed_status(test_db):
    """Test skill execution logging with failed status."""
    result = studio_db.log_skill_execution(
        skill_name="ds-security",
        skill_args="scan",
        status="failed",
        model="claude",
        session_id="test-session-789",
        project_id="test-project",
        error_message="Network timeout during scan",
        db_path=test_db,
    )

    assert result is True

    conn = sqlite3.connect(str(test_db))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM activity_log WHERE session_id='test-session-789'").fetchone()

    assert row is not None
    assert row["status"] == "failed"
    assert row["severity"] == "error"

    conn.close()


def test_log_skill_execution_with_trace_linkage(test_db):
    """Test skill execution logging with PRD/task linkage."""
    result = studio_db.log_skill_execution(
        skill_name="ds-domains",
        skill_args="saas-build",
        status="success",
        model="claude",
        session_id="test-session-xyz",
        project_id="test-project",
        prd_id="PRD-2024-001",
        task_id="TC-007",
        db_path=test_db,
    )

    assert result is True

    conn = sqlite3.connect(str(test_db))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM activity_log WHERE session_id='test-session-xyz'").fetchone()

    assert row is not None
    assert row["prd_id"] == "PRD-2024-001"
    assert row["task_id"] == "TC-007"

    conn.close()


def test_normalizer_integration():
    """Test that EventNormalizer is available and registered."""
    from core.event_store import studio_db

    assert studio_db._NORMALIZER_AVAILABLE is True
    assert studio_db._event_normalizer.is_registered("claude") is True
