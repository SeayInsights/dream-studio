"""`core.gates.pytest_node_resolver` answers "would pytest collect this node id" from source.

The rule-enforcement gate relies on it to notice a rule that names a test which does not
exist. Two ways to be wrong, and both are tested against pytest itself rather than against
this author's idea of pytest:

  * a false positive refuses a reference pytest would collect (an inherited test, a BOM file,
    an imported test, an alias) and teaches people to ignore the gate;
  * a false negative accepts a reference pytest would not collect (a helper, a fixture, a
    class with `__init__`, a def later shadowed), which is a rule enforced by nothing -- the
    disease this resolver was written to cure, one level down.

`test_the_resolver_agrees_with_pytest_collection_*` builds a throwaway tree, asks pytest
what it collects there, and requires the resolver to agree on every candidate id. Any case
added below that the resolver and pytest disagree on fails that test.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from core.gates.pytest_node_resolver import NodeResolver

REPO_ROOT = Path(__file__).resolve().parents[2]


def _tree(root: Path, files: dict[str, str | bytes]) -> Path:
    for name, body in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            path.write_bytes(body)
        else:
            path.write_text(textwrap.dedent(body), encoding="utf-8")
    return root


def _why(root: Path, reference: str) -> str | None:
    return NodeResolver(root).resolve(reference)


# --------------------------------------------------------------------------
# The cases, written once and judged by pytest
# --------------------------------------------------------------------------

_HELPER = """\
def test_shared():
    pass


class TestBaseShared:
    def test_from_base(self):
        pass
"""

_CASES = """\
import sys
import unittest
from typing import TYPE_CHECKING

import helper
import pytest
from helper import TestBaseShared as AliasedBase
from helper import TestBaseShared, test_shared


def test_plain():
    pass


async def test_async():
    pass


@pytest.mark.parametrize("value", [1, 2])
@pytest.mark.slow
def test_decorated(value):
    pass


def helper_x():
    pass


def _test_x():
    pass


@pytest.fixture
def test_a_fixture():
    pass


@pytest.fixture(scope="module")
def test_a_scoped_fixture():
    pass


def test_orig():
    pass


test_alias = test_orig
helper_alias = test_orig


def test_shadowed_by_a_value():
    pass


test_shadowed_by_a_value = None


def test_deleted():
    pass


del test_deleted


def test_twice():
    pass


def test_twice():
    pass


def test_redefined_as_a_value_then_a_def():
    pass


test_redefined_as_a_value_then_a_def = 3


def test_redefined_as_a_value_then_a_def():
    pass


if False:

    def test_under_if_false():
        pass


if 0:

    def test_under_if_zero():
        pass


if TYPE_CHECKING:

    def test_under_type_checking():
        pass


if __name__ == "__main__":

    def test_under_main_guard():
        pass


if sys.platform == "plan9":

    def test_on_another_platform():
        pass

else:

    def test_on_this_platform():
        pass


while False:

    def test_under_while_false():
        pass


try:

    def test_in_try():
        pass

except Exception:
    pass
else:

    def test_in_try_else():
        pass

finally:

    def test_in_finally():
        pass


with open(__file__):

    def test_in_with():
        pass


for _index in range(1):

    def test_in_for():
        pass


class TestNormal:
    def test_a(self):
        pass

    def helper_b(self):
        pass

    class TestNested:
        def test_c(self):
            pass


class NotNamedForPytest:
    def test_in_the_wrong_class(self):
        pass


class TestWithInit:
    def __init__(self):
        pass

    def test_never(self):
        pass


class TestOptedOut:
    __test__ = False

    def test_never(self):
        pass


class TestBase:
    def test_inherited(self):
        pass


class TestChild(TestBase):
    def test_own(self):
        pass


class TestGrandchild(TestChild):
    pass


class TestSharedChild(TestBaseShared):
    pass


class TestViaAlias(AliasedBase):
    pass


class TestViaModule(helper.TestBaseShared):
    pass


class TestOverridden(TestBase):
    test_inherited = None


class TestInheritsInit(TestWithInit):
    pass


TestAliasedClass = TestBase


class TestUnit(unittest.TestCase):
    def test_u(self):
        pass

    def check_u(self):
        pass


class UnittestNamedAnything(unittest.TestCase):
    def test_n(self):
        pass


class TestMixed(TestBase, unittest.TestCase):
    def test_m(self):
        pass
"""

# A second module for the behaviours a mutation pass showed nothing pinned: base-class order,
# a `__new__` constructor, a class inside a unittest class, names rebound by tuple/list/starred
# targets, and a value assigned in an `except` handler that may never run.
_CASES_MORE = """\
import unittest


class TestOrderA:
    def test_x(self):
        pass


class TestOrderB:
    test_x = None


class TestFirstA(TestOrderA, TestOrderB):
    pass


class TestFirstB(TestOrderB, TestOrderA):
    pass


class TestWithNew:
    def __new__(cls):
        return object.__new__(cls)

    def test_never(self):
        pass


class TestInheritsNew(TestWithNew):
    pass


class TestUnitWithNested(unittest.TestCase):
    def test_u(self):
        pass

    class TestInner:
        def test_i(self):
            pass


def test_tuple_shadowed():
    pass


def test_list_shadowed():
    pass


def test_star_shadowed():
    pass


test_tuple_shadowed, _unused_a = 1, 2
[test_list_shadowed, _unused_b] = 1, 2
*test_star_shadowed, _unused_c = 1, 2


def test_kept_by_a_handler():
    pass


try:
    pass
except Exception:
    test_kept_by_a_handler = None
"""

_MORE_CANDIDATES = [
    "TestFirstA::test_x",
    "TestFirstB::test_x",
    "TestWithNew::test_never",
    "TestInheritsNew::test_never",
    "TestUnitWithNested::test_u",
    "TestUnitWithNested::TestInner::test_i",
    "test_tuple_shadowed",
    "test_list_shadowed",
    "test_star_shadowed",
    "test_kept_by_a_handler",
]

# a file the default `python_files` reaches only through its `*_test.py` half
_SUFFIX_FILE = "def test_in_a_suffix_named_file():\n    pass\n"

# Node ids to ask both pytest and the resolver about. Every one names something, or
# looks like it could.
_CANDIDATES = [
    "test_plain",
    "test_async",
    "test_decorated",
    "helper_x",
    "_test_x",
    "test_a_fixture",
    "test_a_scoped_fixture",
    "test_orig",
    "test_alias",
    "helper_alias",
    "test_shadowed_by_a_value",
    "test_deleted",
    "test_twice",
    "test_redefined_as_a_value_then_a_def",
    "test_under_if_false",
    "test_under_if_zero",
    "test_under_type_checking",
    "test_under_main_guard",
    "test_on_this_platform",
    "test_under_while_false",
    "test_in_try",
    "test_in_try_else",
    "test_in_finally",
    "test_in_with",
    "test_in_for",
    "test_shared",  # imported from helper.py: pytest collects it
    "test_missing",
    "TestNormal",
    "TestNormal::test_a",
    "TestNormal::helper_b",
    "TestNormal::TestNested",
    "TestNormal::TestNested::test_c",
    "TestNormal::test_c",
    "NotNamedForPytest::test_in_the_wrong_class",
    "TestWithInit::test_never",
    "TestOptedOut::test_never",
    "TestBase::test_inherited",
    "TestChild::test_inherited",
    "TestChild::test_own",
    "TestGrandchild::test_inherited",
    "TestGrandchild::test_own",
    "TestSharedChild::test_from_base",
    "TestViaAlias::test_from_base",
    "TestViaModule::test_from_base",
    "TestOverridden::test_inherited",
    "TestInheritsInit::test_never",
    "TestAliasedClass::test_inherited",
    "TestBaseShared::test_from_base",
    "TestUnit::test_u",
    "TestUnit::check_u",
    "UnittestNamedAnything::test_n",
    "TestMixed::test_m",
    "TestMixed::test_inherited",
]


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


# --------------------------------------------------------------------------
# The messages, and the cases pytest cannot be asked about
# --------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path):
    return _tree(
        tmp_path,
        {
            "pytest.ini": "[pytest]\n",
            "tests/helper.py": _HELPER,
            "tests/test_cases.py": _CASES,
        },
    )


@pytest.mark.parametrize(
    "candidate,fragment",
    [
        ("test_missing", "no `test_missing` defined in tests/test_cases.py"),
        ("helper_x", "does not match python_functions"),
        ("_test_x", "does not match python_functions"),
        ("test_a_fixture", "is a fixture"),
        ("test_a_scoped_fixture", "is a fixture"),
        ("test_shadowed_by_a_value", "is not a function or class"),
        ("test_deleted", "no `test_deleted` defined"),
        ("test_under_if_false", "no `test_under_if_false` defined"),
        ("test_under_if_zero", "no `test_under_if_zero` defined"),
        ("test_under_type_checking", "no `test_under_type_checking` defined"),
        ("test_under_main_guard", "no `test_under_main_guard` defined"),
        ("test_under_while_false", "no `test_under_while_false` defined"),
        ("NotNamedForPytest::test_in_the_wrong_class", "does not match python_classes"),
        ("TestWithInit::test_never", "defines __init__"),
        ("TestInheritsInit::test_never", "defines __init__"),
        ("TestOptedOut::test_never", "__test__ = False"),
        ("TestOverridden::test_inherited", "is not a function or class"),
        ("TestNormal::helper_b", "does not match python_functions"),
        ("TestNormal::test_c", "no `test_c` defined in TestNormal"),
        ("test_plain::inner", "is a function, not a class"),
        ("TestUnit::check_u", "does not start with `test`"),
    ],
)
def test_a_node_pytest_would_not_collect_is_refused_with_the_reason(repo, candidate, fragment):
    why = _why(repo, f"tests/test_cases.py::{candidate}")
    assert why is not None and fragment in why, why


@pytest.mark.parametrize(
    "candidate",
    [
        "test_plain",
        "test_alias",
        "test_twice",
        "test_redefined_as_a_value_then_a_def",
        "test_on_this_platform",
        "TestChild::test_inherited",
        "TestGrandchild::test_inherited",
        "TestSharedChild::test_from_base",
        "TestViaAlias::test_from_base",
        "TestViaModule::test_from_base",
        "TestAliasedClass::test_inherited",
        "test_shared",
        "TestUnit::test_u",
        "TestMixed::test_inherited",
        # a parametrised id resolves when the function does
        "test_decorated[1]",
        "test_decorated[a-b]",
        "test_decorated[x::y]",
        "TestNormal::test_a[1]",
    ],
)
def test_a_node_pytest_collects_resolves(repo, candidate):
    assert _why(repo, f"tests/test_cases.py::{candidate}") is None


# -- the last definition wins ------------------------------------------------


def test_the_last_definition_wins_as_it_does_at_import(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": """\
                def test_x():
                    pass
                test_x = None

                test_y = None
                def test_y():
                    pass

                class TestC:
                    def test_z(self):
                        pass
                    test_z = 1
                """,
        },
    )
    assert "not a function" in (_why(root, "test_a.py::test_x") or "")
    assert _why(root, "test_a.py::test_y") is None
    assert "not a function" in (_why(root, "test_a.py::TestC::test_z") or "")


# -- every arm of a try, an if and a with is a place a test can live ----------


@pytest.mark.parametrize(
    "arm",
    [
        "try:\n    def test_x(): pass\nexcept Exception:\n    pass\n",
        "try:\n    pass\nexcept Exception:\n    def test_x(): pass\n",
        "try:\n    pass\nexcept Exception:\n    pass\nelse:\n    def test_x(): pass\n",
        "try:\n    pass\nfinally:\n    def test_x(): pass\n",
        "import sys\nif sys.platform == 'plan9':\n    def test_x(): pass\n",
        "import sys\nif sys.platform == 'plan9':\n    pass\nelse:\n    def test_x(): pass\n",
        "with open(__file__):\n    def test_x(): pass\n",
        "for _ in [1]:\n    def test_x(): pass\n",
        "while 1 + 1:\n    def test_x(): pass\n    break\n",
        "if not False:\n    def test_x(): pass\n",
    ],
)
def test_a_def_reachable_through_a_branch_the_gate_cannot_decide_is_accepted(tmp_path, arm):
    root = _tree(tmp_path, {"test_a.py": arm})
    assert _why(root, "test_a.py::test_x") is None


def test_a_def_that_cannot_run_is_not_accepted_in_the_dead_arm_of_a_decidable_if(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": "if True:\n    pass\nelse:\n    def test_x(): pass\n"
            "if not True:\n    def test_y(): pass\n",
        },
    )
    assert "no `test_x`" in (_why(root, "test_a.py::test_x") or "")
    assert "no `test_y`" in (_why(root, "test_a.py::test_y") or "")


def test_a_value_assigned_in_an_undecidable_branch_does_not_erase_a_def(tmp_path):
    """Either outcome is possible; the gate must not decide against the author."""
    root = _tree(
        tmp_path,
        {
            "test_a.py": """\
                import sys
                def test_x():
                    pass
                if sys.platform == "plan9":
                    test_x = None
                """,
        },
    )
    assert _why(root, "test_a.py::test_x") is None


# -- a base class that cannot be read is a named failure, never an acceptance --


def test_a_missing_test_under_a_base_that_cannot_be_read_names_that_base(tmp_path):
    """A third-party base may supply the test. The gate cannot see it, and accepting on
    doubt is the fail-open this issue exists to remove, so it fails and says why."""
    root = _tree(
        tmp_path,
        {
            "test_a.py": """\
                from somewhere_else import Base

                class TestThing(Base):
                    def test_own(self):
                        pass
                """,
        },
    )
    assert _why(root, "test_a.py::TestThing::test_own") is None  # defined here: fine
    why = _why(root, "test_a.py::TestThing::test_inherited_from_outside") or ""
    assert "no `test_inherited_from_outside` defined in TestThing" in why
    assert "bases not searched" in why and "Base" in why and "somewhere_else" in why


def test_a_computed_base_is_named_as_unreadable(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": "class TestThing(make_base()):\n    pass\n",
        },
    )
    why = _why(root, "test_a.py::TestThing::test_x") or ""
    assert "make_base()" in why and "cannot be read statically" in why


def test_a_base_cycle_terminates(tmp_path):
    """Two files importing each other's class as a base. The refusal must come from the
    cycle being cut, not from the interpreter's recursion limit being hit and caught: that
    would pass on "something went wrong" with the guard deleted."""
    root = _tree(
        tmp_path,
        {
            "a.py": "from b import TestB\n\n\nclass TestA(TestB):\n    pass\n",
            "b.py": "from a import TestA\n\n\nclass TestB(TestA):\n    pass\n",
            "test_c.py": "from a import TestA\n\n\nclass TestX(TestA):\n    pass\n",
        },
    )
    why = _why(root, "test_c.py::TestX::test_y")
    assert why is not None and "no `test_y` defined in TestX" in why
    assert "too deeply nested" not in why


def test_a_base_that_is_not_a_class_is_named_as_unreadable(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": "Base = make()\n\n\nclass TestThing(Base):\n    def test_own(self):\n        pass\n"
        },
    )
    why = _why(root, "test_a.py::TestThing::test_missing") or ""
    assert "bases not searched" in why and "Base (not a class)" in why


def test_a_base_that_is_defined_nowhere_is_named_as_unreadable(tmp_path):
    root = _tree(
        tmp_path,
        {"test_a.py": "class TestThing(Missing):\n    def test_own(self):\n        pass\n"},
    )
    why = _why(root, "test_a.py::TestThing::test_missing") or ""
    assert "bases not searched" in why and "Missing (not defined in the file)" in why


@pytest.mark.parametrize("base", ["object", "Exception", "dict"])
def test_a_builtin_base_defines_no_tests_so_it_is_not_reported_as_unreadable(tmp_path, base):
    root = _tree(
        tmp_path,
        {"test_a.py": f"class TestThing({base}):\n    def test_own(self):\n        pass\n"},
    )
    why = _why(root, "test_a.py::TestThing::test_missing") or ""
    assert "no `test_missing` defined in TestThing" in why and "bases not searched" not in why


def test_a_value_assigned_in_an_except_handler_does_not_erase_a_def(tmp_path):
    """The handler may never run; the def is what pytest sees when the body succeeds."""
    root = _tree(
        tmp_path,
        {
            "test_a.py": """\
                def test_x():
                    pass


                try:
                    import sys
                except ImportError:
                    test_x = None
                """,
        },
    )
    assert _why(root, "test_a.py::test_x") is None


@pytest.mark.parametrize("name", ["test_a.py", "a_test.py"])
def test_the_default_python_files_include_both_naming_conventions(tmp_path, name):
    root = _tree(tmp_path, {name: "def test_x():\n    pass\n"})
    assert _why(root, f"{name}::test_x") is None


@pytest.mark.parametrize(
    "candidate,fragment",
    [
        ("TestWithNew::test_never", "defines __init__ or __new__"),
        ("TestInheritsNew::test_never", "defines __init__ or __new__"),
        ("TestUnitWithNested::TestInner::test_i", "nested in a unittest class"),
        ("TestFirstB::test_x", "is not a function or class"),
        ("test_tuple_shadowed", "is not a function or class"),
        ("test_list_shadowed", "is not a function or class"),
        ("test_star_shadowed", "is not a function or class"),
    ],
)
def test_more_nodes_pytest_does_not_collect_are_refused_with_the_reason(
    tmp_path, candidate, fragment
):
    root = _tree(tmp_path, {"tests/test_more.py": _CASES_MORE})
    why = _why(root, f"tests/test_more.py::{candidate}")
    assert why is not None and fragment in why, why


@pytest.mark.parametrize(
    "candidate",
    ["TestFirstA::test_x", "TestUnitWithNested::test_u", "test_kept_by_a_handler"],
)
def test_more_nodes_pytest_collects_resolve(tmp_path, candidate):
    root = _tree(tmp_path, {"tests/test_more.py": _CASES_MORE})
    assert _why(root, f"tests/test_more.py::{candidate}") is None


def test_an_import_chain_is_followed_across_files_and_packages(tmp_path):
    root = _tree(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/base.py": "class TestBase:\n    def test_deep(self):\n        pass\n",
            "pkg/reexport.py": "from .base import TestBase\n",
            "tests/__init__.py": "",
            "tests/test_a.py": (
                "from pkg.reexport import TestBase\n"
                "from pkg import base as base_module\n"
                "class TestOne(TestBase):\n    pass\n"
                "class TestTwo(base_module.TestBase):\n    pass\n"
                "from pkg.base import *\n"
            ),
        },
    )
    assert _why(root, "tests/test_a.py::TestOne::test_deep") is None
    assert _why(root, "tests/test_a.py::TestTwo::test_deep") is None


def test_a_test_imported_by_star_is_found(tmp_path):
    root = _tree(
        tmp_path,
        {
            "helper.py": "def test_shared():\n    pass\n",
            "test_a.py": "from helper import *\n",
        },
    )
    assert _why(root, "test_a.py::test_shared") is None


def test_an_import_that_leaves_the_repository_is_refused_with_its_module(tmp_path):
    root = _tree(tmp_path, {"test_a.py": "from elsewhere import test_x\n"})
    why = _why(root, "test_a.py::test_x") or ""
    assert "outside the repository" in why and "elsewhere" in why


def test_an_import_of_a_name_the_module_does_not_define_is_refused(tmp_path):
    root = _tree(
        tmp_path,
        {"helper.py": "x = 1\n", "test_a.py": "from helper import test_x\n"},
    )
    assert "does not define it" in (_why(root, "test_a.py::test_x") or "")


# -- the path --------------------------------------------------------------


def test_a_path_outside_the_repository_is_refused(tmp_path):
    inner = tmp_path / "repo"
    _tree(inner, {"test_a.py": "def test_x():\n    pass\n"})
    _tree(tmp_path, {"test_outside.py": "def test_x():\n    pass\n"})
    resolver = NodeResolver(inner)
    assert resolver.resolve("test_a.py::test_x") is None
    assert resolver.resolve("../test_outside.py::test_x") == "path escapes the repository"
    absolute = str((tmp_path / "test_outside.py").resolve())
    assert resolver.resolve(f"{absolute}::test_x") == "path escapes the repository"


def test_a_directory_named_like_a_test_file_is_not_a_file(tmp_path):
    (tmp_path / "test_dir.py").mkdir()
    assert _why(tmp_path, "test_dir.py::test_x") == "no such test file"


def test_a_missing_file_says_so(tmp_path):
    assert _why(tmp_path, "test_gone.py::test_x") == "no such test file"


def test_a_file_pytest_does_not_collect_by_name_is_refused(tmp_path):
    root = _tree(tmp_path, {"checks.py": "def test_x():\n    pass\n"})
    assert "python_files" in (_why(root, "checks.py::test_x") or "")


def test_a_node_into_a_non_python_file_is_refused(tmp_path):
    root = _tree(tmp_path, {"notes.md": "def test_x(): pass\n"})
    assert _why(root, "notes.md::test_x") == "node id into a non-python file"


@pytest.mark.parametrize("node", ["test_a.py::", "test_a.py::test_x::", "test_a.py::::test_x"])
def test_an_empty_segment_is_refused(tmp_path, node):
    root = _tree(tmp_path, {"test_a.py": "def test_x():\n    pass\n"})
    assert _why(root, node) == "empty segment in node id"


# -- source that cannot be analysed is a message, never a crash ---------------


def test_a_syntax_error_names_the_line(tmp_path):
    root = _tree(tmp_path, {"test_a.py": "def test_a(:\n    pass\n"})
    why = _why(root, "test_a.py::test_a") or ""
    assert "does not parse" in why and "line 1" in why


def test_source_with_a_null_byte_is_a_message_not_a_crash(tmp_path):
    root = _tree(tmp_path, {"test_a.py": b"def test_a():\n    pass\n\x00\n"})
    assert _why(root, "test_a.py::test_a") is not None


def test_undecodable_source_is_a_message_not_a_crash(tmp_path):
    root = _tree(tmp_path, {"test_a.py": b"# coding: utf-8\nx = '\xe9'\ndef test_a(): pass\n"})
    assert _why(root, "test_a.py::test_a") is not None


@pytest.mark.parametrize(
    "source",
    [
        "x = " + "-" * 100_000 + "1\n",
        "x = 1" + " +1" * 20_000 + "\n",
        "x = " + "[" * 5_000 + "]" * 5_000 + "\n",
    ],
    ids=["unary-minus", "chained-plus", "nested-brackets"],
)
def test_a_deeply_nested_file_fails_loudly_instead_of_raising(tmp_path, source):
    root = _tree(tmp_path, {"test_a.py": source + "def test_a():\n    pass\n"})
    why = _why(root, "test_a.py::test_a")
    assert why is not None and (
        "too deeply nested" in why or "does not parse" in why or "not readable" in why
    ), why


def test_deeply_nested_statements_after_a_clean_parse_fail_loudly(tmp_path, monkeypatch):
    """The parse can succeed and the walk of the tree still run out of stack."""
    from core.gates import pytest_node_resolver as module

    root = _tree(tmp_path, {"test_a.py": "def test_a():\n    pass\n"})
    resolver = NodeResolver(root)

    def boom(*args, **kwargs):
        raise RecursionError

    monkeypatch.setattr(module._Module, "scope", property(boom))
    assert resolver.resolve("test_a.py::test_a") == "file too deeply nested to analyse"


def test_a_utf8_bom_and_a_coding_cookie_are_read_as_the_interpreter_reads_them(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_bom.py": b"\xef\xbb\xbfdef test_a():\n    pass\n",
            "test_latin.py": b"# coding: latin-1\nx = '\xe9'\ndef test_a():\n    pass\n",
        },
    )
    assert _why(root, "test_bom.py::test_a") is None
    assert _why(root, "test_latin.py::test_a") is None


# -- never imports ----------------------------------------------------------


def test_resolving_never_imports_or_runs_the_test_module(tmp_path):
    marker = tmp_path / "ran.txt"
    root = _tree(
        tmp_path,
        {
            "test_side_effect.py": (
                f"open({str(marker)!r}, 'w').write('ran')\n"
                "raise RuntimeError('imported')\n"
                "def test_x():\n    pass\n"
            ),
        },
    )
    assert _why(root, "test_side_effect.py::test_x") is None
    assert not marker.exists()


def test_a_file_is_parsed_once_however_many_references_name_it(tmp_path, monkeypatch):
    import ast

    from core.gates import pytest_node_resolver as module

    root = _tree(tmp_path, {"test_a.py": "def test_a():\n    pass\n\ndef test_b():\n    pass\n"})
    calls = []
    real = ast.parse
    monkeypatch.setattr(module.ast, "parse", lambda *a, **k: calls.append(1) or real(*a, **k))
    resolver = NodeResolver(root)
    for _ in range(5):
        assert resolver.resolve("test_a.py::test_a") is None
        assert resolver.resolve("test_a.py::test_b") is None
    assert len(calls) == 1


# -- config discovery -------------------------------------------------------


@pytest.mark.parametrize(
    "name,body",
    [
        ("pytest.ini", "[pytest]\npython_functions = check_*\n"),
        (".pytest.ini", "[pytest]\npython_functions = check_*\n"),
        ("pyproject.toml", '[tool.pytest.ini_options]\npython_functions = ["check_*"]\n'),
        ("pyproject.toml", '[tool.pytest.ini_options]\npython_functions = "check_*"\n'),
        ("tox.ini", "[pytest]\npython_functions = check_*\n"),
        ("setup.cfg", "[tool:pytest]\npython_functions = check_*\n"),
    ],
)
def test_the_names_come_from_whichever_pytest_config_the_repo_has(tmp_path, name, body):
    root = _tree(
        tmp_path,
        {name: body, "test_a.py": "def check_x(): pass\ndef test_y(): pass\n"},
    )
    assert _why(root, "test_a.py::check_x") is None
    assert "python_functions" in (_why(root, "test_a.py::test_y") or "")


def test_the_defaults_apply_when_the_repo_configures_nothing(tmp_path):
    root = _tree(tmp_path, {"test_a.py": "def test_y(): pass\ndef check_x(): pass\n"})
    assert _why(root, "test_a.py::test_y") is None
    assert "python_functions" in (_why(root, "test_a.py::check_x") or "")


def test_the_real_repository_config_is_the_one_read():
    """pyproject.toml names no collection patterns today, so the defaults hold; if that
    changes, the resolver follows it and this test says what it saw."""
    config = NodeResolver(REPO_ROOT).config
    assert config["python_functions"] and config["python_classes"] and config["python_files"]


@pytest.mark.parametrize(
    "name,body",
    [
        ("pytest.ini", "[pytest\npython_functions = x\n"),
        ("pyproject.toml", "[tool.pytest.ini_options\n"),
        ("tox.ini", "[pytest\n"),
    ],
)
def test_a_pytest_config_that_cannot_be_read_is_an_error_not_a_fall_back_to_defaults(
    tmp_path, name, body
):
    """Judging names by defaults the repo does not use would accept or refuse the wrong
    tests, silently."""
    from core.gates.pytest_node_resolver import CollectionConfigError

    (tmp_path / name).write_text(body, encoding="utf-8")
    with pytest.raises(CollectionConfigError, match="cannot read pytest config"):
        NodeResolver(tmp_path)


def test_a_relative_import_that_climbs_out_of_the_tree_is_refused_not_a_crash(tmp_path):
    root = _tree(tmp_path, {"test_a.py": "from ........ import test_x\n"})
    assert _why(root, "test_a.py::test_x") is not None
