"""Seed DuckDB analytics store from existing studio.db (SQLite) data.

Run once after schema is created to backfill historical business_* rows into
the DuckDB equivalents. Safe to re-run — INSERT OR REPLACE by primary key.

Usage:
    py -m core.analytics.seed_from_sqlite
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.analytics.duckdb_store import connect_analytics, ensure_analytics_schema
from core.config.database import _default_db_path


def _seed_projects(src: sqlite3.Connection, dst) -> int:
    rows = src.execute(
        "SELECT project_id, name, description, status, project_path, detected_stack,"
        " vision_statement, total_sessions, total_tokens, last_session_at,"
        " created_at, updated_at, last_event_id FROM business_projects"
    ).fetchall()
    dst.executemany(
        """INSERT OR REPLACE INTO duckdb_projects
           (project_id, name, description, status, project_path, detected_stack,
            vision_statement, total_sessions, total_tokens, last_session_at,
            created_at, updated_at, last_event_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    return len(rows)


def _seed_milestones(src: sqlite3.Connection, dst) -> int:
    rows = src.execute(
        "SELECT milestone_id, project_id, title, description, status, order_index,"
        " due_date, created_at, updated_at, last_event_id FROM business_milestones"
    ).fetchall()
    dst.executemany(
        """INSERT OR REPLACE INTO duckdb_milestones
           (milestone_id, project_id, title, description, status, order_index,
            due_date, created_at, updated_at, last_event_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    return len(rows)


def _seed_work_orders(src: sqlite3.Connection, dst) -> int:
    rows = src.execute(
        "SELECT work_order_id, project_id, milestone_id, title, description,"
        " work_order_type, status, sequence_order, created_at, last_updated_at, last_event_id"
        " FROM business_work_orders"
    ).fetchall()
    dst.executemany(
        """INSERT OR REPLACE INTO duckdb_work_orders
           (work_order_id, project_id, milestone_id, title, description,
            work_order_type, status, sequence_order, created_at, updated_at, last_event_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    return len(rows)


def _seed_tasks(src: sqlite3.Connection, dst) -> int:
    rows = src.execute(
        "SELECT task_id, work_order_id, project_id, title, description,"
        " status, created_at, updated_at, last_event_id FROM business_tasks"
    ).fetchall()
    dst.executemany(
        """INSERT OR REPLACE INTO duckdb_tasks
           (task_id, work_order_id, project_id, title, description,
            status, created_at, updated_at, last_event_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    return len(rows)


def _seed_design_briefs(src: sqlite3.Connection, dst) -> int:
    rows = src.execute(
        "SELECT brief_id, project_id, status, purpose, audience, tone,"
        " design_system, font_pairing, brand_tokens, created_at, updated_at, last_event_id"
        " FROM business_design_briefs"
    ).fetchall()
    dst.executemany(
        """INSERT OR REPLACE INTO duckdb_design_briefs
           (brief_id, project_id, status, purpose, audience, tone,
            design_system, font_pairing, brand_tokens, created_at, updated_at, last_event_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    return len(rows)


def seed(sqlite_path: Path | None = None, duckdb_path: Path | None = None) -> dict:
    """Seed DuckDB from SQLite. Returns row counts per table."""
    src_path = sqlite_path or _default_db_path()
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    dst = connect_analytics(duckdb_path, read_only=False)
    ensure_analytics_schema(dst)

    counts = {}
    seeders = [
        ("projects", _seed_projects),
        ("milestones", _seed_milestones),
        ("work_orders", _seed_work_orders),
        ("tasks", _seed_tasks),
        ("design_briefs", _seed_design_briefs),
    ]
    for name, fn in seeders:
        try:
            counts[name] = fn(src, dst)
        except Exception as exc:
            counts[name] = f"error: {exc}"

    dst.commit()
    src.close()
    dst.close()
    return counts


if __name__ == "__main__":
    result = seed()
    for table, count in result.items():
        print(f"  {table}: {count}")
