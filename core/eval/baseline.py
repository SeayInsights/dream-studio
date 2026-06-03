"""Baseline storage — reads and writes ds_eval_baselines table.

Baseline is established on first run of an eval case.
Subsequent runs are compared against the baseline.
Regression = composite_score drops more than regression_threshold below baseline.

Baseline updates require explicit `ds eval baseline --update` command.
Auto-update on regression is intentionally prevented.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_conn(db_path: Path | None = None) -> sqlite3.Connection:
    """Get a connection to the studio.db (or test DB)."""
    if db_path is None:
        from core.config.database import _default_db_path

        db_path = _default_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def load_baseline(eval_id: str, version: str, db_path: Path | None = None) -> dict[str, Any] | None:
    """Load the current baseline for an eval case. Returns None if no baseline set."""
    try:
        conn = _get_conn(db_path)
        row = conn.execute(
            "SELECT * FROM ds_eval_baselines WHERE eval_id = ? AND version = ?",
            (eval_id, version),
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        # Table may not exist in test environments
        logger.debug("ds_eval_baselines table not found — no baseline loaded")
        return None
    except Exception as exc:
        logger.warning("Failed to load baseline for %s: %s", eval_id, exc)
        return None


def save_run_result(
    eval_id: str,
    version: str,
    composite_score: float,
    passed: bool,
    *,
    regression_threshold: float = 0.10,
    db_path: Path | None = None,
) -> tuple[bool, bool]:
    """Save a run result and check for regression.

    Returns:
        (is_baseline_run, regression_flagged)
        - is_baseline_run: True if this is the first run (baseline established)
        - regression_flagged: True if score regressed beyond threshold
    """
    try:
        conn = _get_conn(db_path)
        existing = conn.execute(
            "SELECT * FROM ds_eval_baselines WHERE eval_id = ? AND version = ?",
            (eval_id, version),
        ).fetchone()

        if existing is None:
            # First run — establish baseline
            conn.execute(
                """INSERT INTO ds_eval_baselines
                   (eval_id, version, baseline_score, last_run_score, last_run_at,
                    regression_flag, regression_threshold, run_count, last_updated_at)
                   VALUES (?, ?, ?, ?, datetime('now'), 0, ?, 1, datetime('now'))""",
                (eval_id, version, composite_score, composite_score, regression_threshold),
            )
            conn.commit()
            conn.close()
            logger.info("Baseline established for eval %s: %.3f", eval_id, composite_score)
            return True, False
        else:
            baseline_score = existing["baseline_score"]
            drop = baseline_score - composite_score
            regression_flagged = drop > regression_threshold
            conn.execute(
                """UPDATE ds_eval_baselines
                   SET last_run_score = ?, last_run_at = datetime('now'),
                       regression_flag = ?, run_count = run_count + 1,
                       last_updated_at = datetime('now')
                   WHERE eval_id = ? AND version = ?""",
                (composite_score, 1 if regression_flagged else 0, eval_id, version),
            )
            conn.commit()
            conn.close()
            if regression_flagged:
                logger.warning(
                    "REGRESSION flagged for eval %s: baseline=%.3f, current=%.3f, drop=%.3f (threshold=%.3f)",
                    eval_id,
                    baseline_score,
                    composite_score,
                    drop,
                    regression_threshold,
                )
            return False, regression_flagged
    except sqlite3.OperationalError:
        logger.debug("ds_eval_baselines table not found — skipping baseline check")
        return False, False
    except Exception as exc:
        logger.warning("Failed to save run result for %s: %s", eval_id, exc)
        return False, False


def update_baseline(
    eval_id: str,
    version: str,
    new_baseline_score: float,
    db_path: Path | None = None,
) -> bool:
    """Explicitly update the baseline score. Called by 'ds eval baseline --update'."""
    try:
        conn = _get_conn(db_path)
        conn.execute(
            """UPDATE ds_eval_baselines
               SET baseline_score = ?, regression_flag = 0, last_updated_at = datetime('now')
               WHERE eval_id = ? AND version = ?""",
            (new_baseline_score, eval_id, version),
        )
        if conn.execute("SELECT changes()").fetchone()[0] == 0:
            # No existing row — insert new baseline
            conn.execute(
                """INSERT INTO ds_eval_baselines
                   (eval_id, version, baseline_score, last_run_score, last_run_at,
                    regression_flag, regression_threshold, run_count, last_updated_at)
                   VALUES (?, ?, ?, ?, datetime('now'), 0, 0.1, 0, datetime('now'))""",
                (eval_id, version, new_baseline_score, new_baseline_score),
            )
        conn.commit()
        conn.close()
        logger.info("Baseline updated for eval %s to %.3f", eval_id, new_baseline_score)
        return True
    except Exception as exc:
        logger.error("Failed to update baseline for %s: %s", eval_id, exc)
        return False


def get_all_baselines(db_path: Path | None = None) -> list[dict[str, Any]]:
    """Return all eval baselines for the report command."""
    try:
        conn = _get_conn(db_path)
        rows = conn.execute(
            "SELECT * FROM ds_eval_baselines ORDER BY eval_id, version"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    except Exception as exc:
        logger.warning("Failed to load baselines: %s", exc)
        return []
