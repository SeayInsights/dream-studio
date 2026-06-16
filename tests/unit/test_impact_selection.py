"""T1 (WO-BLAST-RADIUS-GATE): impact selection from changed files.

compute_impact_set() maps a set of changed files to the dependent pytest nodes
that must run before merge — a changed test runs itself, and a changed source
module pulls in every test file that imports/references it. It also surfaces the
impacted contract domains (reusing contract_registry.change_impact_report).

The pr-smoke matrix runs only a fixed subset, so stale tests and contract
violations slip through to the post-merge full suite (root cause: main went red
for 11 merges). This selector is the input to the merge-time blast-radius gate.
"""

from __future__ import annotations

from pathlib import Path

from core.gates.blast_radius import compute_impact_set


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_changed_file_selects_dependent_tests(tmp_path: Path) -> None:
    """A changed source module selects the test files that import it, and only those.

    - A test that imports the changed module is selected (dependent).
    - A test that imports an unrelated module is NOT selected.
    - A changed test file selects itself.
    """
    repo = tmp_path
    _write(repo / "core" / "foo" / "bar.py", "def do_thing():\n    return 1\n")
    _write(repo / "core" / "baz" / "qux.py", "def other():\n    return 2\n")

    # Dependent: imports the changed module core.foo.bar
    _write(
        repo / "tests" / "unit" / "test_bar_user.py",
        "from core.foo.bar import do_thing\n\n\ndef test_it():\n    assert do_thing() == 1\n",
    )
    # Unrelated: imports a different module
    _write(
        repo / "tests" / "unit" / "test_unrelated.py",
        "from core.baz.qux import other\n\n\ndef test_other():\n    assert other() == 2\n",
    )
    # A changed test file (runs itself)
    _write(
        repo / "tests" / "unit" / "test_self.py",
        "def test_self():\n    assert True\n",
    )

    result = compute_impact_set(
        ["core/foo/bar.py", "tests/unit/test_self.py"],
        repo_root=repo,
    )

    dependent = set(result["dependent_tests"])
    assert (
        "tests/unit/test_bar_user.py" in dependent
    ), f"test importing core.foo.bar must be selected; got {sorted(dependent)}"
    assert "tests/unit/test_self.py" in dependent, "a changed test file must select itself"
    assert (
        "tests/unit/test_unrelated.py" not in dependent
    ), "a test importing an unrelated module must NOT be selected"


def test_no_python_changes_selects_nothing(tmp_path: Path) -> None:
    """Changed files with no .py and no test impact yield an empty dependent set."""
    repo = tmp_path
    _write(repo / "docs" / "README.md", "# docs\n")
    result = compute_impact_set(["docs/README.md"], repo_root=repo)
    assert result["dependent_tests"] == []
