"""Friction signal aggregation — updates eval_registry.friction_flag.

Three friction sources:
  (a) raw_skill_telemetry JOIN raw_sessions WHERE outcome IN ('failed','error')
  (b) cor_skill_corrections JOIN raw_skill_telemetry
  (c) guardrail_decisions WHERE action='block' for hook targets

Runs as a scheduled/on-demand aggregation — not inline in the request path.

Operator config:
  DREAM_STUDIO_FRICTION_THRESHOLD=<int>
      Global threshold override. When set, every eval_registry target must
      accumulate this many signals before friction_flag is set to 1,
      overriding the per-row friction_threshold column (default 3).
      Example: DREAM_STUDIO_FRICTION_THRESHOLD=5 ds eval queue aggregate
"""

from __future__ import annotations

import logging
import os
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

    # Operator-level threshold override — reads at call time so tests can patch env.
    env_val = os.environ.get("DREAM_STUDIO_FRICTION_THRESHOLD", "")
    effective_threshold: int | None = int(env_val) if env_val.isdigit() else None

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

        # (c) Guardrail blocks on hook targets — single JOIN, no per-row SELECT.
        try:
            rows = conn.execute("""
                SELECT DISTINCT gd.rule_id AS hook_id
                FROM guardrail_decisions gd
                JOIN eval_registry er
                  ON er.target_id = gd.rule_id AND er.target_type = 'hook'
                WHERE gd.action = 'block'
                  AND gd.rule_id IS NOT NULL
                """).fetchall()
            for r in rows:
                flagged.add(r["hook_id"])
            sources_ok += 1
        except Exception as exc:
            logger.debug("Friction source (c) skipped — guardrail_decisions: %s", exc)

        # Batch-increment signal counts and gate friction_flag on threshold.
        # Uses DREAM_STUDIO_FRICTION_THRESHOLD env var as a global override when set;
        # otherwise falls back to the per-row friction_threshold column (default 3).
        updated = 0
        if flagged:
            placeholders = ",".join("?" * len(flagged))
            target_list = list(flagged)
            conn.execute(
                f"UPDATE eval_registry"
                f" SET friction_signal_count = friction_signal_count + 1,"
                f"     updated_at = datetime('now')"
                f" WHERE target_id IN ({placeholders})",
                target_list,
            )
            if effective_threshold is not None:
                cursor = conn.execute(
                    f"UPDATE eval_registry"
                    f" SET friction_flag=1, updated_at=datetime('now')"
                    f" WHERE target_id IN ({placeholders}) AND friction_flag=0"
                    f"   AND friction_signal_count >= ?",
                    target_list + [effective_threshold],
                )
            else:
                cursor = conn.execute(
                    f"UPDATE eval_registry"
                    f" SET friction_flag=1, updated_at=datetime('now')"
                    f" WHERE target_id IN ({placeholders}) AND friction_flag=0"
                    f"   AND friction_signal_count >= friction_threshold",
                    target_list,
                )
            updated = cursor.rowcount

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
            "effective_threshold": (
                effective_threshold if effective_threshold is not None else "per-row"
            ),
        }
    except Exception as exc:
        logger.error("Friction aggregation failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def count_degraded_skills(db_path: Path | None = None) -> int:
    """Return the number of eval_registry entries that are both friction-flagged
    and score below their fixture baseline.

    Degradation requires friction_flag=1 AND rubric_score < baseline_score * 100.
    Targets with no baseline entry are counted as degraded when friction_flag=1
    (no comparison point means we can't rule out regression).
    Used by the pulse check to surface degraded skill count.
    """
    if db_path is None:
        from core.config.database import _default_db_path

        db_path = _default_db_path()
    try:
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("""
            SELECT COUNT(*) FROM eval_registry er
            LEFT JOIN (
                SELECT eval_id, MAX(baseline_score) AS baseline_score
                FROM ds_eval_baselines
                GROUP BY eval_id
            ) b ON b.eval_id = er.eval_id
            WHERE er.friction_flag = 1
              AND er.rubric_score IS NOT NULL
              AND (b.baseline_score IS NULL OR er.rubric_score < b.baseline_score * 100)
            """).fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception as exc:
        logger.debug("count_degraded_skills skipped: %s", exc)
        return 0
