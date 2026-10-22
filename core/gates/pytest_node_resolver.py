"""Decide from source alone whether pytest would collect a node id.

`canonical/rules.yml` names tests as `file.py::Class::test_name`. A name that does not
resolve is an enforcer that is not there, so the rule-enforcement gate needs an answer to
"does this node exist" that does not import the test module (a test module may need a
database, a network, or fixtures no gate should set up, and importing it runs whatever
sits at module level on every push).

THE QUESTION IS "WOULD A DIRECTORY RUN OF PYTEST COLLECT IT", NOT "IS THAT NAME DEFINED".
Finding the name proves the line was typed. The first version of this check asked only that,
and it accepts things pytest skips -- a function not matching `python_functions`, a fixture, a
class with `__init__` or `__test__ = False`, a def later shadowed by an assignment or `del`, a
def under `if TYPE_CHECKING:` -- and each of those is a rule that names an enforcer which
never runs. The second version resolved the test but not the run: pytest given a file by name
collects things a directory run never reaches, and CI runs directories. So this walks what
pytest walks, in two layers.

LAYER ONE, WHICH FILES A DIRECTORY RUN REACHES (`core/gates/pytest_collection_rules.py`):

  * the file must sit inside the repository, match `python_files` and lie under `testpaths`;
  * no directory above it may match `norecursedirs` (pytest's default set unless the repo
    names its own), be `__pycache__` or a virtualenv, or be named by `--ignore` /
    `--ignore-glob` in `addopts` or by `collect_ignore` / `collect_ignore_glob` in the NEAREST
    conftest that defines it; `--deselect` prefixes in `addopts` remove the node itself;
  * a conftest that defines a collection hook, or a `collect_ignore` that is not a literal
    list of strings, makes the answer one this gate cannot give, and it says so instead.

LAYER TWO, WHICH TESTS A FILE HOLDS:

  * names follow `python_functions` / `python_classes` from the repo's own pytest config
    (pytest.toml, pytest.ini, pyproject.toml, tox.ini, setup.cfg, in pytest's order), not
    defaults baked in here; an option that is present and empty is empty, not the default;
    `__test__ = True` collects a name pytest would otherwise skip and a falsy `__test__`
    (`False`, `0`, `None`, assigned in the body, inherited, or set from outside as
    `test_x.__test__ = False`) removes one;
  * a module namespace is built statement by statement, so a later binding wins, an alias of a
    test (`test_b = test_a`, also `= module.attr`, `= functools.partial(test_a)`, a lambda, a
    function assigned in a class body) is collected under its own name, an imported test is
    collected (unless `collect_imported_tests = false`), `del`, a `with ... as test_x`, a walrus
    and a `for test_x in <non-empty literal>` target rebind the name, and the body of a `for`
    over an empty literal never runs;
  * a class is collected when its name matches, it is not abstract (`ABC` or `ABCMeta` with a
    method marked abstract and not overridden), it gets no `__init__`/`__new__` (its own, a
    `@dataclass`, a builtin base that has one such as dict, Exception, int, list, str, tuple or
    type, or an Enum, NamedTuple, TypedDict or Protocol base), does not set a falsy `__test__`,
    and holds at least one test pytest would collect; its members are those of its real C3
    linearisation (so a diamond resolves the way Python resolves it) with bases found in the
    same file or elsewhere in the repo, a subscripted base (`Base[int]`) standing for `Base`;
  * a `@property` is not callable and a fixture, also through `from pytest import fixture as
    fx`, is not a test;
  * a condition is decided when it is a constant, `not`/`and`/`or` over constants, a module
    constant bound to one, `__name__ == "__main__"`, or `TYPE_CHECKING` however imported;
  * a file that raises when imported is refused whole, for the causes a static read can PROVE: a
    top-level `raise` or false `assert`, a base class defined later in the file or nowhere it
    could come from, bases with no consistent MRO, a top-level relative import in a directory
    that is not a package, a top-level `pytest.skip(..., allow_module_level=True)`, an import of
    a module a regular repository package lacks, of a name a repository module does not define
    (when it makes names by no route a static read cannot see), or of a repository helper that
    does not parse;
  * `from x import *` binds what `x.__all__` lists when that is a literal list, otherwise the
    public names, and a star import whose `__all__` cannot be evaluated is named as the doubt;
  * a path is judged as it is SPELLED (`skipme/` is excluded even when it is a link to `real/`)
    and must match the case of the file on disk, as a Linux checkout would require.

WHAT IT DOES NOT PRETEND TO KNOW. When a name cannot be found and a base class could not be
read (it lives outside the repository, or is not a plain name), the answer is a failure that
names that base -- never an acceptance. Accepting on doubt is the fail-open this gate exists to
remove. Branches whose condition cannot be evaluated statically (`if sys.platform ...`) are
accepted: either arm may run, and the gate cannot tell which.

SKIPS. A test skipped by a marker (`@pytest.mark.skip`, `pytestmark`, `skipif`, `xfail`) still
resolves: skipping is a run-time outcome and pytest collects the test either way, so the
question this answers is whether the enforcer is there to run, not whether it runs green on
this machine. A top-level `pytest.skip(..., allow_module_level=True)` is different, because it
raises while the file is imported and no item ever exists, so it is REFUSED; one that is
conditional or reached through a function call is not decidable and is a false accept (below).

THE KNOWN FALSE ACCEPTS: pytest collects nothing and the resolver says yes. Each is a case in
`_KNOWN_LIMITS` (tests/helpers/resolver_cases.py), judged against `pytest --collect-only` by
tests/unit/test_pytest_collection_agreement.py, which fails if one stops being a limit so that
this list is corrected rather than left to rot:

  * a file that fails to import for a reason not provable from source: a module missing from the
    environment or from a namespace directory, a NameError other than an undefined base class,
    a circular import, an `assert` on a condition that cannot be decided, `pytest.importorskip`
    of a missing module, a conditional or function-called `pytest.skip(allow_module_level=True)`;
  * a generator test function (pytest fails the file);
  * a class or function decorator that replaces the object (one that returns `None` or an int)
    or adds an `__init__` (attrs and its kin), and an abstract class reached through a base the
    resolver cannot read;
  * a `def` inside a `try` whose import may fail;
  * options given on a command line or in `PYTEST_ADDOPTS`, `-o python_files=...`, and plugins
    installed in the environment.

THE KNOWN FALSE REFUSALS: pytest collects it and the resolver says no.

  * a base made by a call (`class T(make_base())`) or splatted (`class T(*bases)`) that
    supplies the test; a class built by a factory function; a `def` created through `global`;
    a test made with `setattr`; and `unittest.TestCase.runTest`.

REFUSED CONFIGURATION. `-k`, `-m`, `--noconftest`, `--confcutdir`, `--pyargs`, `--import-mode`,
`--rootdir` and `-p <plugin>` in `addopts` change collection in ways that need marks, imports or
a different rootdir to evaluate; a repo that sets one gets a configuration error, not a guess.
"""

from __future__ import annotations

import ast
import builtins
import fnmatch
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.gates.pytest_collection_rules import (
    DEFAULT_CLASSES,
    DEFAULT_FILES,
    DEFAULT_FUNCTIONS,
    CollectionConfigError,
    CollectionRules,
    Unevaluable,
    fnmatch_ex,
    string_lists,
)

__all__ = [
    "DEFAULT_CLASSES",
    "DEFAULT_FILES",
    "DEFAULT_FUNCTIONS",
    "CollectionConfigError",
    "NodeResolver",
    "load_collection_config",
]

#: Imports followed across files before giving up. A chain this long is not a test layout.
MAX_IMPORT_DEPTH = 8

#: Stdlib bases that define no tests of their own, so a missing name is not hiding in them.
#: Each maps to its own linearisation, nearest first.
_UNITTEST_BASES = {
    "TestCase": ("unittest.TestCase",),
    "IsolatedAsyncioTestCase": ("unittest.IsolatedAsyncioTestCase", "unittest.TestCase"),
}

_TOO_DEEP = "file too deeply nested to analyse"

#: A constant the gate cannot know, and a flag nothing has set.
_UNKNOWN: Any = object()
_ABSENT: Any = object()


def load_collection_config(root: Path) -> dict[str, tuple[str, ...]]:
    rules = CollectionRules(Path(root))
    return {
        "python_files": rules.python_files,
        "python_classes": rules.python_classes,
        "python_functions": rules.python_functions,
    }


def _name_matches(patterns: tuple[str, ...], name: str) -> bool:
    """pytest's rule for classes and functions: a prefix, or a glob when it looks like one."""
    for pattern in patterns:
        if name.startswith(pattern):
            return True
        if any(c in pattern for c in "*?[") and fnmatch.fnmatch(name, pattern):
            return True
    return False


# --------------------------------------------------------------------------
# A module namespace, built the way the interpreter builds it
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Binding:
    kind: str  # def | class | import | module | other
    node: ast.AST | None = None
    mod: _Module | None = None
    target: tuple[str, int, str | None] | None = None  # (module, level, name)
    const: Any = _UNKNOWN  # the literal an `other` was assigned, when it was one


@dataclass(frozen=True)
class _Seen:
    """The names visible at one point of a module: what a class's bases were evaluated against."""

    names: dict[str, _Binding]
    stars: tuple[tuple[str, int], ...]


def _not_a_package(path: Path, level: int) -> bool:
    """A relative import of `level` dots needs `level` directories, the file's own and its
    parents, to be packages; pytest imports a file in a plain directory as a top-level module."""
    directories = [path.parent, *path.parent.parents][:level]
    return len(directories) < level or not all((d / "__init__.py").is_file() for d in directories)


def _skips_the_module(call: ast.expr) -> bool:
    """`pytest.skip(..., allow_module_level=True)` as a statement of its own: it raises while the
    module is imported, so no item is ever created. (A `skip` marker is different: the items
    exist and the skip happens when they run.)"""
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    named = (isinstance(func, ast.Name) and func.id == "skip") or (
        isinstance(func, ast.Attribute) and func.attr == "skip"
    )
    return named and any(
        k.arg == "allow_module_level"
        and isinstance(k.value, ast.Constant)
        and k.value.value is True
        for k in call.keywords
    )


_PYTEST_RAISERS = frozenset({"skip", "xfail", "fail", "exit"})


def _raising_call(expr: ast.expr, lookup: Any) -> str | None:
    """What a top-level expression statement does that always raises while the module is
    imported: `pytest.skip()` (with or without allow_module_level), `pytest.xfail()`,
    `pytest.fail()`, `pytest.exit()`, `sys.exit()`, `exit()`, and a division by a literal zero."""
    if (
        isinstance(expr, ast.BinOp)
        and isinstance(expr.op, (ast.Div, ast.FloorDiv, ast.Mod))
        and isinstance(expr.right, ast.Constant)
        and isinstance(expr.right.value, (int, float))
        and not isinstance(expr.right.value, bool)
        and expr.right.value == 0
    ):
        return "divides by zero"
    if not isinstance(expr, ast.Call):
        return None
    func = expr.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        root = lookup(func.value.id)
        module = root.target[0] if root is not None and root.target else func.value.id
        if module == "pytest" and func.attr in _PYTEST_RAISERS:
            return f"calls `pytest.{func.attr}()`"
        if module == "sys" and func.attr == "exit":
            return "calls `sys.exit()`"
    if isinstance(func, ast.Name):
        bound = lookup(func.id)
        if bound is not None and bound.kind == "import" and bound.target and not bound.target[1]:
            module, name = bound.target[0], bound.target[2]
            if module == "pytest" and name in _PYTEST_RAISERS:
                return f"calls `pytest.{name}()`"
            if module == "sys" and name == "exit":
                return "calls `sys.exit()`"
        if bound is None and func.id in ("exit", "quit"):
            return f"calls `{func.id}()`"
    return None


class _Module:
    def __init__(self, path: Path, tree: ast.Module, raw: bytes = b"") -> None:
        self.path = path
        self.tree = tree
        self.raw = raw
        self.stars: list[tuple[str, int]] = []
        #: id(def or class node) -> the `__test__` assigned from outside its body
        self.flags: dict[int, Any] = {}
        #: id(class node) -> what was visible when its bases were evaluated
        self.befores: dict[int, _Seen] = {}
        #: why importing this file raises, so that pytest collects nothing from it
        self.poison: list[str] = []
        #: whether the file makes names by globals(), exec and the like (read once)
        self.dynamic: bool | None = None
        #: how many `try` bodies with handlers the binding walk is inside
        self.guard = 0
        #: why importing the file provably raises, once worked out (None: nothing provable)
        self.failure: Any = _ABSENT
        self._scope: dict[str, _Binding] | None = None
        self._exports: list[str] | Unevaluable | None | Any = _ABSENT

    @property
    def scope(self) -> dict[str, _Binding]:
        if self._scope is None:
            scope: dict[str, _Binding] = {}
            late: list[tuple[str, str, int]] = []
            for stmt in self.tree.body:
                if isinstance(stmt, ast.ClassDef) and not self.stars:
                    late.extend(
                        (stmt.name, base.id, stmt.lineno)
                        for base in stmt.bases
                        if isinstance(base, ast.Name)
                        and base.id not in scope
                        and not hasattr(builtins, base.id)
                    )
                elif isinstance(stmt, ast.ImportFrom) and stmt.level:
                    if _not_a_package(self.path, stmt.level):
                        self.poison.append(
                            f"line {stmt.lineno} imports `{'.' * stmt.level}{stmt.module or ''}` "
                            "from a directory that is not a package (no `__init__.py`), so the "
                            "import raises ImportError and pytest collects nothing from the file"
                        )
                elif isinstance(stmt, ast.Raise):
                    self.poison.append(
                        f"line {stmt.lineno} always raises at import (a top-level `raise`), so "
                        "pytest collects nothing from the file"
                    )
                elif isinstance(stmt, ast.Assert) and _static_truth(stmt.test, scope) is False:
                    self.poison.append(
                        f"line {stmt.lineno} asserts a condition that is always false at import, "
                        "so pytest collects nothing from the file"
                    )
                elif isinstance(stmt, ast.Expr) and _skips_the_module(stmt.value):
                    self.poison.append(
                        f"line {stmt.lineno} skips the module at import "
                        "(`pytest.skip(..., allow_module_level=True)`), so pytest collects "
                        "nothing from the file"
                    )
                elif isinstance(stmt, ast.Expr) and _raising_call(stmt.value, scope.get):
                    self.poison.append(
                        f"line {stmt.lineno} {_raising_call(stmt.value, scope.get)} at the top "
                        "level, which always raises while importing, so pytest collects nothing "
                        "from the file"
                    )
                elif (
                    isinstance(stmt, ast.AugAssign)
                    and isinstance(stmt.target, ast.Name)
                    and stmt.target.id not in scope
                    and not hasattr(builtins, stmt.target.id)
                    and not self.stars
                ):
                    self.poison.append(
                        f"line {stmt.lineno} augments `{stmt.target.id}` before it is defined, "
                        "which raises NameError while importing, so pytest collects nothing "
                        "from the file"
                    )
                _bind_stmt(stmt, self, scope, False, None)
            for cls, base, line in late:
                if base in scope:
                    self.poison.append(
                        f"class `{cls}` (line {line}) uses base `{base}` before it is defined "
                        "in the file, so importing it raises NameError and pytest collects "
                        "nothing from the file"
                    )
            self._scope = scope
        return self._scope

    @property
    def exports(self) -> list[str] | Unevaluable | None:
        """What `from this import *` binds: a literal `__all__`, `Unevaluable` when it is
        defined in a form that cannot be read, else None (every public name)."""
        if self._exports is _ABSENT:
            self._exports = string_lists(self.tree, ("__all__",)).get("__all__")
        return self._exports


def _literal(node: ast.expr | None) -> Any:
    """The value of a constant expression: a literal, or `not`/`and`/`or` over constants."""
    if node is None:
        return _UNKNOWN
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return _combined_constant(node)


def _combined_constant(node: ast.expr) -> Any:
    """`not x`, `a and b` and `a or b` over constants, or _UNKNOWN when anything is not one."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        inner = _literal(node.operand)
        return _UNKNOWN if inner is _UNKNOWN else (not inner)
    if isinstance(node, ast.BoolOp):
        values = [_literal(v) for v in node.values]
        if _UNKNOWN in values:
            return _UNKNOWN
        keep_going = isinstance(node.op, ast.And)  # `and` goes on while truthy, `or` while falsy
        picked = values[0]
        for value in values[1:]:
            if bool(picked) == keep_going:
                picked = value
        return picked
    return _UNKNOWN


def _static_truth(
    test: ast.expr, scope: dict[str, _Binding], outer: dict[str, _Binding] | None = None
) -> bool | None:
    """True/False when the condition is decidable without running anything, else None."""
    if isinstance(test, ast.Constant):
        return bool(test.value)
    if isinstance(test, ast.Name):
        if test.id == "TYPE_CHECKING":
            return False
        bound = scope.get(test.id) or (outer or {}).get(test.id)
        if bound is not None and bound.kind == "other" and bound.const is not _UNKNOWN:
            return bool(bound.const)
        if bound is not None and bound.kind == "import" and bound.target is not None:
            if bound.target[2] == "TYPE_CHECKING":  # `from typing import TYPE_CHECKING as TC`
                return False
        return None
    if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
        return False
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = _static_truth(test.operand, scope, outer)
        return None if inner is None else not inner
    if isinstance(test, ast.BoolOp):
        parts = [_static_truth(v, scope, outer) for v in test.values]
        decisive = isinstance(test.op, ast.Or)  # one True decides `or`, one False decides `and`
        if decisive in parts:
            return decisive
        return None if None in parts else not decisive
    if (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.ops) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    ):
        if isinstance(test.ops[0], ast.Eq):
            return False
        if isinstance(test.ops[0], ast.NotEq):
            return True
    return None


def _non_empty_literal(node: ast.expr) -> bool:
    """A `for` over this runs at least once, so its target is bound for certain."""
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):  # one element that is not `*x` suffices
        return any(not isinstance(e, ast.Starred) for e in node.elts)
    if isinstance(node, ast.Dict):  # a key of None is a `**x`, which may add nothing
        return any(k is not None for k in node.keys)
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
        return bool(node.value)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "range"
        and 1 <= len(node.args) <= 2
        and not node.keywords
    ):
        bounds = [_literal(a) for a in node.args]
        if all(isinstance(b, int) and not isinstance(b, bool) for b in bounds):
            return bounds[-1] > (bounds[0] if len(bounds) == 2 else 0)
    return False


def _certainly_empty(node: ast.expr) -> bool:
    """A `for` over this never runs its body (its `else` still runs)."""
    if isinstance(node, (ast.List, ast.Tuple)):
        return not node.elts
    if isinstance(node, ast.Dict):
        return not node.keys
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
        return not node.value
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "range"
        and 1 <= len(node.args) <= 2
        and not node.keywords
    ):
        bounds = [_literal(a) for a in node.args]
        if all(isinstance(b, int) and not isinstance(b, bool) for b in bounds):
            return bounds[-1] <= (bounds[0] if len(bounds) == 2 else 0)
    return False


def _set(scope: dict[str, _Binding], name: str, binding: _Binding, conditional: bool) -> None:
    # A value assigned inside a branch that may not run must not erase a def that is
    # already bound: either outcome is possible and the gate cannot tell which. It does
    # make an earlier literal uncertain, so `DEBUG = False` then a conditional rebind is
    # no longer a constant the gate may branch on.
    if conditional and binding.kind == "other" and name in scope:
        if scope[name].kind == "other":
            scope[name] = _Binding("other")
        return
    scope[name] = binding


def _final_name(expr: ast.expr, lookup: Any) -> str:
    """The name a decorator or base is known by where it was defined, through an import alias:
    `fixture` for `@fx` after `from pytest import fixture as fx`."""
    if isinstance(expr, ast.Name):
        bound = lookup(expr.id)
        if bound is not None and bound.kind == "import" and bound.target and bound.target[2]:
            return bound.target[2]
        return expr.id
    if isinstance(expr, ast.Attribute):
        return expr.attr
    return ""


def _alias_binding(
    value: ast.expr | None,
    scope: dict[str, _Binding],
    outer: dict[str, _Binding] | None,
    mod: _Module,
) -> _Binding | None:
    """The binding a plain assignment gives a name when the value is something pytest collects
    under the new name: another name (an alias of a def or class, from this scope or the one
    around a class body), a lambda, a `functools.partial` of a function, or `module.attr`."""

    def lookup(name: str) -> _Binding | None:
        return scope.get(name) or (outer or {}).get(name)

    if isinstance(value, ast.Name):
        return lookup(value.id)
    if isinstance(value, ast.Lambda):  # pytest collects a lambda: it is a function
        return _Binding("def", value, mod)
    if isinstance(value, ast.Call):
        if value.args and _final_name(value.func, lookup) == "partial":
            first = value.args[0]
            bound = lookup(first.id) if isinstance(first, ast.Name) else None
            if bound is not None and bound.kind in ("def", "import"):
                return bound  # pytest unwraps a partial to the function it wraps
        return None
    if isinstance(value, ast.Attribute):
        parts: list[str] = []
        node: ast.expr = value
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        root = lookup(node.id) if isinstance(node, ast.Name) else None
        if root is not None and root.kind in ("module", "import"):
            return _Binding("attr", mod=mod, const=(root, tuple(reversed(parts))))
    return None


def _bind_walrus(
    expr: ast.expr | None,
    mod: _Module,
    scope: dict[str, _Binding],
    cond: bool,
    outer: dict[str, _Binding] | None,
) -> None:
    """`(name := value)` binds `name` wherever it sits, unless a short-circuit, a conditional
    expression or a comprehension may keep it from running."""
    if expr is None:
        return
    if isinstance(expr, ast.NamedExpr):
        _bind_walrus(expr.value, mod, scope, cond, outer)
        _bind_target(expr.target, expr.value, scope, cond, mod, outer)
    elif isinstance(expr, ast.BoolOp):
        _bind_walrus(expr.values[0], mod, scope, cond, outer)
        for later in expr.values[1:]:
            _bind_walrus(later, mod, scope, True, outer)
    elif isinstance(expr, ast.IfExp):
        _bind_walrus(expr.test, mod, scope, cond, outer)
        _bind_walrus(expr.body, mod, scope, True, outer)
        _bind_walrus(expr.orelse, mod, scope, True, outer)
    elif isinstance(expr, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
        for inner in ast.walk(expr):
            if isinstance(inner, ast.NamedExpr):
                _bind_target(inner.target, inner.value, scope, True, mod, outer)
    elif not isinstance(expr, ast.Lambda):
        for child in ast.iter_child_nodes(expr):
            if isinstance(child, ast.expr):
                _bind_walrus(child, mod, scope, cond, outer)


def _bind_target(
    target: ast.expr,
    value: ast.expr | None,
    scope: dict[str, _Binding],
    conditional: bool,
    mod: _Module,
    outer: dict[str, _Binding] | None = None,
) -> None:
    if isinstance(target, ast.Name):
        alias = _alias_binding(value, scope, outer, mod)
        if alias is not None:
            _set(scope, target.id, alias, conditional)
        else:
            _set(scope, target.id, _Binding("other", const=_literal(value)), conditional)
    elif isinstance(target, (ast.Tuple, ast.List, ast.Starred)):
        for inner in ast.walk(target):
            if isinstance(inner, ast.Name):
                _set(scope, inner.id, _Binding("other"), conditional)
    elif isinstance(target, ast.Attribute) and target.attr == "__test__" and not conditional:
        holder = scope.get(target.value.id) if isinstance(target.value, ast.Name) else None
        if holder is not None and holder.kind in ("def", "class") and holder.node is not None:
            mod.flags[id(holder.node)] = _literal(value)


def _bind_body(
    body: list[ast.stmt],
    mod: _Module,
    scope: dict[str, _Binding],
    conditional: bool,
    outer: dict[str, _Binding] | None,
) -> None:
    for stmt in body:
        _bind_stmt(stmt, mod, scope, conditional, outer)


def _bind_stmt(
    stmt: ast.stmt,
    mod: _Module,
    scope: dict[str, _Binding],
    cond: bool,
    outer: dict[str, _Binding] | None,
) -> None:
    if isinstance(stmt, ast.Expr):
        _bind_walrus(stmt.value, mod, scope, cond, outer)
    elif isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        _bind_walrus(stmt.value, mod, scope, cond, outer)
    elif isinstance(stmt, (ast.If, ast.While)):
        _bind_walrus(stmt.test, mod, scope, cond, outer)

    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        scope[stmt.name] = _Binding("def", stmt, mod)
    elif isinstance(stmt, ast.ClassDef):
        mod.befores[id(stmt)] = _Seen({**(outer or {}), **scope}, tuple(mod.stars))
        scope[stmt.name] = _Binding("class", stmt, mod)
    elif isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            _bind_target(target, stmt.value, scope, cond, mod, outer)
    elif isinstance(stmt, ast.AnnAssign):
        if stmt.value is not None:
            _bind_target(stmt.target, stmt.value, scope, cond, mod, outer)
    elif isinstance(stmt, ast.AugAssign):
        _bind_target(stmt.target, None, scope, cond, mod, outer)
    elif isinstance(stmt, ast.Delete):
        if not cond:
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    scope.pop(target.id, None)
    elif isinstance(stmt, ast.Import):
        for alias in stmt.names:
            bound = alias.asname or alias.name.split(".")[0]
            full = alias.name if alias.asname else alias.name.split(".")[0]
            scope[bound] = _Binding("module", mod=mod, target=(full, 0, None))
    elif isinstance(stmt, ast.ImportFrom):
        module = stmt.module or ""
        for alias in stmt.names:
            if alias.name == "*":
                mod.stars.append((module, stmt.level))
            else:
                name = alias.asname or alias.name
                prev = scope.get(name)
                if (cond or mod.guard) and prev is not None and prev.kind in ("def", "class"):
                    continue  # the import may not happen (a try/except ImportError, an `if`)
                scope[name] = _Binding(
                    "import",
                    mod=mod,
                    target=(module, stmt.level, alias.name),
                    const=prev if prev is not None else _UNKNOWN,
                )
    elif isinstance(stmt, ast.If):
        truth = _static_truth(stmt.test, scope, outer)
        if truth is True:
            _bind_body(stmt.body, mod, scope, cond, outer)
        elif truth is False:
            _bind_body(stmt.orelse, mod, scope, cond, outer)
        else:  # cannot be decided here: either arm may run, so both are accepted
            _bind_body(stmt.body, mod, scope, True, outer)
            _bind_body(stmt.orelse, mod, scope, True, outer)
    elif isinstance(stmt, (ast.Try, getattr(ast, "TryStar", ast.Try))):
        mod.guard += bool(stmt.handlers)  # an import in the body may fail into a handler
        _bind_body(stmt.body, mod, scope, cond, outer)
        mod.guard -= bool(stmt.handlers)
        for handler in stmt.handlers:
            _bind_body(handler.body, mod, scope, True, outer)
        _bind_body(stmt.orelse, mod, scope, cond, outer)
        _bind_body(stmt.finalbody, mod, scope, cond, outer)
    elif isinstance(stmt, (ast.With, ast.AsyncWith)):
        for item in stmt.items:  # `as name` binds before the body runs, whatever the body does
            if item.optional_vars is not None:
                _bind_target(item.optional_vars, None, scope, cond, mod)
        _bind_body(stmt.body, mod, scope, cond, outer)
    elif isinstance(stmt, (ast.For, ast.AsyncFor)):
        if _certainly_empty(stmt.iter):  # the body never runs; the `else` always does
            _bind_body(stmt.orelse, mod, scope, cond, outer)
        else:
            runs = _non_empty_literal(stmt.iter)  # an unknown iterable may bind nothing
            _bind_target(stmt.target, None, scope, cond or not runs, mod, outer)
            _bind_body(stmt.body, mod, scope, cond or not runs, outer)
            _bind_body(stmt.orelse, mod, scope, True, outer)
    elif isinstance(stmt, ast.While):
        if _static_truth(stmt.test, scope, outer) is not False:
            _bind_body(stmt.body, mod, scope, True, outer)
        _bind_body(stmt.orelse, mod, scope, True, outer)
    elif isinstance(stmt, ast.Match):
        for case in stmt.cases:
            _bind_body(case.body, mod, scope, True, outer)


def _decorators(node: ast.AST, mod: _Module) -> list[tuple[str, ast.expr]]:
    """Each decorator as (the name it is known by where defined, the expression)."""
    found = []
    for decorator in getattr(node, "decorator_list", []):
        expr = decorator.func if isinstance(decorator, ast.Call) else decorator
        found.append((_final_name(expr, mod.scope.get), decorator))
    return found


def _is_fixture(node: ast.AST, mod: _Module) -> bool:
    return any(name == "fixture" for name, _ in _decorators(node, mod))


#: Decorators whose result is not a callable test: `@property` and its relatives.
_NOT_CALLABLE = frozenset({"property", "cached_property", "setter", "getter", "deleter"})

#: Decorators that mark a method abstract.
_ABSTRACT = frozenset(
    {"abstractmethod", "abstractproperty", "abstractclassmethod", "abstractstaticmethod"}
)

#: Stdlib bases that bring an `__init__` or `__new__` of their own, which pytest will not collect.
_ENUM_BASES = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag", "ReprEnum"})
_TYPING_CONSTRUCTING = frozenset({"NamedTuple", "TypedDict", "Protocol"})


def _stdlib_base(module: str, name: str) -> str | None:
    """What a base imported from the stdlib means: "unittest", "constructs" (it brings an
    __init__ or __new__), "abc" (it makes the class abstract-capable), "ignore" (it adds nothing
    to look at), or None for a base this does not know."""
    if module == "unittest" and name in _UNITTEST_BASES:
        return "unittest"
    if module == "enum" and name in _ENUM_BASES:
        return "constructs"
    if module in ("typing", "typing_extensions"):
        if name in _TYPING_CONSTRUCTING:
            return "constructs"
        if name == "Generic":
            return "ignore"
    if module == "abc" and name == "ABC":
        return "abc"
    return None


def _dataclass_problem(node: ast.ClassDef, mod: _Module) -> str | None:
    """A `@dataclass` class is not collected: it gains an `__init__`, and with the default
    `eq=True` it loses `__hash__`, which pytest needs of the instance it collects from. Only
    `init=False` with `eq=False` leaves a class pytest can collect."""
    for name, decorator in _decorators(node, mod):
        if name != "dataclass":
            continue
        if isinstance(decorator, ast.Call):
            switched_off = {
                k.arg
                for k in decorator.keywords
                if k.arg in ("init", "eq")
                and isinstance(k.value, ast.Constant)
                and k.value.value is False
            }
            if switched_off == {"init", "eq"}:
                return None
        return "its `@dataclass` decorator"
    return None


def _verdict(flag: Any) -> bool | None:
    """What `getattr(obj, "__test__", True)` comes to: True/False, or None when the gate
    cannot know the value."""
    if flag is _ABSENT:
        return True
    if flag is _UNKNOWN:
        return None
    return bool(flag)


@dataclass
class _ClassInfo:
    node: ast.ClassDef
    mod: _Module
    own: dict[str, _Binding] = field(default_factory=dict)
    #: C3 linearisation: this class's key first, then bases. Keys are id(node) for a class
    #: the resolver can read, "unittest.X" for a stdlib base, "?n" for one it cannot.
    lin: list[Any] = field(default_factory=list)
    classes: dict[Any, _ClassInfo] = field(default_factory=dict)
    members: dict[str, _Binding] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)
    unittest: bool = False
    error: str | None = None
    #: why the class has an `__init__` or `__new__` it does not define itself, if it does
    constructor: str | None = None
    #: whether `abc.ABC` or `ABCMeta` is in play, so an unimplemented abstract method counts
    abc: bool = False


def _c3(sequences: list[list[Any]]) -> list[Any] | None:
    """Python's C3 merge, or None when the bases have no consistent order."""
    work = [list(s) for s in sequences if s]
    merged: list[Any] = []
    while work:
        for sequence in work:
            head = sequence[0]
            if not any(head in other[1:] for other in work):
                break
        else:
            return None
        merged.append(head)
        for sequence in work:
            if sequence[0] == head:
                del sequence[0]
        work = [s for s in work if s]
    return merged


# --------------------------------------------------------------------------
# The resolver
# --------------------------------------------------------------------------


def _split_parameters(node_part: str) -> tuple[str, str | None]:
    """The node path with its parameter id cut off, or why the brackets are not one. Parameter
    ids are generated at collection time and may hold `::` themselves, so the cut is made at
    the first `[` and the id must close the whole id: `test_x[a::b]` is one, `TestA[x]::test_x`
    is not (pytest ids hang off a function, never a class)."""
    head, bracket, tail = node_part.partition("[")
    if bracket and (not tail.endswith("]") or "]::" in tail):
        return head, "a parameter id `[...]` can only close the last segment of a node id"
    return head, None


class NodeResolver:
    """Resolves node ids against one repository. One instance per audit: files are parsed
    once however many rules name them."""

    def __init__(self, repo_root: Path) -> None:
        self.root = Path(repo_root).resolve()
        self.rules = CollectionRules(self.root)
        self.config = {
            "python_files": self.rules.python_files,
            "python_classes": self.rules.python_classes,
            "python_functions": self.rules.python_functions,
        }
        self._modules: dict[Path, _Module | str] = {}
        self._classes: dict[int, _ClassInfo] = {}
        self._building: set[int] = set()
        self._opaque = 0
        self._listings: dict[Path, list[str]] = {}
        self._found: dict[tuple[str, int, Path], _Module | str | None] = {}

    # -- files ------------------------------------------------------------

    def _load(self, path: Path) -> _Module | str:
        """The parsed module, or the reason it cannot be. Parsed from bytes so the
        tokenizer applies a BOM or a coding cookie exactly as the interpreter does."""
        if path not in self._modules:
            try:
                raw = path.read_bytes()
                tree = ast.parse(raw, filename=str(path))
                self._modules[path] = _Module(path, tree, raw)
            except SyntaxError as exc:
                self._modules[path] = f"test file does not parse (line {exc.lineno})"
            except (MemoryError, RecursionError):
                self._modules[path] = f"test file too deeply nested to analyse ({path.name})"
            except (ValueError, UnicodeDecodeError, OSError):
                self._modules[path] = "test file is not readable as python source"
        return self._modules[path]

    def _inside(self, file_part: str) -> Path | None:
        """The path as it is SPELLED when it lies within the repository, else None.

        pytest walks directories as they are spelled, so an exclusion applies to `skipme/` even
        when that is a link to `real/`: the spelled path is what is judged. A link that leads
        out of the repository is still refused by where it really points, since the file would
        not be in a checkout."""
        spelled = Path(os.path.abspath(self.root / file_part))
        if not spelled.is_relative_to(self.root) or not spelled.resolve().is_relative_to(self.root):
            return None
        return spelled

    def _listing(self, directory: Path) -> list[str]:
        if directory not in self._listings:
            try:
                self._listings[directory] = os.listdir(directory)
            except OSError:
                self._listings[directory] = []
        return self._listings[directory]

    def _case_problem(self, path: Path) -> str | None:
        """Windows finds `TESTS/Test_A.PY` for `tests/test_a.py`; a Linux checkout, which is
        what CI is, does not. Every component must be spelled as it is on disk."""
        current = self.root
        for part in path.relative_to(self.root).parts:
            names = self._listing(current)
            if names and part not in names:
                actual = next((n for n in names if n.lower() == part.lower()), None)
                if actual is not None:
                    return (
                        f"`{part}` differs in case from `{actual}` on disk, so a case-sensitive "
                        "checkout, which CI is, would not find it"
                    )
            current = current / part
        return None

    def _find_module(self, name: str, level: int, origin: _Module) -> _Module | str | None:
        """An imported module that lives in the repository, best effort. None when it does
        not (a stdlib or third-party import); a string when the import itself cannot work.
        Asked about the same import many times as the import graph is walked, so remembered."""
        key = (name, level, origin.path)
        if key not in self._found:
            self._found[key] = self._find_module_uncached(name, level, origin)
        return self._found[key]

    def _find_module_uncached(self, name: str, level: int, origin: _Module) -> _Module | str | None:
        if level:
            if _not_a_package(origin.path, level):
                return (
                    "is a relative import from a directory that is not a package "
                    "(no `__init__.py`), which raises ImportError"
                )
            bases = [origin.path.parent.parents[level - 2]] if level > 1 else [origin.path.parent]
        else:
            bases = [self.root, origin.path.parent]
        parts = [p for p in name.split(".") if p]
        for base in bases:
            target = base.joinpath(*parts) if parts else base
            for candidate in (target.with_suffix(".py") if parts else None, target / "__init__.py"):
                if candidate is None or not candidate.is_file():
                    continue
                inside = self._inside(str(candidate))
                if inside is not None:
                    return self._load(inside)
        return None

    # -- names ------------------------------------------------------------

    def _lookup_in(
        self,
        mod: _Module,
        names: dict[str, _Binding],
        stars: tuple[tuple[str, int], ...],
        name: str,
        depth: int = 0,
    ) -> _Binding | None:
        found = names.get(name)
        if found is not None or depth >= MAX_IMPORT_DEPTH:
            return found
        for module, level in stars:
            other = self._find_module(module, level, mod)
            if not isinstance(other, _Module):
                continue
            exported = other.exports
            if isinstance(exported, Unevaluable):
                continue  # named as a doubt by _star_doubts when the name is not found
            if exported is not None:
                if name not in exported:
                    continue
            elif name.startswith("_"):  # a star import binds public names only
                continue
            found = self._lookup_in(other, other.scope, tuple(other.stars), name, depth + 1)
            if found is not None:
                return found
        return None

    def _lookup(self, mod: _Module, name: str) -> _Binding | None:
        return self._lookup_in(mod, mod.scope, tuple(mod.stars), name)

    def _star_doubts(self, mod: _Module) -> list[str]:
        doubts = []
        for module, level in mod.stars:
            other = self._find_module(module, level, mod)
            if isinstance(other, _Module) and isinstance(other.exports, Unevaluable):
                where = ("." * level) + module
                doubts.append(f"`from {where} import *`, whose __all__ cannot be evaluated")
        return doubts

    def _follow(self, binding: _Binding) -> tuple[_Binding, str | None]:
        """Follow imports until a def, class, module or plain value. The second item is
        why it could not, naming the import."""
        for _ in range(MAX_IMPORT_DEPTH):
            if binding.kind == "attr":  # `x = module.attr`
                root, parts = binding.const
                assert binding.mod is not None
                found, why = self._resolve_attribute(root, parts, binding.mod)
                if found is None:
                    return binding, why
                binding = found
                continue
            if binding.kind != "import":
                return binding, None
            assert binding.target is not None and binding.mod is not None
            module, level, name = binding.target
            other = self._find_module(module, level, binding.mod)
            where = ("." * level) + module
            if other is None:
                return binding, f"is imported from `{where}`, which is outside the repository"
            if isinstance(other, str):
                return binding, f"is imported from `{where}`, which {other}"
            found = self._lookup(other, name or "")
            if found is binding:  # the module imports a name from itself, bound by this very import
                if isinstance(binding.const, _Binding):
                    binding = binding.const  # what the name was before the import ran
                    continue
                return binding, "is imported from the module that holds it, so it is not defined"
            if found is None:
                sub = self._find_module(
                    f"{module}.{name}" if module else str(name), level, binding.mod
                )
                if isinstance(sub, _Module):
                    return _Binding("module", mod=sub), None
                return binding, f"is imported from `{where}`, which does not define it"
            binding = found
        return binding, "is reached through an import chain too long to follow"

    def _resolve_attribute(
        self, root: _Binding, parts: tuple[str, ...] | list[str], mod: _Module
    ) -> tuple[_Binding | None, str | None]:
        """What `root.a.b` names when `root` is a module in the repository: its binding, or
        None and why it cannot be said. ("unittest.TestCase" style stdlib names are the
        caller's business: `unittest` is not in the repository.)"""
        followed, why = self._follow(root)
        if why or followed.kind != "module":
            return None, "is read from something that is not a module in the repository"
        if followed.target is not None:
            dotted = ".".join([followed.target[0], *parts[:-1]]).strip(".")
            other = self._find_module(dotted, 0, mod)
        else:  # a submodule imported by name, already loaded
            other = followed.mod if len(parts) == 1 else None
            dotted = ""
        if isinstance(other, str):
            return None, f"is read from `{dotted}`, which {other}"
        if other is None:
            return None, "is read from a module outside the repository"
        found = self._lookup(other, parts[-1])
        if found is None:
            return None, f"is read from `{dotted or other.path.stem}`, which does not define it"
        return found, None

    # -- classes ----------------------------------------------------------

    def _base(self, expr: ast.expr, mod: _Module, seen: _Seen) -> tuple[str, Any]:
        """How one base class reads: ("class", (node, module)) | ("unittest", name) |
        ("constructs", text) | ("abc", None) | ("ignore", None) | ("unresolved", text)."""
        text = ast.unparse(expr)
        if isinstance(expr, ast.Subscript):  # `Base[int]`: a Generic alias stands for its origin
            kind, payload = self._base(expr.value, mod, seen)
            if kind in ("unresolved", "constructs"):
                return kind, payload.replace(ast.unparse(expr.value), text, 1)
            return kind, payload

        def lookup(name: str) -> _Binding | None:
            return self._lookup_in(mod, seen.names, seen.stars, name)

        if isinstance(expr, ast.Name):
            binding = lookup(expr.id)
            if binding is None:
                found = getattr(builtins, expr.id, None)
                if isinstance(found, type):
                    # a builtin brings its own constructor unless it inherits object's
                    if found.__init__ is not object.__init__ or found.__new__ is not object.__new__:
                        return "constructs", text
                    return "ignore", None
                if found is not None:
                    return "ignore", None
                return "unresolved", f"{text} (not defined in the file)"
            followed, why = self._follow(binding)
            if why:
                target = binding.target
                std = _stdlib_base(target[0], target[2]) if target and not target[1] else None
                if std is not None:
                    return self._stdlib_kind(std, target[2], text)  # type: ignore[index]
                return "unresolved", f"{text} ({why})"
            if followed.kind == "class":
                return "class", (followed.node, followed.mod)
            return "unresolved", f"{text} (not a class)"
        if isinstance(expr, ast.Attribute):
            parts: list[str] = []
            node: ast.expr = expr
            while isinstance(node, ast.Attribute):
                parts.append(node.attr)
                node = node.value
            parts.reverse()
            root = lookup(node.id) if isinstance(node, ast.Name) else None
            if root is not None:
                followed, _ = self._follow(root)
                if followed.kind == "module" and followed.target is not None:
                    dotted = ".".join([followed.target[0], *parts[:-1]]).strip(".")
                    std = _stdlib_base(dotted, parts[-1])
                    if std is not None:
                        return self._stdlib_kind(std, parts[-1], text)
                found, why = self._resolve_attribute(root, parts, mod)
                if found is not None:
                    inner, why = self._follow(found)
                    if not why and inner.kind == "class":
                        return "class", (inner.node, inner.mod)
                return "unresolved", f"{text} (outside the repository or not a class)"
        return "unresolved", f"{text} (cannot be read statically)"

    @staticmethod
    def _stdlib_kind(std: str, name: str, text: str) -> tuple[str, Any]:
        if std == "unittest":
            return "unittest", name
        if std == "constructs":
            return "constructs", text
        return std, None

    def _class_info(self, node: ast.ClassDef, mod: _Module) -> _ClassInfo:
        key = id(node)
        if key in self._classes:
            return self._classes[key]
        info = _ClassInfo(node, mod, lin=[key])
        if key in self._building:  # a base cycle; stop rather than recurse forever
            info.error = "is part of an inheritance cycle"
            return info
        self._building.add(key)
        try:
            seen = mod.befores.get(id(node)) or _Seen(mod.scope, tuple(mod.stars))
            _bind_body(node.body, mod, info.own, False, seen.names)
            for body_stmt in node.body:  # a statement that always raises while the body runs
                if (
                    isinstance(body_stmt, ast.Raise)
                    or (
                        isinstance(body_stmt, ast.Assert)
                        and _static_truth(body_stmt.test, info.own, seen.names) is False
                    )
                    or (
                        isinstance(body_stmt, ast.Expr)
                        and _raising_call(body_stmt.value, info.own.get)
                    )
                ):
                    info.error = info.error or (
                        "has a body that always raises while it runs, so importing the file raises"
                    )
            sequences: list[list[Any]] = []
            direct: list[Any] = []
            info.constructor = _dataclass_problem(node, mod)
            info.abc = any(
                kw.arg == "metaclass" and _final_name(kw.value, mod.scope.get) == "ABCMeta"
                for kw in node.keywords
            )
            for expr in node.bases:
                kind, payload = self._base(expr, mod, seen)
                if kind == "constructs":
                    info.constructor = info.constructor or f"its base `{payload}`"
                elif kind == "abc":
                    info.abc = True
                elif kind == "class":
                    inner = self._class_info(*payload)
                    if inner.error:
                        info.error = f"has a base `{ast.unparse(expr)}` that {inner.error}"
                    sequences.append(inner.lin)
                    direct.append(inner.lin[0])
                    info.classes.update(inner.classes)
                    info.unresolved.extend(inner.unresolved)
                    info.unittest = info.unittest or inner.unittest
                    info.abc = info.abc or inner.abc
                    if inner.constructor and not info.constructor:
                        info.constructor = f"{inner.constructor} on its base `{ast.unparse(expr)}`"
                elif kind == "unittest":
                    chain = list(_UNITTEST_BASES[payload])
                    sequences.append(chain)
                    direct.append(chain[0])
                    info.unittest = True
                elif kind == "unresolved":
                    if payload.endswith("(not defined in the file)") and self._names_certain(
                        mod, seen
                    ):
                        info.error = info.error or (
                            f"has a base `{ast.unparse(expr)}` that is not defined anywhere it "
                            "could come from, so importing the file raises NameError"
                        )
                    self._opaque += 1
                    placeholder = f"?{self._opaque}"
                    sequences.append([placeholder])
                    direct.append(placeholder)
                    info.unresolved.append(payload)
            merged = _c3([*sequences, direct])
            if merged is None:
                info.error = info.error or (
                    "has bases with no consistent method resolution order, so importing "
                    "it raises TypeError"
                )
                merged = [k for s in sequences for k in s]
            info.lin = [key, *merged]
            info.classes[key] = info
            for member in reversed(info.lin):
                owner = info.classes.get(member)
                if owner is not None:
                    info.members.update(owner.own)
        finally:
            self._building.discard(key)
        self._classes[key] = info
        return info

    def _flag(self, info: _ClassInfo) -> Any:
        """`__test__` as getattr would find it: the nearest class in the MRO that sets it, an
        assignment from outside its body winning over one inside."""
        for key in info.lin:
            owner = info.classes.get(key)
            if owner is None:
                continue
            outside = owner.mod.flags.get(id(owner.node), _ABSENT)
            if outside is not _ABSENT:
                return outside
            inside = owner.own.get("__test__")
            if inside is not None:
                return inside.const if inside.kind == "other" else _UNKNOWN
        return _ABSENT

    def _function_problem(
        self, name: str, node: ast.AST, mod: _Module, in_unittest: bool
    ) -> str | None:
        flag = mod.flags.get(id(node), _ABSENT)
        if in_unittest:
            if not name.startswith("test"):
                return f"`{name}` does not start with `test`, so unittest never runs it"
        elif not (_name_matches(self.rules.python_functions, name) or flag is True):
            return (
                f"`{name}` does not match python_functions "
                f"({' '.join(self.rules.python_functions)}), so pytest never collects it"
            )
        if _is_fixture(node, mod):
            return f"`{name}` is a fixture, not a test"
        if any(decorated in _NOT_CALLABLE for decorated, _ in _decorators(node, mod)):
            return f"`{name}` is a property, which is not callable, so pytest never collects it"
        if _verdict(flag) is False:
            return f"`{name}` sets __test__ = {flag!r}, so pytest never collects it"
        return None

    def _names_certain(self, mod: _Module, seen: _Seen) -> bool:
        """Whether a name missing from `seen` is missing for certain: every star import before it
        is a module in the repository (an outside one may supply anything) and the file does not
        make names by `globals()`, `exec` and the like."""
        if any(
            not isinstance(self._find_module(module, level, mod), _Module)
            for module, level in seen.stars
        ):
            return False
        return not any(
            isinstance(n, ast.Name) and n.id in self._DYNAMIC for n in ast.walk(mod.tree)
        )

    def _is_abstract(self, info: _ClassInfo) -> bool:
        """`inspect.isabstract`: the class is built on `abc.ABC` or `ABCMeta` and the nearest
        definition of some method in its MRO is still marked abstract."""
        if not info.abc:
            return False
        for binding in info.members.values():
            if binding.kind == "def" and binding.mod is not None and binding.node is not None:
                if any(n in _ABSTRACT for n, _ in _decorators(binding.node, binding.mod)):
                    return True
        return False

    def _class_problem(self, name: str, info: _ClassInfo) -> str | None:
        flag = self._flag(info)
        if not info.unittest:
            if not (_name_matches(self.rules.python_classes, name) or flag is True):
                return (
                    f"class `{name}` does not match python_classes "
                    f"({' '.join(self.rules.python_classes)}), so pytest never collects it"
                )
            if self._is_abstract(info):
                return (
                    f"class `{name}` is abstract (a method marked abstract is not overridden), "
                    "so pytest never collects it"
                )
            if info.constructor:
                return (
                    f"class `{name}` gets __init__ or __new__ from {info.constructor}, "
                    "so pytest never collects it"
                )
            if "__init__" in info.members or "__new__" in info.members:
                return f"class `{name}` defines __init__ or __new__, so pytest never collects it"
        if _verdict(flag) is False:
            return f"class `{name}` sets __test__ = {flag!r}, so pytest never collects it"
        return None

    def _has_tests(self, info: _ClassInfo, depth: int = 0) -> bool:
        """Whether pytest finds anything in this class: a collectable method, or a nested
        class that itself holds one."""
        if depth >= MAX_IMPORT_DEPTH:
            return False
        for name, binding in info.members.items():
            followed, why = self._follow(binding)
            if why or followed.node is None or followed.mod is None:
                continue
            if followed.kind == "def":
                if self._function_problem(name, followed.node, followed.mod, info.unittest) is None:
                    return True
            elif followed.kind == "class" and not info.unittest:
                inner = self._class_info(followed.node, followed.mod)  # type: ignore[arg-type]
                if (
                    not inner.error
                    and self._class_problem(name, inner) is None
                    and self._has_tests(inner, depth + 1)
                ):
                    return True
        return False

    # -- imports a static read can prove fail ---------------------------------

    #: A module that reaches names by a route a static read cannot follow.
    _DYNAMIC = frozenset({"globals", "locals", "vars", "setattr", "exec", "eval", "__getattr__"})

    def _rel(self, path: Path) -> str:
        return (
            path.relative_to(self.root).as_posix() if path.is_relative_to(self.root) else str(path)
        )

    def _package_bases(self, level: int, origin: _Module) -> list[Path]:
        """Where an import of `level` dots looks: the sys.path entries a test is run with for an
        absolute one, the file's own package (or a parent of it) for a relative one."""
        if level == 0:
            return [self.root, origin.path.parent]
        parents = origin.path.parent.parents
        if level == 1:
            return [origin.path.parent]
        return [parents[level - 2]] if level - 2 < len(parents) else []

    def _uses_dynamic_names(self, mod: _Module) -> bool:
        if mod.dynamic is None and not any(name.encode() in mod.raw for name in self._DYNAMIC):
            mod.dynamic = False  # none of the words appears in the source at all
        if mod.dynamic is None:
            mod.dynamic = any(
                (isinstance(n, ast.Name) and n.id in self._DYNAMIC)
                or (
                    isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.name in self._DYNAMIC
                )
                for n in ast.walk(mod.tree)
            )
        return mod.dynamic

    def _missing_submodule(self, dotted: str, origin: _Module, level: int = 0) -> str | None:
        """Why `import a.b.c` (or `from .a.b import c`) provably fails: the first name is a
        regular package here and some name below it has no such module, or is a module that
        cannot hold the next name. Nothing else is claimed: a namespace directory, or a first
        name that is not a package in the repository, may be completed from somewhere a static
        read cannot see."""
        parts = dotted.split(".") if dotted else []
        missing: str | None = None
        for base in self._package_bases(level, origin):
            if level == 0:
                current = base / parts[0]
                if not (current / "__init__.py").is_file():
                    continue
                chain = parts[1:]
            else:
                current, chain = base, parts
            for index, part in enumerate(chain):
                if (current / part / "__init__.py").is_file():
                    current = current / part
                elif (current / f"{part}.py").is_file():
                    if index < len(chain) - 1:
                        module_file = self._rel(current / f"{part}.py")
                        missing = f"`{module_file}` is a module, not a package"
                        break
                    return None  # the last name is a module that exists
                elif (current / part).is_dir():
                    return None  # a namespace directory: not provable
                else:
                    missing = f"package `{self._rel(current)}` has no module `{part}`"
                    break
            else:
                return None  # the whole chain exists
        return missing

    def _missing_name(self, stmt: ast.ImportFrom, other: _Module, origin: _Module) -> str | None:
        """Why `from m import name` provably fails: `m` is a repository module (this very file
        included: a name it never defines cannot be imported from it) that defines no such name
        by any route a static read can see, and `name` is not a submodule."""
        other.scope  # noqa: B018 -- the star imports are known only once the namespace is built
        if self._uses_dynamic_names(other):
            return None
        for star_module, star_level in other.stars:
            if not isinstance(self._find_module(star_module, star_level, other), _Module):
                return None  # a star import from outside may supply anything
        module = stmt.module or ""
        for alias in stmt.names:
            found = self._lookup(other, alias.name)
            if (
                found is not None
                and other is origin
                and found.kind == "import"
                and found.target == (module, stmt.level, alias.name)
                and not isinstance(found.const, _Binding)
            ):
                found = None  # bound by this very statement: nothing defines it
            if alias.name == "*" or found is not None:
                continue
            submodule = f"{module}.{alias.name}" if module else alias.name
            if self._find_module(submodule, stmt.level, origin) is not None:
                continue  # a submodule
            if any(
                base.joinpath(*[p for p in module.split(".") if p], alias.name).is_dir()
                for base in self._package_bases(stmt.level, origin)
            ):
                continue  # a namespace directory
            where = ("." * stmt.level) + module
            return f"line {stmt.lineno} imports `{alias.name}` from `{where}`, which does not define it"
        return None

    def _module_chain_problem(
        self, dotted: str, level: int, stmt: ast.stmt, origin: _Module, seen: set[Path], ending: str
    ) -> str | None:
        """Importing `a.b.c` runs `a`, then `a.b`, then `a.b.c`: each is a repository module that
        may itself fail."""
        parts = [p for p in dotted.split(".") if p]
        for end in range(1, len(parts) + 1):
            name = ".".join(parts[:end])
            other = self._find_module(name, level, origin)
            where = ("." * level) + name
            if isinstance(other, str):
                return f"line {stmt.lineno} imports `{where}`, which {other}, {ending}"
            if isinstance(other, _Module) and self.rules.under_a_root(other.path):
                # only what the test run itself owns is followed: a product module that cannot be
                # imported breaks far more than one rule, and walking all of them is the cost
                inner = self._import_failure(other, seen)
                if inner:
                    return (
                        f"line {stmt.lineno} imports `{where}`, which fails to import "
                        f"({inner}), {ending}"
                    )
        return None

    def _import_problem(self, mod: _Module, seen: set[Path]) -> str | None:
        """An import statement of the file that provably raises, directly or because a
        repository module it imports does. Only top-level statements are read: one inside a
        `try`, an `if` or a function may never run."""
        ending = "so importing the file raises and pytest collects nothing from the file"
        for stmt in mod.tree.body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    why = self._missing_submodule(alias.name, mod)
                    if why:
                        return f"line {stmt.lineno} imports `{alias.name}`, but {why}, {ending}"
                    problem = self._module_chain_problem(alias.name, 0, stmt, mod, seen, ending)
                    if problem:
                        return problem
            elif isinstance(stmt, ast.ImportFrom) and (stmt.module or stmt.level):
                module = stmt.module or ""
                why = self._missing_submodule(module, mod, stmt.level) if module else None
                if why:
                    where = ("." * stmt.level) + module
                    return f"line {stmt.lineno} imports from `{where}`, but {why}, {ending}"
                problem = self._module_chain_problem(module, stmt.level, stmt, mod, seen, ending)
                if problem:
                    return problem
                other = self._find_module(module, stmt.level, mod)
                if isinstance(other, _Module):
                    why = self._missing_name(stmt, other, mod)
                    if why:
                        return f"{why}, {ending}"
                    for alias in stmt.names:  # a name that is a submodule is imported too
                        if alias.name == "*" or self._lookup(other, alias.name) is not None:
                            continue
                        sub_name = f"{module}.{alias.name}" if module else alias.name
                        problem = self._module_chain_problem(
                            sub_name, stmt.level, stmt, mod, seen, ending
                        )
                        if problem:
                            return problem
        return None

    def _import_failure(self, mod: _Module, seen: set[Path] | None = None) -> str | None:
        """Why importing this module provably raises: a statement that always raises, an import
        that cannot work, a class that cannot be built, or any of those in a repository module
        it imports. None when nothing is provable (a cycle is walked once, not followed)."""
        if mod.failure is not _ABSENT:
            return mod.failure
        seen = set() if seen is None else seen
        if mod.path in seen:
            return None
        seen.add(mod.path)
        mod.scope  # noqa: B018 -- building the namespace is what finds what poisons the file
        failure = mod.poison[0] if mod.poison else self._import_problem(mod, seen)
        if failure is None:
            for stmt in mod.tree.body:  # a class that cannot be built raises while importing
                if isinstance(stmt, ast.ClassDef):
                    error = self._class_info(stmt, mod).error
                    if error:
                        failure = (
                            f"class `{stmt.name}` {error}; pytest collects nothing from the file"
                        )
                        break
        mod.failure = failure
        return failure

    def _duplicate_problem(self, path: Path) -> str | None:
        """pytest imports a test file in a directory with no `__init__.py` as a top-level module
        named after the file, so a second one with the same name, collected later, fails with
        "import file mismatch"."""
        if (path.parent / "__init__.py").is_file():
            return None
        files = self.rules.collected_files()
        if path not in files:
            return None
        for other in files:
            if other == path:
                return None
            if other.name == path.name and not (other.parent / "__init__.py").is_file():
                return (
                    f"`{path.name}` is also `{self._rel(other)}`, which pytest imports first as "
                    "the same top-level module, so this one fails with an import file mismatch "
                    "and pytest collects nothing from the file"
                )
        return None

    def _file_has_tests(self, mod: _Module) -> bool:
        """Whether the file holds a test pytest would collect, by any name it binds."""
        for name, binding in mod.scope.items():
            followed, why = self._follow(binding)
            if why or followed.node is None or followed.mod is None:
                continue
            if not self.rules.collect_imported_tests and followed.mod is not mod:
                continue
            if followed.kind == "def":
                if self._function_problem(name, followed.node, followed.mod, False) is None:
                    return True
            elif followed.kind == "class":
                info = self._class_info(followed.node, followed.mod)  # type: ignore[arg-type]
                if not info.error and self._class_problem(name, info) is None:
                    if self._has_tests(info):
                        return True
        return False

    # -- the walk ---------------------------------------------------------

    def file_problem(self, file_part: str) -> str | None:
        """Why a directory run would not collect the file a reference names without naming a
        test in it, or would collect nothing from it, else None. Judged only for a file that is
        named like a test file AND lies under `testpaths`: elsewhere the name is not evidence
        the file is meant as a test (`core/gates/test_isolation.py` is a gate that happens to be
        called that), and existence is the caller's check."""
        path = self._inside(file_part)
        if path is None or not path.is_file():
            return None
        if not any(fnmatch_ex(p, path) for p in self.rules.python_files):
            return None
        if not self.rules.under_a_root(path):
            return None
        problem = (
            self._case_problem(path)
            or self.rules.conftest_problem(path)
            or self.rules.excluded(path)
            or self._duplicate_problem(path)
        )
        if problem:
            return problem
        mod = self._load(path)
        if isinstance(mod, str):
            return mod
        try:
            problem = self._import_failure(mod)
            if problem:
                return problem
            flag = mod.scope.get("__test__")
            if flag is not None and flag.kind == "other" and _verdict(flag.const) is False:
                return f"the module sets __test__ = {flag.const!r}, so pytest collects nothing"
            if not self._file_has_tests(mod):
                return "the file holds no test pytest would collect"
        except (RecursionError, MemoryError):
            return _TOO_DEEP
        return None

    def resolve(self, reference: str) -> str | None:
        """None when pytest would collect the node; otherwise why it would not."""
        file_part, _, node_part = reference.partition("::")
        nodeid_tail = node_part
        node_part, malformed = _split_parameters(node_part)

        path = self._inside(file_part)
        if path is None:
            return "path escapes the repository"
        if not path.is_file():
            return "no such test file"
        problem = self._case_problem(path)
        if problem:
            return problem
        if path.suffix != ".py":
            return "node id into a non-python file"
        relative = path.relative_to(self.root).as_posix()

        problem = self.rules.conftest_problem(path)
        if problem:
            return problem
        patterns = self.rules.python_files
        if not self.rules.explicit(path) and not any(fnmatch_ex(p, path) for p in patterns):
            return (
                f"file does not match python_files ({' '.join(patterns) or 'none set'}), so a directory "
                "run never collects it"
            )
        excluded = self.rules.excluded(path) or self._duplicate_problem(path)
        if excluded:
            return excluded
        deselected = self.rules.deselected_by(
            relative + (f"::{nodeid_tail}" if nodeid_tail else "")
        )
        if deselected:
            return deselected

        if malformed:
            return malformed
        segments = node_part.split("::")
        if not all(segments):
            return "empty segment in node id"

        mod = self._load(path)
        if isinstance(mod, str):
            return mod
        try:
            failure = self._import_failure(mod)
            if failure:
                return failure
            return self._walk(mod, segments, file_part)
        except (RecursionError, MemoryError):
            return _TOO_DEEP

    def _walk(self, mod: _Module, segments: list[str], file_part: str) -> str | None:
        module_flag = mod.scope.get("__test__")
        if module_flag is not None and module_flag.kind == "other":
            if _verdict(module_flag.const) is False:
                return (
                    f"the module sets __test__ = {module_flag.const!r}, so pytest collects "
                    "nothing from it"
                )
        members: dict[str, _Binding] | None = None
        cls: _ClassInfo | None = None

        for position, name in enumerate(segments):
            last = position == len(segments) - 1
            where = "::".join(segments[:position]) or file_part

            binding = self._lookup(mod, name) if cls is None else (members or {}).get(name)
            if binding is None:
                message = f"no `{name}` defined in {where}"
                if cls is not None and cls.unresolved:
                    message += f" (bases not searched: {'; '.join(cls.unresolved)})"
                if cls is None and self._star_doubts(mod):
                    message += f" (not searched: {'; '.join(self._star_doubts(mod))})"
                return message

            followed, why = self._follow(binding)
            if why:
                return f"`{name}` {why}"
            if followed.kind not in ("def", "class"):
                return f"`{name}` is not a function or class in {where} (it is assigned a value)"
            if cls is None and followed.mod is not mod and not self.rules.collect_imported_tests:
                return (
                    f"`{name}` is imported from another module and collect_imported_tests is "
                    "false, so pytest does not collect it from here"
                )

            if followed.kind == "def":
                if not last:
                    return f"`{name}` is a function, not a class holding tests"
                assert followed.node is not None and followed.mod is not None
                return self._function_problem(
                    name, followed.node, followed.mod, cls is not None and cls.unittest
                )

            assert isinstance(followed.node, ast.ClassDef) and followed.mod is not None
            info = self._class_info(followed.node, followed.mod)
            if cls is not None and cls.unittest:
                return f"`{name}` is a class nested in a unittest class, which is not collected"
            if info.error:
                return f"class `{name}` {info.error}"
            problem = self._class_problem(name, info)
            if problem:
                return problem
            if last:
                if not self._has_tests(info):
                    return f"class `{name}` holds no test pytest would collect"
                return None
            cls = info
            members = info.members
        return None
