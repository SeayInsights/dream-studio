"""event_writer hooks group: sentinels + hook execution + skill execution logging.

WO-GF-PROJECTION-ENGINE: split from ``core/event_store/event_writer.py``.
NOTE: log_skill_execution has NO @_with_retry decorator — preserved verbatim
(asymmetry from the pre-split source).
LANDMINE #2 (4 of 4): tests/unit/emitters/test_emitter_tool_normalization.py reads
this file's source text to assert `model: str = "unspecified"` (log_skill_execution's
default) is present.
"""

from __future__ import annotations
import hashlib
import json
from pathlib import Path

from .connection import (
    _CanonicalEventType,
    _NOW,
    _db_transaction,
    _reraise_if_busy,
    _try_emit_canonical,
    _with_retry,
    paths,
)


@_with_retry
def set_sentinel(
    sentinel_key: str,
    sentinel_type: str,
    *,
    expires_at: str | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                """INSERT OR REPLACE INTO raw_sentinels
                   (sentinel_key, sentinel_type, created_at, expires_at)
                   VALUES (?, ?, ?, ?)""",
                (sentinel_key, sentinel_type, _NOW(), expires_at),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


@_with_retry
def clear_expired_sentinels(db_path: Path | None = None) -> int:
    try:
        with _db_transaction(db_path) as c:
            n = c.execute(
                "DELETE FROM raw_sentinels WHERE expires_at IS NOT NULL AND expires_at < ?",
                (_NOW(),),
            ).rowcount
        return n
    except Exception as e:
        _reraise_if_busy(e)
        return 0


@_with_retry
def insert_hook_execution(
    hook_name: str,
    hook_type: str,
    trigger_context: dict,
    started_at: str,
    completed_at: str | None = None,
    duration_ms: int | None = None,
    exit_code: int = 0,
    status: str = "success",
    output: str | None = None,
    error_message: str | None = None,
    cpu_time_ms: int | None = None,
    memory_mb: float | None = None,
    prd_id: str | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
    db_path: Path | None = None,
) -> int | None:
    """
    Emit the HOOK_EXECUTION_LOGGED canonical event for a hook execution.

    The SQLite hook_executions projection table was dropped in migration 129
    (WO-READMODELS-DUCKDB). Hook executions are now served by the DuckDB
    hook_executions VIEW in aggregate_metrics.db, derived from this canonical
    event via the events_fact pipeline. This function only emits the canonical
    event; it no longer writes a SQLite projection row.

    Returns None (activity_id is a retired FK column).
    Uses fire-and-forget pattern with DB lock fallback to text file.
    """
    try:
        with _db_transaction(db_path):
            # Emit canonical event (TA0c: activity_log retired). The DuckDB
            # hook_executions view is derived from this event via events_fact.
            _try_emit_canonical(
                _CanonicalEventType.HOOK_EXECUTION_LOGGED,
                {
                    "hook_name": hook_name,
                    "hook_type": hook_type,
                    "trigger_context": trigger_context,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "duration_ms": duration_ms,
                    "exit_code": exit_code,
                    "status": status,
                    "output": output,
                    "error_message": error_message,
                    "cpu_time_ms": cpu_time_ms,
                    "memory_mb": memory_mb,
                },
                session_id=session_id,
                task_id=task_id,
                prd_id=prd_id,
            )
            return None
    except Exception as e:
        # 3. If DB locked: write to fallback file
        _reraise_if_busy(e)
        try:
            fallback = paths.state_dir() / "hook_executions_fallback.jsonl"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            with open(fallback, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "hook_name": hook_name,
                            "hook_type": hook_type,
                            "trigger_context": trigger_context,
                            "started_at": started_at,
                            "completed_at": completed_at,
                            "duration_ms": duration_ms,
                            "exit_code": exit_code,
                            "status": status,
                            "output": output,
                            "error_message": error_message,
                            "cpu_time_ms": cpu_time_ms,
                            "memory_mb": memory_mb,
                            "prd_id": prd_id,
                            "task_id": task_id,
                            "session_id": session_id,
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass  # Fire-and-forget - don't fail the hook
        return -1  # Return sentinel value for fallback


def log_skill_execution(
    skill_name: str,
    skill_args: str = "",
    *,
    status: str = "success",
    model: str = "unspecified",
    session_id: str | None = None,
    project_id: str | None = None,
    prd_id: str | None = None,
    task_id: str | None = None,
    duration_ms: int | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    error_message: str | None = None,
    db_path: Path | None = None,
) -> bool:
    """
    Log skill execution to activity_log via EventNormalizer (TC-007).

    This function integrates the EventNormalizer with skill invocations, ensuring
    all skill outputs are normalized before being written to activity_log.

    Args:
        skill_name: Skill identifier (e.g., "ds-core", "ds-quality")
        skill_args: Skill arguments/mode (e.g., "build", "debug")
        status: Execution status ("success", "failed", "error")
        model: Optional tool/model metadata label
        session_id: Tool/session ID
        project_id: Project identifier
        prd_id: Optional PRD ID for cross-domain linkage
        task_id: Optional task ID for cross-domain linkage
        duration_ms: Execution duration in milliseconds
        input_tokens: Input token count
        output_tokens: Output token count
        error_message: Optional error message if status != "success"
        db_path: Optional database path

    Returns:
        True on success, False on failure
    """
    try:
        # Generate unique skill execution ID
        skill_exec_id = hashlib.sha256(
            f"{skill_name}:{skill_args}:{session_id}:{_NOW()}".encode()
        ).hexdigest()[:16]

        # Map user-friendly status to DB-compatible status
        # DB schema only allows: 'pending', 'in_progress', 'completed', 'failed', 'cancelled'
        status_map = {
            "success": "completed",
            "error": "failed",
            "pending": "pending",
            "in_progress": "in_progress",
            "completed": "completed",
            "failed": "failed",
            "cancelled": "cancelled",
        }
        db_status = status_map.get(status, "completed")  # Default to "completed" for unknown

        # Emit canonical event (TA0c: activity_log retired)
        _try_emit_canonical(
            _CanonicalEventType.SKILL_EXECUTED,
            {
                "skill_exec_id": skill_exec_id,
                "skill_name": skill_name,
                "skill_args": skill_args,
                "model": model,
                "status": db_status,
                "duration_ms": duration_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "error_message": error_message,
                "session_id": session_id,
                "project_id": project_id,
            },
            session_id=session_id,
            task_id=task_id,
            prd_id=prd_id,
            skill_id=skill_name,
        )

        return True
    except Exception as e:
        _reraise_if_busy(e)
        # Fallback: write to JSONL file if DB write fails
        try:
            fallback = paths.state_dir() / "skill_executions_fallback.jsonl"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            with open(fallback, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "skill_name": skill_name,
                            "skill_args": skill_args,
                            "status": status,
                            "model": model,
                            "session_id": session_id,
                            "project_id": project_id,
                            "error_message": error_message,
                            "logged_at": _NOW(),
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass  # Fire-and-forget - don't fail the hook
        return False
