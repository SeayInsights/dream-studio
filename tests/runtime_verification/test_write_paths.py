#!/usr/bin/env python3
"""
Runtime Verification of SQLite Write Paths

Tests each critical write path end-to-end with full tracing.
"""

import sqlite3
import sys
from pathlib import Path
from typing import Callable, Optional
import json
import os

import pytest

RUNTIME_WRITE_VERIFY_ENABLED = os.environ.get("DREAM_STUDIO_RUNTIME_WRITE_VERIFY") == "1"

if not RUNTIME_WRITE_VERIFY_ENABLED and "pytest" in sys.modules:
    pytest.skip(
        "runtime write-path verification touches the real Dream Studio DB; "
        "set DREAM_STUDIO_RUNTIME_WRITE_VERIFY=1 to run explicitly",
        allow_module_level=True,
    )

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.observability.trace_logger import trace
from core.config import paths
from core.config.database import get_connection


def get_main_db_path() -> Path:
    """Get path to main studio database."""
    return paths.state_dir() / "studio.db"


def verify_write_path(
    name: str,
    write_func: Callable,
    verify_query: str,
    table_name: str,
    cleanup_func: Optional[Callable] = None,
) -> bool:
    """
    Test a single write path end-to-end.

    Args:
        name: Test name
        write_func: Function that performs the write
        verify_query: SQL query to count rows (should return single integer)
        table_name: Table being written to
        cleanup_func: Optional cleanup function

    Returns:
        True if test passed, False otherwise
    """
    print(f"\n{'='*70}")
    print(f"TEST: {name}")
    print("=" * 70)

    # Clear trace log
    trace.clear()

    # Get database connection
    db_path = get_main_db_path()
    if not db_path.exists():
        print(f"[ERROR] Database does not exist: {db_path}")
        return False

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get row count BEFORE
        cursor.execute(verify_query)
        before_count = cursor.fetchone()[0]
        print(f"Rows BEFORE: {before_count}")

        # Execute the write
        print(f"\nExecuting write function...")
        try:
            result = write_func()
            print(f"Write function returned: {result}")
        except Exception as e:
            print(f"[ERROR] Write function failed: {e}")
            import traceback

            traceback.print_exc()
            return False

        # Get row count AFTER
        cursor.execute(verify_query)
        after_count = cursor.fetchone()[0]

        print(f"\nRows AFTER: {after_count}")
        print(f"Change: {after_count - before_count}")

        # Analyze trace log
        traces = trace.get_traces()
        print(f"\nTrace entries: {len(traces)}")

        if len(traces) == 0:
            print("[WARNING] No trace entries found - function may not be instrumented")

        stages_seen = set()
        errors = []

        for trace_entry in traces:
            stage = trace_entry["stage"]
            stages_seen.add(stage)
            print(f"  [{stage}] {json.dumps(trace_entry.get('data', {}), default=str)[:100]}")

            if stage == "ERROR":
                errors.append(trace_entry["data"])

        # Verification checks
        required_stages = {"TRIGGER", "PREPARE", "EXECUTE", "COMMIT", "VERIFY"}
        missing_stages = required_stages - stages_seen

        row_increased = after_count > before_count
        no_errors = len(errors) == 0
        all_stages_present = len(missing_stages) == 0

        success = row_increased and no_errors and all_stages_present

        # Print results
        print(f"\n{'='*70}")
        print(f"RESULTS")
        print("=" * 70)
        print(f"Row count increased: {'PASS' if row_increased else 'FAIL'}")
        print(f"No errors: {'PASS' if no_errors else 'FAIL'}")
        print(f"All stages present: {'PASS' if all_stages_present else 'FAIL'}")

        if missing_stages:
            print(f"\nMissing stages: {missing_stages}")
            print("[BREAKPOINT] Write path incomplete - check instrumentation")

        if errors:
            print(f"\nErrors encountered:")
            for error in errors:
                print(f"  - {error.get('error_type')}: {error.get('error')}")

        if not row_increased and not errors:
            print(f"\n[CRITICAL] Row count did not increase but no errors logged")
            print(f"This indicates a SILENT FAILURE")

        # Cleanup
        if cleanup_func and success:
            try:
                cleanup_func()
                print(f"\nCleanup completed")
            except Exception as e:
                print(f"[WARNING] Cleanup failed: {e}")

        print(f"\n{'[PASS]' if success else '[FAIL]'} {name}")
        print("=" * 70)

        conn.close()
        return success

    except Exception as e:
        print(f"[ERROR] Test framework error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_event_emission():
    """Test emit_event() write path."""
    from core.events.emitter import emit_event

    success = emit_event(
        event_type="test.runtime_verification",
        payload={"test": True, "timestamp": "runtime_test"},
        severity="info",
    )

    if not success:
        print("[ERROR] emit_event returned False")

    return success


def cleanup_test_event():
    """Clean up test event (WO-M: canonical_events retired, clean dual-canonical authority tables)."""
    conn = get_connection()
    for table in ("business_canonical_events", "ai_canonical_events"):
        try:
            conn.execute(f"DELETE FROM {table} WHERE event_type = 'test.runtime_verification'")
        except Exception:
            pass
    conn.commit()
    conn.close()


def test_activity_log():
    """Test activity_log write path."""
    from core.event_store.studio_db import _insert_activity_log

    try:
        _insert_activity_log(
            activity_type="test_verification",
            details={"test": "runtime_verification"},
            severity="info",
        )
        return True
    except Exception as e:
        print(f"[ERROR] _insert_activity_log failed: {e}")
        return False


def cleanup_test_activity():
    """Clean up test activity."""
    db_path = get_main_db_path()
    conn = get_connection()
    conn.execute("DELETE FROM activity_log WHERE activity_type = 'test_verification'")
    conn.commit()
    conn.close()


def run_all_tests():
    """Run all write path verification tests."""
    print("\n" + "=" * 70)
    print("SQLITE WRITE PATH RUNTIME VERIFICATION")
    print("=" * 70)
    print(f"Database: {get_main_db_path()}")
    print(f"Trace log: {trace.trace_file}")

    results = []

    # Test 1: Event Emission (WO-M: verify writes land in ai_canonical_events, not legacy table)
    results.append(
        verify_write_path(
            name="Event Emission (emit_event)",
            write_func=test_event_emission,
            verify_query='SELECT COUNT(*) FROM ai_canonical_events WHERE event_type = "test.runtime_verification"',
            table_name="ai_canonical_events",
            cleanup_func=cleanup_test_event,
        )
    )

    # Test 2: Activity Log
    results.append(
        verify_write_path(
            name="Activity Log (_insert_activity_log)",
            write_func=test_activity_log,
            verify_query='SELECT COUNT(*) FROM activity_log WHERE activity_type = "test_verification"',
            table_name="activity_log",
            cleanup_func=cleanup_test_activity,
        )
    )

    # Summary
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print("=" * 70)
    print(f"Tests run: {len(results)}")
    print(f"Passed: {sum(results)}")
    print(f"Failed: {len(results) - sum(results)}")
    print(f"Success rate: {sum(results) / len(results) * 100:.1f}%")

    if all(results):
        print("\n[OK] All write paths verified successfully")
        return 0
    else:
        print("\n[FAIL] Some write paths failed verification")
        print("Review trace logs for breakpoints")
        return 1


if __name__ == "__main__":
    if not RUNTIME_WRITE_VERIFY_ENABLED:
        print("Set DREAM_STUDIO_RUNTIME_WRITE_VERIFY=1 to run real runtime write verification.")
        sys.exit(2)

    exit_code = run_all_tests()

    print(f"\nTrace log saved to: {trace.trace_file}")
    print("Run analysis: python scripts/analyze_traces.py")

    sys.exit(exit_code)
