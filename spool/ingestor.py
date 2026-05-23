from __future__ import annotations
import json
import os
import re
import signal
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SKILL_ID_RE = re.compile(r"^ds-[a-z][a-z0-9-]*$")

from spool.config import get_spool_root
from spool.states import SpoolState, ensure_dirs, state_dir

# NOTE: This ingestor is called inline from the emitter after a spool write.
# This coupling is explicitly temporary — proof-of-pipeline only for Slice 1.
# Slice 3 will introduce a proper trigger (ds spool ingest CLI + Stop hook
# registration). The spool write is the success condition; ingest is
# best-effort. SQLite busy/locked errors are non-fatal: the event remains
# in spool/ for retry on next run.

# Windows-only: intercept spurious console control events delivered during
# filesystem and SQLite operations. During development we observed phantom
# SIGINT delivery on Windows 11 + Python 3.12 during the ingest pipeline's
# rapid file moves and SQLite writes. Investigation eliminated Defender,
# OneDrive, peripheral software, all pytest plugins, WAL mode, symlink
# privileges, and filesystem ACLs. The signal source could not be fully
# isolated but is reproducible during ingest operations.
#
# We register a Windows console control handler via SetConsoleCtrlHandler.
# This intercepts CTRL_C_EVENT at the OS level before Python's signal
# machinery sees it. We absorb single phantom events while preserving real
# user Ctrl+C: two within 1 second pass through to default Windows handling
# (which raises KeyboardInterrupt as normal). On Linux this code is
# inactive. End users on Windows get this automatically without setup.
if sys.platform == "win32":
    import ctypes
    import time as _time

    _last_ctrl_time = [0.0]

    # CTRL_C_EVENT = 0, CTRL_BREAK_EVENT = 1
    _HANDLER_ROUTINE = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)

    def _ds_console_handler(ctrl_type):
        if ctrl_type == 0:  # CTRL_C_EVENT
            now = _time.time()
            if now - _last_ctrl_time[0] < 1.0:
                # Two events within 1 second: real user Ctrl+C, let it through.
                return 0  # FALSE: pass to next handler in chain
            _last_ctrl_time[0] = now
            return 1  # TRUE: handled, suppress
        return 0  # other event types: pass through

    # Store handler as module-level reference so ctypes callback isn't GC'd.
    _handler_ref = _HANDLER_ROUTINE(_ds_console_handler)
    ctypes.windll.kernel32.SetConsoleCtrlHandler(_handler_ref, True)


REQUIRED_FIELDS: frozenset[str] = frozenset(
    {"event_id", "event_type", "timestamp", "schema_version"}
)


@dataclass
class IngestResult:
    processed: int = 0
    failed: int = 0
    skipped: int = 0
    lock_error: bool = False


def ingest(root: Path | None = None, db_path: Path | None = None) -> IngestResult:
    r = root if root is not None else get_spool_root()
    ensure_dirs(r)
    spool_dir = state_dir(SpoolState.SPOOL, r)
    processing_dir = state_dir(SpoolState.PROCESSING, r)
    processed_dir = state_dir(SpoolState.PROCESSED, r)
    failed_dir = state_dir(SpoolState.FAILED, r)

    if db_path is None:
        # Delegate to the canonical resolver so DREAM_STUDIO_DB_PATH overrides
        # are honored uniformly. Tests rely on this to avoid touching the
        # operator's real ~/.dream-studio/state/studio.db.
        from core.config.database import _default_db_path

        db_path = _default_db_path()

    result = IngestResult()

    for event_file in sorted(spool_dir.glob("*.json")):
        try:
            _process_one(event_file, processing_dir, processed_dir, failed_dir, db_path, result)
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                result.lock_error = True
                result.skipped += 1
            else:
                _move_to_failed(event_file, failed_dir, f"sqlite_error: {e}")
                result.failed += 1
        except Exception as e:
            _move_to_failed(event_file, failed_dir, str(e))
            result.failed += 1

    return result


def _process_one(
    event_file: Path,
    processing_dir: Path,
    processed_dir: Path,
    failed_dir: Path,
    db_path: Path,
    result: IngestResult,
) -> None:
    processing_path = processing_dir / event_file.name
    os.replace(event_file, processing_path)

    try:
        data = json.loads(processing_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        _move_to_failed(processing_path, failed_dir, f"parse_error: {e}")
        result.failed += 1
        return

    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        _move_to_failed(processing_path, failed_dir, f"missing_fields: {sorted(missing)}")
        result.failed += 1
        return

    if data.get("event_type") == "skill.invoked":
        skill_id = data.get("skill_id", "")
        if not _SKILL_ID_RE.match(skill_id):
            _move_to_failed(processing_path, failed_dir, "malformed_skill_id")
            result.failed += 1
            return

    # Phase 18.1.1: write to raw FIRST (v2 data architecture — raw before canonical)
    # If raw write fails, the spool file returns to inbox for retry.
    try:
        _write_to_raw_sqlite(data, db_path)
    except Exception:
        # Restore file to inbox so it retries on next ingest run.
        try:
            os.replace(processing_path, event_file)
        except OSError:
            pass
        raise  # re-raise: outer handler in ingest() decides skip vs fail

    # Phase 18.1.2: route to dual canonical (business + AI) per event type registry.
    # Best-effort: dual canonical failure does not block legacy canonical write.
    try:
        _write_to_dual_canonical(data, db_path)
    except Exception as exc:
        print(
            f"[ds-ingestor] WARNING: dual canonical write failed for"
            f" {data.get('event_id')!r} ({data.get('event_type')!r}): {exc}",
            file=sys.stderr,
        )

    _write_to_sqlite(data, db_path)

    processed_path = processed_dir / event_file.name
    os.replace(processing_path, processed_path)
    result.processed += 1


def _extract_correlation_ids(envelope: dict[str, Any]) -> dict[str, Any]:
    """Extract correlation IDs from a CanonicalEventEnvelope dict.

    Pulls session_id, project_id, and context IDs from top-level fields,
    trace dict, and payload dict (in that priority order). Composes a
    correlation_id string from non-null components.
    """
    # Normalize trace
    trace = envelope.get("trace", {})
    if isinstance(trace, str):
        try:
            trace = json.loads(trace)
        except (json.JSONDecodeError, TypeError):
            trace = {}
    if not isinstance(trace, dict):
        trace = {}

    # Normalize payload
    payload = envelope.get("payload", {})
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            payload = {}
    if not isinstance(payload, dict):
        payload = {}

    def _first(*candidates):
        for v in candidates:
            if v is not None:
                return v
        return None

    session_id = _first(
        envelope.get("session_id"), trace.get("session_id"), payload.get("session_id")
    )
    project_id = _first(
        envelope.get("project_id"), trace.get("project_id"), payload.get("project_id")
    )
    workflow_id = _first(
        trace.get("workflow_id"), trace.get("stream_id"), payload.get("workflow_id")
    )
    skill_id = _first(trace.get("skill_id"), trace.get("skill_specifier"))
    agent_id = _first(trace.get("agent_id"), payload.get("agent_id"))
    hook_id = trace.get("hook_id")
    tool_id = trace.get("tool_id")
    model_id = trace.get("model_id")
    adapter_id = trace.get("adapter_id")

    # Compose correlation_id from non-null components in defined order
    parts = []
    if session_id is not None:
        parts.append(f"sess-{session_id}")
    if workflow_id is not None:
        parts.append(f"wf-{workflow_id}")
    if skill_id is not None:
        parts.append(f"skill-{skill_id}")
    if agent_id is not None:
        parts.append(f"agent-{agent_id}")
    if hook_id is not None:
        parts.append(f"hook-{hook_id}")
    if tool_id is not None:
        parts.append(f"tool-{tool_id}")

    correlation_id = ":".join(parts) if parts else None

    return {
        "session_id": session_id,
        "project_id": project_id,
        "workflow_id": workflow_id,
        "skill_id": skill_id,
        "agent_id": agent_id,
        "hook_id": hook_id,
        "tool_id": tool_id,
        "model_id": model_id,
        "adapter_id": adapter_id,
        "correlation_id": correlation_id,
    }


def _write_to_dual_canonical(envelope: dict[str, Any], db_path: Path) -> None:
    """Route event to business_canonical_events and/or ai_canonical_events.

    Reads the event type registry to determine routing. Writes to zero, one,
    or both canonical tables. Logs a warning for unregistered event_types.
    Idempotent: uses INSERT OR IGNORE on the event_id PK.
    """
    from config.event_type_registry import get_routes, is_registered

    import datetime

    event_type = envelope.get("event_type", "")
    routes = get_routes(event_type)

    if not is_registered(event_type):
        print(
            f"[ds-ingestor] WARNING: event_type {event_type!r} not in registry"
            f" — defaulting to dual canonical write (event_id={envelope.get('event_id')!r})",
            file=sys.stderr,
        )

    if not routes:
        return  # raw-only event (Commitment 9: mechanical detail stays in raw)

    ids = _extract_correlation_ids(envelope)
    received_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    trace = envelope.get("trace", {})
    if isinstance(trace, str):
        try:
            trace = json.loads(trace)
        except (json.JSONDecodeError, TypeError):
            trace = {}
    if not isinstance(trace, dict):
        trace = {}

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    try:
        conn.execute("PRAGMA journal_mode = WAL")

        if "business" in routes:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS business_canonical_events (
                    event_id TEXT PRIMARY KEY,
                    received_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
                    event_type TEXT NOT NULL,
                    event_timestamp TEXT NOT NULL,
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    trace JSON NOT NULL DEFAULT '{}',
                    payload JSON NOT NULL DEFAULT '{}',
                    correlation_id TEXT,
                    project_id TEXT,
                    milestone_id TEXT,
                    work_order_id TEXT,
                    task_id TEXT,
                    severity TEXT NOT NULL DEFAULT 'info',
                    source TEXT NOT NULL DEFAULT 'ingestor'
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_bce_correlation_id"
                " ON business_canonical_events(correlation_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_bce_event_type"
                " ON business_canonical_events(event_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_bce_project_id"
                " ON business_canonical_events(project_id)"
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO business_canonical_events
                (event_id, received_at, event_type, event_timestamp, schema_version,
                 trace, payload, correlation_id, project_id, milestone_id,
                 work_order_id, task_id, severity, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    envelope["event_id"],
                    received_at,
                    event_type,
                    envelope["timestamp"],
                    envelope.get("schema_version", 1),
                    json.dumps(trace),
                    json.dumps(envelope.get("payload", {})),
                    ids["correlation_id"],
                    ids.get("project_id") or trace.get("project_id"),
                    trace.get("milestone_id"),
                    trace.get("work_order_id"),
                    trace.get("task_id"),
                    envelope.get("severity", "info"),
                    "ingestor",
                ),
            )

        if "ai" in routes:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_canonical_events (
                    event_id TEXT PRIMARY KEY,
                    received_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
                    event_type TEXT NOT NULL,
                    event_timestamp TEXT NOT NULL,
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    trace JSON NOT NULL DEFAULT '{}',
                    payload JSON NOT NULL DEFAULT '{}',
                    correlation_id TEXT,
                    session_id TEXT,
                    skill_id TEXT,
                    workflow_id TEXT,
                    agent_id TEXT,
                    hook_id TEXT,
                    model_id TEXT,
                    severity TEXT NOT NULL DEFAULT 'info',
                    source TEXT NOT NULL DEFAULT 'ingestor'
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ace_correlation_id"
                " ON ai_canonical_events(correlation_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ace_event_type"
                " ON ai_canonical_events(event_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ace_session_id"
                " ON ai_canonical_events(session_id)"
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO ai_canonical_events
                (event_id, received_at, event_type, event_timestamp, schema_version,
                 trace, payload, correlation_id, session_id, skill_id,
                 workflow_id, agent_id, hook_id, model_id, severity, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    envelope["event_id"],
                    received_at,
                    event_type,
                    envelope["timestamp"],
                    envelope.get("schema_version", 1),
                    json.dumps(trace),
                    json.dumps(envelope.get("payload", {})),
                    ids["correlation_id"],
                    ids["session_id"],
                    ids["skill_id"],
                    ids["workflow_id"],
                    ids["agent_id"],
                    ids["hook_id"],
                    ids["model_id"],
                    envelope.get("severity", "info"),
                    "ingestor",
                ),
            )

        conn.commit()
    finally:
        conn.close()


def _write_to_raw_sqlite(envelope: dict[str, Any], db_path: Path) -> None:
    """Write a raw event to raw_claude_code_events before canonical ingest.

    Uses CREATE TABLE IF NOT EXISTS and INSERT OR IGNORE for idempotency.
    Indexes are created inline so the table is queryable even if the full
    migration set has not been applied yet.
    """
    import datetime

    ids = _extract_correlation_ids(envelope)
    received_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    source_payload = json.dumps(envelope)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS raw_claude_code_events (
                event_id TEXT PRIMARY KEY,
                received_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
                event_type TEXT NOT NULL,
                event_timestamp TEXT NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                source_payload TEXT NOT NULL DEFAULT '{}',
                session_id TEXT,
                project_id TEXT,
                workflow_id TEXT,
                skill_id TEXT,
                agent_id TEXT,
                hook_id TEXT,
                tool_id TEXT,
                model_id TEXT,
                adapter_id TEXT,
                correlation_id TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_raw_cce_event_type ON raw_claude_code_events(event_type)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_raw_cce_received_at ON raw_claude_code_events(received_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_raw_cce_correlation_id ON raw_claude_code_events(correlation_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_raw_cce_session_id ON raw_claude_code_events(session_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_raw_cce_project_id ON raw_claude_code_events(project_id)"
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO raw_claude_code_events
            (event_id, received_at, event_type, event_timestamp, schema_version,
             source_payload, session_id, project_id, workflow_id, skill_id,
             agent_id, hook_id, tool_id, model_id, adapter_id, correlation_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                envelope["event_id"],
                received_at,
                envelope["event_type"],
                envelope["timestamp"],
                envelope.get("schema_version", 1),
                source_payload,
                ids["session_id"],
                ids["project_id"],
                ids["workflow_id"],
                ids["skill_id"],
                ids["agent_id"],
                ids["hook_id"],
                ids["tool_id"],
                ids["model_id"],
                ids["adapter_id"],
                ids["correlation_id"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _write_to_sqlite(envelope: dict[str, Any], db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS canonical_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                trace JSON NOT NULL DEFAULT '{}',
                severity TEXT NOT NULL DEFAULT 'info',
                payload JSON NOT NULL DEFAULT '{}',
                actor JSON,
                confidence_score REAL,
                source_type TEXT,
                raw_prompt_retained INTEGER NOT NULL DEFAULT 0,
                raw_tool_output_retained INTEGER NOT NULL DEFAULT 0,
                schema_version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                invocation_mode TEXT
            )
        """)
        conn.execute(
            """
            INSERT OR IGNORE INTO canonical_events
            (event_id, event_type, timestamp, trace, severity, payload,
             raw_prompt_retained, raw_tool_output_retained, schema_version,
             invocation_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                envelope["event_id"],
                envelope["event_type"],
                envelope["timestamp"],
                json.dumps(envelope.get("trace", {})),
                envelope.get("severity", "info"),
                json.dumps(envelope.get("payload", {})),
                int(bool(envelope.get("raw_prompt_retained", False))),
                int(bool(envelope.get("raw_tool_output_retained", False))),
                envelope.get("schema_version", 1),
                envelope.get("invocation_mode"),
            ),
        )
        _trace = envelope.get("trace", {})
        if isinstance(_trace, str):
            try:
                _trace = json.loads(_trace)
            except (json.JSONDecodeError, TypeError):
                _trace = {}
        if not _trace.get("domain"):
            print(
                f"[ds-ingestor] WARNING: event {envelope['event_id']!r} type={envelope['event_type']!r} missing trace.domain",
                file=sys.stderr,
            )
        conn.commit()
        # Best-effort projection: execution events → execution_events table
        try:
            from projections.core.execution_events_projection import apply as _project_execution

            projected = _project_execution(envelope, conn)
            if projected:
                conn.commit()
        except Exception:
            pass
    finally:
        conn.close()


def ingest_pending(root: Path | None = None, db_path: Path | None = None) -> IngestResult:
    """Process all pending spool events and clean up stale session files.

    Safe to run anytime. Returns counts. Exit-safe — never raises.
    """
    result = ingest(root=root, db_path=db_path)
    _cleanup_stale_sessions(root)
    return result


def _cleanup_stale_sessions(root: Path | None = None) -> None:
    """Delete .sessions/<pid>.json files for dead processes. Best-effort."""
    try:
        r = root if root is not None else get_spool_root()
        sessions_dir = r / ".sessions"
        if not sessions_dir.exists():
            return
        try:
            session_files = list(sessions_dir.glob("*.json"))
        except OSError:
            return  # Windows can raise WinError 87 on glob; nothing to clean
        for session_file in session_files:
            try:
                pid = int(session_file.stem)
                if not _pid_alive(pid):
                    session_file.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception:
        pass


def _pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except (OSError, SystemError):
        # SystemError can occur on Windows when os.kill raises a C-level error
        return True  # can't tell; assume alive


def _move_to_failed(src: Path, failed_dir: Path, reason: str) -> None:
    reasons_dir = failed_dir / "reasons"
    try:
        reasons_dir.mkdir(parents=True, exist_ok=True)
        reason_file = reasons_dir / (src.stem + ".reason.json")
        reason_file.write_text(
            json.dumps({"reason": reason, "file": src.name}),
            encoding="utf-8",
        )
    except OSError:
        pass
    try:
        os.replace(src, failed_dir / src.name)
    except OSError:
        pass
