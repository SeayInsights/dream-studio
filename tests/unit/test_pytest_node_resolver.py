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

from pathlib import Path

import pytest

from core.gates.pytest_node_resolver import NodeResolver
from tests.helpers.resolver_cases import (
    _CASES,
    _CASES_FOLLOWUP,
    _CASES_VERIFIER2,
    _CASES_ITEM3,
    _CASES_MORE,
    _HELPER,
    _IMPORT_FILES,
    _PACKAGES,
    _POISONED,
    _STAR_HELPER,
    _STAR_NOLIST,
)
from tests.helpers.resolver_cases import write_tree as _tree

REPO_ROOT = Path(__file__).resolve().parents[2]


def _why(root: Path, reference: str) -> str | None:
    return NodeResolver(root).resolve(reference)


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
    assert why is not None and "inheritance cycle" in why
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


def test_a_base_that_is_defined_nowhere_raises_at_import_and_is_named(tmp_path):
    root = _tree(
        tmp_path,
        {"test_a.py": "class TestThing(Missing):\n    def test_own(self):\n        pass\n"},
    )
    why = _why(root, "test_a.py::TestThing::test_own") or ""
    assert "`Missing`" in why and "NameError" in why and "collects nothing from the file" in why


def test_a_base_that_may_come_from_a_star_import_the_resolver_cannot_read_is_only_named(tmp_path):
    """An outside star import may supply any name, so a base missing after one is a doubt, not
    a proof, and it is reported as an unreadable base rather than a NameError."""
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "from elsewhere import *\n\n\nclass TestThing(Missing):\n"
                "    def test_own(self):\n        pass\n"
            ),
        },
    )
    assert _why(root, "test_a.py::TestThing::test_own") is None
    why = _why(root, "test_a.py::TestThing::test_missing") or ""
    assert "bases not searched" in why and "Missing (not defined in the file)" in why


def test_a_base_that_the_file_could_build_by_globals_is_only_named(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "globals()['Missing'] = object\n\n\nclass TestThing(Missing):\n"
                "    def test_own(self):\n        pass\n"
            ),
        },
    )
    assert _why(root, "test_a.py::TestThing::test_own") is None


def test_a_base_supplied_by_a_star_import_that_comes_after_the_class_is_a_name_error(tmp_path):
    root = _tree(
        tmp_path,
        {
            "helper.py": "class TestBaseShared:\n    def test_from_base(self):\n        pass\n",
            "test_a.py": (
                "class TestA(TestBaseShared):\n    def test_own(self):\n        pass\n\n\n"
                "from helper import *\n"
            ),
        },
    )
    why = _why(root, "test_a.py::TestA::test_own") or ""
    assert "NameError" in why and "TestBaseShared" in why


@pytest.mark.parametrize(
    "base", ["object", "len"]
)  # no tests in them, and no constructor of their own
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
                "import sys\nif sys.platform:\n    raise RuntimeError('imported')\n"
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


# --------------------------------------------------------------------------
# Follow-ups from the independent verifier of #913
# --------------------------------------------------------------------------


@pytest.fixture
def item3(tmp_path):
    return _tree(
        tmp_path,
        {
            "tests/test_item3.py": _CASES_ITEM3,
            "tests/star_helper.py": _STAR_HELPER,
            "tests/star_nolist.py": _STAR_NOLIST,
        },
    )


@pytest.mark.parametrize(
    "candidate,fragment",
    [
        ("TestDiaE::test_x", "is not a function or class"),
        ("TestDiaF::test_x", "is not a function or class"),
        ("TestEmptyOne", "holds no test pytest would collect"),
        ("TestOnlyHelpers", "holds no test pytest would collect"),
        ("TestOnlyFixture", "holds no test pytest would collect"),
        ("TestOnlyEmptyNested", "holds no test pytest would collect"),
        ("TestZero::test_a", "sets __test__ = 0"),
        ("TestNone::test_a", "sets __test__ = None"),
        ("TestExternalFalse::test_a", "sets __test__ = False"),
        ("TestChildFlag::test_p", "sets __test__ = False"),
        ("TestMethodFlag::test_m", "sets __test__ = False"),
        ("test_attr_false", "sets __test__ = False"),
        ("test_with_before", "is not a function or class"),
        ("test_for_before", "is not a function or class"),
        ("test_for_range", "is not a function or class"),
        ("test_under_debug", "no `test_under_debug` defined"),
        ("test_and", "no `test_and` defined"),
        ("test_hidden", "no `test_hidden` defined"),
        ("TestHiddenBase::test_hidden_base", "no `TestHiddenBase` defined"),
    ],
)
def test_nodes_the_verifier_found_accepted_are_refused_with_the_reason(item3, candidate, fragment):
    why = _why(item3, f"tests/test_item3.py::{candidate}")
    assert why is not None and fragment in why, why


@pytest.mark.parametrize(
    "candidate",
    [
        "TestDiaG::test_x",
        "TestDiaC::test_x",
        "TestOnlyInherited",
        "TestOnlyNested",
        "TestOnlyNested::TestNested",
        "TestOnlyNested::TestNested::test_n",
        "TestStr::test_a",
        "NotNamedButTrue::test_a",
        "NotNamedAssignedTrue::test_a",
        "TestChildBack::test_p",
        "TestMethodFlag::test_n",
        "helper_attr_true",
        "test_lambda",
        "test_with_after",
        "test_for_empty",
        "test_not_debug",
        "test_flagged",
        "test_or",
        "test_not",
        "test_exported",
        "TestExportedBase::test_in_base",
        "test_public",
        "test_skipped_by_a_marker",
        "TestSkippedClass::test_s",
    ],
)
def test_nodes_the_verifier_found_refused_resolve(item3, candidate):
    assert _why(item3, f"tests/test_item3.py::{candidate}") is None


@pytest.mark.parametrize("name", sorted(_POISONED))
def test_a_file_that_raises_on_import_refuses_every_reference_into_it(tmp_path, name):
    body, candidates = _POISONED[name]
    root = _tree(tmp_path, {name: body, "tests/helper.py": _HELPER, **_PACKAGES})
    for candidate in candidates:
        why = _why(root, f"{name}::{candidate}") or ""
        assert "collects nothing from" in why, (candidate, why)


def test_a_base_defined_later_in_the_file_is_named(tmp_path):
    body, _ = _POISONED["tests/test_late_base.py"]
    root = _tree(tmp_path, {"tests/test_late_base.py": body})
    why = _why(root, "tests/test_late_base.py::test_beside_the_cause") or ""
    assert "class `TestLateChild` (line 1) uses base `TestLateBase` before it is defined" in why
    assert "NameError" in why


def test_a_base_defined_earlier_or_by_a_star_import_is_not_late(tmp_path):
    root = _tree(
        tmp_path,
        {
            "helper.py": "class TestFromStar:\n    def test_h(self):\n        pass\n",
            "test_a.py": (
                "from helper import *\n\n\nclass TestChild(TestFromStar):\n    pass\n\n\n"
                "class TestEarly:\n    def test_e(self):\n        pass\n\n\n"
                "class TestLaterChild(TestEarly):\n    pass\n"
            ),
        },
    )
    assert _why(root, "test_a.py::TestChild::test_h") is None
    assert _why(root, "test_a.py::TestLaterChild::test_e") is None


def test_bases_with_no_consistent_mro_are_named(tmp_path):
    body, _ = _POISONED["tests/test_bad_mro.py"]
    root = _tree(tmp_path, {"tests/test_bad_mro.py": body})
    why = _why(root, "tests/test_bad_mro.py::test_beside_the_cause") or ""
    assert "TestBadC" in why and "no consistent method resolution order" in why
    assert "collects nothing from" in why


def test_a_diamond_is_linearised_the_way_python_does_it(tmp_path):
    """E(C, B) with B overriding A's test: C3 puts B before A, so the override wins."""
    root = _tree(
        tmp_path,
        {
            "test_a.py": """\
                class TestA:
                    def test_x(self): pass
                    def test_y(self): pass

                class TestB(TestA):
                    test_x = None

                class TestC(TestA):
                    def test_y(self): pass

                class TestE(TestC, TestB):
                    pass
                """,
        },
    )
    assert "is not a function or class" in (_why(root, "test_a.py::TestE::test_x") or "")
    assert _why(root, "test_a.py::TestE::test_y") is None


def test_an_unreadable_base_in_a_diamond_is_still_named(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "from elsewhere import Mixin\n\n\nclass TestA:\n    def test_x(self):\n        pass\n\n\n"
                "class TestB(Mixin, TestA):\n    pass\n"
            ),
        },
    )
    assert _why(root, "test_a.py::TestB::test_x") is None  # found beyond the opaque base
    why = _why(root, "test_a.py::TestB::test_missing") or ""
    assert "Mixin" in why and "bases not searched" in why


def test_star_import_binds_what_all_lists_and_names_an_all_it_cannot_read(tmp_path):
    root = _tree(
        tmp_path,
        {
            "listed.py": (
                "__all__ = ['test_a']\n__all__ += ['test_b']\n__all__.append('test_c')\n"
                "__all__.extend(['test_d'])\n\n"
                + "".join(f"def test_{c}(): pass\n" for c in "abcde")
            ),
            "opaque.py": "import listed\n__all__ = listed.__all__ + ['test_z']\ndef test_z(): pass\n",
            "test_a.py": "from listed import *\nfrom opaque import *\n",
        },
    )
    for name in "abcd":
        assert _why(root, f"test_a.py::test_{name}") is None, name
    assert "no `test_e` defined" in (_why(root, "test_a.py::test_e") or "")
    why = _why(root, "test_a.py::test_z") or ""
    assert "whose __all__ cannot be evaluated" in why and "opaque" in why


def test_a_star_import_does_not_bind_private_names(tmp_path):
    root = _tree(
        tmp_path,
        {
            "helper.py": "class _Hidden:\n    def test_h(self):\n        pass\n",
            "test_a.py": "from helper import *\n\n\nclass TestA(_Hidden):\n    pass\n",
        },
    )
    why = _why(root, "test_a.py::TestA::test_h") or ""
    assert "`_Hidden`" in why and "NameError" in why  # pytest: NameError, the star skipped it


def test_a_relative_import_in_a_directory_that_is_not_a_package_names_the_cause(tmp_path):
    body, _ = _POISONED["tests/test_relative.py"]
    root = _tree(tmp_path, {"tests/test_relative.py": body, "tests/helper.py": _HELPER})
    why = _why(root, "tests/test_relative.py::test_beside_the_cause") or ""
    assert "not a package" in why and "`.helper`" in why and "ImportError" in why


def test_a_relative_import_reached_through_a_chain_in_a_plain_directory_is_refused(tmp_path):
    root = _tree(
        tmp_path,
        {
            "plain/base.py": "from .other import TestOther\n",
            "plain/other.py": "class TestOther:\n    def test_o(self):\n        pass\n",
            "pkg/__init__.py": "",
            "pkg/test_a.py": (
                "from plain.base import TestOther\n\n\nclass TestA(TestOther):\n    pass\n"
            ),
        },
    )
    why = _why(root, "pkg/test_a.py::TestA::test_o") or ""
    assert "not a package" in why


def test_the_relative_imports_a_package_allows_resolve(tmp_path):
    root = _tree(tmp_path, {"tests/helper.py": _HELPER, **_PACKAGES})
    assert _why(root, "tests/pkgrel/test_ok_rel.py::test_in_rel") is None
    assert _why(root, "tests/pkgrel/sub/test_up.py::test_in_rel") is None


def test_a_module_that_skips_itself_at_import_collects_nothing_but_a_skip_marker_does(tmp_path):
    """The two skips differ in what pytest does with the items: a marker collects them and
    skips at run time; `pytest.skip(allow_module_level=True)` raises while importing, so no
    item exists. The first is a run-time outcome this resolver does not judge (documented);
    the second is an import-time fact, like a NameError."""
    root = _tree(
        tmp_path,
        {
            "test_skip_marker.py": (
                "import pytest\n\npytestmark = pytest.mark.skip\n\n\n" "def test_x():\n    pass\n"
            ),
            "test_skip_module.py": (
                "from pytest import skip\n\nskip('x', allow_module_level=True)\n\n\n"
                "def test_x():\n    pass\n"
            ),
            "test_skip_conditional.py": (
                "import sys\nimport pytest\n\nif sys.platform == 'plan9':\n"
                "    pytest.skip('x', allow_module_level=True)\n\n\ndef test_x():\n    pass\n"
            ),
        },
    )
    assert _why(root, "test_skip_marker.py::test_x") is None
    assert "skips the module at import" in (_why(root, "test_skip_module.py::test_x") or "")
    assert _why(root, "test_skip_conditional.py::test_x") is None


def test_module_constants_decide_an_if_only_while_they_are_certain(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": """\
                import sys

                DEBUG = False
                MAYBE = False
                if sys.platform == "plan9":
                    MAYBE = True

                if DEBUG:
                    def test_debug(): pass

                if MAYBE:
                    def test_maybe(): pass

                class TestA:
                    if DEBUG:
                        def test_in_class_debug(self): pass
                    def test_kept(self): pass
                """,
        },
    )
    assert "no `test_debug` defined" in (_why(root, "test_a.py::test_debug") or "")
    # a conditional rebind makes the constant uncertain: either arm may run, so accept
    assert _why(root, "test_a.py::test_maybe") is None
    assert "no `test_in_class_debug` defined" in (
        _why(root, "test_a.py::TestA::test_in_class_debug") or ""
    )
    assert _why(root, "test_a.py::TestA::test_kept") is None


def test_the_for_target_rebinds_only_when_the_loop_certainly_runs(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": """\
                def test_unknown(): pass
                for test_unknown in make():
                    pass

                def test_literal(): pass
                for test_literal in (1, 2):
                    pass

                def test_string(): pass
                for test_string in "ab":
                    pass

                def test_range_one(): pass
                for test_range_one in range(1):
                    pass

                def test_range_two_args(): pass
                for test_range_two_args in range(2, 5):
                    pass

                def test_range_zero(): pass
                for test_range_zero in range(0):
                    pass

                def test_range_empty_two(): pass
                for test_range_empty_two in range(5, 5):
                    pass

                def test_empty_string(): pass
                for test_empty_string in "":
                    pass

                def test_star(): pass
                for test_star in [*make()]:
                    pass

                def test_dict(): pass
                for test_dict in {"k": 1}:
                    pass

                def test_set(): pass
                for test_set in {1}:
                    pass

                def test_body_assign(): pass
                for _ in [1]:
                    test_body_assign = None
                """,
        },
    )
    for kept in ("test_unknown", "test_range_zero", "test_range_empty_two", "test_empty_string"):
        assert _why(root, f"test_a.py::{kept}") is None, kept
    for shadowed in (
        "test_literal",
        "test_string",
        "test_range_one",
        "test_range_two_args",
        "test_dict",
        "test_set",
        "test_body_assign",
    ):
        assert "not a function or class" in (_why(root, f"test_a.py::{shadowed}") or ""), shadowed
    assert _why(root, "test_a.py::test_star") is None  # a starred element may be empty


def test_boolean_conditions_on_constants_are_evaluated(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": """\
                import sys
                T = True
                F = False

                if F and sys.platform == "x":
                    def test_false_and_unknown(): pass
                if T or sys.platform == "x":
                    def test_true_or_unknown(): pass
                if T and sys.platform == "x":
                    def test_true_and_unknown(): pass
                if F or sys.platform == "x":
                    def test_false_or_unknown(): pass
                if T and T:
                    def test_all_true(): pass
                if F or F:
                    def test_all_false(): pass
                """,
        },
    )
    assert "no `test_false_and_unknown`" in (_why(root, "test_a.py::test_false_and_unknown") or "")
    assert _why(root, "test_a.py::test_true_or_unknown") is None
    assert _why(root, "test_a.py::test_true_and_unknown") is None
    assert _why(root, "test_a.py::test_false_or_unknown") is None
    assert _why(root, "test_a.py::test_all_true") is None
    assert "no `test_all_false`" in (_why(root, "test_a.py::test_all_false") or "")


_SAMPLE_FOR_PARAMS = (
    "def test_y():\n    pass\n\n\nclass TestA:\n    def test_x(self):\n        pass\n"
)


def test_a_parameter_id_may_only_close_the_last_segment(tmp_path):
    root = _tree(tmp_path, {"test_a.py": _SAMPLE_FOR_PARAMS})
    for bad in ("TestA[x]::test_x", "TestA[x]::test_x[1]", "TestA::test_x[1]::more"):
        why = _why(root, f"test_a.py::{bad}") or ""
        assert "can only close the last segment" in why, (bad, why)
    for good in ("test_y[1]", "test_y[a::b]", "TestA::test_x[1]", "TestA::test_x[a-b]"):
        assert _why(root, f"test_a.py::{good}") is None, good


def test_a_decorator_that_replaces_the_function_cannot_be_judged_and_is_taken_at_its_word(
    tmp_path,
):
    """Documented limit: `@deco` where deco returns None leaves `test_x = None` at import and
    pytest collects nothing, but that needs running `deco`. The resolver does not."""
    root = _tree(
        tmp_path,
        {
            "test_a.py": "def deco(f):\n    return None\n\n\n@deco\ndef test_x():\n    pass\n",
        },
    )
    assert _why(root, "test_a.py::test_x") is None


def test_a_def_in_a_try_whose_import_may_fail_is_accepted(tmp_path):
    """Documented limit: whether the import fails is a fact about the environment."""
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "try:\n    import not_installed_anywhere\n\n    def test_x():\n        pass\n"
                "except ImportError:\n    pass\n"
            ),
        },
    )
    assert _why(root, "test_a.py::test_x") is None


def test_a_falsy_module_flag_collects_nothing_and_a_truthy_one_does_not_matter(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_off.py": "__test__ = 0\n\n\ndef test_x():\n    pass\n",
            "test_on.py": "__test__ = 1\n\n\ndef test_x():\n    pass\n",
        },
    )
    assert "the module sets __test__ = 0" in (_why(root, "test_off.py::test_x") or "")
    assert _why(root, "test_on.py::test_x") is None


def test_a_conditional_flag_assignment_is_not_trusted_either_way(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "import sys\n\n\nclass TestA:\n    def test_x(self):\n        pass\n\n\n"
                "if sys.platform == 'plan9':\n    TestA.__test__ = False\n"
            ),
        },
    )
    assert _why(root, "test_a.py::TestA::test_x") is None


def test_collect_imported_tests_false_leaves_imported_names_out(tmp_path):
    files = {
        "helper.py": (
            "def test_shared():\n    pass\n\n\nclass TestShared:\n"
            "    def test_s(self):\n        pass\n"
        ),
        "test_a.py": (
            "from helper import TestShared, test_shared\n\n\ndef test_own():\n    pass\n\n\n"
            "test_alias = test_own\n"
        ),
    }
    root = _tree(tmp_path, {"pytest.ini": "[pytest]\n", **files})
    for name in ("test_shared", "TestShared::test_s", "test_own", "test_alias"):
        assert _why(root, f"test_a.py::{name}") is None, name
    other = tmp_path / "other"
    _tree(other, {"pytest.ini": "[pytest]\ncollect_imported_tests = false\n", **files})
    why = _why(other, "test_a.py::test_shared") or ""
    assert "imported from another module" in why and "collect_imported_tests" in why
    assert "collect_imported_tests" in (_why(other, "test_a.py::TestShared::test_s") or "")
    assert _why(other, "test_a.py::test_own") is None
    assert _why(other, "test_a.py::test_alias") is None


def test_collect_imported_tests_must_be_a_bool(tmp_path):
    from core.gates.pytest_node_resolver import CollectionConfigError

    (tmp_path / "pytest.ini").write_text("[pytest]\ncollect_imported_tests = maybe\n")
    with pytest.raises(CollectionConfigError, match="collect_imported_tests"):
        NodeResolver(tmp_path)


def test_a_nested_class_inherited_from_a_base_resolves(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "class TestBase:\n    class TestInner:\n        def test_i(self):\n"
                "            pass\n\n\nclass TestChild(TestBase):\n    pass\n"
            ),
        },
    )
    assert _why(root, "test_a.py::TestChild::TestInner::test_i") is None
    assert _why(root, "test_a.py::TestChild") is None


def test_a_class_nested_too_deeply_for_the_walk_is_not_a_test_holder(tmp_path):
    levels = 12
    body = "".join("    " * i + f"class TestL{i}:\n" for i in range(levels))
    body += "    " * levels + "x = 1\n"
    root = _tree(tmp_path, {"test_a.py": body})
    assert "holds no test" in (_why(root, "test_a.py::TestL0") or "")


def test_a_unittest_class_counts_its_test_methods_only(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "import unittest\n\n\nclass TestHas(unittest.TestCase):\n"
                "    def test_a(self):\n        pass\n\n\n"
                "class TestNone(unittest.TestCase):\n    def helper(self):\n        pass\n"
            ),
        },
    )
    assert _why(root, "test_a.py::TestHas") is None
    assert "holds no test" in (_why(root, "test_a.py::TestNone") or "")


def test_a_builtin_base_is_not_late_when_the_module_rebinds_its_name_afterwards(tmp_path):
    """`object` resolves to the builtin when the class is made; defining a name `object`
    further down does not make the earlier use a NameError."""
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "class TestA(object):\n    def test_a(self):\n        pass\n\n\nobject = None\n"
            ),
        },
    )
    assert _why(root, "test_a.py::TestA::test_a") is None


def test_a_base_from_a_star_import_is_not_late_when_the_module_redefines_it_below(tmp_path):
    root = _tree(
        tmp_path,
        {
            "helper.py": "class TestBase:\n    def test_h(self):\n        pass\n",
            "test_a.py": (
                "from helper import *\n\n\nclass TestChild(TestBase):\n    pass\n\n\n"
                "class TestBase:\n    def test_local(self):\n        pass\n"
            ),
        },
    )
    assert _why(root, "test_a.py::TestChild::test_h") is None


def test_only_pytest_skip_with_allow_module_level_skips_the_module(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": "configure(allow_module_level=True)\n\n\ndef test_x():\n    pass\n",
            "test_b.py": "import pytest\n\npytest.skip('x', allow_module_level=False)\n\n\ndef test_x():\n    pass\n",
        },
    )
    assert _why(root, "test_a.py::test_x") is None  # only a call to pytest's skip raises
    # without allow_module_level it raises too: pytest refuses a skip outside a test
    assert "always raises" in (_why(root, "test_b.py::test_x") or "")


def test_a_with_target_rebinds_a_def_that_came_before_it(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "def test_x():\n    pass\n\n\nwith open(__file__) as test_x:\n    pass\n\n\n"
                "def test_y():\n    pass\n\n\nwith open(__file__) as (test_y, other):\n    pass\n"
            ),
        },
    )
    assert "not a function or class" in (_why(root, "test_a.py::test_x") or "")
    assert "not a function or class" in (_why(root, "test_a.py::test_y") or "")


# --------------------------------------------------------------------------
# Follow-ups: what a verifier found the resolver still got wrong
# --------------------------------------------------------------------------


@pytest.fixture
def followup(tmp_path):
    return _tree(tmp_path, {"tests/test_followup.py": _CASES_FOLLOWUP, "tests/helper.py": _HELPER})


@pytest.mark.parametrize(
    "candidate,fragment",
    [
        ("TestDataclass::test_a", "`@dataclass` decorator"),
        ("TestDataclassNoInit::test_a", "`@dataclass` decorator"),
        ("TestDataclassFrozen::test_a", "`@dataclass` decorator"),
        ("TestDataclassChild::test_a", "`@dataclass` decorator"),
        ("TestDictBase::test_a", "base `dict`"),
        ("TestExceptionBase::test_a", "base `Exception`"),
        ("TestIntBase::test_a", "base `int`"),
        ("TestListBase::test_a", "base `list`"),
        ("TestStrBase::test_a", "base `str`"),
        ("TestTupleBase::test_a", "base `tuple`"),
        ("TestTypeBase::test_a", "base `type`"),
        ("TestEnum::test_a", "base `Enum`"),
        ("TestEnumDirect::test_a", "base `enum.IntEnum`"),
        ("TestNamedTuple::test_a", "base `NamedTuple`"),
        ("TestProtocol::test_a", "base `Protocol`"),
        ("TestProperty::test_prop", "is a property"),
        ("TestAbstract::test_concrete", "is abstract"),
        ("TestAbstractMeta::test_concrete", "is abstract"),
        ("TestAbstractChildStillAbstract::test_concrete", "is abstract"),
        ("test_under_not_true", "no `test_under_not_true` defined"),
        ("test_under_type_checking_alias", "no `test_under_type_checking_alias` defined"),
        ("test_under_type_checking_attribute", "no `test_under_type_checking_attribute`"),
        ("test_walrus_def", "is not a function or class"),
        ("test_in_empty_for", "no `test_in_empty_for` defined"),
        ("test_fixture_alias", "is a fixture"),
    ],
)
def test_the_follow_up_nodes_pytest_does_not_collect_are_refused(followup, candidate, fragment):
    why = _why(followup, f"tests/test_followup.py::{candidate}")
    assert why is not None and fragment in why, why
    if "base `" in fragment or "decorator" in fragment:
        assert "__init__ or __new__" in why


@pytest.mark.parametrize(
    "candidate",
    [
        "TestDataclassNoInitNoEq::test_a",
        "TestObjectBase::test_a",
        "TestGeneric::test_a",
        "TestSubscripted::test_a",
        "TestProperty::test_real",
        "TestAbstractChildOk::test_concrete",
        "TestAbstractChildOk::test_abstract",
        "TestAbcWithNothingAbstract::test_a",
        "test_under_not_false",
        "test_in_for_else",
        "test_alias_attr",
        "test_partial",
        "test_partial_attr",
        "TestClassAlias::test_from_outer",
    ],
)
def test_the_follow_up_nodes_pytest_collects_resolve(followup, candidate):
    assert _why(followup, f"tests/test_followup.py::{candidate}") is None


@pytest.mark.parametrize("name", sorted(_IMPORT_FILES))
def test_imports_that_work_or_may_work_are_not_refused(tmp_path, name):
    body, candidates = _IMPORT_FILES[name]
    root = _tree(tmp_path, {name: body, "tests/helper.py": _HELPER, **_PACKAGES})
    for candidate in candidates:
        assert _why(root, f"{name}::{candidate}") is None, candidate


@pytest.mark.parametrize(
    "body,fragment",
    [
        ("raise RuntimeError('x')\n", "always raises"),
        ("assert False\n", "assert"),
        ("assert 0, 'x'\n", "assert"),
        ("assert not True\n", "assert"),
        ("from pkgmiss.gone import x\n", "pkgmiss"),
        ("import pkgmiss.gone\n", "pkgmiss"),
        ("from helper import nothing_here\n", "nothing_here"),
        ("import broken_helper\n", "does not parse"),
    ],
)
def test_a_file_that_provably_raises_when_imported_says_what_raises(tmp_path, body, fragment):
    root = _tree(
        tmp_path,
        {
            "tests/test_a.py": body + "\n\ndef test_x():\n    pass\n",
            "tests/helper.py": _HELPER,
            **_PACKAGES,
        },
    )
    why = _why(root, "tests/test_a.py::test_x") or ""
    assert fragment in why and "collects nothing from the file" in why, why


@pytest.mark.parametrize(
    "files",
    [
        # inside a try, an if, a function or a class: it may never run
        {"test_a.py": "try:\n    raise RuntimeError\nexcept RuntimeError:\n    pass\n"},
        {"test_a.py": "import sys\nif sys.platform == 'x':\n    raise RuntimeError\n"},
        {"test_a.py": "def f():\n    raise RuntimeError\n"},
        {"test_a.py": "assert True\nassert 1 + 1 == 2\nimport sys\nassert sys\n"},
        # a namespace package may be completed by another path entry: not provable
        {"nspkg/mod.py": "x = 1\n", "test_a.py": "from nspkg.gone import y\n"},
        # a name a module may provide by a route a static read cannot see
        {
            "mod.py": "def __getattr__(name):\n    return 1\n",
            "test_a.py": "from mod import anything\n",
        },
        {"mod.py": "globals()['made'] = 1\n", "test_a.py": "from mod import made\n"},
        {"mod.py": "from elsewhere import *\n", "test_a.py": "from mod import anything\n"},
        {"mod.py": "x = 1\n", "test_a.py": "import mod\nfrom mod import x\n"},
        # a regular package with the submodule present
        {"pkg/__init__.py": "", "pkg/sub.py": "x = 1\n", "test_a.py": "from pkg.sub import x\n"},
        # a name that is itself a submodule
        {"pkg/__init__.py": "", "pkg/sub.py": "x = 1\n", "test_a.py": "from pkg import sub\n"},
        # a module that is not in the repository at all: stdlib, installed, or unknown
        {"test_a.py": "import json\nimport not_installed_anywhere_zzz\n"},
    ],
)
def test_an_import_that_cannot_be_proven_to_fail_is_not_refused(tmp_path, files):
    body = {**files}
    body["test_a.py"] = body["test_a.py"] + "\n\ndef test_x():\n    pass\n"
    root = _tree(tmp_path, body)
    assert _why(root, "test_a.py::test_x") is None


def test_the_wrong_spelling_of_a_decorator_alias_is_not_a_fixture(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "from pytest import fixture as fx\nfrom pytest import fixture\n"
                "import pytest as pt\n\n\n@fx\ndef test_aliased():\n    pass\n\n\n"
                "@fixture\ndef test_bare():\n    pass\n\n\n@pt.fixture(scope='module')\n"
                "def test_attr():\n    pass\n\n\n@other\ndef test_other():\n    pass\n"
            ),
        },
    )
    for name in ("test_aliased", "test_bare", "test_attr"):
        assert "is a fixture" in (_why(root, f"test_a.py::{name}") or ""), name
    assert _why(root, "test_a.py::test_other") is None


@pytest.mark.parametrize(
    "head",
    [
        "import typing\nif typing.TYPE_CHECKING:",
        "import typing as t\nif t.TYPE_CHECKING:",
        "from typing import TYPE_CHECKING as TC\nif TC:",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:",
        "from typing_extensions import TYPE_CHECKING as TC\nif TC:",
    ],
)
def test_type_checking_in_every_spelling_is_never_true_at_run_time(tmp_path, head):
    root = _tree(tmp_path, {"test_a.py": head + "\n    def test_x():\n        pass\n"})
    assert "no `test_x` defined" in (_why(root, "test_a.py::test_x") or "")


def test_a_del_inside_a_branch_that_may_not_run_does_not_erase_a_def(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "import sys\n\n\ndef test_x():\n    pass\n\n\ndef test_y():\n    pass\n\n\n"
                "if sys.platform == 'plan9':\n    del test_x\nif True:\n    del test_y\n"
            ),
        },
    )
    assert _why(root, "test_a.py::test_x") is None
    assert "no `test_y` defined" in (_why(root, "test_a.py::test_y") or "")


def test_import_a_dot_b_binds_a_and_reaches_b_through_it(tmp_path):
    root = _tree(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/base.py": "class TestBase:\n    def test_deep(self):\n        pass\n",
            "test_a.py": "import pkg.base\n\n\nclass TestA(pkg.base.TestBase):\n    pass\n",
        },
    )
    assert _why(root, "test_a.py::TestA::test_deep") is None


def test_a_while_loop_is_decided_by_its_condition_and_its_else_always_runs(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "while False:\n    def test_body_never():\n        pass\n"
                "else:\n    def test_else_always():\n        pass\n\n"
                "while True:\n    def test_body_may():\n        pass\n    break\n\n"
                "import sys\nwhile sys.platform == 'x':\n    def test_body_unknown():\n"
                "        pass\n"
            ),
        },
    )
    assert "no `test_body_never` defined" in (_why(root, "test_a.py::test_body_never") or "")
    assert _why(root, "test_a.py::test_else_always") is None
    assert _why(root, "test_a.py::test_body_may") is None
    assert _why(root, "test_a.py::test_body_unknown") is None


def test_an_assignment_in_the_body_of_a_try_is_not_conditional(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "def test_x():\n    pass\n\n\ntry:\n    test_x = None\nexcept Exception:\n    pass\n"
            ),
        },
    )
    assert "not a function or class" in (_why(root, "test_a.py::test_x") or "")


def test_a_dict_with_a_double_star_may_be_empty_so_a_for_over_it_may_not_run(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "def test_x():\n    pass\n\n\nfor test_x in {**make()}:\n    pass\n\n\n"
                "def test_y():\n    pass\n\n\nfor test_y in {'k': 1, **make()}:\n    pass\n"
            ),
        },
    )
    assert _why(root, "test_a.py::test_x") is None
    assert "not a function or class" in (_why(root, "test_a.py::test_y") or "")


@pytest.mark.parametrize(
    "option,pattern,name,expected",
    [
        ("python_functions", "check_?", "check_a", True),
        ("python_functions", "check_?", "check_ab", False),
        ("python_functions", "[xy]est_*", "yest_a", True),
        ("python_functions", "[xy]est_*", "zest_a", False),
        ("python_functions", "*_check", "a_check", True),
        ("python_functions", "*_check", "a_checks", False),
    ],
)
def test_question_mark_and_bracket_globs_in_name_patterns_are_globs(
    tmp_path, option, pattern, name, expected
):
    root = _tree(
        tmp_path,
        {
            "pytest.ini": f"[pytest]\n{option} = {pattern}\n",
            "test_a.py": f"def {name}():\n    pass\n",
        },
    )
    assert (_why(root, f"test_a.py::{name}") is None) is expected


def test_a_class_pattern_glob_matches_the_class_name(tmp_path):
    root = _tree(
        tmp_path,
        {
            "pytest.ini": "[pytest]\npython_classes = Spec?\n",
            "test_a.py": (
                "class SpecA:\n    def test_x(self):\n        pass\n\n\n"
                "class SpecAB:\n    def test_x(self):\n        pass\n"
            ),
        },
    )
    assert _why(root, "test_a.py::SpecA::test_x") is None
    assert "does not match python_classes" in (_why(root, "test_a.py::SpecAB::test_x") or "")


def test_a_function_assigned_in_a_class_body_is_a_method_pytest_collects(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "def helper_f(self):\n    pass\n\n\nclass TestA:\n    test_from_outer = helper_f\n"
                "    not_a_test = helper_f\n"
            ),
        },
    )
    assert _why(root, "test_a.py::TestA::test_from_outer") is None
    assert "does not match python_functions" in (_why(root, "test_a.py::TestA::not_a_test") or "")


def test_a_partial_of_something_that_is_not_a_function_is_not_a_function(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "from functools import partial\n\nVALUE = 3\ntest_p = partial(VALUE)\n"
                "test_q = partial()\ntest_r = partial(make)\n"
            ),
        },
    )
    for name in ("test_p", "test_q", "test_r"):
        assert "is not a function or class" in (_why(root, f"test_a.py::{name}") or ""), name


def test_a_module_attribute_alias_reaches_through_a_package_and_a_class(tmp_path):
    root = _tree(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/mod.py": "def test_f():\n    pass\n\n\nclass TestC:\n    def test_m(self):\n        pass\n",
            "test_a.py": (
                "import pkg.mod\nimport pkg.mod as m\n\ntest_one = pkg.mod.test_f\ntest_two = m.test_f\n"
                "TestAlias = m.TestC\ntest_missing = m.nothing_here\ntest_val = m.__name__\n"
            ),
        },
    )
    assert _why(root, "test_a.py::test_one") is None
    assert _why(root, "test_a.py::test_two") is None
    assert _why(root, "test_a.py::TestAlias::test_m") is None
    assert "does not define it" in (_why(root, "test_a.py::test_missing") or "")


def test_an_abstract_method_overridden_by_a_non_def_is_not_abstract(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "from abc import ABC, abstractmethod\n\n\nclass TestA(ABC):\n"
                "    @abstractmethod\n    def test_x(self):\n        pass\n\n"
                "    def test_y(self):\n        pass\n\n\nclass TestB(TestA):\n    test_x = None\n"
            ),
        },
    )
    assert "is abstract" in (_why(root, "test_a.py::TestA::test_y") or "")
    assert _why(root, "test_a.py::TestB::test_y") is None


@pytest.mark.parametrize("decorator", ["dataclass", "dataclasses.dataclass", "dc"])
def test_a_dataclass_is_found_through_its_import_alias(tmp_path, decorator):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "import dataclasses\nfrom dataclasses import dataclass\n"
                "from dataclasses import dataclass as dc\n\n\n"
                f"@{decorator}\nclass TestA:\n    def test_x(self):\n        pass\n"
            ),
        },
    )
    assert "`@dataclass` decorator" in (_why(root, "test_a.py::TestA::test_x") or "")


def test_a_builtin_that_adds_no_constructor_is_not_a_reason(tmp_path):
    """Only a base whose __init__ or __new__ is not object's brings one."""
    root = _tree(
        tmp_path,
        {"test_a.py": "class TestA(object):\n    def test_x(self):\n        pass\n"},
    )
    assert _why(root, "test_a.py::TestA::test_x") is None


def test_an_imported_stdlib_base_is_known_by_the_name_it_was_imported_under(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "from enum import Enum as E\nimport typing as t\nfrom abc import ABC as Base\n\n\n"
                "class TestA(E):\n    def test_x(self):\n        pass\n\n\n"
                "class TestB(t.Protocol):\n    def test_x(self):\n        pass\n\n\n"
                "class TestC(Base):\n    def test_x(self):\n        pass\n"
            ),
        },
    )
    assert "__init__ or __new__" in (_why(root, "test_a.py::TestA::test_x") or "")
    assert "__init__ or __new__" in (_why(root, "test_a.py::TestB::test_x") or "")
    assert _why(root, "test_a.py::TestC::test_x") is None


def test_a_subscripted_base_that_cannot_be_read_is_still_named(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "from elsewhere import Base\n\n\nclass TestA(Base[int]):\n"
                "    def test_x(self):\n        pass\n"
            ),
        },
    )
    why = _why(root, "test_a.py::TestA::test_missing") or ""
    assert "Base[int]" in why and "bases not searched" in why


def test_a_not_of_a_constant_is_a_constant(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "A = not True\nB = not False\nC = True and False\nD = make()\n\n"
                "if A:\n    def test_a(): pass\nif B:\n    def test_b(): pass\n"
                "if C:\n    def test_c(): pass\nif D:\n    def test_d(): pass\n"
            ),
        },
    )
    assert "no `test_a` defined" in (_why(root, "test_a.py::test_a") or "")
    assert _why(root, "test_a.py::test_b") is None
    assert "no `test_c` defined" in (_why(root, "test_a.py::test_c") or "")
    assert _why(root, "test_a.py::test_d") is None


def test_a_walrus_rebinds_for_certain_only_where_it_certainly_runs(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "def test_x():\n    pass\n\n\n(test_x := 3)\n\n\n"
                "def test_y():\n    pass\n\n\nimport sys\nsys.platform == 'x' and (test_y := 3)\n\n\n"
                "def test_z():\n    pass\n\n\nif (test_z := 3):\n    pass\n\n\n"
                "def test_w():\n    pass\n\n\nvalue = [(test_w := n) for n in (1, 2)]\n"
            ),
        },
    )
    assert "is not a function or class" in (_why(root, "test_a.py::test_x") or "")
    assert _why(root, "test_a.py::test_y") is None  # the right of an `and` may never run
    assert "is not a function or class" in (_why(root, "test_a.py::test_z") or "")
    assert _why(root, "test_a.py::test_w") is None  # a comprehension may not run


def test_a_for_over_a_literal_that_is_empty_never_runs_its_body(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "for _ in ():\n    def test_tuple(): pass\nfor _ in {}:\n    def test_dict(): pass\n"
                "for _ in '':\n    def test_str(): pass\nfor _ in range(0):\n    def test_range(): pass\n"
                "for _ in range(3, 3):\n    def test_range2(): pass\n"
                "for _ in [1]:\n    def test_one(): pass\nfor _ in make():\n    def test_unknown(): pass\n"
                "for _ in [*make()]:\n    def test_star(): pass\n"
            ),
        },
    )
    for gone in ("test_tuple", "test_dict", "test_str", "test_range", "test_range2"):
        assert f"no `{gone}` defined" in (_why(root, f"test_a.py::{gone}") or ""), gone
    for kept in ("test_one", "test_unknown", "test_star"):
        assert _why(root, f"test_a.py::{kept}") is None, kept


def test_a_list_with_one_plain_element_and_a_star_is_not_empty(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "def test_x():\n    pass\n\n\nfor test_x in [1, *make()]:\n    pass\n\n\n"
                "def test_y():\n    pass\n\n\nfor test_y in (*make(), 2):\n    pass\n"
            ),
        },
    )
    assert "not a function or class" in (_why(root, "test_a.py::test_x") or "")
    assert "not a function or class" in (_why(root, "test_a.py::test_y") or "")


def test_constants_combined_with_and_or_are_decided_the_way_python_decides_them(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "A = 0 or 3\nB = 3 and 0\nC = 0 or 0\nD = 2 and 5\nE = 1 or make()\n\n"
                "if A:\n    def test_a(): pass\nif B:\n    def test_b(): pass\n"
                "if C:\n    def test_c(): pass\nif D:\n    def test_d(): pass\n"
                "if E:\n    def test_e(): pass\n"
            ),
        },
    )
    assert _why(root, "test_a.py::test_a") is None
    assert "no `test_b` defined" in (_why(root, "test_a.py::test_b") or "")
    assert "no `test_c` defined" in (_why(root, "test_a.py::test_c") or "")
    assert _why(root, "test_a.py::test_d") is None
    assert _why(root, "test_a.py::test_e") is None  # E is not decided: make() may be called


def test_a_generic_base_adds_nothing_to_search(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "from typing import Generic, TypeVar\n\nT = TypeVar('T')\n\n\n"
                "class TestA(Generic[T]):\n    def test_x(self):\n        pass\n\n\n"
                "class TestB(Generic[T], object):\n    pass\n"
            ),
        },
    )
    why = _why(root, "test_a.py::TestA::test_missing") or ""
    assert "no `test_missing` defined in TestA" in why and "bases not searched" not in why


def test_an_abstract_method_makes_a_class_abstract_only_with_abc_in_play(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "from abc import abstractmethod\n\n\nclass TestA:\n    @abstractmethod\n"
                "    def test_x(self):\n        pass\n"
            ),
        },
    )
    assert _why(root, "test_a.py::TestA::test_x") is None


def test_a_namespace_directory_inside_a_regular_package_cannot_be_proven_missing(tmp_path):
    root = _tree(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/sub/other.py": "x = 1\n",
            "test_a.py": "from pkg.sub.gone import y\n\n\ndef test_x():\n    pass\n",
        },
    )
    assert _why(root, "test_a.py::test_x") is None


def test_a_relative_import_is_not_judged_as_an_absolute_one(tmp_path):
    """`from .present import f` means pkg/present.py, not the unrelated top-level package that
    happens to share the name."""
    root = _tree(
        tmp_path,
        {
            "present/__init__.py": "",
            "pkg/__init__.py": "",
            "pkg/present.py": "def f():\n    pass\n",
            "pkg/test_a.py": "from .present import f\n\n\ndef test_x():\n    pass\n",
        },
    )
    assert _why(root, "pkg/test_a.py::test_x") is None


# --------------------------------------------------------------------------
# Follow-ups: a bare file reference is judged for its content, not only its exclusion
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(_POISONED))
def test_a_bare_reference_to_a_file_that_cannot_be_imported_is_refused_like_a_node(tmp_path, name):
    """The same file with `::test_a` was refused and the bare path was accepted: file_problem
    asked only whether the file was excluded, never whether pytest would get anything from it."""
    body, candidates = _POISONED[name]
    root = _tree(tmp_path, {name: body, "tests/helper.py": _HELPER, **_PACKAGES})
    resolver = NodeResolver(root)
    assert resolver.file_problem(name) is not None, name
    assert resolver.resolve(f"{name}::{candidates[0]}") is not None, name


@pytest.mark.parametrize(
    "body,fragment",
    [
        ("", "holds no test"),
        ("x = 1\n", "holds no test"),
        ("__test__ = False\n\n\ndef test_a():\n    pass\n", "__test__ = False"),
        ("def test_a(:\n    pass\n", "does not parse"),
        ("import pytest\n\npytest.skip('x', allow_module_level=True)\n", "skips the module"),
        ("def helper():\n    pass\n", "holds no test"),
        ("class TestA:\n    value = 1\n", "holds no test"),
    ],
)
def test_a_bare_reference_to_a_file_with_nothing_to_collect_is_refused(tmp_path, body, fragment):
    root = _tree(tmp_path, {"test_a.py": body})
    why = NodeResolver(root).file_problem("test_a.py") or ""
    assert fragment in why, why


@pytest.mark.parametrize(
    "body",
    [
        "def test_a():\n    pass\n",
        "class TestA:\n    def test_a(self):\n        pass\n",
        "from helper import test_shared\n",
        "from helper import TestBaseShared\n",
    ],
)
def test_a_bare_reference_to_a_file_with_a_test_in_it_is_accepted(tmp_path, body):
    root = _tree(tmp_path, {"test_a.py": body, "helper.py": _HELPER})
    assert NodeResolver(root).file_problem("test_a.py") is None


def test_a_bare_reference_to_a_file_whose_only_test_is_imported_is_empty_when_imports_are_off(
    tmp_path,
):
    root = _tree(
        tmp_path,
        {
            "pytest.ini": "[pytest]\ncollect_imported_tests = false\n",
            "helper.py": _HELPER,
            "test_a.py": "from helper import test_shared\n",
        },
    )
    assert "holds no test" in (NodeResolver(root).file_problem("test_a.py") or "")


def test_the_first_of_two_files_with_one_name_is_collected_and_the_second_is_not(tmp_path):
    root = _tree(
        tmp_path,
        {
            "tests/a/test_dup.py": "def test_x():\n    pass\n",
            "tests/b/test_dup.py": "def test_x():\n    pass\n",
        },
    )
    assert _why(root, "tests/a/test_dup.py::test_x") is None
    why = _why(root, "tests/b/test_dup.py::test_x") or ""
    assert "import file mismatch" in why and "tests/a/test_dup.py" in why


def test_two_files_with_one_name_are_fine_when_either_directory_is_a_package(tmp_path):
    root = _tree(
        tmp_path,
        {
            "tests/a/__init__.py": "",
            "tests/a/test_dup.py": "def test_x():\n    pass\n",
            "tests/b/test_dup.py": "def test_x():\n    pass\n",
            "tests/c/__init__.py": "",
            "tests/c/test_other.py": "def test_x():\n    pass\n",
            "tests/d/test_other.py": "def test_x():\n    pass\n",
        },
    )
    # a/ is a package (module a.test_dup) and b/ is not (module test_dup): no clash. The same
    # for c/ and d/. Only two files that are BOTH top-level modules clash.
    for ref in (
        "tests/a/test_dup.py",
        "tests/b/test_dup.py",
        "tests/c/test_other.py",
        "tests/d/test_other.py",
    ):
        assert _why(root, f"{ref}::test_x") is None, ref


def test_a_duplicate_name_that_a_directory_run_never_collects_does_not_count(tmp_path):
    root = _tree(
        tmp_path,
        {
            "pytest.ini": "[pytest]\nnorecursedirs = skipme\n",
            "tests/a/test_dup.py": "def test_x():\n    pass\n",
            "tests/skipme/test_dup.py": "def test_x():\n    pass\n",
            "tests/z/test_dup.py": "def test_x():\n    pass\n",
        },
    )
    assert _why(root, "tests/a/test_dup.py::test_x") is None
    assert "import file mismatch" in (_why(root, "tests/z/test_dup.py::test_x") or "")
    assert "norecursedirs" in (_why(root, "tests/skipme/test_dup.py::test_x") or "")


def test_the_order_pytest_collects_in_decides_which_duplicate_survives(tmp_path):
    """Entries are scanned sorted by name, files and directories together."""
    root = _tree(
        tmp_path,
        {
            "tests/test_dup.py": "def test_x():\n    pass\n",
            "tests/sub/test_dup.py": "def test_x():\n    pass\n",
        },
    )
    # `sub` sorts before `test_dup.py`, so the file in it is imported first
    assert _why(root, "tests/sub/test_dup.py::test_x") is None
    assert "import file mismatch" in (_why(root, "tests/test_dup.py::test_x") or "")


@pytest.mark.parametrize(
    "body",
    [
        "import sys\nsys.exit(0)\n",
        "from sys import exit\nexit()\n",
        "exit()\n",
        "quit(1)\n",
        "import pytest as pt\npt.fail('x')\n",
        "from pytest import xfail\nxfail()\n",
        "from pytest import skip\nskip('x')\n",
        "1 // 0\n",
        "5 % 0\n",
        "1 / 0.0\n",
    ],
)
def test_a_top_level_statement_that_always_raises_poisons_the_file(tmp_path, body):
    root = _tree(tmp_path, {"test_a.py": body + "\n\ndef test_x():\n    pass\n"})
    why = _why(root, "test_a.py::test_x") or ""
    assert "always raises" in why or "skips the module" in why, why


@pytest.mark.parametrize(
    "body",
    [
        "import sys\nif sys.platform == 'x':\n    sys.exit(0)\n",
        "def f():\n    exit()\n",
        "import pytest\n\n\ndef f():\n    pytest.fail('x')\n",
        "x = 1 / 2\n",
        "import os\nos.exit_code = 0\n",
        "def exit():\n    return 1\n\n\nexit()\n",
        "True / True\n",
        "class Thing:\n    def skip(self):\n        pass\n\n\nThing().skip()\n",
    ],
)
def test_a_call_that_looks_like_one_that_raises_but_may_not_is_not_refused(tmp_path, body):
    root = _tree(tmp_path, {"test_a.py": body + "\n\ndef test_x():\n    pass\n"})
    assert _why(root, "test_a.py::test_x") is None


def test_a_name_augmented_after_it_is_defined_is_fine_and_before_it_is_not(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": "count = 0\ncount += 1\n\n\ndef test_x():\n    pass\n",
            "test_b.py": "late += 1\nlate = 0\n\n\ndef test_x():\n    pass\n",
            "test_c.py": "from helper import *\nfrom_star += 1\n\n\ndef test_x():\n    pass\n",
            "helper.py": "from_star = 0\n",
        },
    )
    assert _why(root, "test_a.py::test_x") is None
    assert "augments `late`" in (_why(root, "test_b.py::test_x") or "")
    assert _why(root, "test_c.py::test_x") is None  # a star import may have supplied it


def test_a_class_whose_body_raises_poisons_the_file(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "class TestA:\n    raise RuntimeError\n\n\ndef test_beside():\n    pass\n"
            ),
            "test_b.py": (
                "class TestA:\n    assert False, 'no'\n\n\ndef test_beside():\n    pass\n"
            ),
            "test_c.py": (
                "import pytest\n\n\nclass TestA:\n    pytest.fail('x')\n\n\n"
                "def test_beside():\n    pass\n"
            ),
            "test_d.py": ("class TestA:\n    assert True\n\n    def test_a(self):\n        pass\n"),
        },
    )
    for name in ("test_a", "test_b", "test_c"):
        why = _why(root, f"{name}.py::test_beside") or ""
        assert "always raises while" in why and "collects nothing from the file" in why, name
    assert _why(root, "test_d.py::TestA::test_a") is None


def test_a_helper_that_raises_or_cannot_import_poisons_every_file_that_imports_it(tmp_path):
    root = _tree(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/boom.py": "raise RuntimeError('x')\n",
            "pkg/fine.py": "x = 1\n",
            "pkg/chain.py": "from pkg import boom\n",
            "test_a.py": "import pkg.boom\n\n\ndef test_x():\n    pass\n",
            "test_b.py": "from pkg import chain\n\n\ndef test_x():\n    pass\n",
            "test_c.py": "from pkg.fine import x\n\n\ndef test_x():\n    pass\n",
            "test_d.py": "import pkg.fine\nimport pkg\n\n\ndef test_x():\n    pass\n",
        },
    )
    assert "fails to import" in (_why(root, "test_a.py::test_x") or "")
    why = _why(root, "test_b.py::test_x") or ""
    assert "pkg.chain" in why and "pkg.boom" in why  # two hops are followed
    assert _why(root, "test_c.py::test_x") is None
    assert _why(root, "test_d.py::test_x") is None


def test_a_package_init_that_raises_poisons_what_imports_below_it(tmp_path):
    root = _tree(
        tmp_path,
        {
            "pkg/__init__.py": "raise RuntimeError('x')\n",
            "pkg/mod.py": "x = 1\n",
            "test_a.py": "from pkg.mod import x\n\n\ndef test_x():\n    pass\n",
        },
    )
    assert "fails to import" in (_why(root, "test_a.py::test_x") or "")


def test_an_import_cycle_between_helpers_is_walked_once_and_not_called_a_failure(tmp_path):
    root = _tree(
        tmp_path,
        {
            "a.py": "import b\nvalue = 1\n",
            "b.py": "import a\n",
            "test_a.py": "import a\n\n\ndef test_x():\n    pass\n",
        },
    )
    assert _why(root, "test_a.py::test_x") is None


@pytest.mark.parametrize(
    "files,fragment",
    [
        (
            {
                "pkg/__init__.py": "",
                "pkg/lib.py": "x = 1\n",
                "pkg/test_a.py": "from .lib import nothere\n",
            },
            "nothere",
        ),
        ({"pkg/__init__.py": "", "pkg/test_a.py": "from . import nomod\n"}, "nomod"),
        ({"pkg/__init__.py": "", "pkg/test_a.py": "from .gone import x\n"}, "gone"),
        ({"pkg/__init__.py": "", "pkg/test_a.py": "from .gone.deeper import x\n"}, "gone"),
        (
            {
                "pkg/__init__.py": "",
                "pkg/lib.py": "x = 1\n",
                "pkg/sub/__init__.py": "",
                "pkg/sub/test_a.py": "from ..lib import nothere\n",
            },
            "nothere",
        ),
        (
            {
                "pkg/__init__.py": "",
                "pkg/sub/__init__.py": "",
                "pkg/sub/test_a.py": "from ..gone import x\n",
            },
            "gone",
        ),
        (
            {
                "pkg/__init__.py": "",
                "pkg/lib.py": "x = 1\n",
                "pkg/test_a.py": "from .lib.deeper import y\n",
            },
            "is a module, not a package",
        ),
    ],
)
def test_a_relative_import_of_something_the_package_lacks_poisons_the_file(
    tmp_path, files, fragment
):
    root = _tree(tmp_path, files)
    target = next(name for name in files if name.endswith("test_a.py"))
    body = (root / target).read_text(encoding="utf-8")
    (root / target).write_text(body + "\n\ndef test_x():\n    pass\n", encoding="utf-8")
    why = _why(root, f"{target}::test_x") or ""
    assert fragment in why and "collects nothing from the file" in why, why


@pytest.mark.parametrize(
    "files",
    [
        {"pkg/__init__.py": "", "pkg/lib.py": "x = 1\n", "pkg/test_a.py": "from .lib import x\n"},
        {"pkg/__init__.py": "", "pkg/lib.py": "", "pkg/test_a.py": "from . import lib\n"},
        {"pkg/__init__.py": "x = 1\n", "pkg/test_a.py": "from . import x\n"},
        {
            "pkg/__init__.py": "",
            "pkg/sub/__init__.py": "",
            "pkg/sub/m.py": "y = 1\n",
            "pkg/test_a.py": "from .sub.m import y\n",
        },
        {"pkg/__init__.py": "", "pkg/sub/m.py": "y = 1\n", "pkg/test_a.py": "from .sub import m\n"},
        {
            "pkg/__init__.py": "",
            "pkg/sub/__init__.py": "",
            "pkg/lib.py": "x = 1\n",
            "pkg/sub/test_a.py": "from ..lib import x\n",
        },
        {
            "pkg/__init__.py": "def __getattr__(n):\n    return 1\n",
            "pkg/test_a.py": "from . import anything\n",
        },
    ],
)
def test_a_relative_import_that_works_is_not_refused(tmp_path, files):
    root = _tree(tmp_path, files)
    target = next(name for name in files if name.endswith("test_a.py"))
    body = (root / target).read_text(encoding="utf-8")
    (root / target).write_text(body + "\n\ndef test_x():\n    pass\n", encoding="utf-8")
    assert _why(root, f"{target}::test_x") is None


def test_a_module_importing_itself_by_name_is_judged_by_what_it_defines(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_ok.py": "def test_a():\n    pass\n\n\nfrom test_ok import test_a\n",
            "test_bad.py": "from test_bad import nothere\n\n\ndef test_a():\n    pass\n",
            "test_dyn.py": "globals()['made'] = 1\nfrom test_dyn import made\n\n\ndef test_a():\n    pass\n",
        },
    )
    assert _why(root, "test_ok.py::test_a") is None
    assert "nothere" in (_why(root, "test_bad.py::test_a") or "")
    assert _why(root, "test_dyn.py::test_a") is None


def test_an_import_through_a_module_file_is_refused_only_when_a_name_follows_it(tmp_path):
    root = _tree(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/mod.py": "x = 1\n",
            "test_a.py": "import pkg.mod.deeper\n\n\ndef test_x():\n    pass\n",
            "test_b.py": "import pkg.mod\n\n\ndef test_x():\n    pass\n",
        },
    )
    assert "is a module, not a package" in (_why(root, "test_a.py::test_x") or "")
    assert _why(root, "test_b.py::test_x") is None


# --------------------------------------------------------------------------
# Follow-ups: standard-library bases, __eq__ without __hash__, and a few spellings
# --------------------------------------------------------------------------


@pytest.fixture
def verifier2(tmp_path):
    return _tree(tmp_path, {"tests/test_verifier2.py": _CASES_VERIFIER2})


@pytest.mark.parametrize(
    "candidate,fragment",
    [
        ("TestThread::test_a", "base `threading.Thread`"),
        ("TestStringIO::test_a", "base `io.StringIO`"),
        ("TestHandler::test_a", "base `logging.Handler`"),
        ("TestNamespace::test_a", "base `argparse.Namespace`"),
        ("TestPurePath::test_a", "base `pathlib.PurePath`"),
        ("TestMock::test_a", "base `mock.Mock`"),
        ("TestOrderedDict::test_a", "base `collections.OrderedDict`"),
        ("TestNamedTupleCall::test_a", "base `namedtuple('Point', 'x y')`"),
        ("TestContextManagerAbstract::test_a", "is abstract"),
        ("TestMapping::test_a", "is abstract"),
        ("TestEq::test_a", "defines __eq__ without __hash__"),
        ("TestHashNone::test_a", "sets __hash__ = None"),
        ("TestEqChild::test_a", "defines __eq__ without __hash__"),
        ("TestFalseComparison::test_a", "sets __test__ = False"),
        ("TestSetattr::test_a", "sets __test__ = False"),
        ("test_decorated_nottest", "sets __test__ = False"),
        ("TestDecoratedNottest::test_a", "sets __test__ = False"),
        ("test_while_true", "is not a function or class"),
    ],
)
def test_the_third_review_nodes_pytest_does_not_collect_are_refused(verifier2, candidate, fragment):
    why = _why(verifier2, f"tests/test_verifier2.py::{candidate}")
    assert why is not None and fragment in why, why


@pytest.mark.parametrize(
    "candidate",
    [
        "test_kept",
        "TestContextManagerImplemented::test_a",
        "TestEqHash::test_a",
        "TestEqChildHash::test_a",
        "TestTrueComparison::test_a",
        "helper_decorated_istest",
        "TestStatic::test_s",
        "TestStatic::test_c",
    ],
)
def test_the_third_review_nodes_pytest_collects_resolve(verifier2, candidate):
    assert _why(verifier2, f"tests/test_verifier2.py::{candidate}") is None


def test_a_standard_library_base_that_is_not_safe_to_import_is_not_imported(tmp_path):
    """`this` prints a poem and `antigravity` opens a browser when imported, so a class built on
    something from them is read as an unreadable base, never by importing the module."""
    import sys

    from core.gates.pytest_node_resolver import _stdlib_traits

    assert _stdlib_traits("this", "d") == {}
    assert _stdlib_traits("antigravity", "geohash") == {}
    assert "this" not in sys.modules and "antigravity" not in sys.modules


def test_a_name_that_is_not_a_class_or_not_in_the_module_gives_no_traits():
    from core.gates.pytest_node_resolver import _stdlib_traits

    assert _stdlib_traits("threading", "no_such_name_zzz") == {}
    assert _stdlib_traits("threading", "active_count") == {}  # a function, not a class
    assert _stdlib_traits("not_a_stdlib_module_zzz", "X") == {}
    assert _stdlib_traits("threading", "Thread")["constructs"] is True
    assert _stdlib_traits("collections.abc", "Mapping")["abstract"]
    assert _stdlib_traits("collections", "OrderedDict")["constructs"] is True
    assert _stdlib_traits("collections.abc", "Mapping")["unhashable"] is True
    assert _stdlib_traits("threading", "Thread")["unhashable"] is False


def test_a_third_party_base_is_not_imported_and_is_only_named(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "from vendored_zzz import Base\n\n\nclass TestA(Base):\n"
                "    def test_a(self):\n        pass\n"
            )
        },
    )
    assert _why(root, "test_a.py::TestA::test_a") is None
    assert "Base" in (_why(root, "test_a.py::TestA::test_missing") or "")


def test_a_subclass_that_redefines_hash_is_hashable_again(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "class TestEq:\n    def __eq__(self, o):\n        return True\n"
                "    def test_a(self):\n        pass\n\n\n"
                "class TestBack(TestEq):\n    __hash__ = object.__hash__\n\n\n"
                "class TestStill(TestEq):\n    pass\n\n\n"
                "class TestFresh:\n    __hash__ = None\n\n\n"
                "class TestFreshChild(TestFresh):\n    def __eq__(self, o):\n"
                "        return True\n\n    def __hash__(self):\n        return 1\n\n"
                "    def test_a(self):\n        pass\n"
            )
        },
    )
    assert _why(root, "test_a.py::TestBack::test_a") is None
    assert "defines __eq__" in (_why(root, "test_a.py::TestStill::test_a") or "")
    assert _why(root, "test_a.py::TestFreshChild::test_a") is None


def test_an_unhashable_stdlib_base_is_overridden_by_a_hash_in_the_subclass(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "import collections.abc as abc\n\n\nclass TestA(abc.Mapping):\n"
                "    def __getitem__(self, k):\n        return 1\n    def __iter__(self):\n"
                "        return iter(())\n    def __len__(self):\n        return 0\n"
                "    def __hash__(self):\n        return 1\n    def test_a(self):\n        pass\n\n\n"
                "class TestB(abc.Mapping):\n    def __getitem__(self, k):\n        return 1\n"
                "    def __iter__(self):\n        return iter(())\n    def __len__(self):\n"
                "        return 0\n    def test_a(self):\n        pass\n"
            )
        },
    )
    assert _why(root, "test_a.py::TestA::test_a") is None
    assert "unhashable" in (_why(root, "test_a.py::TestB::test_a") or "")


@pytest.mark.parametrize(
    "expression,truthy",
    [
        ("1 > 2", False),
        ("2 > 1", True),
        ("1 == 1", True),
        ("1 != 1", False),
        ("1 <= 1", True),
        ("2 >= 3", False),
        ("1 < 2 < 3", True),
        ("1 < 3 < 2", False),
        ("'a' in 'abc'", True),
        ("'z' in 'abc'", False),
        ("'z' not in 'abc'", True),
        ("None is None", True),
        ("None is not None", False),
        ("1 + 1 == 2", True),
        ("2 * 3 - 6", False),
        ("7 // 2 - 3", False),
        ("7 % 2", True),
    ],
)
def test_comparisons_and_arithmetic_over_constants_are_decided(tmp_path, expression, truthy):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                f"VALUE = {expression}\n\nif VALUE:\n    def test_x():\n        pass\n"
                "else:\n    def test_y():\n        pass\n"
            )
        },
    )
    chosen, other = ("test_x", "test_y") if truthy else ("test_y", "test_x")
    assert _why(root, f"test_a.py::{chosen}") is None
    assert f"no `{other}` defined" in (_why(root, f"test_a.py::{other}") or "")


@pytest.mark.parametrize("expression", ["1 / 0", "'a' > 1", "make() > 1", "1 < make()", "2 ** 3"])
def test_an_expression_that_cannot_be_evaluated_leaves_both_arms_possible(tmp_path, expression):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                f"VALUE = {expression}\n\nif VALUE:\n    def test_x():\n        pass\n"
                "else:\n    def test_y():\n        pass\n"
            )
        },
    )
    assert _why(root, "test_a.py::test_x") is None
    assert _why(root, "test_a.py::test_y") is None


def test_setattr_of_the_test_flag_is_read_only_when_it_certainly_runs(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "import sys\n\n\ndef test_x():\n    pass\n\n\ndef test_y():\n    pass\n\n\n"
                "def test_z():\n    pass\n\n\ndef test_w():\n    pass\n\n\n"
                "setattr(test_x, '__test__', False)\n"
                "if sys.platform == 'plan9':\n    setattr(test_y, '__test__', False)\n"
                "setattr(test_z, 'other', False)\n"
                "setattr(test_w, '__test__', make())\n"
            )
        },
    )
    assert "sets __test__ = False" in (_why(root, "test_a.py::test_x") or "")
    assert _why(root, "test_a.py::test_y") is None
    assert _why(root, "test_a.py::test_z") is None
    assert _why(root, "test_a.py::test_w") is None


def test_nottest_and_istest_are_read_by_name_through_an_alias(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "from nose.tools import nottest as skip_me\nfrom nose.tools import istest\n\n\n"
                "@skip_me\ndef test_x():\n    pass\n\n\n@istest\ndef helper_y():\n    pass\n"
            )
        },
    )
    assert "sets __test__ = False" in (_why(root, "test_a.py::test_x") or "")
    assert _why(root, "test_a.py::helper_y") is None


def test_yield_fixture_is_a_fixture(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "import pytest\nfrom pytest import yield_fixture as yf\n\n\n"
                "@pytest.yield_fixture\ndef test_x():\n    yield 1\n\n\n"
                "@yf\ndef test_y():\n    yield 1\n"
            )
        },
    )
    assert "is a fixture" in (_why(root, "test_a.py::test_x") or "")
    assert "is a fixture" in (_why(root, "test_a.py::test_y") or "")


def test_a_while_true_body_runs_and_its_else_does_not(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "def test_x():\n    pass\n\n\ndef test_y():\n    pass\n\n\n"
                "while True:\n    test_x = None\n    break\nelse:\n    del test_y\n"
            )
        },
    )
    assert "not a function or class" in (_why(root, "test_a.py::test_x") or "")
    assert _why(root, "test_a.py::test_y") is None


def test_an_import_that_may_fail_does_not_replace_a_def(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "import sys\n\n\ndef test_a():\n    pass\n\n\ndef test_b():\n    pass\n\n\n"
                "def test_c():\n    pass\n\n\ntry:\n    from nomod_zzz import test_a\n"
                "except ImportError:\n    pass\n\nif sys.platform == 'plan9':\n"
                "    from nomod_zzz import test_b\n\nfrom nomod_zzz import test_c\n"
            )
        },
    )
    assert _why(root, "test_a.py::test_a") is None
    assert _why(root, "test_a.py::test_b") is None
    assert "outside the repository" in (_why(root, "test_a.py::test_c") or "")


def test_a_try_without_handlers_does_not_guard_its_imports(tmp_path):
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "def test_a():\n    pass\n\n\ntry:\n    from nomod_zzz import test_a\n"
                "finally:\n    pass\n"
            )
        },
    )
    assert "outside the repository" in (_why(root, "test_a.py::test_a") or "")


def test_a_test_inherited_from_an_imported_base_is_collected_when_imported_tests_are_off(tmp_path):
    """collect_imported_tests = false drops a test or class IMPORTED into the module, not the
    tests a class inherits from a base it imported: those are members of a class defined here."""
    root = _tree(
        tmp_path,
        {
            "pytest.ini": "[pytest]\ncollect_imported_tests = false\n",
            "lib.py": "class TestBaseX:\n    def test_b(self):\n        pass\n",
            "test_a.py": "from lib import TestBaseX\n\n\nclass TestA(TestBaseX):\n    pass\n",
        },
    )
    assert _why(root, "test_a.py::TestA::test_b") is None
    assert "collect_imported_tests" in (_why(root, "test_a.py::TestBaseX::test_b") or "")


@pytest.mark.parametrize(
    "header",
    [
        "import unittest.case\n\n\nclass TestU(unittest.case.TestCase):",
        "from unittest.case import TestCase as TC\n\n\nclass TestU(TC):",
        "import unittest\n\n\nclass TestU(unittest.TestCase):",
        "from unittest import IsolatedAsyncioTestCase\n\n\nclass TestU(IsolatedAsyncioTestCase):",
    ],
)
def test_every_spelling_of_a_unittest_case_is_a_unittest_class_not_a_constructor_class(
    tmp_path, header
):
    """unittest.case.TestCase has an __init__, and pytest collects it anyway (through unittest)."""
    body = (
        header + "\n    def test_a(self):\n        pass\n\n    def check_a(self):\n        pass\n"
    )
    root = _tree(tmp_path, {"test_a.py": body})
    assert _why(root, "test_a.py::TestU::test_a") is None
    assert "does not start with `test`" in (_why(root, "test_a.py::TestU::check_a") or "")
    assert _why(root, "test_a.py::TestU") is None


def test_a_module_file_cannot_hold_a_submodule(tmp_path):
    root = _tree(
        tmp_path,
        {
            "lib.py": "x = 1\n",
            "test_a.py": "import lib.sub\n\n\ndef test_x():\n    pass\n",
            "test_b.py": "import lib\n\n\ndef test_x():\n    pass\n",
        },
    )
    assert "is a module, not a package" in (_why(root, "test_a.py::test_x") or "")
    assert _why(root, "test_b.py::test_x") is None


def test_a_test_file_reached_by_two_spellings_is_one_module_not_a_name_clash(tmp_path):
    from tests.unit.test_pytest_collection_rules import _link

    root = _tree(tmp_path, {"tests/real/test_a.py": "def test_x():\n    pass\n"})
    if not _link(root / "tests" / "alias", root / "tests" / "real"):
        pytest.skip("this platform will not make a directory link here")
    assert _why(root, "tests/alias/test_a.py::test_x") is None
    assert _why(root, "tests/real/test_a.py::test_x") is None
