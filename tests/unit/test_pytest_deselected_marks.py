"""``-m "not <mark>"`` in addopts is the one marker expression the resolver evaluates.

The repo keeps ``install_check`` tests out of a default run with ``addopts = "... -m 'not
install_check'"``. It used to be a ``pytest_collection_modifyitems`` hook in ``tests/conftest.py``,
and the rule-enforcement gate refuses to answer under a conftest that can change collection, so
one hook made every claim in ``canonical/rules.yml`` unresolvable. The declarative spelling is
something the gate CAN read, but only if it then applies the mark to the node it is asked about:
a register entry that names an ``install_check`` test is not enforced by a default run, and a
resolver that says it is collected is a false accept.

Each case writes a small project, resolves nodes in it, and for the shapes that matter also
asks real ``pytest --collect-only`` the same question and compares.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from core.gates.pytest_collection_rules import CollectionConfigError, load_rules
from core.gates.pytest_node_resolver import NodeResolver

REPO_ROOT = Path(__file__).resolve().parents[2]

_INI = "[pytest]\naddopts = {addopts}\n"

_SOURCE = """\
import pytest


def real_engine(fn):
    return pytest.mark.install_check(fn)


def unrelated(fn):
    return pytest.mark.slow(fn)


class registry:
    install_check = staticmethod(lambda fn: fn)


def test_plain():
    pass


@pytest.mark.install_check
def test_decorated():
    pass


@pytest.mark.slow
def test_other_mark():
    pass


@pytest.mark.parametrize("x", [1, 2])
@pytest.mark.install_check
def test_decorated_under_parametrize(x):
    pass


@registry.install_check
def test_an_attribute_that_is_named_like_the_mark_but_is_not_one():
    pass


@real_engine
def test_through_a_helper():
    pass


@unrelated
def test_through_a_helper_that_applies_another_mark():
    pass


@pytest.mark.install_check
class TestMarkedClass:
    def test_inherits_the_class_mark(self):
        pass


class TestUnmarkedClass:
    def test_plain_method(self):
        pass

    @pytest.mark.install_check
    def test_marked_method(self):
        pass


class TestClassPytestmark:
    pytestmark = pytest.mark.install_check

    def test_inherits_the_class_pytestmark(self):
        pass
"""

_MODULE_MARKED = """\
import pytest

pytestmark = pytest.mark.install_check


def test_a():
    pass
"""

_MODULE_LIST = """\
import pytest

pytestmark = [pytest.mark.slow, pytest.mark.install_check]


def test_a():
    pass
"""

_CASES = {
    "test_plain": True,
    "test_decorated": False,
    "test_other_mark": True,
    "test_decorated_under_parametrize": False,
    "test_an_attribute_that_is_named_like_the_mark_but_is_not_one": True,
    "test_through_a_helper": False,
    "test_through_a_helper_that_applies_another_mark": True,
    "TestMarkedClass::test_inherits_the_class_mark": False,
    "TestUnmarkedClass::test_plain_method": True,
    "TestUnmarkedClass::test_marked_method": False,
    "TestClassPytestmark::test_inherits_the_class_pytestmark": False,
}

_DEFAULT = "-v -m 'not install_check'"


def _project(tmp_path: Path, addopts: str = _DEFAULT) -> Path:
    (tmp_path / "pytest.ini").write_text(_INI.format(addopts=addopts), encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_shapes.py").write_text(_SOURCE, encoding="utf-8")
    (tests / "test_module_marked.py").write_text(_MODULE_MARKED, encoding="utf-8")
    (tests / "test_module_list.py").write_text(_MODULE_LIST, encoding="utf-8")
    return tmp_path


def _collected_by_pytest(root: Path) -> set[str]:
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=-m 'not install_check'",
            "--rootdir",
            str(root),
            "-c",
            str(root / "pytest.ini"),
            "tests",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    return {
        line.split("[", 1)[0].strip()
        for line in done.stdout.splitlines()
        if "::" in line and not line.startswith((" ", "="))
    }


# --- reading the option ------------------------------------------------------------------


def test_a_not_mark_expression_is_read_as_the_mark_to_leave_out(tmp_path):
    (tmp_path / "pytest.ini").write_text(_INI.format(addopts=_DEFAULT), encoding="utf-8")
    assert load_rules(tmp_path).deselected_marks == ("install_check",)


def test_with_no_marker_expression_nothing_is_deselected(tmp_path):
    (tmp_path / "pytest.ini").write_text(_INI.format(addopts="-v"), encoding="utf-8")
    assert load_rules(tmp_path).deselected_marks == ()


def test_the_last_marker_expression_wins_as_it_does_in_pytest(tmp_path):
    (tmp_path / "pytest.ini").write_text(
        _INI.format(addopts="-m 'not first' -m 'not second'"), encoding="utf-8"
    )
    assert load_rules(tmp_path).deselected_marks == ("second",)


@pytest.mark.parametrize(
    "addopts",
    [
        "-m slow",
        "-m 'slow or fast'",
        "-m 'not slow and not fast'",
        "-m 'not (slow)'",
        "-m 'not slow or fast'",
        "-m 'not'",
        "-m ''",
        "-m",
        "-mnot_slow",
    ],
)
def test_every_other_marker_expression_is_still_a_configuration_error(tmp_path, addopts):
    (tmp_path / "pytest.ini").write_text(_INI.format(addopts=addopts), encoding="utf-8")
    with pytest.raises(CollectionConfigError):
        load_rules(tmp_path)


# --- applying it to a node ---------------------------------------------------------------


@pytest.mark.parametrize("node", sorted(_CASES))
def test_a_node_carrying_the_mark_is_not_collected_and_one_without_it_is(tmp_path, node):
    resolver = NodeResolver(_project(tmp_path))
    problem = resolver.resolve(f"tests/test_shapes.py::{node}")
    if _CASES[node]:
        assert problem is None, (node, problem)
    else:
        assert problem and "install_check" in problem and "-m 'not install_check'" in problem, (
            node,
            problem,
        )


@pytest.mark.parametrize("file", ["tests/test_module_marked.py", "tests/test_module_list.py"])
def test_a_module_level_pytestmark_deselects_every_test_in_the_module(tmp_path, file):
    problem = NodeResolver(_project(tmp_path)).resolve(f"{file}::test_a")
    assert problem and "install_check" in problem, (file, problem)


def test_without_the_addopts_expression_a_marked_node_is_collected(tmp_path):
    resolver = NodeResolver(_project(tmp_path, addopts="-v"))
    assert resolver.resolve("tests/test_shapes.py::test_decorated") is None
    assert resolver.resolve("tests/test_module_marked.py::test_a") is None


def test_a_node_that_does_not_exist_reports_that_not_a_mark(tmp_path):
    problem = NodeResolver(_project(tmp_path)).resolve("tests/test_shapes.py::test_nope")
    assert problem and "no `test_nope`" in problem, problem


def test_the_resolver_agrees_with_pytest_on_every_shape(tmp_path):
    root = _project(tmp_path)
    resolver = NodeResolver(root)
    collected = _collected_by_pytest(root)
    assert "tests/test_shapes.py::test_plain" in collected, collected

    def pytest_collects(file: str, node: str) -> bool:
        wanted = f"{file}::{node}"
        return wanted in collected or any(c.startswith(wanted + "::") for c in collected)

    for node in _CASES:
        assert (resolver.resolve(f"tests/test_shapes.py::{node}") is None) == pytest_collects(
            "tests/test_shapes.py", node
        ), node
    for file in ("tests/test_module_marked.py", "tests/test_module_list.py"):
        assert (resolver.resolve(f"{file}::test_a") is None) == pytest_collects(file, "test_a")


# --- the real repository -----------------------------------------------------------------


def test_the_repository_leaves_install_checks_out_through_addopts_and_not_a_hook():
    rules = NodeResolver(REPO_ROOT).rules
    assert rules.deselected_marks == ("install_check",)
    conftest = (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "def pytest_collection_modifyitems" not in conftest, (
        "a collection hook in tests/conftest.py makes every rule-enforcement claim "
        "unresolvable; say it in addopts"
    )


def test_a_real_engine_test_of_the_repository_resolves_as_deselected_and_its_neighbour_as_collected():
    resolver = NodeResolver(REPO_ROOT)
    marked = resolver.resolve("tests/unit/test_lane_sandbox.py::test_real_container_has_no_network")
    assert marked and "install_check" in marked, marked
    plain = resolver.resolve(
        "tests/unit/test_lane_sandbox.py::test_docker_unavailable_says_so_rather_than_raising"
    )
    assert plain is None, plain
