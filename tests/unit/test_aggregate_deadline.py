"""The aggregate-deadline detector the lane declared and nobody wrote.

`a-per-item-wait-with-no-aggregate-deadline` named
`py -m core.gates.aggregate_deadline`, which was a ModuleNotFoundError.

The shape it looks for is NESTING, and that shape came from a false positive.
The first cut -- a sleep in a loop, in a module defining a budget constant --
found `core/work_orders/artifacts.py:216`, which reading showed to be
`_LOCK_ATTEMPTS = 4` at 0.15s backoff: 0.90s worst case, in no outer loop.
Bounded, and not the finding. `test_a_bounded_retry_not_in_an_outer_loop_is_clean`
pins that case, because a gate that reports bounded retries is a gate whose
findings get ignored.

These run against synthetic trees. The detector currently reports zero across
921 files, and zero is the one result that proves nothing about a scanner unless
something shows it can still say yes.
"""

from __future__ import annotations

import textwrap

from core.gates import aggregate_deadline as gate


def _write(root, rel, body):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return root


def test_sleeping_loop_inside_a_loop_is_a_finding(tmp_path):
    """The defect: each item waits a bounded amount, and the total multiplies by
    a count the data decides."""
    _write(
        tmp_path,
        "core/w.py",
        """
        import time

        def drain(items):
            for item in items:
                for attempt in range(5):
                    if send(item):
                        break
                    time.sleep(0.5)
        """,
    )
    result = gate.run(tmp_path)
    assert result["status"] == "found"
    assert len(result["findings"]) == 1
    assert result["findings"][0]["file"] == "core/w.py"


def test_a_bounded_retry_not_in_an_outer_loop_is_clean(tmp_path):
    """The false positive that forced this detector's shape. A retry loop with a
    fixed attempt count and no outer loop has a bounded worst case -- 0.90s in
    the real instance. Reporting it would be noise."""
    _write(
        tmp_path,
        "core/w.py",
        """
        import time

        _LOCK_ATTEMPTS = 4

        def acquire():
            for attempt in range(_LOCK_ATTEMPTS):
                if try_lock():
                    return True
                time.sleep(0.15)
            return False
        """,
    )
    assert gate.run(tmp_path)["status"] == "clean"


def test_an_outer_loop_with_a_deadline_is_clean(tmp_path):
    """Something bounds the total, which is the whole question the lane asks."""
    _write(
        tmp_path,
        "core/w.py",
        """
        import time

        def drain(items, deadline):
            for item in items:
                if time.monotonic() > deadline:
                    break
                for attempt in range(5):
                    if send(item):
                        break
                    time.sleep(0.5)
        """,
    )
    assert gate.run(tmp_path)["status"] == "clean"


def test_an_inner_loop_with_its_own_budget_is_clean(tmp_path):
    _write(
        tmp_path,
        "core/w.py",
        """
        import time

        def drain(items):
            for item in items:
                budget = 2.0
                while budget > 0:
                    if send(item):
                        break
                    time.sleep(0.5)
                    budget -= 0.5
        """,
    )
    assert gate.run(tmp_path)["status"] == "clean"


def test_a_loop_without_a_sleep_is_not_this_lane(tmp_path):
    """Nested loops are ordinary. The defect is a nested loop that WAITS."""
    _write(
        tmp_path,
        "core/w.py",
        """
        def totals(rows):
            for row in rows:
                for cell in row:
                    accumulate(cell)
        """,
    )
    assert gate.run(tmp_path)["status"] == "clean"


def test_while_loops_count_too(tmp_path):
    """A while is a loop. Matching only `for` would leave the more common
    unbounded shape unwatched."""
    _write(
        tmp_path,
        "core/w.py",
        """
        import time

        def drain(queue):
            while queue:
                item = queue.pop()
                while not send(item):
                    time.sleep(0.5)
        """,
    )
    assert gate.run(tmp_path)["status"] == "found"


def test_a_declared_site_is_exempt(tmp_path):
    _write(
        tmp_path,
        "core/w.py",
        """
        import time

        def drain(items):
            # aggregate-deadline: items is capped at 3 by the caller's schema
            for item in items:
                for attempt in range(5):
                    time.sleep(0.5)
        """,
    )
    assert gate.run(tmp_path)["status"] == "clean"


def test_tests_are_out_of_scope(tmp_path):
    """A product file is included so the scan has something to look at -- a tree
    of only test files has no product files at all, which reports `unknown` and
    would pass this assertion for the wrong reason."""
    _write(tmp_path, "core/ok.py", "def f():\n    pass\n")
    _write(
        tmp_path,
        "tests/unit/test_x.py",
        """
        import time

        def test_retry(items):
            for item in items:
                for attempt in range(5):
                    time.sleep(0.5)
        """,
    )
    result = gate.run(tmp_path)
    assert result["status"] == "clean"
    assert result["files_scanned"] == 1, "the test file must not even be scanned"


def test_no_files_is_unknown_not_clean(tmp_path):
    """A scan with nothing to scan is not a clean scan."""
    result = gate.run(tmp_path)
    assert result["status"] == "unknown"
    assert result["status"] != "clean"


def test_unknown_exits_zero_but_does_not_print_ok(tmp_path, capsys):
    rc = gate.main(["--repo-root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "UNKNOWN" in out
    assert "OK" not in out


def test_finding_exits_nonzero(tmp_path):
    """The convener reads returncode: 0 is clean, so a detector that found
    something and exited 0 would have its finding discarded."""
    _write(
        tmp_path,
        "core/w.py",
        """
        import time

        def drain(items):
            for item in items:
                for attempt in range(5):
                    time.sleep(0.5)
        """,
    )
    assert gate.main(["--repo-root", str(tmp_path)]) == 1


def test_accepts_repo_root(tmp_path):
    _write(tmp_path, "core/w.py", "def f():\n    pass\n")
    assert gate.main(["--repo-root", str(tmp_path)]) == 0


def test_real_tree_scans_a_plausible_number_of_files():
    """Against the actual repository. The gate reports zero here, and zero is
    only meaningful if it looked at something -- a scan narrowed to nothing by a
    path bug would also report zero findings."""
    result = gate.run()
    assert result["status"] in {"clean", "found"}
    assert result["files_scanned"] > 500, result["files_scanned"]
