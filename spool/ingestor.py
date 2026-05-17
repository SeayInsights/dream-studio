from __future__ import annotations
import json
import os
import re
import signal
import sqlite3
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

REQUIRED_FIELDS: frozenset[str] = frozenset({"event_id", "event_type", "timestamp", "schema_version"})


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
        db_path = Path.home() / ".dream-studio" / "state" / "studio.db"

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

    _write_to_sqlite(data, db_path)

    processed_path = processed_dir / event_file.name
    os.replace(processing_path, processed_path)
    result.processed += 1


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
        conn.commit()
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
