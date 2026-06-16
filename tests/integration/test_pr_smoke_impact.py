"""T3/T5 (WO-BLAST-RADIUS-GATE): the blast-radius gate blocks merge.

The gate (core.gates.blast_radius.evaluate) is wired into ci_gate.py and the
pr-smoke matrix so a nothing-left-hanging finding BLOCKS the PR instead of
slipping to the post-merge full suite. These tests exercise the gate's pass/fail
contract on isolated temp repos.
"""

from __future__ import annotations

from pathlib import Path

from core.gates.blast_radius import evaluate


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_pr_smoke_blocks_on_hanging_detector(tmp_path: Path) -> None:
    """A diff that leaves a duplicate table writer makes the gate status 'fail'."""
    repo = tmp_path
    _write(
        repo / "core" / "telemetry" / "execution_spine.py",
        'def record():\n    conn.execute("INSERT INTO token_usage_records (id) VALUES (1)")\n',
    )
    diff = (
        "diff --git a/core/projections/token_projection.py b/core/projections/token_projection.py\n"
        "--- a/core/projections/token_projection.py\n"
        "+++ b/core/projections/token_projection.py\n"
        "@@ -1,1 +1,2 @@\n"
        '+    conn.execute("INSERT INTO token_usage_records (id) VALUES (2)")\n'
    )

    report = evaluate(diff, ["core/projections/token_projection.py"], repo_root=repo)

    assert report["status"] == "fail", f"gate must block on a hanging finding; got {report}"
    assert report["blocking_finding_count"] >= 1
    assert any(f["detector"] == "unowned_table_write" for f in report["findings"])


def test_clean_change_passes(tmp_path: Path) -> None:
    """A diff with no hanging findings passes, and still reports its impact set."""
    repo = tmp_path
    _write(repo / "core" / "foo" / "bar.py", "def do_thing():\n    return 1\n")
    _write(
        repo / "tests" / "unit" / "test_bar.py",
        "from core.foo.bar import do_thing\n\n\ndef test_it():\n    assert do_thing() == 1\n",
    )
    diff = (
        "diff --git a/core/foo/bar.py b/core/foo/bar.py\n"
        "--- a/core/foo/bar.py\n"
        "+++ b/core/foo/bar.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-def do_thing():\n"
        "+def do_thing():  # touched\n"
    )

    report = evaluate(diff, ["core/foo/bar.py"], repo_root=repo)

    assert report["status"] == "pass", f"clean change must pass; got {report}"
    assert "tests/unit/test_bar.py" in report["impact_set"]["dependent_tests"]


def test_end_to_end(tmp_path: Path) -> None:
    """Full pipeline: a mixed change set yields the impact set AND the blocking verdict.

    One file change is clean (selects its dependent test); another removes a
    symbol a stale test still asserts. The gate must surface the dependent test
    in the impact set AND fail on the stale-test finding.
    """
    repo = tmp_path
    # Clean source change with a dependent test.
    _write(repo / "core" / "svc" / "calc.py", "def add(a, b):\n    return a + b\n")
    _write(
        repo / "tests" / "unit" / "test_calc.py",
        "from core.svc.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
    )
    # Stale test asserting a symbol the diff removes.
    _write(
        repo / "tests" / "unit" / "test_legacy_widget.py",
        "def test_widget():\n    assert 'legacy-widget-id' in render()\n",
    )

    diff = (
        "diff --git a/core/svc/calc.py b/core/svc/calc.py\n"
        "--- a/core/svc/calc.py\n"
        "+++ b/core/svc/calc.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-def add(a, b):\n"
        "+def add(a, b):  # touched\n"
        "diff --git a/projections/frontend/widget.html b/projections/frontend/widget.html\n"
        "--- a/projections/frontend/widget.html\n"
        "+++ b/projections/frontend/widget.html\n"
        "@@ -1,1 +1,1 @@\n"
        '-  <div id="legacy-widget-id">x</div>\n'
        "+  <div>x</div>\n"
    )

    report = evaluate(
        diff,
        ["core/svc/calc.py", "projections/frontend/widget.html"],
        repo_root=repo,
    )

    # Impact set surfaces the dependent test for the clean change.
    assert "tests/unit/test_calc.py" in report["impact_set"]["dependent_tests"]
    # And the gate blocks on the stale-test finding.
    assert report["status"] == "fail"
    assert any(
        f["detector"] == "stale_removed_symbol_test"
        and f["path"] == "tests/unit/test_legacy_widget.py"
        for f in report["findings"]
    ), f"stale-test finding missing; got {report['findings']}"
