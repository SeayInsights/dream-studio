#!/usr/bin/env python3
"""Phase 18.1.1: Backfill raw_claude_code_events from existing canonical_events.

Best-effort reconstruction. canonical_events doesn't preserve the full native
event shape (session_id, project_id are not stored as top-level columns there),
so backfilled raw rows may be incomplete. The _backfill=True flag in source_payload
marks reconstructed rows. Future events written by the dual-write ingestor will
have complete native shape.

Safe to re-run: uses INSERT OR IGNORE.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# DB path resolution
# ---------------------------------------------------------------------------

DB_PATH_ENV = "DREAM_STUDIO_DB_PATH"
_DEFAULT_DB_PATH = Path.home() / ".dream-studio" / "state" / "studio.db"


def _resolve_db_path(cli_override: str | None) -> Path:
    if cli_override:
        return Path(cli_override)
    env = os.environ.get(DB_PATH_ENV)
    if env:
        return Path(env)
    return _DEFAULT_DB_PATH


# ---------------------------------------------------------------------------
# Correlation ID extraction (mirrors ingestor._extract_correlation_ids)
# ---------------------------------------------------------------------------


def _safe_parse_json(raw: Any) -> dict:
    """Parse a JSON string or dict safely; return {} on failure or None."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _extract_correlation_ids(trace: dict, payload: dict) -> dict[str, Any]:
    """Extract correlation IDs from already-parsed trace and payload dicts.

    Mirrors spool/ingestor._extract_correlation_ids but accepts pre-parsed
    dicts since canonical_events rows store trace/payload as JSON strings and
    the caller already parsed them for source_payload reconstruction.
    """

    def _first(*candidates):
        for v in candidates:
            if v is not None:
                return v
        return None

    session_id = _first(trace.get("session_id"), payload.get("session_id"))
    project_id = _first(trace.get("project_id"), payload.get("project_id"))
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


# ---------------------------------------------------------------------------
# Table creation (mirrors ingestor._write_to_raw_sqlite DDL exactly)
# ---------------------------------------------------------------------------

_CREATE_RAW_TABLE = """
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
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_raw_cce_event_type ON raw_claude_code_events(event_type)",
    "CREATE INDEX IF NOT EXISTS idx_raw_cce_received_at ON raw_claude_code_events(received_at)",
    "CREATE INDEX IF NOT EXISTS idx_raw_cce_correlation_id ON raw_claude_code_events(correlation_id)",
    "CREATE INDEX IF NOT EXISTS idx_raw_cce_session_id ON raw_claude_code_events(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_raw_cce_project_id ON raw_claude_code_events(project_id)",
]

_INSERT_RAW = """
INSERT OR IGNORE INTO raw_claude_code_events
(event_id, received_at, event_type, event_timestamp, schema_version,
 source_payload, session_id, project_id, workflow_id, skill_id,
 agent_id, hook_id, tool_id, model_id, adapter_id, correlation_id)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


# ---------------------------------------------------------------------------
# Row reconstruction
# ---------------------------------------------------------------------------


def _reconstruct_row(row: sqlite3.Row) -> tuple[tuple, dict[str, Any]]:
    """Reconstruct a raw_claude_code_events insert tuple from a canonical_events row.

    Returns (insert_params, ids) where ids contains the extracted correlation IDs
    for logging purposes.

    Raises ValueError if the row is irrecoverably malformed.
    """
    event_id = row["event_id"]
    event_type = row["event_type"]
    timestamp = row["timestamp"]

    if not event_id:
        raise ValueError("missing event_id")
    if not event_type:
        raise ValueError("missing event_type")
    if not timestamp:
        raise ValueError("missing timestamp")

    schema_version = row["schema_version"]
    if schema_version is None:
        schema_version = 1

    # received_at: best approximation — canonical write time ≈ original ingest time
    received_at = row["created_at"] or timestamp

    # Parse trace and payload for ID extraction and source_payload construction
    trace = _safe_parse_json(row["trace"])
    payload = _safe_parse_json(row["payload"])

    source_payload = json.dumps(
        {
            "event_id": event_id,
            "event_type": event_type,
            "timestamp": timestamp,
            "schema_version": schema_version,
            "severity": row["severity"],
            "trace": trace,
            "payload": payload,
            "invocation_mode": row["invocation_mode"],
            # Note: session_id and project_id not stored in canonical_events directly;
            # may be available in trace or payload
            "_backfill": True,  # mark as reconstructed, not original
        }
    )

    ids = _extract_correlation_ids(trace, payload)

    params = (
        event_id,
        received_at,
        event_type,
        timestamp,
        schema_version,
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
    )
    return params, ids


# ---------------------------------------------------------------------------
# Main backfill logic
# ---------------------------------------------------------------------------

BATCH_SIZE = 200
PROGRESS_INTERVAL = 100


def _count_canonical(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM canonical_events").fetchone()
    return row[0] if row else 0


def _ensure_raw_table(conn: sqlite3.Connection) -> None:
    conn.execute(_CREATE_RAW_TABLE)
    for stmt in _CREATE_INDEXES:
        conn.execute(stmt)
    conn.commit()


def run_backfill(db_path: Path) -> int:
    """Run the backfill. Returns 0 on success, 1 on catastrophic error."""

    print(f"Connecting to {db_path}")

    if not db_path.exists():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        return 1

    try:
        conn = sqlite3.connect(str(db_path), timeout=30.0)
    except sqlite3.Error as e:
        print(f"ERROR: cannot connect to database: {e}", file=sys.stderr)
        return 1

    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")

        # Verify canonical_events exists
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "canonical_events" not in tables:
            print("ERROR: canonical_events table not found in database.", file=sys.stderr)
            return 1

        # Ensure raw table exists
        _ensure_raw_table(conn)

        total = _count_canonical(conn)
        print(f"Found {total} rows in canonical_events to process.")

        backfilled = 0
        skipped = 0
        failures: list[tuple[str, str]] = []
        processed = 0

        offset = 0
        while True:
            batch = conn.execute(
                """
                SELECT event_id, event_type, timestamp, trace, severity,
                       payload, invocation_mode, schema_version, created_at
                FROM canonical_events
                ORDER BY rowid
                LIMIT ? OFFSET ?
                """,
                (BATCH_SIZE, offset),
            ).fetchall()

            if not batch:
                break

            for row in batch:
                event_id = row["event_id"] or f"<unknown-offset-{offset + processed}>"
                try:
                    params, _ = _reconstruct_row(row)
                except Exception as e:
                    failures.append((event_id, str(e)))
                    processed += 1
                    if processed % PROGRESS_INTERVAL == 0:
                        print(f"Processed {processed}/{total}...")
                    continue

                try:
                    cursor = conn.execute(_INSERT_RAW, params)
                    conn.commit()
                    if cursor.rowcount > 0:
                        backfilled += 1
                    else:
                        skipped += 1
                except sqlite3.Error as e:
                    failures.append((event_id, f"db_error: {e}"))

                processed += 1
                if processed % PROGRESS_INTERVAL == 0:
                    print(f"Processed {processed}/{total}...")

            offset += BATCH_SIZE

        # Final progress line if last batch didn't land on interval
        if processed % PROGRESS_INTERVAL != 0:
            print(f"Processed {processed}/{total}...")

        print(
            f"Backfill complete: {backfilled} rows inserted, "
            f"{skipped} already existed, "
            f"{len(failures)} reconstruction failures"
        )

        if failures:
            print("\nFailure details:")
            for fid, reason in failures:
                print(f"  event_id={fid!r}  reason={reason}")

        return 0

    except Exception as e:
        print(f"ERROR: catastrophic failure: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 18.1.1: Backfill raw_claude_code_events from canonical_events. "
            "Safe to re-run (INSERT OR IGNORE)."
        )
    )
    parser.add_argument(
        "--db-path",
        metavar="PATH",
        help=(
            "Path to studio.db. Overrides DREAM_STUDIO_DB_PATH env var and the "
            "default ~/.dream-studio/state/studio.db."
        ),
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    db_path = _resolve_db_path(args.db_path)
    return run_backfill(db_path)


if __name__ == "__main__":
    sys.exit(main())
