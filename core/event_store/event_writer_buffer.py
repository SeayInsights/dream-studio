"""event_writer buffer group: telemetry buffer import, rolling-window prune, operational snapshots.

WO-GF-PROJECTION-ENGINE: split from ``core/event_store/event_writer.py``.
"""

from __future__ import annotations
import hashlib
import json
from datetime import datetime, timedelta, UTC
from pathlib import Path

from .connection import _NOW, _db_transaction, _reraise_if_busy, _with_retry


@_with_retry
def import_buffer(buffer_path: Path, db_path: Path | None = None) -> int:
    try:
        raw = buffer_path.read_bytes()
        if not raw.strip():
            return 0
        bid = hashlib.sha256(raw).hexdigest()
        with _db_transaction(db_path) as c:
            if c.execute("SELECT 1 FROM log_batch_imports WHERE batch_id=?", (bid,)).fetchone():
                return 0
            rows = [json.loads(ln) for ln in raw.decode().splitlines() if ln.strip()]
            for r in rows:
                c.execute(
                    "INSERT INTO raw_skill_telemetry(skill_name,invoked_at,model,input_tokens,output_tokens,success,execution_time_s) VALUES(?,?,?,?,?,?,?)",
                    (
                        r["skill_name"],
                        r.get("invoked_at", _NOW()),
                        r.get("model"),
                        r.get("input_tokens"),
                        r.get("output_tokens"),
                        int(r["success"]),
                        r.get("execution_time_s"),
                    ),
                )
            c.execute(
                "INSERT INTO log_batch_imports(batch_id,imported_at,row_count) VALUES(?,?,?)",
                (bid, _NOW(), len(rows)),
            )
        return len(rows)
    except Exception as e:
        _reraise_if_busy(e)
        return 0


@_with_retry
def rolling_window_prune(db_path: Path | None = None) -> int:
    """Prune rolling-window telemetry tables.

    WO 9f47a1a0: the raw_workflow_nodes/raw_workflow_runs DELETEs that used to
    live here were dropped along with the tables themselves (migration 141,
    write-orphaned since 2026-05-18 — see
    core/event_store/migrations/141_drop_orphaned_workflow_raw_tables.sql).
    Canonical workflow.completed/workflow.node.completed events are
    append-only in ai_canonical_events and are not pruned by this function.
    """
    try:
        cutoff = (datetime.now(UTC) - timedelta(days=90)).isoformat()
        with _db_transaction(db_path) as c:
            d1 = c.execute(
                "DELETE FROM raw_skill_telemetry WHERE id NOT IN (SELECT id FROM raw_skill_telemetry t2 WHERE t2.skill_name=raw_skill_telemetry.skill_name ORDER BY id DESC LIMIT 100)"
            ).rowcount
            d4 = c.execute("DELETE FROM raw_approaches WHERE captured_at<?", (cutoff,)).rowcount
        return d1 + d4
    except Exception as e:
        _reraise_if_busy(e)
        return 0


@_with_retry
def insert_operational_snapshot(
    snapshot_date: str,
    project_slug: str,
    *,
    ci_status: str | None = None,
    open_prs: int | None = None,
    stale_branches: int | None = None,
    pending_drafts: int | None = None,
    open_escalations: int | None = None,
    report_body: str | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        with _db_transaction(db_path) as c:
            # Feature-detect report_body (migration 153, WO-FILESDB-C4B S4). The column
            # is unreleased, so the live authority DB lacks it until `ds migrate activate`;
            # in that window we write the snapshot without the body rather than error.
            has_body = any(
                row[1] == "report_body"
                for row in c.execute("PRAGMA table_info(raw_operational_snapshots)")
            )
            if has_body:
                c.execute(
                    """INSERT OR REPLACE INTO raw_operational_snapshots
                       (snapshot_date, project_slug, ci_status, open_prs,
                        stale_branches, pending_drafts, open_escalations, report_body, captured_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        snapshot_date,
                        project_slug,
                        ci_status,
                        open_prs,
                        stale_branches,
                        pending_drafts,
                        open_escalations,
                        report_body,
                        _NOW(),
                    ),
                )
            else:
                c.execute(
                    """INSERT OR REPLACE INTO raw_operational_snapshots
                       (snapshot_date, project_slug, ci_status, open_prs,
                        stale_branches, pending_drafts, open_escalations, captured_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        snapshot_date,
                        project_slug,
                        ci_status,
                        open_prs,
                        stale_branches,
                        pending_drafts,
                        open_escalations,
                        _NOW(),
                    ),
                )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False
