"""Decide from source alone whether pytest would collect a node id.

`canonical/rules.yml` names tests as `file.py::Class::test_name`. A name that does not
resolve is an enforcer that is not there, so the rule-enforcement gate needs an answer to
"does this node exist" that does not import the test module (a test module may need a
database, a network, or fixtures no gate should set up, and importing it runs whatever
sits at module level on every push).

THE QUESTION IS "WOULD PYTEST COLLECT IT", NOT "IS THAT NAME DEFINED". Finding the name
proves the line was typed. The first version of this check asked only that, and it accepts
things pytest skips -- a function not matching `python_functions`, a fixture, a class
with `__init__` or `__test__ = False`, a def later shadowed by an assignment or `del`, a
def under `if TYPE_CHECKING:` -- and each of those is a rule that names an enforcer which
never runs. So this walks what pytest walks:

  * the file must sit inside the repository and match `python_files`;
  * names follow `python_functions` / `python_classes` from the repo's own pytest config
    (pytest.ini, pyproject.toml, tox.ini, setup.cfg, in pytest's order), not defaults
    baked in here;
  * a module namespace is built statement by statement, so a later binding wins, an
    alias of a test (`test_b = test_a`) is collected under its own name, an imported
    test is collected, and `del` removes;
  * a class is collected when its name matches, it defines no `__init__`/`__new__` and
    does not set `__test__ = False`; its members include those inherited from bases in the
    same file or elsewhere in the repo.

WHAT IT DOES NOT PRETEND TO KNOW. When a name cannot be found and a base class could not be
read (it lives outside the repository, or is not a plain name), the answer is a failure that
names that base -- never an acceptance. Accepting on doubt is the fail-open this gate exists to
remove. Branches whose condition cannot be evaluated statically (`if sys.platform ...`) are
accepted: either arm may run, and the gate cannot tell which. `if False`, `if 0`,
`if TYPE_CHECKING` and `if __name__ == "__main__"` never run under pytest and are skipped.
`-o python_files=...` passed on a command line is not read; only the config files are.
"""

from __future__ import annotations

import ast
import builtins
import configparser
import fnmatch
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_FILES = ("test_*.py", "*_test.py")
DEFAULT_CLASSES = ("Test",)
DEFAULT_FUNCTIONS = ("test",)

#: Imports followed across files before giving up. A chain this long is not a test layout.
MAX_IMPORT_DEPTH = 8

#: Stdlib bases that define no tests of their own, so a missing name is not hiding in them.
_UNITTEST_BASES = frozenset({"TestCase", "IsolatedAsyncioTestCase"})

_TOO_DEEP = "file too deeply nested to analyse"


# --------------------------------------------------------------------------
# pytest's own collection config
# --------------------------------------------------------------------------


def _split(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    return tuple(str(value).split())


class CollectionConfigError(ValueError):
    """The repo's pytest config exists and cannot be read. Falling back to pytest's defaults
    would judge names by rules the repo does not use, so it is an error, not a shrug."""


def _read_ini(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError) as exc:
        raise CollectionConfigError(f"cannot read pytest config {path.name}: {exc}") from exc
    return parser


def _ini_section(root: Path) -> dict[str, Any]:
    """The pytest ini section pytest itself would pick, in its order of precedence."""
    for name in ("pytest.ini", ".pytest.ini"):
        path = root / name
        if path.is_file():
            parser = _read_ini(path)
            return dict(parser["pytest"]) if parser.has_section("pytest") else {}

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as exc:
            raise CollectionConfigError(f"cannot read pytest config pyproject.toml: {exc}") from exc
        options = data.get("tool", {}).get("pytest", {}).get("ini_options")
        if isinstance(options, dict):
            return options

    for name, section in (("tox.ini", "pytest"), ("setup.cfg", "tool:pytest")):
        path = root / name
        if path.is_file():
            parser = _read_ini(path)
            if parser.has_section(section):
                return dict(parser[section])
    return {}


def load_collection_config(root: Path) -> dict[str, tuple[str, ...]]:
    section = _ini_section(root)
    return {
        "python_files": _split(section.get("python_files")) or DEFAULT_FILES,
        "python_classes": _split(section.get("python_classes")) or DEFAULT_CLASSES,
        "python_functions": _split(section.get("python_functions")) or DEFAULT_FUNCTIONS,
    }


def _name_matches(patterns: tuple[str, ...], name: str) -> bool:
    """pytest's rule for classes and functions: a prefix, or a glob."""
    return any(name.startswith(p) or fnmatch.fnmatchcase(name, p) for p in patterns)


def _file_matches(patterns: tuple[str, ...], relative: str) -> bool:
    base = relative.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(relative if "/" in p else base, p) for p in patterns)


# --------------------------------------------------------------------------
# A module namespace, built the way the interpreter builds it
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Binding:
    kind: str  # def | class | import | module | other
    node: ast.AST | None = None
    mod: _Module | None = None
    target: tuple[str, int, str | None] | None = None  # (module, level, name)
    const: Any = None


class _Module:
    def __init__(self, path: Path, tree: ast.Module) -> None:
        self.path = path
        self.tree = tree
        self.stars: list[tuple[str, int]] = []
        self._scope: dict[str, _Binding] | None = None

    @property
    def scope(self) -> dict[str, _Binding]:
        if self._scope is None:
            scope: dict[str, _Binding] = {}
            _bind_body(self.tree.body, self, scope, False)
            self._scope = scope
        return self._scope


def _static_truth(test: ast.expr) -> bool | None:
    """True/False when the condition is decidable without running anything, else None."""
    if isinstance(test, ast.Constant):
        return bool(test.value)
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return False
    if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
        return False
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = _static_truth(test.operand)
        return None if inner is None else not inner
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


def _set(scope: dict[str, _Binding], name: str, binding: _Binding, conditional: bool) -> None:
    # A value assigned inside a branch that may not run must not erase a def that is
    # already bound: either outcome is possible and the gate cannot tell which.
    if conditional and binding.kind == "other" and name in scope:
        return
    scope[name] = binding


def _bind_target(
    target: ast.expr,
    value: ast.expr | None,
    scope: dict[str, _Binding],
    conditional: bool,
) -> None:
    if isinstance(target, ast.Name):
        if isinstance(value, ast.Name) and value.id in scope:
            _set(scope, target.id, scope[value.id], conditional)  # an alias of a def or class
        elif isinstance(value, ast.Constant):
            _set(scope, target.id, _Binding("other", const=value.value), conditional)
        else:
            _set(scope, target.id, _Binding("other"), conditional)
    elif isinstance(target, (ast.Tuple, ast.List, ast.Starred)):
        for inner in ast.walk(target):
            if isinstance(inner, ast.Name):
                _set(scope, inner.id, _Binding("other"), conditional)


def _bind_body(
    body: list[ast.stmt], mod: _Module, scope: dict[str, _Binding], conditional: bool
) -> None:
    for stmt in body:
        _bind_stmt(stmt, mod, scope, conditional)


def _bind_stmt(stmt: ast.stmt, mod: _Module, scope: dict[str, _Binding], cond: bool) -> None:
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        scope[stmt.name] = _Binding("def", stmt, mod)
    elif isinstance(stmt, ast.ClassDef):
        scope[stmt.name] = _Binding("class", stmt, mod)
    elif isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            _bind_target(target, stmt.value, scope, cond)
    elif isinstance(stmt, ast.AnnAssign):
        if stmt.value is not None:
            _bind_target(stmt.target, stmt.value, scope, cond)
    elif isinstance(stmt, ast.AugAssign):
        _bind_target(stmt.target, None, scope, cond)
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
        truth = _static_truth(stmt.test)
        if truth is True:
            _bind_body(stmt.body, mod, scope, cond)
        elif truth is False:
            _bind_body(stmt.orelse, mod, scope, cond)
        else:  # cannot be decided here: either arm may run, so both are accepted
            _bind_body(stmt.body, mod, scope, True)
            _bind_body(stmt.orelse, mod, scope, True)
    elif isinstance(stmt, (ast.Try, getattr(ast, "TryStar", ast.Try))):
        _bind_body(stmt.body, mod, scope, cond)
        for handler in stmt.handlers:
            _bind_body(handler.body, mod, scope, True)
        _bind_body(stmt.orelse, mod, scope, cond)
        _bind_body(stmt.finalbody, mod, scope, cond)
    elif isinstance(stmt, (ast.With, ast.AsyncWith)):
        _bind_body(stmt.body, mod, scope, cond)
    elif isinstance(stmt, (ast.For, ast.AsyncFor)):
        _bind_body(stmt.body, mod, scope, True)
        _bind_body(stmt.orelse, mod, scope, True)
    elif isinstance(stmt, ast.While):
        if _static_truth(stmt.test) is not False:
            _bind_body(stmt.body, mod, scope, True)
        _bind_body(stmt.orelse, mod, scope, True)
    elif isinstance(stmt, ast.Match):
        for case in stmt.cases:
            _bind_body(case.body, mod, scope, True)


def _is_fixture(node: ast.AST) -> bool:
    for decorator in getattr(node, "decorator_list", []):
        expr = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(expr, ast.Name) and expr.id == "fixture":
            return True
        if isinstance(expr, ast.Attribute) and expr.attr == "fixture":
            return True
    return False


@dataclass
class _ClassInfo:
    members: dict[str, _Binding] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)
    unittest: bool = False


# --------------------------------------------------------------------------
# The resolver
# --------------------------------------------------------------------------


class NodeResolver:
    """Resolves node ids against one repository. One instance per audit: files are parsed
    once however many rules name them."""

    def __init__(self, repo_root: Path) -> None:
        self.root = Path(repo_root).resolve()
        self.config = load_collection_config(self.root)
        self._modules: dict[Path, _Module | str] = {}
        self._classes: dict[int, _ClassInfo] = {}
        self._building: set[int] = set()

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
        """The resolved path when it lies within the repository, else None."""
        resolved = (self.root / file_part).resolve()
        return resolved if resolved.is_relative_to(self.root) else None

    def _find_module(self, name: str, level: int, origin: _Module) -> _Module | str | None:
        """An imported module that lives in the repository, best effort. None when it does
        not (a stdlib or third-party import)."""
        if level:
            parents = origin.path.parent.parents
            if level > len(parents) + 1:  # a relative import that climbs out of the filesystem
                return None
            bases = [parents[level - 2]] if level > 1 else [origin.path.parent]
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

    def _lookup(self, mod: _Module, name: str, depth: int = 0) -> _Binding | None:
        found = mod.scope.get(name)
        if found is not None or depth >= MAX_IMPORT_DEPTH:
            return found
        for module, level in mod.stars:
            other = self._find_module(module, level, mod)
            if isinstance(other, _Module):
                found = self._lookup(other, name, depth + 1)
                if found is not None:
                    return found
        return None

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

    def _base(self, expr: ast.expr, mod: _Module) -> tuple[str, Any]:
        """How one base class reads: ("class", (node, module)) | ("unittest", None) |
        ("ignore", None) | ("unresolved", text)."""
        text = ast.unparse(expr)
        if isinstance(expr, ast.Name):
            binding = self._lookup(mod, expr.id)
            if binding is None:
                if hasattr(builtins, expr.id):
                    return "ignore", None
                return "unresolved", f"{text} (not defined in the file)"
            followed, why = self._follow(binding)
            if why:
                target = binding.target
                if target and target[0] == "unittest" and target[2] in _UNITTEST_BASES:
                    return "unittest", None
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
                root = self._lookup(mod, node.id)
                if root is not None:
                    followed, _ = self._follow(root)
                    if followed.kind == "module":
                        parts.reverse()
                        if followed.target is not None:
                            dotted = ".".join([followed.target[0], *parts[:-1]]).strip(".")
                            if dotted == "unittest" and parts[-1] in _UNITTEST_BASES:
                                return "unittest", None
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
        info = _ClassInfo()
        if key in self._building:  # a base cycle; stop rather than recurse forever
            return info
        self._building.add(key)
        try:
            own: dict[str, _Binding] = {}
            _bind_body(node.body, mod, own, False)
            for base in reversed(node.bases):  # earlier bases win, as in the MRO
                kind, payload = self._base(base, mod)
                if kind == "class":
                    inner_node, inner_mod = payload
                    inner = self._class_info(inner_node, inner_mod)
                    info.members.update(inner.members)
                    info.unresolved.extend(inner.unresolved)
                    info.unittest = info.unittest or inner.unittest
                elif kind == "unittest":
                    info.unittest = True
                elif kind == "unresolved":
                    info.unresolved.append(payload)
            info.members.update(own)
        finally:
            self._building.discard(key)
        self._classes[key] = info
        return info

    # -- the walk ---------------------------------------------------------

    def resolve(self, reference: str) -> str | None:
        """None when pytest would collect the node; otherwise why it would not."""
        file_part, _, node_part = reference.partition("::")
        # A parametrised id (`name[a-b]`) resolves when the function does. Parameter ids
        # are generated at collection time and may hold `::` themselves, so the bracket is
        # cut off before the path is split.
        node_part = node_part.split("[", 1)[0]

        path = self._inside(file_part)
        if path is None:
            return "path escapes the repository"
        if not path.is_file():
            return "no such test file"
        if path.suffix != ".py":
            return "node id into a non-python file"
        relative = path.relative_to(self.root).as_posix()
        patterns = self.config["python_files"]
        if not _file_matches(patterns, relative):
            return (
                f"file does not match python_files ({' '.join(patterns)}), so a directory "
                "run never collects it"
            )

        segments = node_part.split("::")
        if not all(segments):
            return "empty segment in node id"

        mod = self._load(path)
        if isinstance(mod, str):
            return mod
        try:
            return self._walk(mod, segments, file_part)
        except (RecursionError, MemoryError):
            return _TOO_DEEP

    def _walk(self, mod: _Module, segments: list[str], file_part: str) -> str | None:
        functions = self.config["python_functions"]
        classes = self.config["python_classes"]
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
                return message

            followed, why = self._follow(binding)
            if why:
                return f"`{name}` {why}"
            if followed.kind not in ("def", "class"):
                return f"`{name}` is not a function or class in {where} (it is assigned a value)"

            if followed.kind == "def":
                if not last:
                    return f"`{name}` is a function, not a class holding tests"
                prefix = "test" if cls is not None and cls.unittest else None
                if prefix is not None:
                    if not name.startswith(prefix):
                        return f"`{name}` does not start with `test`, so unittest never runs it"
                elif not _name_matches(functions, name):
                    return (
                        f"`{name}` does not match python_functions ({' '.join(functions)}), "
                        "so pytest never collects it"
                    )
                if _is_fixture(followed.node):
                    return f"`{name}` is a fixture, not a test"
                return None

            assert isinstance(followed.node, ast.ClassDef) and followed.mod is not None
            info = self._class_info(followed.node, followed.mod)
            if cls is not None and cls.unittest:
                return f"`{name}` is a class nested in a unittest class, which is not collected"
            if not info.unittest:
                if not _name_matches(classes, name):
                    return (
                        f"class `{name}` does not match python_classes ({' '.join(classes)}), "
                        "so pytest never collects it"
                    )
                if "__init__" in info.members or "__new__" in info.members:
                    return (
                        f"class `{name}` defines __init__ or __new__, so pytest never collects it"
                    )
            flag = info.members.get("__test__")
            if flag is not None and flag.kind == "other" and flag.const is False:
                return f"class `{name}` sets __test__ = False, so pytest never collects it"
            if last:
                return None
            cls = info
            members = info.members
        return None
