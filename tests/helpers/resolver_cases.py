"""Trees and candidates the pytest-collection tests share.

The unit tests for the resolver, the collection rules and the rule-enforcement gate, and the
agreement tests that put the resolver beside `pytest --collect-only`, all build the same
throwaway repositories. They live here so each file holds only what it asserts.
"""

from __future__ import annotations

import textwrap
from pathlib import Path


def write_tree(root: Path, files: dict[str, str | bytes]) -> Path:
    for name, body in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            path.write_bytes(body)
        else:
            path.write_text(textwrap.dedent(body), encoding="utf-8")
    return root


_OK = "def test_ok():\n    pass\n\n\ndef test_ok_two():\n    pass\n"

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

# Behaviours found by an independent verifier after #913, each a place the resolver accepted
# what pytest does not collect or refused what it does: diamond inheritance (a flat merge, not
# an MRO), a class with nothing in it, `__all__` on a star import, `with`/`for` targets that
# rebind a def, a module constant in an `if`, a falsy or true-but-oddly-spelled `__test__`, a
# `__test__` set from outside, and a lambda assigned to a test name.
_STAR_HELPER = """\
__all__ = ["test_exported", "TestExportedBase"]


def test_exported():
    pass


def test_hidden():
    pass


class TestExportedBase:
    def test_in_base(self):
        pass


class TestHiddenBase:
    def test_hidden_base(self):
        pass
"""

_STAR_NOLIST = """\
def test_public():
    pass
"""

_CASES_ITEM3 = """\
import sys

import pytest
from star_helper import *
from star_nolist import *


class TestDiaA:
    def test_x(self):
        pass


class TestDiaB(TestDiaA):
    test_x = None


class TestDiaC(TestDiaA):
    pass


class TestDiaE(TestDiaC, TestDiaB):
    pass


class TestDiaF(TestDiaB, TestDiaC):
    pass


class TestDiaG(TestDiaC, TestDiaA):
    pass


class TestEmptyOne:
    value = 1


class TestOnlyHelpers:
    def helper(self):
        pass


class TestOnlyFixture:
    @pytest.fixture
    def test_fixture_in_class(self):
        pass


class TestOnlyInherited(TestDiaA):
    pass


class TestOnlyNested:
    class TestNested:
        def test_n(self):
            pass


class TestOnlyEmptyNested:
    class TestNested:
        value = 1


class TestZero:
    __test__ = 0

    def test_a(self):
        pass


class TestStr:
    __test__ = "yes"

    def test_a(self):
        pass


class TestNone:
    __test__ = None

    def test_a(self):
        pass


class NotNamedButTrue:
    __test__ = True

    def test_a(self):
        pass


class TestExternalFalse:
    def test_a(self):
        pass


TestExternalFalse.__test__ = False


class NotNamedAssignedTrue:
    def test_a(self):
        pass


NotNamedAssignedTrue.__test__ = True


class TestParent:
    def test_p(self):
        pass


class TestChildFlag(TestParent):
    __test__ = False


class TestChildBack(TestChildFlag):
    __test__ = True


class TestMethodFlag:
    def test_m(self):
        pass

    test_m.__test__ = False

    def test_n(self):
        pass


def test_attr_false():
    pass


test_attr_false.__test__ = False


def helper_attr_true():
    pass


helper_attr_true.__test__ = True

test_lambda = lambda: None  # noqa: E731


def test_with_before():
    pass


with open(__file__) as test_with_before:
    pass

with open(__file__) as test_with_after:
    pass


def test_with_after():
    pass


def test_for_before():
    pass


for test_for_before in [1]:
    pass


def test_for_range():
    pass


for test_for_range in range(3):
    pass


def test_for_empty():
    pass


for test_for_empty in []:
    pass


DEBUG = False
FLAG = True

if DEBUG:

    def test_under_debug():
        pass

else:

    def test_not_debug():
        pass


if FLAG:

    def test_flagged():
        pass


if DEBUG and FLAG:

    def test_and():
        pass


if DEBUG or FLAG:

    def test_or():
        pass


if not DEBUG:

    def test_not():
        pass


@pytest.mark.skip(reason="resolves: a skip is a run-time outcome, pytest still collects it")
def test_skipped_by_a_marker():
    pass


class TestSkippedClass:
    pytestmark = pytest.mark.skip

    def test_s(self):
        pass
"""

_ITEM3_CANDIDATES = [
    "TestDiaE::test_x",
    "TestDiaF::test_x",
    "TestDiaG::test_x",
    "TestDiaC::test_x",
    "TestEmptyOne",
    "TestOnlyHelpers",
    "TestOnlyFixture",
    "TestOnlyInherited",
    "TestOnlyNested",
    "TestOnlyNested::TestNested",
    "TestOnlyEmptyNested",
    "TestZero::test_a",
    "TestStr::test_a",
    "TestNone::test_a",
    "NotNamedButTrue::test_a",
    "TestExternalFalse::test_a",
    "NotNamedAssignedTrue::test_a",
    "TestChildFlag::test_p",
    "TestChildBack::test_p",
    "TestMethodFlag::test_m",
    "TestMethodFlag::test_n",
    "test_attr_false",
    "helper_attr_true",
    "test_lambda",
    "test_with_before",
    "test_with_after",
    "test_for_before",
    "test_for_range",
    "test_for_empty",
    "test_under_debug",
    "test_not_debug",
    "test_flagged",
    "test_and",
    "test_or",
    "test_not",
    "test_skipped_by_a_marker",
    "TestSkippedClass::test_s",
    # through `from star_helper import *` (it lists test_exported and TestExportedBase) and
    # `from star_nolist import *` (no __all__: every public name)
    "test_exported",
    "test_hidden",
    "TestExportedBase::test_in_base",
    "TestHiddenBase::test_hidden_base",
    "test_public",
]

# Files where importing raises, so pytest collects NOTHING from them -- every reference into
# one must be refused, including the plain test that sits beside the cause.
_POISONED = {
    "tests/test_bad_mro.py": (
        "class TestBadA:\n    def test_a(self):\n        pass\n\n\n"
        "class TestBadB(TestBadA):\n    pass\n\n\n"
        "class TestBadC(TestBadA, TestBadB):\n    pass\n\n\n"
        "def test_beside_the_cause():\n    pass\n",
        ["TestBadA::test_a", "TestBadC::test_a", "test_beside_the_cause"],
    ),
    "tests/test_late_base.py": (
        "class TestLateChild(TestLateBase):\n    pass\n\n\n"
        "class TestLateBase:\n    def test_b(self):\n        pass\n\n\n"
        "def test_beside_the_cause():\n    pass\n",
        ["TestLateBase::test_b", "TestLateChild::test_b", "test_beside_the_cause"],
    ),
    "tests/test_relative.py": (
        "from .helper import test_shared\n\n\ndef test_beside_the_cause():\n    pass\n",
        ["test_shared", "test_beside_the_cause"],
    ),
    "tests/test_modskip.py": (
        "import pytest\n\npytest.skip('whole module', allow_module_level=True)\n\n\n"
        "def test_beside_the_cause():\n    pass\n",
        ["test_beside_the_cause"],
    ),
    "tests/test_modflag.py": (
        "__test__ = False\n\n\ndef test_beside_the_cause():\n    pass\n",
        ["test_beside_the_cause"],
    ),
    "tests/pkgrel2/sub/test_beyond.py": (
        "from ..y import test_y\n\n\ndef test_beside_the_cause():\n    pass\n",
        ["test_y", "test_beside_the_cause"],
    ),
}

# Relative imports that DO work: every directory up to the dots is a package
_PACKAGES = {
    "tests/pkgrel/__init__.py": "",
    "tests/pkgrel/helper_rel.py": "def test_in_rel():\n    pass\n",
    "tests/pkgrel/test_ok_rel.py": "from .helper_rel import test_in_rel\n",
    "tests/pkgrel/sub/__init__.py": "",
    "tests/pkgrel/sub/test_up.py": "from ..helper_rel import test_in_rel\n",
    "tests/pkgrel2/y.py": "def test_y():\n    pass\n",
    "tests/pkgrel2/sub/__init__.py": "",
    # a regular package in the repository, and a helper that cannot be imported
    "tests/pkgmiss/__init__.py": "",
    "tests/pkgmiss/present.py": "def test_in_present():\n    pass\n",
    "tests/broken_helper.py": "def broken(:\n    pass\n",
    "tests/helper_raises.py": "raise RuntimeError('at import')\n",
    "tests/helper_imports_missing.py": "from pkgmiss.gone import thing\n",
    # the FIRST of two files with one name: pytest imports it, so it is collected
    "tests/dupx/test_dup.py": "def test_a():\n    pass\n",
}

# More files that raise when imported, each from a cause a static read can PROVE: a statement
# that always raises, an import of a module a regular repository package does not have, a name a
# repository module does not define, a helper that does not parse.
_POISONED.update(
    {
        "tests/test_raises.py": (
            "def test_before():\n    pass\n\n\nraise RuntimeError('at import')\n",
            ["test_before"],
        ),
        "tests/test_assert_false.py": (
            "def test_before():\n    pass\n\n\nassert False, 'refused at import'\n",
            ["test_before"],
        ),
        "tests/test_missing_module.py": (
            "from pkgmiss.gone import thing\n\n\ndef test_beside_the_cause():\n    pass\n",
            ["test_beside_the_cause"],
        ),
        "tests/test_missing_module_plain.py": (
            "import pkgmiss.gone\n\n\ndef test_beside_the_cause():\n    pass\n",
            ["test_beside_the_cause"],
        ),
        "tests/test_missing_name.py": (
            "from helper import nothing_here\n\n\ndef test_beside_the_cause():\n    pass\n",
            ["test_beside_the_cause"],
        ),
        "tests/test_bad_helper.py": (
            "import broken_helper\n\n\ndef test_beside_the_cause():\n    pass\n",
            ["test_beside_the_cause"],
        ),
        # relative imports inside a package: a name, a submodule, a package member, two levels up
        "tests/pkgrel/test_rel_missing_name.py": (
            "from .helper_rel import nothere\n\n\ndef test_beside_the_cause():\n    pass\n",
            ["test_beside_the_cause"],
        ),
        "tests/pkgrel/test_rel_missing_member.py": (
            "from . import nomod\n\n\ndef test_beside_the_cause():\n    pass\n",
            ["test_beside_the_cause"],
        ),
        "tests/pkgrel/test_rel_missing_sub.py": (
            "from .gone import x\n\n\ndef test_beside_the_cause():\n    pass\n",
            ["test_beside_the_cause"],
        ),
        "tests/pkgrel/sub/test_rel_up_missing.py": (
            "from ..helper_rel import nothere\n\n\ndef test_beside_the_cause():\n    pass\n",
            ["test_beside_the_cause"],
        ),
        # a top-level call that always raises
        "tests/test_skip_plain.py": (
            "import pytest\n\npytest.skip('x')\n\n\ndef test_beside_the_cause():\n    pass\n",
            ["test_beside_the_cause"],
        ),
        "tests/test_skip_false.py": (
            "import pytest\n\npytest.skip('x', allow_module_level=False)\n\n\n"
            "def test_beside_the_cause():\n    pass\n",
            ["test_beside_the_cause"],
        ),
        "tests/test_xfail_call.py": (
            "import pytest\n\npytest.xfail('x')\n\n\ndef test_beside_the_cause():\n    pass\n",
            ["test_beside_the_cause"],
        ),
        "tests/test_fail_call.py": (
            "import pytest\n\npytest.fail('x')\n\n\ndef test_beside_the_cause():\n    pass\n",
            ["test_beside_the_cause"],
        ),
        "tests/test_zero_division.py": (
            "1 / 0\n\n\ndef test_beside_the_cause():\n    pass\n",
            ["test_beside_the_cause"],
        ),
        # a class body that raises, a name augmented before it exists
        "tests/test_class_raises.py": (
            "class TestA:\n    raise RuntimeError('in the body')\n\n    def test_a(self):\n"
            "        pass\n",
            ["TestA::test_a"],
        ),
        "tests/test_class_asserts.py": (
            "class TestA:\n    assert False\n\n    def test_a(self):\n        pass\n",
            ["TestA::test_a"],
        ),
        "tests/test_augment_undefined.py": (
            "nothere += 1\n\n\ndef test_beside_the_cause():\n    pass\n",
            ["test_beside_the_cause"],
        ),
        # a helper the file imports raises, imports what is not there, or is not a package
        "tests/test_helper_raises.py": (
            "import helper_raises\n\n\ndef test_beside_the_cause():\n    pass\n",
            ["test_beside_the_cause"],
        ),
        "tests/test_helper_imports_missing.py": (
            "import helper_imports_missing\n\n\ndef test_beside_the_cause():\n    pass\n",
            ["test_beside_the_cause"],
        ),
        "tests/test_not_a_package.py": (
            "import pkgmiss.present.deeper\n\n\ndef test_beside_the_cause():\n    pass\n",
            ["test_beside_the_cause"],
        ),
        "tests/test_self_import.py": (
            "from test_self_import import nothere\n\n\ndef test_beside_the_cause():\n    pass\n",
            ["test_beside_the_cause"],
        ),
        # the second of two files with one name in directories that are not packages
        "tests/dupy/test_dup.py": ("def test_a():\n    pass\n", ["test_a"]),
    }
)

# Imports that look like the cases above and work, or may: none may be refused.
_IMPORT_FILES = {
    "tests/test_import_guarded.py": (
        "try:\n    from pkgmiss.gone import thing\nexcept ImportError:\n    thing = None\n\n\n"
        "def test_guarded():\n    pass\n",
        ["test_guarded"],
    ),
    # importing itself by name works for what it has defined above the import
    "tests/test_self_ok.py": (
        "def test_a():\n    pass\n\n\nfrom test_self_ok import test_a  # noqa: E402,F401\n",
        ["test_a"],
    ),
    "tests/test_import_ok.py": (
        "import pkgmiss.present\nfrom pkgmiss import present\n"
        "from pkgmiss.present import test_in_present\n\n\ndef test_here():\n    pass\n",
        ["test_in_present", "test_here"],
    ),
}

# What a verifier of the directory-run change found: classes pytest does not collect (a dataclass
# or an Enum gains __init__/__new__, a dict or Exception base brings its own, an abstract class),
# functions that are not callable (a property), conditions that are decidable (`not True`,
# `TYPE_CHECKING as TC`, an empty `for`), a walrus that rebinds a def, and names pytest collects
# that were refused (a partial, `x = module.attr`, a function assigned in a class body, a
# subscripted Generic base).
_CASES_FOLLOWUP = """\
import abc
import dataclasses
import enum
import functools
import typing
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from functools import partial
from typing import TYPE_CHECKING as TC
from typing import Generic, NamedTuple, Protocol, TypeVar

import helper
from pytest import fixture as fx

T = TypeVar("T")


@dataclass
class TestDataclass:
    def test_a(self):
        pass


@dataclasses.dataclass(init=False)
class TestDataclassNoInit:
    def test_a(self):
        pass


@dataclasses.dataclass(init=False, eq=False)
class TestDataclassNoInitNoEq:
    def test_a(self):
        pass


@dataclass(frozen=True)
class TestDataclassFrozen:
    def test_a(self):
        pass


class TestDataclassChild(TestDataclass):
    pass


class TestDictBase(dict):
    def test_a(self):
        pass


class TestExceptionBase(Exception):
    def test_a(self):
        pass


class TestIntBase(int):
    def test_a(self):
        pass


class TestListBase(list):
    def test_a(self):
        pass


class TestStrBase(str):
    def test_a(self):
        pass


class TestTupleBase(tuple):
    def test_a(self):
        pass


class TestTypeBase(type):
    def test_a(cls):
        pass


class TestObjectBase(object):
    def test_a(self):
        pass


class TestEnum(Enum):
    A = 1

    def test_a(self):
        pass


class TestEnumDirect(enum.IntEnum):
    A = 1

    def test_a(self):
        pass


class TestNamedTuple(NamedTuple):
    x: int

    def test_a(self):
        pass


class TestProtocol(Protocol):
    def test_a(self):
        pass


class TestGeneric(Generic[T]):
    def test_a(self):
        pass


class TestSubscripted(TestGeneric[int]):
    pass


class TestProperty:
    @property
    def test_prop(self):
        return 1

    def test_real(self):
        pass


class TestAbstract(ABC):
    @abstractmethod
    def test_abstract(self):
        pass

    def test_concrete(self):
        pass


class TestAbstractMeta(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def test_abstract(self):
        pass

    def test_concrete(self):
        pass


class TestAbstractChildOk(TestAbstract):
    def test_abstract(self):
        pass


class TestAbstractChildStillAbstract(TestAbstract):
    pass


class TestAbcWithNothingAbstract(ABC):
    def test_a(self):
        pass


X = not True
Y = not False

if X:

    def test_under_not_true():
        pass


if Y:

    def test_under_not_false():
        pass


if TC:

    def test_under_type_checking_alias():
        pass


if typing.TYPE_CHECKING:

    def test_under_type_checking_attribute():
        pass


def test_walrus_def():
    pass


(test_walrus_def := 3)

for _ in []:

    def test_in_empty_for():
        pass

else:

    def test_in_for_else():
        pass


@fx
def test_fixture_alias():
    pass


def test_orig():
    pass


test_alias_attr = helper.test_shared
test_partial = partial(test_orig)
test_partial_attr = functools.partial(test_orig)


class TestClassAlias:
    test_from_outer = test_orig
"""

_FOLLOWUP_CANDIDATES = [
    "TestDataclass::test_a",
    "TestDataclassNoInit::test_a",
    "TestDataclassNoInitNoEq::test_a",
    "TestDataclassFrozen::test_a",
    "TestDataclassChild::test_a",
    "TestDictBase::test_a",
    "TestExceptionBase::test_a",
    "TestIntBase::test_a",
    "TestListBase::test_a",
    "TestStrBase::test_a",
    "TestTupleBase::test_a",
    "TestTypeBase::test_a",
    "TestObjectBase::test_a",
    "TestEnum::test_a",
    "TestEnumDirect::test_a",
    "TestNamedTuple::test_a",
    "TestProtocol::test_a",
    "TestGeneric::test_a",
    "TestSubscripted::test_a",
    "TestProperty::test_prop",
    "TestProperty::test_real",
    "TestAbstract::test_concrete",
    "TestAbstractMeta::test_concrete",
    "TestAbstractChildOk::test_concrete",
    "TestAbstractChildOk::test_abstract",
    "TestAbstractChildStillAbstract::test_concrete",
    "TestAbcWithNothingAbstract::test_a",
    "test_under_not_true",
    "test_under_not_false",
    "test_under_type_checking_alias",
    "test_under_type_checking_attribute",
    "test_walrus_def",
    "test_in_empty_for",
    "test_in_for_else",
    "test_fixture_alias",
    "test_alias_attr",
    "test_partial",
    "test_partial_attr",
    "TestClassAlias::test_from_outer",
]

# The third review: standard-library bases that bring a constructor, a missing hash or abstract
# methods of their own; `__eq__` without `__hash__`; constants that are comparisons; the setattr,
# nottest and staticmethod spellings; and `while True`, which always runs its body.
_CASES_VERIFIER2 = """\
import argparse
import collections
import collections.abc
import contextlib
import io
import logging
import pathlib
import threading
from collections import namedtuple
from unittest import mock

try:
    from nomod_zzz import test_kept
except ImportError:
    pass


def test_kept():
    pass


def nottest(obj):
    obj.__test__ = False
    return obj


def istest(obj):
    obj.__test__ = True
    return obj


class TestThread(threading.Thread):
    def test_a(self):
        pass


class TestStringIO(io.StringIO):
    def test_a(self):
        pass


class TestHandler(logging.Handler):
    def test_a(self):
        pass


class TestNamespace(argparse.Namespace):
    def test_a(self):
        pass


class TestPurePath(pathlib.PurePath):
    def test_a(self):
        pass


class TestMock(mock.Mock):
    def test_a(self):
        pass


class TestOrderedDict(collections.OrderedDict):
    def test_a(self):
        pass


class TestNamedTupleCall(namedtuple("Point", "x y")):
    def test_a(self):
        pass


class TestContextManagerAbstract(contextlib.AbstractContextManager):
    def test_a(self):
        pass


class TestContextManagerImplemented(contextlib.AbstractContextManager):
    def __exit__(self, *exc):
        return None

    def test_a(self):
        pass


class TestMapping(collections.abc.Mapping):
    def test_a(self):
        pass


class TestEq:
    def __eq__(self, other):
        return True

    def test_a(self):
        pass


class TestEqHash:
    def __eq__(self, other):
        return True

    def __hash__(self):
        return 1

    def test_a(self):
        pass


class TestHashNone:
    __hash__ = None

    def test_a(self):
        pass


class TestEqChild(TestEq):
    pass


class TestEqChildHash(TestEq):
    def __hash__(self):
        return 2


class TestFalseComparison:
    __test__ = 1 > 2

    def test_a(self):
        pass


class TestTrueComparison:
    __test__ = 1 < 2

    def test_a(self):
        pass


class TestSetattr:
    def test_a(self):
        pass


setattr(TestSetattr, "__test__", False)


@nottest
def test_decorated_nottest():
    pass


@nottest
class TestDecoratedNottest:
    def test_a(self):
        pass


@istest
def helper_decorated_istest():
    pass


class TestStatic:
    test_s = staticmethod(lambda: None)
    test_c = classmethod(lambda cls: None)


def test_while_true():
    pass


while True:
    test_while_true = None
    break
"""

# a fixture spelled yield_fixture: either pytest still has it and it is a fixture, or it does not and
# the file does not import; pytest collects nothing from it either way
_YIELD_FIXTURE = "import pytest\n\n\n@pytest.yield_fixture\ndef test_f():\n    yield 1\n"

_VERIFIER2_CANDIDATES = [
    "test_kept",
    "TestThread::test_a",
    "TestStringIO::test_a",
    "TestHandler::test_a",
    "TestNamespace::test_a",
    "TestPurePath::test_a",
    "TestMock::test_a",
    "TestOrderedDict::test_a",
    "TestNamedTupleCall::test_a",
    "TestContextManagerAbstract::test_a",
    "TestContextManagerImplemented::test_a",
    "TestMapping::test_a",
    "TestEq::test_a",
    "TestEqHash::test_a",
    "TestHashNone::test_a",
    "TestEqChild::test_a",
    "TestEqChildHash::test_a",
    "TestFalseComparison::test_a",
    "TestTrueComparison::test_a",
    "TestSetattr::test_a",
    "test_decorated_nottest",
    "TestDecoratedNottest::test_a",
    "helper_decorated_istest",
    "TestStatic::test_s",
    "TestStatic::test_c",
    "test_while_true",
]

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


# --------------------------------------------------------------------------
# Scenarios: each is a tree, a config file name, and the files in it that hold tests
# --------------------------------------------------------------------------

_DEFAULT_DIRS = [
    "build",
    "dist",
    "node_modules",
    "venv",
    ".hidden",
    "pkg.egg",
    "CVS",
    "_darcs",
    "{arch}",
    "_build",
    "ok",
    "tmp_x",
]


def _defaults() -> dict[str, str]:
    files = {"pytest.ini": "[pytest]\n"}
    for index, directory in enumerate(_DEFAULT_DIRS):
        files[f"{directory}/test_top_{index}.py"] = _OK
        files[f"{directory}/inner/test_inner_{index}.py"] = _OK
    files["ok/build/test_ok_then_build.py"] = _OK
    files["ok/node_modules/test_ok_then_modules.py"] = _OK
    files["ok/.cache/test_ok_then_hidden.py"] = _OK
    files["__pycache__/test_in_pycache.py"] = _OK
    files["myenv/pyvenv.cfg"] = "home = x\n"
    files["myenv/test_in_a_virtualenv.py"] = _OK
    files["test_at_the_root.py"] = _OK
    return files


_CONFTEST_ROOT = """\
collect_ignore = ["test_root_ignored.py", "ignored_dir", "sub/test_masked.py"]
collect_ignore_glob = ["glob_*"]
"""

_SCENARIOS = {
    "defaults": (_defaults(), "pytest.ini"),
    "conftest": (
        {
            "pytest.ini": "[pytest]\n",
            "conftest.py": _CONFTEST_ROOT,
            "test_root_kept.py": _OK,
            "test_root_ignored.py": _OK,
            "ignored_dir/test_in_ignored_dir.py": _OK,
            "glob_test.py": _OK,
            "glob_dir/test_in_glob_dir.py": _OK,
            # the nearest conftest that defines collect_ignore is the only one pytest reads:
            # sub/ defines it (empty), so the root's entry for sub/test_masked.py is not seen
            "sub/conftest.py": 'collect_ignore = ["test_sub_ignored.py"]\n',
            "sub/test_sub_ignored.py": _OK,
            "sub/test_masked.py": _OK,
            "sub/test_sub_kept.py": _OK,
            "sub/deep/test_deep_kept.py": _OK,
            # a directory with no conftest of its own reads the parent's
            "plain/test_plain_kept.py": _OK,
        },
        "pytest.ini",
    ),
    "addopts": (
        {
            "pytest.ini": (
                "[pytest]\n"
                "addopts = --ignore=ign_file/test_ign.py --ignore ign_dir\n"
                "    --ignore-glob=*/globbed_*_test.py\n"
                "    --deselect=desel_dir/test_desel.py::test_ok\n"
                "    --deselect desel_other/\n"
            ),
            "ign_file/test_ign.py": _OK,
            "ign_file/test_ign_sibling.py": _OK,
            "ign_dir/test_in_ign_dir.py": _OK,
            "x/globbed_one_test.py": _OK,
            "x/y/globbed_two_test.py": _OK,
            "globbed_three_test.py": _OK,
            "desel_dir/test_desel.py": _OK,
            "desel_dir/test_desel_kept.py": _OK,
            "desel_other/test_a.py": _OK,
            "desel_other/sub/test_b.py": _OK,
            "kept/test_kept.py": _OK,
        },
        "pytest.ini",
    ),
    "testpaths": (
        {
            "pytest.ini": "[pytest]\ntestpaths = in_a in_b/sub globdir_* checks.py build\n",
            "in_a/test_a.py": _OK,
            "in_a/build/test_in_a_build.py": _OK,
            "in_b/test_b_top.py": _OK,
            "in_b/sub/test_b_sub.py": _OK,
            "globdir_1/test_g1.py": _OK,
            "globdir_2/test_g2.py": _OK,
            "other/test_other.py": _OK,
            "test_root.py": _OK,
            "checks.py": _OK,
            # a testpath that is itself in norecursedirs is an explicit argument: collected,
            # while what it holds is judged by the rules again
            "build/test_in_build.py": _OK,
            "build/dist/test_nested_dist.py": _OK,
        },
        "pytest.ini",
    ),
    "norecursedirs": (
        {
            "pytest.ini": "[pytest]\nnorecursedirs = skipme custom_* a/b\n",
            # naming norecursedirs REPLACES the defaults, so build/ is collected here
            "build/test_b.py": _OK,
            "skipme/test_s.py": _OK,
            "custom_x/test_c.py": _OK,
            "ok/skipme/test_deep.py": _OK,
            "a/b/test_path_pattern.py": _OK,
            "c/a/b/test_path_pattern_two.py": _OK,
            "a/test_a_only.py": _OK,
        },
        "pytest.ini",
    ),
    "collect-imported-tests": (
        {
            "pytest.ini": "[pytest]\ncollect_imported_tests = false\n",
            "helper_mod.py": _OK,
            "test_imp.py": "from helper_mod import test_ok\n\n\ndef test_ok_two():\n    pass\n",
            "test_own.py": _OK,
        },
        "pytest.ini",
    ),
    # an option that is present and empty is not an option that is absent
    "empty-norecursedirs": (
        {
            "pytest.ini": "[pytest]\nnorecursedirs =\n",
            "build/test_b.py": _OK,
            "node_modules/test_n.py": _OK,
            ".hidden/test_h.py": _OK,
            "__pycache__/test_pyc.py": _OK,
            "myenv/pyvenv.cfg": "home = x\n",
            "myenv/test_in_a_virtualenv.py": _OK,
        },
        "pytest.ini",
    ),
    "empty-python-files": (
        {
            "pytest.ini": "[pytest]\npython_files =\ntestpaths = checks.py\n",
            "checks.py": _OK,
            "test_not_collected.py": _OK,
        },
        "pytest.ini",
    ),
    "toml": (
        {
            "pytest.toml": (
                '[pytest]\naddopts = ["--ignore=ign"]\nnorecursedirs = ["skipme"]\n'
                'testpaths = ["suite"]\n'
            ),
            "suite/test_kept.py": _OK,
            "suite/skipme/test_skipped.py": _OK,
            "suite/build/test_default_no_longer_applies.py": _OK,
            "ign/test_ign_outside_testpaths.py": _OK,
            "suite/ign/test_ign_inside.py": _OK,
        },
        "pytest.toml",
    ),
    "pyproject-native": (
        {
            "pyproject.toml": '[tool.pytest]\ntestpaths = ["only"]\nnorecursedirs = ["no"]\n',
            "only/test_kept.py": _OK,
            "only/no/test_skipped.py": _OK,
            "elsewhere/test_not_in_testpaths.py": _OK,
        },
        "pyproject.toml",
    ),
    "pyproject-ini": (
        {
            "pyproject.toml": (
                "[tool.pytest.ini_options]\n"
                'testpaths = ["only"]\n'
                'addopts = "--ignore-glob=*/skip_*_test.py"\n'
            ),
            "only/test_kept.py": _OK,
            "only/skip_me_test.py": _OK,
            "elsewhere/test_not_in_testpaths.py": _OK,
        },
        "pyproject.toml",
    ),
}

# What the resolver is KNOWN to get wrong, each judged against pytest by the agreement test and
# listed in the resolver's docstring. "accept" is a false accept (pytest collects nothing and the
# resolver says yes); "refuse" a false refusal (pytest collects it and the resolver says no).
# They are pinned, not hidden: when one is fixed the agreement test fails until it is moved out
# of this table and the docstring, so the list of limits cannot go stale.
_LIM_HELPER = (
    "tests/lim_helper.py",
    "class TestBaseShared:\n    def test_from_base(self):\n        pass\n",
)

_KNOWN_LIMITS = {
    "a module missing from the environment": (
        "accept",
        {"tests/test_lim_env.py": "import not_installed_zzz\n\n\ndef test_x():\n    pass\n"},
        "tests/test_lim_env.py::test_x",
    ),
    "a module missing from a namespace directory": (
        "accept",
        {
            "tests/nspkg_lim/m.py": "x = 1\n",
            "tests/test_lim_ns.py": "from nspkg_lim.gone import y\n\n\ndef test_x():\n    pass\n",
        },
        "tests/test_lim_ns.py::test_x",
    ),
    "a NameError at import": (
        "accept",
        {"tests/test_lim_name.py": "x = undefined_name\n\n\ndef test_x():\n    pass\n"},
        "tests/test_lim_name.py::test_x",
    ),
    "an assert on a condition that cannot be decided": (
        "accept",
        {
            "tests/test_lim_assert.py": (
                "import sys\nassert sys.platform == 'plan9'\n\n\ndef test_x():\n    pass\n"
            )
        },
        "tests/test_lim_assert.py::test_x",
    ),
    "a circular import": (
        "accept",
        {
            "tests/circ_a.py": "import circ_b\nthing = 1\n",
            "tests/circ_b.py": "from circ_a import thing\n",
            "tests/test_lim_circ.py": "import circ_a\n\n\ndef test_x():\n    pass\n",
        },
        "tests/test_lim_circ.py::test_x",
    ),
    "importorskip of a missing module": (
        "accept",
        {
            "tests/test_lim_skip1.py": (
                "import pytest\n\npytest.importorskip('not_installed_zzz')\n\n\n"
                "def test_x():\n    pass\n"
            )
        },
        "tests/test_lim_skip1.py::test_x",
    ),
    "a conditional pytest.skip(allow_module_level=True)": (
        "accept",
        {
            "tests/test_lim_skip2.py": (
                "import sys\nimport pytest\n\nif sys.platform:\n"
                "    pytest.skip('x', allow_module_level=True)\n\n\ndef test_x():\n    pass\n"
            )
        },
        "tests/test_lim_skip2.py::test_x",
    ),
    "a pytest.skip(allow_module_level=True) reached through a function": (
        "accept",
        {
            "tests/test_lim_skip3.py": (
                "import pytest\n\n\ndef stop():\n    pytest.skip('x', allow_module_level=True)\n\n\n"
                "stop()\n\n\ndef test_x():\n    pass\n"
            )
        },
        "tests/test_lim_skip3.py::test_x",
    ),
    "a generator test function": (
        "accept",
        {"tests/test_lim_gen.py": "def test_x():\n    yield 1\n"},
        "tests/test_lim_gen.py::test_x",
    ),
    "a class decorator that returns None": (
        "accept",
        {
            "tests/test_lim_cdeco.py": (
                "def deco(c):\n    return None\n\n\n@deco\nclass TestA:\n"
                "    def test_x(self):\n        pass\n"
            )
        },
        "tests/test_lim_cdeco.py::TestA::test_x",
    ),
    "a function decorator that returns None": (
        "accept",
        {
            "tests/test_lim_fdeco.py": (
                "def deco(f):\n    return None\n\n\n@deco\ndef test_x():\n    pass\n"
            )
        },
        "tests/test_lim_fdeco.py::test_x",
    ),
    "a class decorator that adds an __init__": (
        "accept",
        {
            "tests/test_lim_init.py": (
                "def define(c):\n    def __init__(self):\n        pass\n\n"
                "    c.__init__ = __init__\n    return c\n\n\n@define\nclass TestA:\n"
                "    def test_x(self):\n        pass\n"
            )
        },
        "tests/test_lim_init.py::TestA::test_x",
    ),
    "a def in a try whose import fails": (
        "accept",
        {
            "tests/test_lim_try.py": (
                "try:\n    import not_installed_zzz\n\n    def test_x():\n        pass\n"
                "except ImportError:\n    pass\n"
            )
        },
        "tests/test_lim_try.py::test_x",
    ),
    "a base made by a call": (
        "refuse",
        dict(
            [_LIM_HELPER],
            **{
                "tests/test_lim_call.py": (
                    "from lim_helper import TestBaseShared\n\n\ndef make():\n"
                    "    return TestBaseShared\n\n\nclass TestA(make()):\n    pass\n"
                )
            },
        ),
        "tests/test_lim_call.py::TestA::test_from_base",
    ),
    "a base that is splatted": (
        "refuse",
        dict(
            [_LIM_HELPER],
            **{
                "tests/test_lim_splat.py": (
                    "from lim_helper import TestBaseShared\n\nbases = (TestBaseShared,)\n\n\n"
                    "class TestA(*bases):\n    pass\n"
                )
            },
        ),
        "tests/test_lim_splat.py::TestA::test_from_base",
    ),
    "a class built by a factory function": (
        "refuse",
        {
            "tests/test_lim_factory.py": (
                "def make():\n    class TestMade:\n        def test_x(self):\n"
                "            pass\n\n    return TestMade\n\n\nTestMade = make()\n"
            )
        },
        "tests/test_lim_factory.py::TestMade::test_x",
    ),
    "a def created through global": (
        "refuse",
        {
            "tests/test_lim_global.py": (
                "def make():\n    global test_made\n\n    def test_made():\n        pass\n\n\n"
                "make()\n"
            )
        },
        "tests/test_lim_global.py::test_made",
    ),
    "unittest.TestCase.runTest": (
        "refuse",
        {
            "tests/test_lim_runtest.py": (
                "import unittest\n\n\nclass TestU(unittest.TestCase):\n"
                "    def runTest(self):\n        pass\n"
            )
        },
        "tests/test_lim_runtest.py::TestU::runTest",
    ),
    "a test made with setattr": (
        "refuse",
        {
            "tests/test_lim_setattr.py": (
                "import sys\n\nsetattr(sys.modules[__name__], 'test_made', lambda: None)\n"
            )
        },
        "tests/test_lim_setattr.py::test_made",
    ),
}

# The third review's findings that stay limits: a branch only the run can decide, a name rebound
# on a path only the run takes, a parametrized id (the resolver cannot know a decorator's ids), a
# base from outside the standard library, and two refusals that need an import to be settled.
_KNOWN_LIMITS.update(
    {
        "a def under a branch decided only at run time": (
            "accept",
            {
                "tests/test_lim_branch.py": (
                    "import sys\n\nif sys.version_info < (3, 0):\n\n    def test_x():\n"
                    "        pass\n"
                )
            },
            "tests/test_lim_branch.py::test_x",
        ),
        "a def in an except handler that never runs": (
            "accept",
            {
                "tests/test_lim_except.py": (
                    "try:\n    pass\nexcept Exception:\n\n    def test_x():\n        pass\n"
                )
            },
            "tests/test_lim_except.py::test_x",
        ),
        "a def in a match case that never matches": (
            "accept",
            {
                "tests/test_lim_match.py": (
                    "match 1:\n    case 2:\n\n        def test_x():\n            pass\n"
                )
            },
            "tests/test_lim_match.py::test_x",
        ),
        "a name rebound by a loop over an iterable only the run knows": (
            "accept",
            {
                "tests/test_lim_loop.py": (
                    "def test_x():\n    pass\n\n\nfor test_x in sorted(['a']):\n    pass\n"
                )
            },
            "tests/test_lim_loop.py::test_x",
        ),
        "a name rebound through global": (
            "accept",
            {
                "tests/test_lim_rebind.py": (
                    "def test_x():\n    pass\n\n\ndef rebind():\n    global test_x\n"
                    "    test_x = 1\n\n\nrebind()\n"
                )
            },
            "tests/test_lim_rebind.py::test_x",
        ),
        "an except-as name that deletes a def": (
            "accept",
            {
                "tests/test_lim_exceptas.py": (
                    "def test_x():\n    pass\n\n\ntry:\n    raise ValueError\n"
                    "except ValueError as test_x:\n    pass\n"
                )
            },
            "tests/test_lim_exceptas.py::test_x",
        ),
        "a star import after a def whose module redefines the name": (
            "accept",
            {
                "tests/lim_star.py": "test_x = None\n",
                "tests/test_lim_star.py": "def test_x():\n    pass\n\n\nfrom lim_star import *\n",
            },
            "tests/test_lim_star.py::test_x",
        ),
        "a base from a third-party package that defines __init__": (
            "accept",
            {
                "tests/test_lim_third.py": (
                    "from _pytest.outcomes import OutcomeException\n\n\n"
                    "class TestA(OutcomeException):\n    def test_a(self):\n        pass\n"
                )
            },
            "tests/test_lim_third.py::TestA::test_a",
        ),
        "a parametrized id that does not exist": (
            "accept",
            {
                "tests/test_lim_param.py": (
                    "import pytest\n\n\n@pytest.mark.parametrize('a', [1, 2])\n"
                    "def test_p(a):\n    pass\n"
                )
            },
            "tests/test_lim_param.py::test_p[nonexistent]",
        ),
        "a test assigned by tuple unpacking": (
            "refuse",
            {"tests/test_lim_tuple.py": "test_x, = [lambda: None]\n"},
            "tests/test_lim_tuple.py::test_x",
        ),
        "a star import that overrides a base class defined above it": (
            "refuse",
            {
                "tests/lim_base.py": "class TestBase:\n    def test_b(self):\n        pass\n",
                "tests/test_lim_override.py": (
                    "class TestBase:\n    def test_a(self):\n        pass\n\n\n"
                    "from lim_base import *\n\n\nclass TestA(TestBase):\n    pass\n"
                ),
            },
            "tests/test_lim_override.py::TestA::test_b",
        ),
        "a base defined in each arm of a run-time if": (
            "refuse",
            {
                "tests/test_lim_arms.py": (
                    "import sys\n\nif sys.version_info >= (3, 0):\n\n    class TestBase:\n"
                    "        def test_a(self):\n            pass\n\nelse:\n\n"
                    "    class TestBase:\n        def test_b(self):\n            pass\n\n\n"
                    "class TestA(TestBase):\n    pass\n"
                )
            },
            "tests/test_lim_arms.py::TestA::test_a",
        ),
    }
)
