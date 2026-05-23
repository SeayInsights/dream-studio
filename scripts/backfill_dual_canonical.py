#!/usr/bin/env python3
"""Phase 18.1.2: Backfill business_canonical_events and ai_canonical_events
from existing canonical_events rows.

Reads every row in canonical_events, looks up its event_type in the event type
registry, and inserts copies into the appropriate dual canonical table(s).
Uses INSERT OR IGNORE throughout — safe to re-run.

Routing:
  routes_to = ("business",)       → business_canonical_events only
  routes_to = ("ai",)             → ai_canonical_events only
  routes_to = ("business", "ai")  → both tables (paired events)
  routes_to = ()                  → skipped (raw-only per Commitment 9)
  unregistered event_type         → both tables as safe default; logged as warning

Run:
  py scripts/backfill_dual_canonical.py [--db-path PATH] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

DB_PATH_ENV = "DREAM_STUDIO_DB_PATH"
_DEFAULT_DB_PATH = Path.home() / ".dream-studio" / "state" / "studio.db"


def _resolve_db_path(cli_override: str | None) -> Path:
    if cli_override:
        return Path(cli_override)
    env = os.environ.get(DB_PATH_ENV)
    if env:
        return Path(env)
    return _DEFAULT_DB_PATH


def _safe_json(raw: Any) -> dict:
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


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
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
        );
        CREATE INDEX IF NOT EXISTS idx_bce_correlation_id
            ON business_canonical_events(correlation_id);
        CREATE INDEX IF NOT EXISTS idx_bce_event_type
            ON business_canonical_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_bce_project_id
            ON business_canonical_events(project_id);

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
        );
        CREATE INDEX IF NOT EXISTS idx_ace_correlation_id
            ON ai_canonical_events(correlation_id);
        CREATE INDEX IF NOT EXISTS idx_ace_event_type
            ON ai_canonical_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_ace_session_id
            ON ai_canonical_events(session_id);
    """)
    conn.commit()


def _compose_correlation_id(trace: dict) -> str | None:
    parts = []
    session_id = trace.get("session_id")
    workflow_id = trace.get("workflow_id") or trace.get("stream_id")
    skill_id = trace.get("skill_id") or trace.get("skill_specifier")
    agent_id = trace.get("agent_id")
    hook_id = trace.get("hook_id")
    tool_id = trace.get("tool_id")
    if session_id:
        parts.append(f"sess-{session_id}")
    if workflow_id:
        parts.append(f"wf-{workflow_id}")
    if skill_id:
        parts.append(f"skill-{skill_id}")
    if agent_id:
        parts.append(f"agent-{agent_id}")
    if hook_id:
        parts.append(f"hook-{hook_id}")
    if tool_id:
        parts.append(f"tool-{tool_id}")
    return ":".join(parts) if parts else None


_INSERT_BUSINESS = """
INSERT OR IGNORE INTO business_canonical_events
(event_id, received_at, event_type, event_timestamp, schema_version,
 trace, payload, correlation_id, project_id, milestone_id,
 work_order_id, task_id, severity, source)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERT_AI = """
INSERT OR IGNORE INTO ai_canonical_events
(event_id, received_at, event_type, event_timestamp, schema_version,
 trace, payload, correlation_id, session_id, skill_id,
 workflow_id, agent_id, hook_id, model_id, severity, source)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

BATCH_SIZE = 200
PROGRESS_INTERVAL = 100


def run_backfill(db_path: Path, dry_run: bool = False) -> int:
    print(f"Connecting to {db_path}")
    if not db_path.exists():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        return 1

    # Import registry from repo root (add to sys.path if needed)
    repo_root = Path(__file__).parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from config.event_type_registry import get_routes, is_registered

    try:
        conn = sqlite3.connect(str(db_path), timeout=30.0)
    except sqlite3.Error as exc:
        print(f"ERROR: cannot connect: {exc}", file=sys.stderr)
        return 1

    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")

        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "canonical_events" not in tables:
            print("ERROR: canonical_events not found.", file=sys.stderr)
            return 1

        if not dry_run:
            _ensure_tables(conn)

        total = conn.execute("SELECT COUNT(*) FROM canonical_events").fetchone()[0]
        print(f"Found {total} rows in canonical_events.")
        if dry_run:
            print("DRY RUN — no writes will be performed.")

        # Counters
        to_business = 0
        to_ai = 0
        to_both = 0
        to_neither = 0
        unregistered: dict[str, int] = {}
        failures: list[tuple[str, str]] = []
        processed = 0
        offset = 0

        while True:
            batch = conn.execute(
                """
                SELECT event_id, event_type, timestamp, trace, payload,
                       schema_version, severity, created_at
                FROM canonical_events
                ORDER BY rowid
                LIMIT ? OFFSET ?
                """,
                (BATCH_SIZE, offset),
            ).fetchall()
            if not batch:
                break

            for row in batch:
                event_id = row["event_id"] or f"<unknown-{offset + processed}>"
                event_type = row["event_type"] or ""

                if not is_registered(event_type):
                    unregistered[event_type] = unregistered.get(event_type, 0) + 1

                routes = get_routes(event_type)
                trace = _safe_json(row["trace"])
                payload = _safe_json(row["payload"])
                correlation_id = _compose_correlation_id(trace)
                received_at = row["created_at"] or row["timestamp"]
                schema_version = row["schema_version"] or 1
                severity = row["severity"] or "info"
                trace_json = json.dumps(trace)
                payload_json = json.dumps(payload)

                has_business = "business" in routes
                has_ai = "ai" in routes

                if has_business and has_ai:
                    to_both += 1
                elif has_business:
                    to_business += 1
                elif has_ai:
                    to_ai += 1
                else:
                    to_neither += 1

                if not dry_run and routes:
                    try:
                        if has_business:
                            conn.execute(
                                _INSERT_BUSINESS,
                                (
                                    event_id,
                                    received_at,
                                    event_type,
                                    row["timestamp"],
                                    schema_version,
                                    trace_json,
                                    payload_json,
                                    correlation_id,
                                    trace.get("project_id"),
                                    trace.get("milestone_id"),
                                    trace.get("work_order_id"),
                                    trace.get("task_id"),
                                    severity,
                                    "backfill",
                                ),
                            )
                        if has_ai:
                            conn.execute(
                                _INSERT_AI,
                                (
                                    event_id,
                                    received_at,
                                    event_type,
                                    row["timestamp"],
                                    schema_version,
                                    trace_json,
                                    payload_json,
                                    correlation_id,
                                    trace.get("session_id"),
                                    trace.get("skill_id") or trace.get("skill_specifier"),
                                    trace.get("workflow_id") or trace.get("stream_id"),
                                    trace.get("agent_id"),
                                    trace.get("hook_id"),
                                    trace.get("model_id"),
                                    severity,
                                    "backfill",
                                ),
                            )
                        conn.commit()
                    except sqlite3.Error as exc:
                        failures.append((event_id, f"db_error: {exc}"))

                processed += 1
                if processed % PROGRESS_INTERVAL == 0:
                    print(f"  Processed {processed}/{total}...")

            offset += BATCH_SIZE

        if processed % PROGRESS_INTERVAL != 0:
            print(f"  Processed {processed}/{total}...")

        print()
        print("=== Backfill complete ===")
        print(f"  Total canonical_events processed : {processed}")
        print(f"  Routed to business only          : {to_business}")
        print(f"  Routed to AI only                : {to_ai}")
        print(f"  Routed to both (paired)          : {to_both}")
        print(f"  Skipped (raw-only, Commitment 9) : {to_neither}")
        print(f"  Write failures                   : {len(failures)}")

        if unregistered:
            print()
            print(
                f"  WARNING: {len(unregistered)} unregistered event_type(s)"
                " — defaulted to both canonicals:"
            )
            for et, cnt in sorted(unregistered.items(), key=lambda x: -x[1]):
                print(f"    {cnt:>5}  {et}")

        if failures:
            print()
            print("Write failures:")
            for fid, reason in failures:
                print(f"  event_id={fid!r}  reason={reason}")

        return 0

    except Exception as exc:
        print(f"ERROR: catastrophic failure: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Phase 18.1.2: Backfill business_canonical_events and ai_canonical_events "
            "from canonical_events. Safe to re-run (INSERT OR IGNORE)."
        )
    )
    p.add_argument(
        "--db-path",
        metavar="PATH",
        help="Path to studio.db (overrides DREAM_STUDIO_DB_PATH env var)",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="Count routing decisions without writing to the DB"
    )
    return p


def main() -> int:
    args = _build_parser().parse_args()
    return run_backfill(_resolve_db_path(args.db_path), dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
