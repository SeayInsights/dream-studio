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


def test_a_data_file_no_test_names_selects_nothing(tmp_path: Path) -> None:
    """A changed data file selects the tests whose text names its path; when none does,
    the dependent set is empty. This used to assert that any non-.py change selected
    nothing at all, which is the rule that let the canonical/rules.yml edit in #784 reach
    zero of the two tests naming that file."""
    repo = tmp_path
    _write(repo / "docs" / "README.md", "# docs\n")
    result = compute_impact_set(["docs/README.md"], repo_root=repo)
    assert result["dependent_tests"] == []


def test_the_pre_push_regression_is_selected() -> None:
    """The measured miss: a change to core/gates/pre_push.py must select
    tests/unit/gates/test_pre_push_outcome_event.py, which imports it with
    `from core.gates import pre_push` -- a shape text matching cannot see (see
    test_a_from_pkg_import_mod_change_selects_its_importer below for the synthetic
    version). Run against the real repository because the miss was real: pr-smoke
    stayed green on all three platforms with this test broken.
    """
    from core.gates.blast_radius import REPO_ROOT

    result = compute_impact_set(["core/gates/pre_push.py"], repo_root=REPO_ROOT)
    assert "tests/unit/gates/test_pre_push_outcome_event.py" in result["dependent_tests"]


def test_a_from_pkg_import_mod_change_selects_its_importer(tmp_path: Path) -> None:
    """`from pkg import mod` splits the changed module's dotted path across two
    tokens -- `pkg` then `mod`, joined by the word `import` -- so the contiguous
    substring `pkg.mod` the text rule needs never appears in the importing test's
    source. Synthetic version of the real pre_push.py regression above.
    """
    repo = tmp_path
    _write(repo / "mypkg" / "__init__.py", "")
    _write(repo / "mypkg" / "sub.py", "def f():\n    return 1\n")
    _write(
        repo / "tests" / "unit" / "test_importer.py",
        "from mypkg import sub\n\n\ndef test_it():\n    assert sub.f() == 1\n",
    )
    result = compute_impact_set(["mypkg/sub.py"], repo_root=repo)
    assert "tests/unit/test_importer.py" in result["dependent_tests"]


def test_a_facade_reexport_selects_the_test_that_imports_the_package(tmp_path: Path) -> None:
    """A package `__init__.py` that does `from .impl import helper` re-exports a
    name without ever writing the wrapped module's dotted path: a test importing the
    package (`from pkgx import helper`) names neither `pkgx.impl` nor
    `pkgx.impl.helper`, so text matching finds nothing to select. This shape put
    main red twice before the import graph closed it -- the facade's own module
    imports the changed submodule (one hop) and the test imports the facade (a
    second hop), a transitive closure rather than a direct reference.
    """
    repo = tmp_path
    _write(repo / "pkgx" / "__init__.py", "from .impl import helper\n\n__all__ = ['helper']\n")
    _write(repo / "pkgx" / "impl.py", "def helper():\n    return 1\n")
    _write(
        repo / "tests" / "unit" / "test_facade_user.py",
        "from pkgx import helper\n\n\ndef test_it():\n    assert helper() == 1\n",
    )
    result = compute_impact_set(["pkgx/impl.py"], repo_root=repo)
    assert "tests/unit/test_facade_user.py" in result["dependent_tests"]


def test_a_relative_import_chain_is_followed_transitively(tmp_path: Path) -> None:
    """A sibling module reached only through a RELATIVE import (`from .leaf import
    value`), two hops from the test that exercises it: leaf <- wrapper (relative
    import) <- test (imports wrapper directly). The test's source never mentions
    `leaf` at all, so text matching selects nothing; the closure must cross the
    relative-import edge and then the ordinary one to reach it.
    """
    repo = tmp_path
    _write(repo / "core" / "pkgz" / "__init__.py", "")
    _write(repo / "core" / "pkgz" / "leaf.py", "def value():\n    return 1\n")
    _write(
        repo / "core" / "pkgz" / "wrapper.py",
        "from .leaf import value\n\n\ndef call():\n    return value()\n",
    )
    _write(
        repo / "tests" / "unit" / "test_wrapper.py",
        "from core.pkgz.wrapper import call\n\n\ndef test_it():\n    assert call() == 1\n",
    )
    result = compute_impact_set(["core/pkgz/leaf.py"], repo_root=repo)
    assert "tests/unit/test_wrapper.py" in result["dependent_tests"]


def test_a_changed_source_file_selects_tests_that_name_it_by_path(tmp_path):
    """A test that reads source as TEXT names the file, not the module.

    The guards that walk an AST, parse a workflow or check for drift all depend on a
    source file without importing it, and the only handle they have is its repo-relative
    path. Before this, editing the file they guard did not select them -- which is how a
    check ends up correct and wired to nothing.
    """
    root = tmp_path
    (root / "interfaces" / "cli").mkdir(parents=True)
    (root / "interfaces" / "cli" / "dispatch.py").write_text("x = 1\n", encoding="utf-8")
    (root / "tests" / "unit").mkdir(parents=True)
    # Names the file by path and imports nothing from it, exactly as a guard does.
    (root / "tests" / "unit" / "test_guard.py").write_text(
        'PATHS = ["interfaces/cli/dispatch.py"]\n\n\ndef test_g():\n    assert PATHS\n',
        encoding="utf-8",
    )

    result = compute_impact_set(["interfaces/cli/dispatch.py"], repo_root=root)
    assert "tests/unit/test_guard.py" in result["dependent_tests"]
