"""Friction signal aggregation — updates eval_registry.friction_flag.

Three friction sources:
  (a) raw_skill_telemetry JOIN raw_sessions WHERE outcome IN ('failed','error')
  (b) cor_skill_corrections JOIN raw_skill_telemetry
  (c) guardrail_decisions WHERE action='block' for hook targets

Runs as a scheduled/on-demand aggregation — not inline in the request path.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def aggregate_friction_signals(db_path: Path | None = None) -> dict:
    """Scan friction sources and update eval_registry.friction_flag=1.

    Returns a summary dict with keys: ok, sources_checked, new_flags, total_signaled.
    Non-fatal on individual source failures — a missing table skips that source.
    """
    if db_path is None:
        from core.config.database import _default_db_path

        db_path = _default_db_path()

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        flagged: set[str] = set()
        sources_ok = 0

        # (a) Session failures linked to skill invocations.
        # The task spec references skill_invocations.skill_id; that table does not
        # exist in the schema — raw_skill_telemetry is the canonical skill-run table
        # (confirmed by sqlite_master inspection 2026-06-11). Using it here is correct.
        try:
            rows = conn.execute("""
                SELECT DISTINCT rst.skill_name AS skill_id
                FROM raw_skill_telemetry rst
                JOIN raw_sessions rs ON rs.session_id = rst.session_id
                WHERE rs.outcome IN ('failed', 'error')
                  AND rst.skill_name IS NOT NULL
                """).fetchall()
            for r in rows:
                flagged.add(r["skill_id"])
            sources_ok += 1
        except Exception as exc:
            logger.debug("Friction source (a) skipped — raw_skill_telemetry/raw_sessions: %s", exc)

        # (b) Skill corrections
        try:
            rows = conn.execute("""
                SELECT DISTINCT rst.skill_name AS skill_id
                FROM cor_skill_corrections csc
                JOIN raw_skill_telemetry rst ON rst.id = csc.telemetry_id
                WHERE rst.skill_name IS NOT NULL
                """).fetchall()
            for r in rows:
                flagged.add(r["skill_id"])
            sources_ok += 1
        except Exception as exc:
            logger.debug("Friction source (b) skipped — cor_skill_corrections: %s", exc)

        # (c) Guardrail blocks on hook targets
        try:
            rows = conn.execute("""
                SELECT DISTINCT rule_id AS candidate_hook_id
                FROM guardrail_decisions
                WHERE action = 'block'
                  AND rule_id IS NOT NULL
                """).fetchall()
            for r in rows:
                hit = conn.execute(
                    "SELECT 1 FROM eval_registry WHERE target_id=? AND target_type='hook'",
                    (r["candidate_hook_id"],),
                ).fetchone()
                if hit:
                    flagged.add(r["candidate_hook_id"])
            sources_ok += 1
        except Exception as exc:
            logger.debug("Friction source (c) skipped — guardrail_decisions: %s", exc)

        # Increment signal counts and gate friction_flag on threshold.
        # friction_threshold defaults to 3 (column default); friction_flag is only
        # set to 1 when friction_signal_count reaches the per-row threshold.
        updated = 0
        for target_id in flagged:
            conn.execute(
                "UPDATE eval_registry"
                " SET friction_signal_count = friction_signal_count + 1,"
                "     updated_at = datetime('now')"
                " WHERE target_id=?",
                (target_id,),
            )
            cursor = conn.execute(
                "UPDATE eval_registry"
                " SET friction_flag=1, updated_at=datetime('now')"
                " WHERE target_id=? AND friction_flag=0"
                "   AND friction_signal_count >= friction_threshold",
                (target_id,),
            )
            updated += cursor.rowcount

        conn.commit()
        conn.close()
        logger.info(
            "Friction aggregation: %d sources checked, %d targets signaled, %d newly flagged",
            sources_ok,
            len(flagged),
            updated,
        )
        return {
            "ok": True,
            "sources_checked": sources_ok,
            "new_flags": updated,
            "total_signaled": len(flagged),
        }
    except Exception as exc:
        logger.error("Friction aggregation failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def count_degraded_skills(db_path: Path | None = None) -> int:
    """Return the number of eval_registry entries with friction_flag=1.

    Used by the pulse check to surface degraded skill count.
    """
    if db_path is None:
        from core.config.database import _default_db_path

        db_path = _default_db_path()
    try:
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT COUNT(*) FROM eval_registry WHERE friction_flag=1").fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception as exc:
        logger.debug("count_degraded_skills skipped: %s", exc)
        return 0
