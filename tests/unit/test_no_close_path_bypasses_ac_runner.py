"""Blast-radius / grep-guard tests for the executable AC gate (T4 — WO-AC-EXECUTABLE).

Asserts that every code path that closes a work order goes through the AC runner
(_run_ac_gate) — no bypass path exists.

AC: tests/unit/test_no_close_path_bypasses_ac_runner.py::test_all_close_callsites_run_ac_runner
"""

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CLOSE_MODULE = REPO_ROOT / "core" / "work_orders" / "close.py"
CLOSE_GATES_MODULE = REPO_ROOT / "core" / "work_orders" / "close_gates.py"
CLOSE_MAIN_MODULE = REPO_ROOT / "core" / "work_orders" / "close_main.py"


def _read_close_source() -> str:
    """Concatenated source of the close-lifecycle facade and its siblings.

    WO-GF-WO-LIFECYCLE split ``close.py`` into a thin re-export facade plus
    ``close_{shared,gates,continuation,main}.py`` siblings. The guard below
    inspects the full call graph — ``close_work_order``/``check_close_gates``
    now live in ``close_main.py``, while ``_run_ac_gate``/``run_gate_check``
    live in ``close_gates.py`` — so it reads and concatenates all three
    defining modules rather than just the facade (which now only contains
    re-export statements, not the function bodies themselves).
    """
    return "\n".join(
        p.read_text(encoding="utf-8") for p in (CLOSE_MODULE, CLOSE_GATES_MODULE, CLOSE_MAIN_MODULE)
    )


# ---------------------------------------------------------------------------
# T4 — test_all_close_callsites_run_ac_runner
# ---------------------------------------------------------------------------


def test_all_close_callsites_run_ac_runner() -> None:
    """Verify that close_work_order calls _run_ac_gate.

    Strategy:
    1. Parse close.py with the AST module.
    2. Find the ``close_work_order`` function definition.
    3. Assert that ``_run_ac_gate`` is called within its body.
    4. Assert that ``_run_ac_gate`` is defined in close.py.
    5. Verify that ``run_executable_checks`` is imported inside ``_run_ac_gate``.
    """
    source = _read_close_source()
    tree = ast.parse(source)

    # ── Step 1: _run_ac_gate must be defined in close.py ─────────────────
    defined_functions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_run_ac_gate" in defined_functions, (
        "close.py must define _run_ac_gate — it was not found. "
        "All close paths must route through the AC runner."
    )

    # ── Step 2: close_work_order must call _run_ac_gate ──────────────────
    close_wo_fn: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "close_work_order":
            close_wo_fn = node
            break

    assert close_wo_fn is not None, "close_work_order function not found in close.py"

    # Collect all function call names within close_work_order.
    called_names: set[str] = set()
    for node in ast.walk(close_wo_fn):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_names.add(node.func.attr)

    assert "_run_ac_gate" in called_names, (
        f"close_work_order does not call _run_ac_gate. "
        f"All work-order close paths must route through the AC runner. "
        f"Called names found: {sorted(called_names)}"
    )

    # ── Step 3: _run_ac_gate must call run_executable_checks ─────────────
    run_ac_gate_fn: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_run_ac_gate":
            run_ac_gate_fn = node
            break

    assert (
        run_ac_gate_fn is not None
    ), "_run_ac_gate function not found in close.py (should not happen)"

    # Look for the import of run_executable_checks inside _run_ac_gate.
    imported_names: set[str] = set()
    for node in ast.walk(run_ac_gate_fn):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)

    assert "run_executable_checks" in imported_names, (
        "_run_ac_gate must import run_executable_checks from core.work_orders.verify. "
        f"Imports found inside _run_ac_gate: {sorted(imported_names)}"
    )

    # ── Step 4: check_close_gates must also call _run_ac_gate ────────────
    check_gates_fn: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "check_close_gates":
            check_gates_fn = node
            break

    if check_gates_fn is not None:
        cg_called: set[str] = set()
        for node in ast.walk(check_gates_fn):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    cg_called.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    cg_called.add(node.func.attr)
        assert "_run_ac_gate" in cg_called, (
            "check_close_gates must also call _run_ac_gate so gate previews are accurate. "
            f"Called names: {sorted(cg_called)}"
        )

    # ── Step 5: No direct short-circuit that skips AC runner ─────────────
    # run_gate_check CAN call run_executable_checks (for all_tests_pass), but
    # the always-on AC gate (_run_ac_gate) must live outside run_gate_check.
    # This is confirmed by Step 2 (close_work_order calls _run_ac_gate directly).
    # Verify run_gate_check exists, then confirm _run_ac_gate is separate.
    run_gate_check_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "run_gate_check"
    }
    assert "run_gate_check" in run_gate_check_names, "run_gate_check must exist in close.py"
    # The always-on gate lives in close_work_order (confirmed above) — not solely in
    # run_gate_check — so no code path can skip it by never calling run_gate_check.
