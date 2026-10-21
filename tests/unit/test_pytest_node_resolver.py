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
    _CASES_ITEM3,
    _CASES_MORE,
    _HELPER,
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
    assert why is not None and "inheritance cycle" in why and "TestX" in why
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
    assert "_Hidden (not defined in the file)" in why or "uses base `_Hidden`" in why


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
    """`Exception` resolves to the builtin when the class is made; defining a name `Exception`
    further down does not make the earlier use a NameError."""
    root = _tree(
        tmp_path,
        {
            "test_a.py": (
                "class TestA(Exception):\n    def test_a(self):\n        pass\n\n\nException = None\n"
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
    assert _why(root, "test_a.py::test_x") is None
    assert _why(root, "test_b.py::test_x") is None


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
