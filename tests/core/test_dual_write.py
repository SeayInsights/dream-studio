"""
Test dual-write migration for event backbone.

Validates that legacy activity_log writes also emit canonical events.
"""

import sys
from pathlib import Path
import tempfile
import sqlite3

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.event_store import studio_db


def test_dual_write():
    """Test that _insert_activity_log writes to both legacy and canonical tables."""
    # Create temporary database with shared connection
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    conn = None
    try:
        # Create shared connection for both legacy and canonical writes.
        # Use a migrated temp DB so the test never touches the runtime DB.
        conn = studio_db._connect(db_path)
        conn.row_factory = sqlite3.Row

        # Initialize legacy schema (activity_log table)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_type TEXT,
                stream_id TEXT,
                stream_type TEXT,
                event_timestamp DATETIME,
                event_data TEXT,
                prd_id TEXT,
                task_id TEXT,
                session_id TEXT,
                workflow_run_key TEXT,
                skill_id TEXT,
                status TEXT,
                severity TEXT,
                duration_ms INTEGER
            )
        """)
        conn.commit()

        # Insert activity via legacy interface with shared connection
        activity_id = studio_db._insert_activity_log(
            activity_type="workflow_node",
            stream_id="test_workflow",
            stream_type="workflow",
            event_data={"node": "test_node"},
            status="completed",
            severity="info",
            db_path=db_path,
            conn=conn,  # Pass shared connection
        )

        assert activity_id is not None, "Legacy write failed"

        # Verify legacy table has data
        cursor = conn.execute("SELECT COUNT(*) FROM activity_log")
        legacy_count = cursor.fetchone()[0]

        assert legacy_count == 1, f"Expected 1 legacy record, got {legacy_count}"

        # Verify canonical table has data
        cursor = conn.execute("SELECT COUNT(*) FROM canonical_events")
        canonical_count = cursor.fetchone()[0]

        assert canonical_count == 1, f"Expected 1 canonical event, got {canonical_count}"

        # Verify canonical event structure
        cursor = conn.execute("SELECT event_type, payload FROM canonical_events")
        row = cursor.fetchone()

        assert row is not None, "Canonical event not found"
        event_type = row[0]

        # If validation failed, check what went wrong
        if event_type == "event.validation.failed":
            cursor = conn.execute(
                "SELECT errors, attempted_event FROM validation_failures ORDER BY attempted_at DESC LIMIT 1"
            )
            failure_row = cursor.fetchone()
            if failure_row:
                import json

                errors = json.loads(failure_row[0])
                attempted = json.loads(failure_row[1])
                print(f"\nVALIDATION FAILED:")
                print(f"  Errors: {errors}")
                print(f"  Attempted event_type: {attempted.get('event_type')}")
                print(f"  Attempted event: {json.dumps(attempted, indent=2)}")
                raise AssertionError(f"Event validation failed: {errors}")

        assert "workflow.execution" in event_type, f"Unexpected event_type: {event_type}"

        print("DUAL-WRITE VALIDATION PASSED")
        print(f"  - Legacy activity_log: {legacy_count} records")
        print(f"  - Canonical events: {canonical_count} records")
        print(f"  - Event type: {event_type}")

    finally:
        # Cleanup
        if conn is not None:
            conn.close()
        if db_path.exists():
            db_path.unlink()


if __name__ == "__main__":
    test_dual_write()
