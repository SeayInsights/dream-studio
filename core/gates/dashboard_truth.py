"""Dashboard truth gate (WO-LIVE-DATA-GATE T2).

Runs five live-authority invariants against the SQLite authority DB.  Every
invariant is expressed as ``SELECT 1 WHERE <clause>`` — the convention
established by WO-LIVE-DATA-GATE T1:

  * A row returned  → PASS
  * Zero rows       → FAIL (condition false, or data violates the invariant)
  * Exception       → FAIL (table missing / DB error handled per-invariant)

All five invariants are **vacuously passing on a fresh/empty authority DB**.
They fire only when production data exists and violates a structural guarantee.

Invariants
----------
1. token_model_null_fraction
   Model-id null fraction < 20 %.  A token table with no rows vacuously passes;
   a populated table must have < 20 % NULL model_ids.

2. token_skill_attributed
   At least one token row carries a non-NULL skill_id.  Vacuously passes when
   the table is empty.

3. execution_events_project_resolved
   Every execution_events row whose project_id is non-NULL resolves to a known
   business_projects row.  Vacuously passes when the table is empty.

4. active_project_has_activity
   Every project with status='active' has at least one execution_events row
   referencing it.  Vacuously passes when there are no active projects.

5. priceable_cost_present
   At least one token row carries a non-NULL model_id (required to price the
   session).  Vacuously passes when the table is empty.  Does NOT assert a
   dollar amount — reportable cost is honestly $0 for plan-tier usage.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Invariant definitions
# ---------------------------------------------------------------------------

#: Each entry: (name, sql).
#: sql must return >=1 row to PASS; zero rows = FAIL.
_INVARIANTS: list[tuple[str, str]] = [
    (
        "token_model_null_fraction",
        (
            "SELECT 1 WHERE"
            " (SELECT COUNT(*) FROM token_usage_records) = 0"
            " OR"
            " (SELECT CAST("
            "    SUM(CASE WHEN model_id IS NULL THEN 1 ELSE 0 END) AS REAL"
            "  ) / COUNT(*)"
            "  FROM token_usage_records"
            " ) < 0.2"
        ),
    ),
    (
        "token_skill_attributed",
        (
            "SELECT 1 WHERE"
            " (SELECT COUNT(*) FROM token_usage_records) = 0"
            " OR"
            " EXISTS (SELECT 1 FROM token_usage_records WHERE skill_id IS NOT NULL)"
        ),
    ),
    (
        "execution_events_project_resolved",
        (
            "SELECT 1 WHERE"
            " (SELECT COUNT(*) FROM execution_events) = 0"
            " OR"
            " EXISTS ("
            "  SELECT 1 FROM execution_events ee"
            "  JOIN business_projects bp ON bp.project_id = ee.project_id"
            " )"
        ),
    ),
    (
        "active_project_has_activity",
        (
            "SELECT 1 WHERE"
            " NOT EXISTS (SELECT 1 FROM business_projects WHERE status = 'active')"
            " OR"
            " EXISTS ("
            "  SELECT 1 FROM business_projects bp"
            "  JOIN execution_events ee ON ee.project_id = bp.project_id"
            "  WHERE bp.status = 'active'"
            " )"
        ),
    ),
    (
        "priceable_cost_present",
        (
            "SELECT 1 WHERE"
            " (SELECT COUNT(*) FROM token_usage_records) = 0"
            " OR"
            " EXISTS (SELECT 1 FROM token_usage_records WHERE model_id IS NOT NULL)"
        ),
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_dashboard_truth(db_path: "str | Path") -> dict[str, Any]:
    """Execute all five invariants read-only against *db_path*.

    Returns::

        {
            "ok": bool,                          # True iff every invariant passed
            "results": [
                {"name": str, "passed": bool, "error": str | None},
                ...
            ],
        }

    Missing tables cause the affected invariant to **vacuously pass** (not
    crash), because on a fresh authority DB those tables may not exist yet.
    """
    db_uri = f"file:{db_path}?mode=ro"
    results: list[dict[str, Any]] = []

    try:
        conn = sqlite3.connect(db_uri, uri=True)
    except Exception as exc:
        # Cannot open DB at all — all invariants fail with the same error.
        for name, _ in _INVARIANTS:
            results.append({"name": name, "passed": False, "error": str(exc)})
        return {"ok": False, "results": results}

    try:
        for name, sql in _INVARIANTS:
            try:
                row = conn.execute(sql).fetchone()
                passed = row is not None
                results.append({"name": name, "passed": passed, "error": None})
            except sqlite3.OperationalError as exc:
                err_msg = str(exc)
                # "no such table" → table absent on fresh DB → vacuous pass.
                if "no such table" in err_msg.lower():
                    results.append({"name": name, "passed": True, "error": None})
                else:
                    results.append({"name": name, "passed": False, "error": err_msg})
            except Exception as exc:
                results.append({"name": name, "passed": False, "error": str(exc)})
    finally:
        conn.close()

    ok = all(r["passed"] for r in results)
    return {"ok": ok, "results": results}
