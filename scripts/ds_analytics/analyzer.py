"""Analysis functions: compute trends and metrics from harvested data."""
from __future__ import annotations
import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))
from lib import paths


def compute_pulse_trend(db_path: Path | None = None) -> dict:
    """Compute health-score trend from pulse snapshots using linear regression.

    Returns a dict with dates, scores, trend_slope, and trend_direction.
    """
    if db_path is None:
        db_path = paths.state_dir() / "studio.db"

    empty = {"dates": [], "scores": [], "trend_slope": 0.0, "trend_direction": "stable"}

    if not db_path.exists():
        return empty

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT snapshot_date, health_score FROM raw_pulse_snapshots ORDER BY snapshot_date"
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return empty
    conn.close()

    if len(rows) < 2:
        return empty

    dates = [r[0] for r in rows]
    scores = [r[1] for r in rows]

    # Convert dates to ordinal day numbers for regression
    from datetime import date as _date

    ordinals = []
    for d in dates:
        parts = d.split("-")
        ordinals.append(_date(int(parts[0]), int(parts[1]), int(parts[2])).toordinal())

    from sklearn.linear_model import LinearRegression
    import numpy as np

    X = np.array(ordinals).reshape(-1, 1)
    y = np.array(scores, dtype=float)
    model = LinearRegression().fit(X, y)
    slope = float(model.coef_[0])

    if slope > 1.0:
        direction = "improving"
    elif slope < -1.0:
        direction = "degrading"
    else:
        direction = "stable"

    return {
        "dates": dates,
        "scores": scores,
        "trend_slope": slope,
        "trend_direction": direction,
    }


def compute_skill_velocity(db_path: Path | None = None):
    """Compute per-skill invocation counts, success rates, and avg token usage.

    Returns a pandas DataFrame sorted by invocation_count descending.
    """
    import pandas as pd

    columns = ["skill_name", "invocation_count", "success_rate", "avg_tokens"]

    if db_path is None:
        db_path = paths.state_dir() / "studio.db"

    if not db_path.exists():
        return pd.DataFrame(columns=columns)

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            """
            SELECT
                skill_name,
                COUNT(*)            AS invocation_count,
                AVG(success)        AS success_rate,
                AVG(input_tokens + output_tokens) AS avg_tokens
            FROM effective_skill_runs
            GROUP BY skill_name
            ORDER BY invocation_count DESC
            """
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return pd.DataFrame(columns=columns)
    conn.close()

    if not rows:
        return pd.DataFrame(columns=columns)

    return pd.DataFrame(rows, columns=columns)


def compute_conversion_rate(db_path: Path | None = None) -> dict:
    """Compute spec-to-build conversion rate from planning specs.

    Returns dict with total, orphaned, and rate keys.
    """
    if db_path is None:
        db_path = paths.state_dir() / "studio.db"

    empty = {"total": 0, "orphaned": 0, "rate": 0.0}

    if not db_path.exists():
        return empty

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*)                         AS total,
                SUM(CASE WHEN has_build_commit = 0 THEN 1 ELSE 0 END) AS orphaned
            FROM raw_planning_specs
            """
        ).fetchone()
    except sqlite3.OperationalError:
        conn.close()
        return empty
    conn.close()

    if row is None or row[0] == 0:
        return empty

    total = row[0]
    orphaned = row[1]
    rate = (total - orphaned) / total

    return {"total": total, "orphaned": orphaned, "rate": float(rate)}
