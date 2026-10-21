"""The resolver beside pytest's own collection, on throwaway trees.

`core/gates/pytest_node_resolver.py` decides from source whether pytest would collect a node
id, and `core/gates/pytest_collection_rules.py` whether a DIRECTORY run would reach its file.
Two ways to be wrong, both tested against pytest itself rather than against this author's idea
of pytest:

  * a false positive refuses a reference pytest collects (an inherited test, a BOM file, an
    imported test, an alias) and teaches people to ignore the gate;
  * a false negative accepts a reference pytest does not collect (a helper, a fixture, a class
    with `__init__`, a def later shadowed, a file under `--ignore`), which is a rule enforced by
    nothing -- the disease the gate exists to cure.

Each test builds a tree, runs `pytest --collect-only` in it, and requires the resolver to agree
on every candidate, in both directions. The candidates are in `tests/helpers/resolver_cases.py`;
a case added there that the two disagree on fails here.

These start a pytest process per tree (about fifteen seconds in all), so CI runs them and the
pre-push pin list does not. The pinned tests (`test_pytest_node_resolver.py`,
`test_pytest_collection_rules.py`, `test_rule_enforcement_gate.py`) assert the same behaviours on
the same trees by message, without a subprocess, and `test_rule_enforcement_gate.py` also runs
the real register against a directory run of `tests/unit` on every push.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.gates.pytest_node_resolver import NodeResolver
from tests.helpers.resolver_cases import (
    _CANDIDATES,
    _CASES,
    _CASES_ITEM3,
    _CASES_MORE,
    _HELPER,
    _ITEM3_CANDIDATES,
    _MORE_CANDIDATES,
    _PACKAGES,
    _POISONED,
    _SCENARIOS,
    _STAR_HELPER,
    _STAR_NOLIST,
    _SUFFIX_FILE,
)
from tests.helpers.resolver_cases import write_tree as _tree


def _collected(root: Path, target: str, config: Path) -> set[str]:
    """What pytest itself collects under `target`: node ids with parameters dropped."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",
            "--rootdir",
            str(root),
            "-c",
            str(config),
            target,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    nodes = {
        line.split("[", 1)[0].strip()
        for line in result.stdout.splitlines()
        if "::" in line and not line.startswith((" ", "="))
    }
    assert nodes, f"pytest collected nothing:\n{result.stdout}\n{result.stderr}"
    return nodes


def _would_pytest_collect(collected: set[str], file: str, candidate: str) -> bool:
    node = f"{file}::{candidate}"
    return node in collected or any(c.startswith(node + "::") for c in collected)


def test_the_resolver_agrees_with_pytest_collection_on_every_candidate(tmp_path):
    root = _tree(
        tmp_path,
        {
            "pytest.ini": "[pytest]\n",
            "tests/helper.py": _HELPER,
            "tests/test_cases.py": _CASES,
            "tests/test_more.py": _CASES_MORE,
            "tests/test_item3.py": _CASES_ITEM3,
            "tests/star_helper.py": _STAR_HELPER,
            "tests/star_nolist.py": _STAR_NOLIST,
            **{name: body for name, (body, _) in _POISONED.items()},
            **_PACKAGES,
            "tests/other_test.py": _SUFFIX_FILE,
            "tests/test_bom.py": b"\xef\xbb\xbfdef test_with_a_bom():\n    pass\n",
            "tests/test_latin.py": (
                b"# -*- coding: latin-1 -*-\n"
                b"def test_latin_one():\n    assert '\xe9' == '\xe9'\n"
            ),
        },
    )
    collected = _collected(root, "tests", root / "pytest.ini")
    resolver = NodeResolver(root)

    disagreements = []
    verdicts = []
    for file, candidates in (
        ("tests/test_cases.py", _CANDIDATES),
        ("tests/test_more.py", _MORE_CANDIDATES),
        ("tests/test_item3.py", _ITEM3_CANDIDATES),
        *((name, names) for name, (_, names) in _POISONED.items()),
        ("tests/pkgrel/test_ok_rel.py", ["test_in_rel"]),
        ("tests/pkgrel/sub/test_up.py", ["test_in_rel"]),
    ):
        for candidate in candidates:
            expected = _would_pytest_collect(collected, file, candidate)
            verdicts.append(expected)
            why = resolver.resolve(f"{file}::{candidate}")
            if (why is None) != expected:
                disagreements.append(
                    f"{file}::{candidate}: pytest {'collects' if expected else 'does not collect'}"
                    f" it, resolver says {why!r}"
                )
    for file, name in (
        ("test_bom.py", "test_with_a_bom"),
        ("test_latin.py", "test_latin_one"),
        ("other_test.py", "test_in_a_suffix_named_file"),
    ):
        why = resolver.resolve(f"tests/{file}::{name}")
        if why is not None:
            disagreements.append(f"{file}::{name}: pytest collects it, resolver says {why!r}")
    assert not disagreements, "\n".join(disagreements)

    # the check is only as strong as its spread: both outcomes must be well represented
    assert verdicts.count(True) >= 20 and verdicts.count(False) >= 20


def test_the_resolver_agrees_with_pytest_when_the_repo_configures_its_own_names(tmp_path):
    """The names are read from the repo's pytest config, not hardcoded."""
    root = _tree(
        tmp_path,
        {
            "pytest.ini": (
                "[pytest]\n"
                "python_files = spec_*.py\n"
                "python_classes = Spec\n"
                "python_functions = check_*\n"
            ),
            "tests/spec_a.py": """\
                def check_ok():
                    pass

                def test_default_name():
                    pass

                class SpecThing:
                    def check_in_class(self):
                        pass

                class TestDefaultName:
                    def check_in_class(self):
                        pass
                """,
            "tests/test_default_file.py": "def check_ok():\n    pass\n",
        },
    )
    collected = _collected(root, "tests/spec_a.py", root / "pytest.ini")
    resolver = NodeResolver(root)
    for candidate in (
        "check_ok",
        "test_default_name",
        "SpecThing::check_in_class",
        "TestDefaultName::check_in_class",
    ):
        expected = _would_pytest_collect(collected, "tests/spec_a.py", candidate)
        assert (resolver.resolve(f"tests/spec_a.py::{candidate}") is None) == expected, candidate
    # a file the config does not name is not collected from a directory run
    assert "python_files" in (resolver.resolve("tests/test_default_file.py::check_ok") or "")


def _bare_run_nodes(root: Path, config: str) -> set[str]:
    """What `pytest` with no arguments collects in `root`, under that tree's own config."""
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "--rootdir",
            str(root),
            "-c",
            str(root / config),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        env=env,
    )
    nodes = {
        line.split("[", 1)[0].strip()
        for line in result.stdout.splitlines()
        if "::" in line and not line.startswith((" ", "="))
    }
    assert nodes, f"pytest collected nothing:\n{result.stdout}\n{result.stderr}"
    assert "error" not in result.stdout.lower().split("warnings summary")[0], result.stdout
    return nodes


@pytest.mark.parametrize("scenario", sorted(_SCENARIOS))
def test_the_resolver_agrees_with_a_directory_run_on_what_is_left_out(tmp_path, scenario):
    """Both directions, on every file: a file the bare run collects must resolve, and a file
    it does not collect must not. The explicit-file collection the gate used to rely on
    collects all of these, which is exactly why it could not see them."""
    files, config = _SCENARIOS[scenario]
    root = _tree(tmp_path, files)
    collected = _bare_run_nodes(root, config)
    resolver = NodeResolver(root)

    disagreements = []
    verdicts = []
    for name in sorted(files):
        if not name.endswith(".py") or name.endswith("conftest.py"):
            continue
        for function in ("test_ok", "test_ok_two"):
            node = f"{name}::{function}"
            expected = node in collected
            verdicts.append(expected)
            why = resolver.resolve(node)
            if (why is None) != expected:
                disagreements.append(
                    f"{node}: a bare pytest run {'collects' if expected else 'does not collect'}"
                    f" it, resolver says {why!r}"
                )
    assert not disagreements, "\n".join(disagreements)
    # the check is only as strong as its spread: both outcomes must be present
    assert verdicts.count(True) >= 2 and verdicts.count(False) >= 2, verdicts
