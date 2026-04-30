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
