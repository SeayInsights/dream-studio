"""How much business data the authority holds, and whether that just fell.

The empty authority that replaced the operator's real one on 2026-09-23 passed
every health check Dream Studio had: a database with the full schema and zero
projects is perfectly healthy by every structural measure. What was wrong was
the DATA, and nothing counted it. ``authority_data_check`` counts the key
business tables read-only, warns on an empty one, and warns when a count fell
below the last recorded baseline. Recording that baseline is a write, so it is
never implicit: ``ds doctor --record-counts`` and ``ds self-install`` record it.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Label -> table. "events" is the canonical event log every recorded action lands in.
KEY_TABLES: dict[str, str] = {
    "projects": "business_projects",
    "work_orders": "business_work_orders",
    "tasks": "business_tasks",
    "events": "business_canonical_events",
}

COUNTS_FILE = "authority-counts.json"


def counts_path(home: Path) -> Path:
    return home / "state" / COUNTS_FILE


def read_counts(db_path: Path) -> dict[str, int | None]:
    """Row counts per KEY_TABLES label through a read-only connection (None: no table)."""
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True, timeout=5.0)
    try:
        present = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
        }
        counts: dict[str, int | None] = {}
        for label, table in KEY_TABLES.items():
            if table not in present:
                counts[label] = None
                continue
            counts[label] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        return counts
    finally:
        conn.close()


def last_recorded(home: Path) -> dict[str, Any] | None:
    path = counts_path(home)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) and isinstance(data.get("counts"), dict) else None


def authority_data_check(home: Path, db_path: Path) -> dict[str, Any]:
    """Counts, the last recorded baseline, and warnings. Writes nothing."""
    result: dict[str, Any] = {
        "db_path": str(db_path),
        "readable": False,
        "counts": {},
        "last_recorded": None,
        "warnings": [],
    }
    if not db_path.is_file():
        result["warnings"].append(f"authority database missing: {db_path}")
        return result
    try:
        counts = read_counts(db_path)
    except sqlite3.Error as exc:
        result["warnings"].append(f"authority unreadable: {type(exc).__name__}: {exc}")
        return result
    result["readable"] = True
    result["counts"] = counts
    previous = last_recorded(home)
    result["last_recorded"] = previous
    for label, count in counts.items():
        if count is None:
            result["warnings"].append(f"{label}: table {KEY_TABLES[label]} is missing")
        elif count == 0:
            result["warnings"].append(f"{label}: zero rows (empty authority?)")
    if previous:
        before = previous["counts"]
        for label, count in counts.items():
            was = before.get(label)
            if isinstance(was, int) and isinstance(count, int) and count < was:
                result["warnings"].append(
                    f"{label}: dropped from {was} to {count} since {previous.get('recorded_at')}"
                )
    return result


def record_counts(home: Path, db_path: Path) -> dict[str, Any]:
    """Write the current counts as the baseline later checks compare against."""
    record = {"recorded_at": datetime.now(UTC).isoformat(), "counts": read_counts(db_path)}
    path = counts_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record
