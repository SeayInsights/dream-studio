"""Executable check runner (SQL-CHECK / TEST-CHECK / API-CHECK) for work orders.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/verify.py``. Holds the
per-check-kind runners and the top-level ``run_executable_checks`` dispatcher,
plus the best-effort validation.result_recorded telemetry emission. No logic
changes — extracted verbatim from the original module.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

_CHECK_PREFIXES = ("SQL-CHECK:", "TEST-CHECK:", "API-CHECK:")

# Timeout in seconds for TEST-CHECK subprocess calls.
_TEST_CHECK_TIMEOUT = 300

# ── SQL-CHECK semantics (authoritative — see also docs/authoring/work-orders.md) ──
#
# A SQL-CHECK acceptance criterion MUST be written in the form:
#
#   SQL-CHECK: SELECT 1 WHERE <condition>
#
# so that a FALSE condition yields ZERO rows, which is an explicit HARD FAIL.
#
# HARD FAIL cases:
#   1. Zero rows returned — the WHERE condition evaluated to false (or no table rows
#      matched).  Error message: "SQL-CHECK returned no rows — condition false".
#   2. The first column value is falsy (NULL, 0, empty string).
#   3. The query raises an exception.
#
# PASS: exactly one or more rows are returned AND the first column value is truthy.
#
# Discouraged (but still handled) form:
#   SQL-CHECK: SELECT COUNT(*) FROM t WHERE cond
#
# COUNT(*) always returns one row, so "zero rows = fail" cannot fire.  A COUNT
# of zero (falsy) still fails via case 2, but a COUNT of 1 passes even when only
# a single incidentally-matching row exists — this masks bulk/threshold errors.
# Prefer the SELECT 1 WHERE form so false conditions yield zero rows.


def _run_one_sql_check(expr: str, db_path: Path) -> dict[str, Any]:
    """Execute a single SQL-CHECK expression.  Returns {kind, expr, passed, result, error}.

    Zero rows returned is an explicit HARD FAIL — it means the WHERE condition
    evaluated to false.  Use ``SELECT 1 WHERE <condition>`` so that a false
    condition yields zero rows = fail.  ``COUNT(*)`` forms always return one row
    and cannot trigger the zero-row fail path; they are discouraged.
    """
    import sqlite3 as _sqlite3

    check: dict[str, Any] = {
        "kind": "SQL-CHECK",
        "expr": expr,
        "passed": False,
        "result": None,
        "error": None,
    }
    try:
        conn = _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute(expr).fetchone()
            if row is None:
                # HARD FAIL: zero rows — condition evaluated to false.
                check["error"] = "SQL-CHECK returned no rows — condition false"
            else:
                val = row[0]
                check["result"] = val
                check["passed"] = bool(val)
        finally:
            conn.close()
    except Exception as exc:
        check["error"] = str(exc)
    return check


def _run_one_test_check(expr: str) -> dict[str, Any]:
    """Run a TEST-CHECK by executing the given pytest node-id in a subprocess.

    Uses ``sys.executable`` so it always resolves to the current interpreter — no
    ``shell=True``, Windows-safe.  The node-id may optionally be prefixed with
    ``tests/`` or another path; it is passed verbatim to pytest.

    Returns {kind, expr, passed, result, error}.
    """
    check: dict[str, Any] = {
        "kind": "TEST-CHECK",
        "expr": expr,
        "passed": False,
        "result": None,
        "error": None,
    }
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", expr, "-q", "--tb=short", "--no-header"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TEST_CHECK_TIMEOUT,
        )
        stdout = (result.stdout or "") + (result.stderr or "")
        check["result"] = stdout[:2000]
        check["passed"] = result.returncode == 0
        if result.returncode != 0:
            check["error"] = f"pytest exited with code {result.returncode}"
    except subprocess.TimeoutExpired:
        check["error"] = f"TEST-CHECK timed out after {_TEST_CHECK_TIMEOUT}s"
    except Exception as exc:
        check["error"] = str(exc)
    return check


def _run_one_api_check(expr: str) -> dict[str, Any]:
    """Run an API-CHECK by booting the FastAPI app via TestClient and issuing the request.

    Syntax: ``METHOD path -> expectation``  (expectation is optional)
    Examples::

        GET /api/health -> 200
        GET /api/health

    The check passes if:
    - The import of ``projections.api.main.app`` succeeds (fail-closed otherwise).
    - The HTTP status is 2xx, OR equals the explicitly stated expected status.
    - The response body is non-empty.

    Returns {kind, expr, passed, result, error}.
    """
    check: dict[str, Any] = {
        "kind": "API-CHECK",
        "expr": expr,
        "passed": False,
        "result": None,
        "error": None,
    }

    # Parse the expression: "METHOD path [-> expected_status]"
    import re as _re

    m = _re.match(r"^(\w+)\s+(\S+)(?:\s*->\s*(\S+))?$", expr.strip())
    if not m:
        check["error"] = f"API-CHECK: unparseable expression: {expr!r}"
        return check

    method = m.group(1).upper()
    path = m.group(2)
    expectation = m.group(3)  # may be None

    # Determine expected status code.
    expected_status: int | None = None
    if expectation is not None:
        try:
            expected_status = int(expectation)
        except ValueError:
            check["error"] = f"API-CHECK: non-integer expectation {expectation!r}"
            return check

    # Import the app — fail-closed if unavailable.
    try:
        from projections.api.main import app as _api_app  # type: ignore[import]
        from fastapi.testclient import TestClient as _TC
    except Exception as exc:
        check["error"] = f"API-CHECK: could not import projections.api.main — {exc}"
        return check

    try:
        client = _TC(_api_app, raise_server_exceptions=False)
        method_fn = getattr(client, method.lower(), None)
        if method_fn is None:
            check["error"] = f"API-CHECK: unsupported HTTP method {method!r}"
            return check
        resp = method_fn(path)
        body = resp.text or ""
        check["result"] = {"status_code": resp.status_code, "body_preview": body[:500]}

        if expected_status is not None:
            status_ok = resp.status_code == expected_status
        else:
            status_ok = 200 <= resp.status_code < 300

        body_ok = bool(body.strip())
        check["passed"] = status_ok and body_ok
        if not status_ok:
            check["error"] = (
                f"API-CHECK: expected status {expected_status or '2xx'}, got {resp.status_code}"
            )
        elif not body_ok:
            check["error"] = "API-CHECK: response body was empty"
    except Exception as exc:
        check["error"] = f"API-CHECK: request failed — {exc}"

    return check


def _emit_validation_result_event(check: dict[str, Any]) -> None:
    """WO-VALIDATION-CAPTURE: emit one validation.result_recorded canonical event
    to the spool for an executable check outcome, so the validations dashboard
    component (WO-DASH-DUCKDB-PROJECTION read over events_fact
    validation.result_recorded) finally has a source.

    Best-effort and non-fatal — a telemetry failure must never break a check run
    or a work-order close. payload carries validation_type + status/outcome_status
    (events_fact derives status from $.status and outcome from $.outcome_status;
    the validations rollup reads $.validation_type). Distinct from
    event.validation.failed (schema-rejected events — ingestion health).
    """
    try:
        from canonical.events.envelope import CanonicalEventEnvelope
        import emitters.shared.spool_writer as _sw

        status = "passed" if check.get("passed") else "failed"
        summary = check.get("error") or (str(check.get("result") or "")[:500]) or None
        _sw.write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type="validation.result_recorded",
                    session_id=None,
                    payload={
                        "validation_type": check.get("kind"),
                        "status": status,
                        "outcome_status": status,
                        "command": check.get("expr"),
                        "summary": summary,
                    },
                    project_id=None,
                    trace={"domain": "telemetry"},
                    confidence="exact",
                )
            ]
        )
    except Exception:
        pass


def run_executable_checks(
    tasks: list[dict[str, Any]],
    db_path: Path,
    source_root: Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Execute all executable checks (SQL-CHECK / TEST-CHECK / API-CHECK) across tasks.

    Iterates every task's ``acceptance_criteria`` field.  Lines that start with a
    recognised ``*-CHECK:`` prefix are dispatched to the appropriate runner.  Lines
    with an unrecognised ``*-CHECK:`` token (e.g. ``UNKNOWN-CHECK:``) are recorded as
    **failed** (fail-closed).  Lines without any ``*-CHECK:`` token are ignored.

    Returns a mapping of ``task_title -> list[{kind, expr, passed, result, error}]``.
    Only tasks that have at least one executable check line produce an entry.

    :param tasks: list of task dicts with ``title`` and ``acceptance_criteria`` keys.
    :param db_path: path to the authority SQLite DB (used by SQL-CHECK).
    :param source_root: repo root (reserved for future use; currently unused).
    """
    import re as _re

    results: dict[str, list[dict[str, Any]]] = {}

    for task in tasks:
        ac = task.get("acceptance_criteria", "") or ""
        checks: list[dict[str, Any]] = []

        for raw_line in ac.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # Detect any "*-CHECK:" token in this line.
            token_match = _re.match(r"^([A-Z][A-Z0-9_]*-CHECK):\s*(.*)", line, _re.IGNORECASE)
            if token_match is None:
                continue

            token = token_match.group(1).upper()
            expr = token_match.group(2).strip()

            if token == "SQL-CHECK":
                checks.append(_run_one_sql_check(expr, db_path))
            elif token == "TEST-CHECK":
                checks.append(_run_one_test_check(expr))
            elif token == "API-CHECK":
                checks.append(_run_one_api_check(expr))
            else:
                # Unknown *-CHECK token — fail-closed.
                checks.append(
                    {
                        "kind": token,
                        "expr": expr,
                        "passed": False,
                        "result": None,
                        "error": f"Unknown check kind: {token!r} — fail-closed",
                    }
                )

        if checks:
            results[task["title"]] = checks

    # WO-VALIDATION-CAPTURE: capture each check outcome as a validation.result_recorded
    # canonical event (best-effort) so the validations analytics have a real source.
    for task_checks in results.values():
        for check in task_checks:
            _emit_validation_result_event(check)

    return results
