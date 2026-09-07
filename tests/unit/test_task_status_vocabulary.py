"""The task-status vocabulary exists twice on purpose, so a test holds the copies together.

``runtime/lib/enforcement.py`` is a standalone hook library: it is loaded by path and imports
only the standard library, so it cannot import ``core.work_orders.task_status``. The constant
therefore MUST exist twice. A parity test is the correct instrument for that, and it is what
was missing -- the copies were free to drift and did.

What the drift cost, measured 2026-09-07: ``business_tasks.status`` holds ``complete`` (2,229
rows) and ``done`` (27 rows). ``mark_task_done`` counted remaining work with
``status NOT IN ('complete', 'cancelled')``, so a ``done`` task counted as still remaining --
ten work orders held one, all already closed, so nothing was blocked today, but the code that
feeds the ``tasks_done`` close gate was wrong for the next one. A separate diagnostic
hardcoded ``('done', 'completed')`` and reported EVERY work order as 0-done, because
``completed`` is not a value this column ever holds.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from core.work_orders.task_status import (
    TASK_ABANDONED_STATUSES,
    TASK_DONE_STATUSES,
    TASK_STATUSES,
    is_done,
    is_open,
    sql_placeholders,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _hook_lib():
    """The standalone hook library, loaded the way the hooks load it."""
    path = REPO_ROOT / "runtime" / "lib" / "enforcement.py"
    spec = importlib.util.spec_from_file_location("enforcement_vocab", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_hook_copy_agrees_with_the_definition():
    """The one assertion this file exists for."""
    hook = _hook_lib()
    assert set(hook.TASK_DONE_STATUSES) == set(TASK_DONE_STATUSES), (
        "runtime/lib/enforcement.py and core/work_orders/task_status.py disagree about what"
        " a finished task looks like. The hook library cannot import core (it is loaded by"
        " path with only stdlib available), so the copies are held together HERE. Update"
        " both."
    )


def test_the_hook_library_takes_no_module_level_repo_import():
    """The reason the duplication is allowed, stated accurately.

    An earlier version of this test asserted the hook library imports ONLY the standard
    library. That was wrong: it already imports ``core.event_store.event_writer`` lazily
    inside a ``try``, as an established best-effort pattern. The real constraint is
    narrower and is what actually forces the second copy -- the module must IMPORT CLEANLY
    where the repo is not importable at all (an installed adapter, a hook fired from
    another project's working directory), so it can carry no module-level repo import. A
    module-level constant cannot be populated from a lazy import without a hardcoded
    fallback, and that fallback would be the same second copy with less supervision.

    An exemption survives only as long as its justification does, so the justification is
    asserted rather than described.
    """
    import ast

    source = (REPO_ROOT / "runtime" / "lib" / "enforcement.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    repo_roots = ("core", "interfaces", "integrations", "projections", "canonical", "spool")
    offenders: list[str] = []
    for node in tree.body:  # module level only -- lazy in-function imports are the pattern
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in repo_roots:
            offenders.append(f"line {node.lineno}: from {node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in repo_roots:
                    offenders.append(f"line {node.lineno}: import {alias.name}")
    assert not offenders, (
        "the hook library gained a module-level repo import: "
        + "; ".join(offenders)
        + ". If it can now depend on the repo at import time, it should import"
        " core.work_orders.task_status instead of keeping its own copy of the vocabulary,"
        " and this parity test should be deleted along with the copy."
    )


def test_completed_is_not_in_the_vocabulary():
    """`completed` reads correctly, appears in OTHER tables, and is wrong here.

    It is the specific value that made a diagnostic report every work order 0-done. Pinning
    its absence is what stops it being 'fixed' back in by someone who finds it in
    scan_runs.status and assumes consistency.
    """
    assert "completed" not in TASK_DONE_STATUSES
    assert "completed" not in TASK_STATUSES
    assert not is_done("completed")


def test_both_stored_values_count_as_done():
    assert is_done("complete")
    assert is_done("done")


def test_an_unknown_status_counts_as_open_not_done():
    """The safe direction. Absorbing an unrecognised value into "done" is what lets a work
    order close over work nobody did."""
    assert is_open("some_status_added_later")
    assert not is_done("some_status_added_later")
    assert is_open(None)
    assert not is_done(None)


def test_abandoned_is_neither_done_nor_open():
    for status in TASK_ABANDONED_STATUSES:
        assert not is_done(status), f"{status} is not finished work"
        assert not is_open(status), f"{status} is not outstanding work"


def test_pending_is_open():
    assert is_open("pending")
    assert not is_done("pending")


def test_sql_placeholders_matches_the_tuple_length():
    assert sql_placeholders(TASK_DONE_STATUSES) == "?,?"
    assert sql_placeholders(("a", "b", "c")) == "?,?,?"
    assert sql_placeholders(()) == ""


def test_the_live_column_holds_nothing_the_vocabulary_omits(tmp_path):
    """Every status a fresh authority can produce must be one this module names.

    Asserted against a bootstrapped database rather than the operator's live one, so it is
    deterministic -- but the point is the same: a value the column can hold and this module
    does not name is a silent gap in every caller that switches on it.
    """
    import sqlite3

    from core.config.sqlite_bootstrap import bootstrap_database

    db_path = tmp_path / "studio.db"
    bootstrap_database(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        cols = {row[1]: row for row in conn.execute('PRAGMA table_info("business_tasks")')}
        assert "status" in cols, "business_tasks lost its status column"
        default = cols["status"][4]
        if default:
            assert default.strip("'\"") in TASK_STATUSES, (
                f"the schema defaults business_tasks.status to {default}, which the"
                " vocabulary does not name"
            )
    finally:
        conn.close()


def test_mark_task_done_no_longer_spells_the_vocabulary_inline():
    """The site the gate found, pinned so it cannot regress to a literal."""
    source = (REPO_ROOT / "core" / "work_orders" / "mutations.py").read_text(encoding="utf-8")
    assert "TASK_DONE_STATUSES" in source, "mutations.py stopped importing the vocabulary"
    assert "NOT IN ('complete', 'cancelled')" not in source, (
        "the inline literal is back. It omits 'done', which 27 stored tasks use, so a done"
        " task counts as still remaining in the number that feeds the tasks_done gate."
    )
