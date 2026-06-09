"""Aggregate metrics pipeline — reads from studio.db, writes to aggregate_metrics.db.

Idempotent: running twice produces same data. Uses INSERT OR REPLACE to overwrite
stale rows rather than accumulating duplicates.

aggregate_metrics.db is a DuckDB file at state_dir() / "aggregate_metrics.db".
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from core.analytics.duckdb_store import (
    analytics_db_path,
    connect_analytics,
    ensure_analytics_schema,
)
from core.config.paths import state_dir


def aggregate_metrics_db_path() -> Path:
    """Return path to aggregate_metrics.db."""
    return analytics_db_path()


def _connect_source() -> sqlite3.Connection:
    """Connect to the live studio.db (read-only)."""
    from core.config.database import _default_db_path

    db_path = _default_db_path()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_aggregate(db_path: Path | None = None):
    """Open a read-write DuckDB connection to aggregate_metrics.db."""
    return connect_analytics(db_path, read_only=False)


def ensure_aggregate_schema(db_path: Path | None = None) -> None:
    """Create aggregate_metrics.db schema if not already present."""
    conn = _connect_aggregate(db_path)
    try:
        ensure_analytics_schema(conn)
    finally:
        conn.close()


def run_aggregation(db_path: Path | None = None) -> dict:
    """Run full aggregation from studio.db → aggregate_metrics.db.

    Returns summary dict with counts of rows written per table.
    Idempotent: INSERT OR REPLACE overwrites stale rows.
    """
    ensure_aggregate_schema(db_path)
    now = datetime.now(timezone.utc).isoformat()
    summary = {}

    try:
        src = _connect_source()
    except Exception as e:
        return {"error": f"Could not connect to studio.db: {e}", "tables_written": {}}

    agg = _connect_aggregate(db_path)
    try:
        # ── finding_rollups ────────────────────────────────────────────────────
        try:
            rows = src.execute("""
                SELECT
                    project_id,
                    'unknown' AS skill_id,
                    COALESCE(severity, 'unknown') AS severity,
                    date(created_at) AS day,
                    COUNT(*) AS finding_count,
                    0 AS new_count,
                    SUM(CASE WHEN current_status IN ('resolved','fixed') THEN 1 ELSE 0 END) AS fixed_count,
                    SUM(CASE WHEN current_status = 'open' THEN 1 ELSE 0 END) AS persisting_count
                FROM findings_current_status
                WHERE project_id IS NOT NULL
                GROUP BY project_id, severity, day
            """).fetchall()
            agg.executemany(
                """INSERT OR REPLACE INTO finding_rollups
                   (project_id, skill_id, severity, day, finding_count,
                    new_count, fixed_count, persisting_count, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        r["project_id"],
                        r["skill_id"],
                        r["severity"],
                        r["day"],
                        r["finding_count"],
                        r["new_count"],
                        r["fixed_count"],
                        r["persisting_count"],
                        now,
                    )
                    for r in rows
                ],
            )
            agg.commit()
            summary["finding_rollups"] = len(rows)
        except Exception as e:
            summary["finding_rollups"] = f"error: {e}"

        # ── rule_fire_rates ────────────────────────────────────────────────────
        try:
            rows = src.execute("""
                SELECT
                    COALESCE(vuln_class, 'unknown') AS rule_id,
                    'unknown' AS skill_id,
                    COUNT(*) AS fire_count,
                    MAX(created_at) AS last_fired_at
                FROM security_events
                WHERE event_kind = 'finding.recorded' AND vuln_class IS NOT NULL
                GROUP BY vuln_class
            """).fetchall()
            # Also get dismiss counts from guard_events
            guard_rows = {}
            try:
                g = src.execute("""
                    SELECT rule_id, COUNT(*) AS dismiss_count
                    FROM guard_events
                    WHERE action = 'dismissed' AND rule_id IS NOT NULL
                    GROUP BY rule_id
                """).fetchall()
                guard_rows = {r["rule_id"]: r["dismiss_count"] for r in g}
            except Exception:
                pass

            agg.executemany(
                """INSERT OR REPLACE INTO rule_fire_rates
                   (rule_id, skill_id, fire_count, dismiss_count, fp_rate,
                    last_fired_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        r["rule_id"],
                        r["skill_id"],
                        r["fire_count"],
                        guard_rows.get(r["rule_id"], 0),
                        guard_rows.get(r["rule_id"], 0) / max(r["fire_count"], 1),
                        r["last_fired_at"],
                        now,
                    )
                    for r in rows
                ],
            )
            agg.commit()
            summary["rule_fire_rates"] = len(rows)
        except Exception as e:
            summary["rule_fire_rates"] = f"error: {e}"

        # ── baseline_trends ────────────────────────────────────────────────────
        try:
            rows = src.execute("""
                SELECT
                    sr.project_id,
                    COALESCE(sr.skill_id, 'unknown') AS skill_id,
                    SUM(CASE WHEN sr.is_baseline = 1 THEN sr.findings_count ELSE 0 END) AS baseline_count,
                    SUM(CASE WHEN sr.is_baseline = 0 THEN sr.findings_count ELSE 0 END) AS current_count,
                    COUNT(sr.scan_id) AS scan_count,
                    MAX(sr.started_at) AS last_scan_at
                FROM scan_runs sr
                WHERE sr.project_id IS NOT NULL AND sr.status = 'completed'
                GROUP BY sr.project_id, sr.skill_id
            """).fetchall()
            agg.executemany(
                """INSERT OR REPLACE INTO baseline_trends
                   (project_id, skill_id, baseline_count, current_count, delta,
                    trend_direction, scan_count, last_scan_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        r["project_id"],
                        r["skill_id"],
                        r["baseline_count"],
                        r["current_count"],
                        r["current_count"] - r["baseline_count"],
                        (
                            "improving"
                            if r["current_count"] < r["baseline_count"]
                            else (
                                "stable"
                                if r["current_count"] == r["baseline_count"]
                                else "regressing"
                            )
                        ),
                        r["scan_count"],
                        r["last_scan_at"],
                        now,
                    )
                    for r in rows
                ],
            )
            agg.commit()
            summary["baseline_trends"] = len(rows)
        except Exception as e:
            summary["baseline_trends"] = f"error: {e}"

        # ── guard_calibration ─────────────────────────────────────────────────
        try:
            rows = src.execute("""
                SELECT
                    rule_id,
                    COUNT(*) AS total_fires,
                    SUM(CASE WHEN action = 'dismissed' THEN 1 ELSE 0 END) AS dismiss_count,
                    SUM(CASE WHEN action = 'blocked' THEN 1 ELSE 0 END) AS block_count,
                    SUM(CASE WHEN action = 'logged' THEN 1 ELSE 0 END) AS advisory_count
                FROM guard_events
                WHERE rule_id IS NOT NULL
                GROUP BY rule_id
            """).fetchall()
            agg.executemany(
                """INSERT OR REPLACE INTO guard_calibration
                   (rule_id, total_fires, dismiss_count, block_count, advisory_count,
                    fp_rate, calibration_status, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        r["rule_id"],
                        r["total_fires"],
                        r["dismiss_count"],
                        r["block_count"],
                        r["advisory_count"],
                        r["dismiss_count"] / max(r["total_fires"], 1),
                        "ready" if r["total_fires"] >= 10 else "pending",
                        now,
                    )
                    for r in rows
                ],
            )
            agg.commit()
            summary["guard_calibration"] = len(rows)
        except Exception as e:
            summary["guard_calibration"] = f"error: {e}"

        # ── pattern_catalog ───────────────────────────────────────────────────
        try:
            rows = src.execute("""
                SELECT
                    project_id,
                    skill_id,
                    COUNT(*) AS occurrence_count,
                    AVG(findings_count) AS avg_findings_per_run,
                    MAX(started_at) AS last_seen_at
                FROM scan_runs
                WHERE project_id IS NOT NULL AND status = 'completed'
                GROUP BY project_id, skill_id
                HAVING occurrence_count >= 2
            """).fetchall()
            import hashlib

            agg.executemany(
                """INSERT OR REPLACE INTO pattern_catalog
                   (pattern_id, project_id, skill_sequence, occurrence_count,
                    avg_findings_per_run, last_seen_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        hashlib.md5(f"{r['project_id']}:{r['skill_id']}".encode()).hexdigest(),
                        r["project_id"],
                        r["skill_id"],
                        r["occurrence_count"],
                        r["avg_findings_per_run"],
                        r["last_seen_at"],
                        now,
                    )
                    for r in rows
                ],
            )
            agg.commit()
            summary["pattern_catalog"] = len(rows)
        except Exception as e:
            summary["pattern_catalog"] = f"error: {e}"

        # ── recommendation_outcomes (seeded from rule fire counts for now) ────
        summary["recommendation_outcomes"] = 0  # No tracking data yet — table seeded empty

        # ── meta ──────────────────────────────────────────────────────────────
        agg.execute(
            "INSERT OR REPLACE INTO _aggregate_meta (key, value) VALUES (?, ?)",
            ("last_aggregated_at", now),
        )
        agg.execute(
            "INSERT OR REPLACE INTO _aggregate_meta (key, value) VALUES (?, ?)",
            ("source_db", str(aggregate_metrics_db_path().parent / "studio.db")),
        )
        agg.commit()

    finally:
        src.close()
        agg.close()

    return {"status": "ok", "tables_written": summary, "timestamp": now}
