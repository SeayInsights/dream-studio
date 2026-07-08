"""Authority-backed store for work-order ceremony artifacts (WO-FILESDB-P1).

Replaces the ``.planning/work-orders/<id>/*.{md,json}`` files that the
close/verify gates read. The store degrades gracefully when the
``business_work_order_artifacts`` table is absent (migration 144 stays
unreleased on the live authority DB until ``ds migrate activate``) — callers
fall back to the legacy ``.planning`` files during the transition.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from core.config import paths

_TABLE = "business_work_order_artifacts"

# Artifact kind -> legacy .planning filename (disk fallback + backfill mapping).
KIND_TO_FILENAME: dict[str, str] = {
    "api_contract": "api-contract.md",
    "security_scan": "security-scan.md",
    "design_audit": "design-audit.md",
    "review_verdict": "review-verdict.json",
    "context": "context.md",
}


def _resolve_db(db_path: Path | None) -> Path:
    return db_path or (paths.state_dir() / "studio.db")


def set_wo_artifact(
    work_order_id: str, kind: str, content: str, *, db_path: Path | None = None
) -> bool:
    """Upsert an artifact. Returns False (no-op) when the table is absent."""
    if kind not in KIND_TO_FILENAME:
        raise ValueError(f"unknown artifact kind: {kind!r}")
    now = datetime.now(UTC).isoformat()
    try:
        conn = sqlite3.connect(str(_resolve_db(db_path)))
    except sqlite3.Error:
        return False
    try:
        conn.execute(
            f"INSERT INTO {_TABLE} (work_order_id, kind, content, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(work_order_id, kind) DO UPDATE SET"
            " content=excluded.content, updated_at=excluded.updated_at",
            (work_order_id, kind, content, now, now),
        )
        conn.commit()
        return True
    except sqlite3.OperationalError:
        return False  # table absent (unreleased migration on the live authority DB)
    finally:
        conn.close()


def get_wo_artifact(work_order_id: str, kind: str, *, db_path: Path | None = None) -> str | None:
    """Return the stored artifact content, or None if absent / table missing."""
    try:
        conn = sqlite3.connect(str(_resolve_db(db_path)))
    except sqlite3.Error:
        return None
    try:
        row = conn.execute(
            f"SELECT content FROM {_TABLE} WHERE work_order_id=? AND kind=?",
            (work_order_id, kind),
        ).fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def has_wo_artifact(work_order_id: str, kind: str, *, db_path: Path | None = None) -> bool:
    return get_wo_artifact(work_order_id, kind, db_path=db_path) is not None
