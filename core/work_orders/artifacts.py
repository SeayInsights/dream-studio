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
# Only the WO-FILESDB-P1 ceremony kinds have a single-file .planning mapping; the
# newer kinds (WO-FILESDB-C*) are authority-only.
KIND_TO_FILENAME: dict[str, str] = {
    "api_contract": "api-contract.md",
    "security_scan": "security-scan.md",
    "design_audit": "design-audit.md",
    "review_verdict": "review-verdict.json",
    "context": "context.md",
}

# All kinds accepted by the table's CHECK constraint (migration 152). Singleton kinds
# use the default instance_key=''; multi-instance kinds (eval) key each row by
# instance_key (e.g. the eval_type). Keep in sync with 152's CHECK.
VALID_KINDS: frozenset[str] = frozenset(
    {
        "api_contract",
        "security_scan",
        "design_audit",
        "review_verdict",
        "context",
        "operator_decision",
        "decision_request",
        "escalation",
        "report",
        "eval",
    }
)


def _resolve_db(db_path: Path | None) -> Path:
    return db_path or (paths.state_dir() / "studio.db")


def set_wo_artifact(
    work_order_id: str,
    kind: str,
    content: str,
    *,
    instance_key: str = "",
    db_path: Path | None = None,
) -> bool:
    """Upsert an artifact. Returns False (no-op) when the table is absent.

    Singleton artifacts use the default instance_key=''; multi-instance kinds
    (e.g. ``eval``) pass instance_key (e.g. the eval_type) so each coexists.
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"unknown artifact kind: {kind!r}")
    now = datetime.now(UTC).isoformat()
    try:
        conn = sqlite3.connect(str(_resolve_db(db_path)))
    except sqlite3.Error:
        return False
    try:
        conn.execute(
            f"INSERT INTO {_TABLE}"
            " (work_order_id, kind, instance_key, content, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(work_order_id, kind, instance_key) DO UPDATE SET"
            " content=excluded.content, updated_at=excluded.updated_at",
            (work_order_id, kind, instance_key, content, now, now),
        )
        conn.commit()
        return True
    except sqlite3.OperationalError:
        return False  # table absent (unreleased migration on the live authority DB)
    finally:
        conn.close()


def get_wo_artifact(
    work_order_id: str, kind: str, *, instance_key: str = "", db_path: Path | None = None
) -> str | None:
    """Return the stored artifact content, or None if absent / table missing."""
    try:
        conn = sqlite3.connect(str(_resolve_db(db_path)))
    except sqlite3.Error:
        return None
    try:
        row = conn.execute(
            f"SELECT content FROM {_TABLE} WHERE work_order_id=? AND kind=? AND instance_key=?",
            (work_order_id, kind, instance_key),
        ).fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def has_wo_artifact(
    work_order_id: str, kind: str, *, instance_key: str = "", db_path: Path | None = None
) -> bool:
    return (
        get_wo_artifact(work_order_id, kind, instance_key=instance_key, db_path=db_path) is not None
    )


def list_wo_artifacts(
    work_order_id: str, kind: str, *, db_path: Path | None = None
) -> list[tuple[str, str]]:
    """Return ``[(instance_key, content), ...]`` for all rows of a kind (e.g. every
    eval stage for a WO), ordered by instance_key. Empty when absent / table missing."""
    try:
        conn = sqlite3.connect(str(_resolve_db(db_path)))
    except sqlite3.Error:
        return []
    try:
        rows = conn.execute(
            f"SELECT instance_key, content FROM {_TABLE}"
            " WHERE work_order_id=? AND kind=? ORDER BY instance_key",
            (work_order_id, kind),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def list_artifacts_by_kind(
    kind: str, *, db_path: Path | None = None
) -> list[tuple[str, str, str, str]]:
    """Return every artifact of a kind across all work orders.

    Yields ``[(work_order_id, instance_key, content, updated_at), ...]`` ordered
    by ``updated_at`` descending (most-recent first). Complements
    ``list_wo_artifacts`` (which is scoped to a single WO) for operator-facing
    cross-WO queries such as ``ds escalation list``. Empty when the artifact
    table is absent (unreleased migration on the live authority DB).
    """
    try:
        conn = sqlite3.connect(str(_resolve_db(db_path)))
    except sqlite3.Error:
        return []
    try:
        rows = conn.execute(
            f"SELECT work_order_id, instance_key, content, updated_at FROM {_TABLE}"
            " WHERE kind=? ORDER BY updated_at DESC, work_order_id, instance_key",
            (kind,),
        ).fetchall()
        return [(r[0], r[1], r[2], r[3]) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def backfill_wo_artifacts(planning_root: Path, *, db_path: Path | None = None) -> int:
    """One-time migration: copy existing .planning/work-orders/<id>/*.{md,json}
    ceremony artifacts into the authority table. Returns the number written.

    Idempotent (upsert). A no-op on a DB where the table is absent (returns 0) —
    run it after ``ds migrate activate`` releases migration 144. Files are left in
    place (gitignored) until Phase 3 retires them.
    """
    wo_root = planning_root / "work-orders"
    if not wo_root.is_dir():
        return 0
    filename_to_kind = {fname: kind for kind, fname in KIND_TO_FILENAME.items()}
    written = 0
    for wo_dir in sorted(wo_root.iterdir()):
        if not wo_dir.is_dir():
            continue
        for fname, kind in filename_to_kind.items():
            fpath = wo_dir / fname
            if fpath.is_file():
                content = fpath.read_text(encoding="utf-8", errors="replace")
                if set_wo_artifact(wo_dir.name, kind, content, db_path=db_path):
                    written += 1
    return written
