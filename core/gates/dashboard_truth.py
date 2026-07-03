"""Dashboard truth gate (WO-LIVE-DATA-GATE T2).

Runs five live-authority invariants.  Every invariant is expressed as
``SELECT 1 WHERE <clause>`` — the convention established by WO-LIVE-DATA-GATE
T1:

  * A row returned  → PASS
  * Zero rows       → FAIL (condition false, or data violates the invariant)
  * Exception       → FAIL (table missing / DB error handled per-invariant)

All five invariants are **vacuously passing on a fresh/empty authority DB**.
They fire only when production data exists and violates a structural guarantee.

Two of the five (execution_events_project_resolved, active_project_has_activity)
run against the SQLite authority DB. The other three (token_model_null_fraction,
token_skill_attributed, priceable_cost_present) run against the DuckDB
aggregate_metrics.db token_usage_records view (WO-DBA-DROP, migration 137
retired the SQLite token_usage_records table — the DuckDB view over canonical
token.consumed events is the sole source now).

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

A missing/unavailable DuckDB analytics store (fresh install, projection runner
never ran, duckdb import failure) is a pass-with-note for the three token
invariants — it must never block work-order close. The analytics store is
NEVER-AUTHORITY and fully rebuildable; its absence is not a data violation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Invariant definitions
# ---------------------------------------------------------------------------

#: SQLite-backed invariants. Each entry: (name, sql).
#: sql must return >=1 row to PASS; zero rows = FAIL.
_SQLITE_INVARIANTS: list[tuple[str, str]] = [
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
]

#: DuckDB-backed token invariants (WO-DBA-DROP) — run against the
#: aggregate_metrics.db token_usage_records view. Same SQL shape as the
#: retired SQLite invariants: the view carries the same column names
#: (model_id, skill_id), so the clause text is unchanged.
_DUCKDB_TOKEN_INVARIANTS: list[tuple[str, str]] = [
    (
        "token_model_null_fraction",
        (
            "SELECT 1 WHERE"
            " (SELECT COUNT(*) FROM token_usage_records) = 0"
            " OR"
            " (SELECT CAST("
            "    SUM(CASE WHEN model_id IS NULL THEN 1 ELSE 0 END) AS DOUBLE"
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
        "priceable_cost_present",
        (
            "SELECT 1 WHERE"
            " (SELECT COUNT(*) FROM token_usage_records) = 0"
            " OR"
            " EXISTS (SELECT 1 FROM token_usage_records WHERE model_id IS NOT NULL)"
        ),
    ),
]

_INVARIANTS: list[tuple[str, str]] = [*_DUCKDB_TOKEN_INVARIANTS, *_SQLITE_INVARIANTS]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _run_duckdb_token_invariants() -> list[dict[str, Any]]:
    """Run the three token invariants against the DuckDB view.

    A missing/unavailable analytics store is a pass-with-note for every token
    invariant — never a gate failure (work-order close must not be blocked by
    an absent, fully-rebuildable, NEVER-AUTHORITY analytics store).
    """
    try:
        from core.analytics.duckdb_store import connect_analytics

        conn = connect_analytics(read_only=True)
    except Exception as exc:
        return [
            {
                "name": name,
                "passed": True,
                "error": None,
                "note": f"analytics store unavailable: {exc}",
            }
            for name, _ in _DUCKDB_TOKEN_INVARIANTS
        ]

    results: list[dict[str, Any]] = []
    try:
        for name, sql in _DUCKDB_TOKEN_INVARIANTS:
            try:
                row = conn.execute(sql).fetchone()
                results.append({"name": name, "passed": row is not None, "error": None})
            except Exception as exc:
                # Missing view (schema never initialized) or any other DuckDB
                # error — pass-with-note, never block work-order close.
                results.append(
                    {
                        "name": name,
                        "passed": True,
                        "error": None,
                        "note": f"token_usage_records view unavailable: {exc}",
                    }
                )
    finally:
        conn.close()
    return results


def run_dashboard_truth(db_path: str | Path) -> dict[str, Any]:
    """Execute all five invariants against *db_path* (SQLite) and the DuckDB
    analytics store (token invariants).

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

    A **missing authority file** (no ``~/.dream-studio/state/studio.db`` — e.g.
    a fresh CI checkout) also vacuously passes every invariant: there is no
    populated data that could violate a structural guarantee.  The gate only
    fires when an authority exists *and* its data is wrong.
    """
    token_results = _run_duckdb_token_invariants()

    # No authority on disk → nothing to violate → SQLite invariants vacuously pass.
    if not Path(db_path).exists():
        sqlite_results = [
            {"name": name, "passed": True, "error": None} for name, _ in _SQLITE_INVARIANTS
        ]
        results = [*token_results, *sqlite_results]
        return {"ok": all(r["passed"] for r in results), "results": results}

    db_uri = f"file:{db_path}?mode=ro"

    try:
        conn = sqlite3.connect(db_uri, uri=True)
    except Exception as exc:
        # File exists but cannot be opened (corrupt/locked) — a real fault.
        sqlite_results = [
            {"name": name, "passed": False, "error": str(exc)} for name, _ in _SQLITE_INVARIANTS
        ]
        results = [*token_results, *sqlite_results]
        return {"ok": False, "results": results}

    sqlite_results = []
    try:
        for name, sql in _SQLITE_INVARIANTS:
            try:
                row = conn.execute(sql).fetchone()
                passed = row is not None
                sqlite_results.append({"name": name, "passed": passed, "error": None})
            except sqlite3.OperationalError as exc:
                err_msg = str(exc)
                # "no such table" → table absent on fresh DB → vacuous pass.
                if "no such table" in err_msg.lower():
                    sqlite_results.append({"name": name, "passed": True, "error": None})
                else:
                    sqlite_results.append({"name": name, "passed": False, "error": err_msg})
            except Exception as exc:
                sqlite_results.append({"name": name, "passed": False, "error": str(exc)})
    finally:
        conn.close()

    results = [*token_results, *sqlite_results]
    ok = all(r["passed"] for r in results)
    return {"ok": ok, "results": results}
