"""Authority DB read helpers and SQL-CHECK execution for work-order verify.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/verify.py``. Holds the
authority-DB lookups (task/work-order reads) and the SQL-CHECK executor used
to annotate task acceptance criteria with ground-truth pass/fail before a
grader ever sees them. No logic changes — extracted verbatim from the
original module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# ── DB helpers ─────────────────────────────────────────────────────────────────


def _require_db(source_root: Path, dream_studio_home: Path | None) -> Path:
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing.")
    return paths.sqlite_path


def _read_tasks(conn: Any, work_order_id: str) -> list[dict[str, str]]:
    has_ac = any(
        r[1] == "acceptance_criteria"
        for r in conn.execute("PRAGMA table_info(business_tasks)").fetchall()
    )
    cols = "title, description, status" + (", acceptance_criteria" if has_ac else "")
    rows = conn.execute(
        f"SELECT {cols} FROM business_tasks WHERE work_order_id = ? ORDER BY created_at ASC",
        (work_order_id,),
    ).fetchall()
    return [
        {
            "title": r[0],
            "description": r[1] or "",
            "status": r[2],
            "acceptance_criteria": (r[3] or "") if has_ac else "",
        }
        for r in rows
    ]


def _read_work_order(conn: Any, work_order_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT work_order_id, title, project_id, milestone_id, sequence_order, work_order_type"
        " FROM business_work_orders WHERE work_order_id = ?",
        (work_order_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "work_order_id": row[0],
        "title": row[1],
        "project_id": row[2],
        "milestone_id": row[3],
        "sequence_order": row[4],
        "work_order_type": row[5],
    }


# ── SQL-CHECK executor ─────────────────────────────────────────────────────────


def _run_sql_checks(tasks: list[dict[str, Any]], db_path: Path) -> dict[str, list[dict[str, Any]]]:
    """Execute SQL-CHECK lines from task acceptance_criteria read-only against the authority DB.

    Convention: a line in acceptance_criteria starting with ``SQL-CHECK:`` (case-insensitive)
    followed by a SELECT statement. The check passes if the query returns at least one row
    with a truthy first-column value (e.g. a non-zero COUNT). Fails on zero/null/no rows or
    on any query error.

    Returns a mapping of task_title -> list of {sql, passed, result, error}.
    Only tasks that have at least one SQL-CHECK line produce an entry.
    """
    import sqlite3 as _sqlite3

    results: dict[str, list[dict[str, Any]]] = {}
    try:
        conn = _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return {}

    try:
        for task in tasks:
            ac = task.get("acceptance_criteria", "") or ""
            checks: list[dict[str, Any]] = []
            for raw_line in ac.splitlines():
                line = raw_line.strip()
                if not line.upper().startswith("SQL-CHECK:"):
                    continue
                sql = line[len("SQL-CHECK:") :].strip()  # noqa: E203
                check: dict[str, Any] = {
                    "sql": sql,
                    "passed": False,
                    "result": None,
                    "error": None,
                }
                try:
                    row = conn.execute(sql).fetchone()
                    if row is not None:
                        val = row[0]
                        check["result"] = val
                        check["passed"] = bool(val)
                    # else: no rows → passed stays False
                except Exception as exc:
                    check["error"] = str(exc)
                checks.append(check)
            if checks:
                results[task["title"]] = checks
    finally:
        conn.close()

    return results


def _format_sql_checks(checks: list[dict[str, Any]]) -> str:
    """Render SQL-CHECK results as annotated lines for the completion grader prompt."""
    if not checks:
        return ""
    lines: list[str] = []
    for c in checks:
        if c.get("error"):
            lines.append(f"\n   SQL-CHECK RESULT: FAIL (error: {c['error']})")
        elif c["passed"]:
            lines.append(f"\n   SQL-CHECK RESULT: PASS (result={c['result']})")
        else:
            lines.append(f"\n   SQL-CHECK RESULT: FAIL (result={c['result']})")
    return "".join(lines)
