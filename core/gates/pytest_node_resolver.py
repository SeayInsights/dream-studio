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
    defaults baked in here; `__test__ = True` collects a name pytest would otherwise skip and a
    falsy `__test__` (`False`, `0`, `None`, assigned in the body, inherited, or set from
    outside as `test_x.__test__ = False`) removes one;
  * a module namespace is built statement by statement, so a later binding wins, an
    alias of a test (`test_b = test_a`) is collected under its own name, an imported
    test is collected (unless `collect_imported_tests = false`), `del` removes, and a
    `with ... as test_x` or `for test_x in <non-empty literal>` target rebinds the name;
  * a class is collected when its name matches, it defines no `__init__`/`__new__`, does not
    set a falsy `__test__`, and holds at least one test pytest would collect; its members
    are those of its real C3 linearisation (so a diamond resolves the way Python resolves it),
    with bases found in the same file or elsewhere in the repo;
  * a base class that is defined later in the file than the class using it, a base list with
    no consistent MRO, and a top-level relative import in a directory that is not a package
    all raise at import, so pytest collects nothing from the file, and the resolver says that;
  * `from x import *` binds what `x.__all__` lists when that is a literal list, otherwise the
    public names, and a star import whose `__all__` cannot be evaluated is named as the doubt.

WHAT IT DOES NOT PRETEND TO KNOW. When a name cannot be found and a base class could not be
read (it lives outside the repository, or is not a plain name), the answer is a failure that
names that base -- never an acceptance. Accepting on doubt is the fail-open this gate exists to
remove. Branches whose condition cannot be evaluated statically (`if sys.platform ...`) are
accepted: either arm may run, and the gate cannot tell which; the same goes for a `def` inside a
`try` whose import might fail. `if False`, `if 0`, `if TYPE_CHECKING`, `if __name__ == "__main__"`
and a module constant bound to a literal (`DEBUG = False`; `if DEBUG:`) never run under pytest
and are skipped.

DELIBERATELY NOT MODELLED, each of them accepted or refused as noted, never guessed:

  * a SKIPPED test still resolves. Skipping (`@pytest.mark.skip`, `pytestmark`,
    `pytest.skip(allow_module_level=True)`, `skipif`, `xfail`) is a run-time outcome, and pytest
    collects the test either way; the question this answers is whether the enforcer is there to
    run, not whether it runs green on this machine;
  * a decorator that replaces the function with something else (one that returns `None` or an
    `int`) cannot be evaluated statically; the decorated def is taken at its word;
  * tests created dynamically (`setattr`, `pytest_generate_tests`, a generator or `exec`), an
    abstract class (`ABC` with an abstract method, which pytest skips), `-o python_files=...` or
    any option given on a command line or in `PYTEST_ADDOPTS` (only the repo's config and its
    `addopts` are read), and plugins installed in the environment;
  * `-k`, `-m`, `--noconftest`, `--confcutdir`, `--pyargs`, `--import-mode` and `-p <plugin>` in
    `addopts` change collection in ways that need marks or imports to evaluate; a repo that sets
    one gets a configuration error rather than a guess.
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


class _Module:
    def __init__(self, path: Path, tree: ast.Module) -> None:
        self.path = path
        self.tree = tree
        self.stars: list[tuple[str, int]] = []
        #: id(def or class node) -> the `__test__` assigned from outside its body
        self.flags: dict[int, Any] = {}
        #: id(class node) -> what was visible when its bases were evaluated
        self.befores: dict[int, _Seen] = {}
        #: why importing this file raises, so that pytest collects nothing from it
        self.poison: list[str] = []
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
                elif isinstance(stmt, ast.Expr) and _skips_the_module(stmt.value):
                    self.poison.append(
                        f"line {stmt.lineno} skips the module at import "
                        "(`pytest.skip(..., allow_module_level=True)`), so pytest collects "
                        "nothing from the file"
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
    if node is None:
        return _UNKNOWN
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
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
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return bool(node.elts) and not any(isinstance(e, ast.Starred) for e in node.elts)
    if isinstance(node, ast.Dict):
        return bool(node.keys) and None not in node.keys
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


def _bind_target(
    target: ast.expr,
    value: ast.expr | None,
    scope: dict[str, _Binding],
    conditional: bool,
    mod: _Module,
) -> None:
    if isinstance(target, ast.Name):
        if isinstance(value, ast.Name) and value.id in scope:
            _set(scope, target.id, scope[value.id], conditional)  # an alias of a def or class
        elif isinstance(value, ast.Lambda):  # pytest collects a lambda: it is a function
            _set(scope, target.id, _Binding("def", value, mod), conditional)
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
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        scope[stmt.name] = _Binding("def", stmt, mod)
    elif isinstance(stmt, ast.ClassDef):
        mod.befores[id(stmt)] = _Seen({**(outer or {}), **scope}, tuple(mod.stars))
        scope[stmt.name] = _Binding("class", stmt, mod)
    elif isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            _bind_target(target, stmt.value, scope, cond, mod)
    elif isinstance(stmt, ast.AnnAssign):
        if stmt.value is not None:
            _bind_target(stmt.target, stmt.value, scope, cond, mod)
    elif isinstance(stmt, ast.AugAssign):
        _bind_target(stmt.target, None, scope, cond, mod)
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
                scope[alias.asname or alias.name] = _Binding(
                    "import", mod=mod, target=(module, stmt.level, alias.name)
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
        _bind_body(stmt.body, mod, scope, cond, outer)
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
        runs = _non_empty_literal(stmt.iter)  # an empty or unknown iterable may bind nothing
        _bind_target(stmt.target, None, scope, cond or not runs, mod)
        _bind_body(stmt.body, mod, scope, cond or not runs, outer)
        _bind_body(stmt.orelse, mod, scope, True, outer)
    elif isinstance(stmt, ast.While):
        if _static_truth(stmt.test, scope, outer) is not False:
            _bind_body(stmt.body, mod, scope, True, outer)
        _bind_body(stmt.orelse, mod, scope, True, outer)
    elif isinstance(stmt, ast.Match):
        for case in stmt.cases:
            _bind_body(case.body, mod, scope, True, outer)


def _is_fixture(node: ast.AST) -> bool:
    for decorator in getattr(node, "decorator_list", []):
        expr = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(expr, ast.Name) and expr.id == "fixture":
            return True
        if isinstance(expr, ast.Attribute) and expr.attr == "fixture":
            return True
    return False


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

    # -- files ------------------------------------------------------------

    def _load(self, path: Path) -> _Module | str:
        """The parsed module, or the reason it cannot be. Parsed from bytes so the
        tokenizer applies a BOM or a coding cookie exactly as the interpreter does."""
        if path not in self._modules:
            try:
                tree = ast.parse(path.read_bytes(), filename=str(path))
                self._modules[path] = _Module(path, tree)
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
        not (a stdlib or third-party import); a string when the import itself cannot work."""
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
            if found is None:
                sub = self._find_module(
                    f"{module}.{name}" if module else str(name), level, binding.mod
                )
                if isinstance(sub, _Module):
                    return _Binding("module", mod=sub), None
                return binding, f"is imported from `{where}`, which does not define it"
            binding = found
        return binding, "is reached through an import chain too long to follow"

    # -- classes ----------------------------------------------------------

    def _base(self, expr: ast.expr, mod: _Module, seen: _Seen) -> tuple[str, Any]:
        """How one base class reads: ("class", (node, module)) | ("unittest", name) |
        ("ignore", None) | ("unresolved", text)."""
        text = ast.unparse(expr)
        if isinstance(expr, ast.Name):
            binding = self._lookup_in(mod, seen.names, seen.stars, expr.id)
            if binding is None:
                if hasattr(builtins, expr.id):
                    return "ignore", None
                return "unresolved", f"{text} (not defined in the file)"
            followed, why = self._follow(binding)
            if why:
                target = binding.target
                if target and target[0] == "unittest" and target[2] in _UNITTEST_BASES:
                    return "unittest", target[2]
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
            if isinstance(node, ast.Name):
                root = self._lookup_in(mod, seen.names, seen.stars, node.id)
                if root is not None:
                    followed, _ = self._follow(root)
                    if followed.kind == "module":
                        parts.reverse()
                        if followed.target is not None:
                            dotted = ".".join([followed.target[0], *parts[:-1]]).strip(".")
                            if dotted == "unittest" and parts[-1] in _UNITTEST_BASES:
                                return "unittest", parts[-1]
                            other = self._find_module(dotted, 0, mod)
                        else:  # a submodule imported by name, already loaded
                            other = followed.mod if len(parts) == 1 else None
                        if isinstance(other, _Module):
                            found = self._lookup(other, parts[-1])
                            if found is not None:
                                inner, why = self._follow(found)
                                if not why and inner.kind == "class":
                                    return "class", (inner.node, inner.mod)
                        return "unresolved", f"{text} (outside the repository or not a class)"
            return "unresolved", f"{text} (cannot be read statically)"
        return "unresolved", f"{text} (cannot be read statically)"

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
            sequences: list[list[Any]] = []
            direct: list[Any] = []
            for expr in node.bases:
                kind, payload = self._base(expr, mod, seen)
                if kind == "class":
                    inner = self._class_info(*payload)
                    if inner.error:
                        info.error = f"has a base `{ast.unparse(expr)}` that {inner.error}"
                    sequences.append(inner.lin)
                    direct.append(inner.lin[0])
                    info.classes.update(inner.classes)
                    info.unresolved.extend(inner.unresolved)
                    info.unittest = info.unittest or inner.unittest
                elif kind == "unittest":
                    chain = list(_UNITTEST_BASES[payload])
                    sequences.append(chain)
                    direct.append(chain[0])
                    info.unittest = True
                elif kind == "unresolved":
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
        if _is_fixture(node):
            return f"`{name}` is a fixture, not a test"
        if _verdict(flag) is False:
            return f"`{name}` sets __test__ = {flag!r}, so pytest never collects it"
        return None

    def _class_problem(self, name: str, info: _ClassInfo) -> str | None:
        flag = self._flag(info)
        if not info.unittest:
            if not (_name_matches(self.rules.python_classes, name) or flag is True):
                return (
                    f"class `{name}` does not match python_classes "
                    f"({' '.join(self.rules.python_classes)}), so pytest never collects it"
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

    # -- the walk ---------------------------------------------------------

    def file_problem(self, file_part: str) -> str | None:
        """Why a directory run would not collect the file a reference names without naming a
        test in it, else None. Judged only for a file that is named like a test file AND lies
        under `testpaths`: elsewhere the name is not evidence the file is meant as a test
        (`core/gates/test_isolation.py` is a gate that happens to be called that), and
        existence is the caller's check."""
        path = self._inside(file_part)
        if path is None or not path.is_file():
            return None
        if not any(fnmatch_ex(p, path) for p in self.rules.python_files):
            return None
        if not self.rules.under_a_root(path):
            return None
        return (
            self._case_problem(path)
            or self.rules.conftest_problem(path)
            or self.rules.excluded(path)
        )

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
        excluded = self.rules.excluded(path)
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
            mod.scope  # noqa: B018 -- building the namespace is what finds what poisons the file
            if mod.poison:
                return mod.poison[0]
            for stmt in mod.tree.body:  # a class that cannot be built raises while importing
                if isinstance(stmt, ast.ClassDef):
                    error = self._class_info(stmt, mod).error
                    if error:
                        return f"class `{stmt.name}` {error}; pytest collects nothing from the file"
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
