"""What pytest's own configuration lets a DIRECTORY run collect, read without running pytest.

`core/gates/pytest_node_resolver.py` answers "would pytest collect this node id". Finding the
test in the file answers a smaller question: pytest given the file by name collects things a
directory run never reaches, because a directory run applies exclusions an explicit file
argument bypasses. CI and developers run directories. A rule enforced only by a test the
directory run skips is enforced by nothing, so the resolver needs the exclusions too, and
they live in three places this module reads:

  * the repo's pytest config (`pytest.toml`, `.pytest.toml`, `pytest.ini`, `.pytest.ini`,
    `pyproject.toml`, `tox.ini`, `setup.cfg`, in pytest's order of precedence): the three name
    patterns, `testpaths`, `norecursedirs` (pytest's default set when the repo names none),
    `collect_imported_tests`, and the `--ignore`, `--ignore-glob` and `--deselect` options in
    `addopts`;
  * `conftest.py` files, read with `ast` and never imported: `collect_ignore` and
    `collect_ignore_glob`, where only the NEAREST conftest that defines the name is read, as
    pytest reads it, so a sub-directory conftest masks its parent's list;
  * pytest's built-in exclusions: `__pycache__` and a virtualenv root.

WHAT IS EVALUATED AND WHAT IS REFUSED. A conftest list is evaluated only in the literal forms
that can be read without running anything: a top-level assignment of a list or tuple of string
constants, `+=` a literal, and `.append('x')` / `.extend([...])` at the top level. Anything
else that touches the name (a conditional assignment, `os.path.join`, a comprehension, an
import) is `Unevaluable`, and a reference under that conftest fails saying so. Accepting it
would be accepting on doubt, the fail-open this gate exists to remove. The same refusal applies
to a conftest that defines a hook which changes what is collected (`pytest_collect_file` and its
relatives), names `pytest_plugins`, or reaches for `config.pluginmanager`: the resolver models
pytest's stock collection, and answering for a different one would be a guess.

NOT MODELLED, deliberately: `PYTEST_ADDOPTS` and command-line options (they belong to one
developer's shell; the repo's own `addopts` is what every run shares), plugins installed in the
environment, `-k` / `-m` / `--noconftest` / `--confcutdir` / `--pyargs` / `--import-mode` /
`-p <plugin>` in `addopts` (each changes collection in a way that needs evaluating marks or
importing, so a repo that sets one gets a configuration error rather than a guess), and a
`collect_ignore` assigned through `globals()` or `setattr`.
"""

from __future__ import annotations

import ast
import configparser
import fnmatch
import glob
import os
import shlex
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any

DEFAULT_FILES = ("test_*.py", "*_test.py")
DEFAULT_CLASSES = ("Test",)
DEFAULT_FUNCTIONS = ("test",)

#: pytest's own default for `norecursedirs` (9.0.x). Copied so the gate does not import pytest;
#: tests/unit/test_pytest_collection_rules.py pins the copy to the installed pytest.
DEFAULT_NORECURSEDIRS = (
    "*.egg",
    ".*",
    "_darcs",
    "build",
    "CVS",
    "dist",
    "node_modules",
    "venv",
    "{arch}",
)

#: Hooks that decide which files and items exist. A conftest defining one is a different
#: collector from the one this module models.
COLLECTION_HOOKS = frozenset(
    {
        "pytest_collect_file",
        "pytest_pycollect_makeitem",
        "pytest_ignore_collect",
        "pytest_collection_modifyitems",
        "pytest_collect_directory",
        "pytest_collection",
        "pytest_make_collect_report",
    }
)

_CONFTEST_LISTS = ("collect_ignore", "collect_ignore_glob")

#: Calls on `config.pluginmanager` that add hooks the resolver cannot see. Reading from it
#: (`get_plugin`) is not one.
_PLUGIN_REGISTRATION = frozenset({"register", "import_plugin", "consider_module"})

#: `addopts` options that change what is collected in a way that cannot be evaluated from
#: source. Each takes a value except those in _FLAG_ONLY.
_UNMODELLED_OPTIONS = frozenset(
    {"-k", "-m", "--noconftest", "--confcutdir", "--pyargs", "--import-mode", "--rootdir"}
)
_FLAG_ONLY = frozenset({"--noconftest", "--pyargs"})

_CONFIG_FILES = (
    "pytest.toml",
    ".pytest.toml",
    "pytest.ini",
    ".pytest.ini",
    "pyproject.toml",
    "tox.ini",
    "setup.cfg",
)


class CollectionConfigError(ValueError):
    """The repo's pytest config exists and cannot be read, or asks for something this gate
    cannot evaluate. Falling back to pytest's defaults would judge names by rules the repo
    does not use, so it is an error, not a shrug."""


@dataclass(frozen=True)
class Unevaluable:
    """A conftest value the gate refuses to guess at."""

    why: str


# --------------------------------------------------------------------------
# Reading the config
# --------------------------------------------------------------------------


def _read_ini(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError) as exc:
        raise CollectionConfigError(f"cannot read pytest config {path.name}: {exc}") from exc
    return parser


def _options_from(path: Path) -> dict[str, Any] | None:
    """The pytest options in one config file, or None when the file holds none (pytest then
    looks at the next file, exactly as it does)."""
    if path.suffix == ".toml":
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as exc:
            raise CollectionConfigError(f"cannot read pytest config {path.name}: {exc}") from exc
        if path.name in ("pytest.toml", ".pytest.toml"):
            table = data.get("pytest", {})
            return dict(table) if isinstance(table, dict) else {}
        tool = data.get("tool", {}).get("pytest", {})
        if not isinstance(tool, dict):
            return None
        native = {k: v for k, v in tool.items() if k != "ini_options"}
        legacy = tool.get("ini_options")
        if native and legacy:
            raise CollectionConfigError(
                f"cannot read pytest config {path.name}: both [tool.pytest] and "
                "[tool.pytest.ini_options] are present, which pytest refuses"
            )
        if native:
            return native
        return dict(legacy) if isinstance(legacy, dict) else None

    parser = _read_ini(path)
    if path.name in ("pytest.ini", ".pytest.ini"):  # always the source, even when empty
        return dict(parser["pytest"]) if parser.has_section("pytest") else {}
    section = "tool:pytest" if path.name == "setup.cfg" else "pytest"
    return dict(parser[section]) if parser.has_section(section) else None


def _options(root: Path) -> tuple[str, dict[str, Any]]:
    for name in _CONFIG_FILES:
        path = root / name
        if path.is_file():
            options = _options_from(path)
            if options is not None:
                return name, options
    return "", {}


def _args(options: dict[str, Any], key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """An ini option of pytest's `args` type: a list, or a string split the way a shell does."""
    value = options.get(key)
    if value is None:  # absent: the default. Present and empty is an empty list, not the default.
        return default
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    try:
        return tuple(shlex.split(str(value)))
    except ValueError as exc:
        raise CollectionConfigError(f"cannot read pytest config option {key}: {exc}") from exc


def _flag(options: dict[str, Any], key: str, default: bool) -> bool:
    value = options.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("y", "yes", "t", "true", "on", "1"):
        return True
    if text in ("n", "no", "f", "false", "off", "0"):
        return False
    raise CollectionConfigError(f"cannot read pytest config option {key}: {value!r} is not a bool")


@dataclass
class _Addopts:
    ignore: tuple[str, ...] = ()
    ignore_glob: tuple[str, ...] = ()
    deselect: tuple[str, ...] = ()
    collect_in_virtualenv: bool = False


def _parse_addopts(tokens: tuple[str, ...], source: str) -> _Addopts:
    found: dict[str, list[str]] = {"--ignore": [], "--ignore-glob": [], "--deselect": []}
    parsed = _Addopts()
    index = 0

    def refuse(token: str) -> CollectionConfigError:
        return CollectionConfigError(
            f"addopts in {source} contains `{token}`, which changes what pytest collects in a "
            "way this gate cannot evaluate from source; it will not guess"
        )

    while index < len(tokens):
        token = tokens[index]
        name, equals, attached = token.partition("=") if token.startswith("--") else (token, "", "")
        if name in found:
            if equals:
                found[name].append(attached)
            elif index + 1 < len(tokens):
                index += 1
                found[name].append(tokens[index])
            else:
                raise CollectionConfigError(f"addopts in {source} has `{token}` with no value")
        elif token == "--collect-in-virtualenv":
            parsed.collect_in_virtualenv = True
        elif name in _UNMODELLED_OPTIONS:
            raise refuse(name)
        elif not token.startswith("--") and token[:2] in ("-k", "-m") and len(token) > 2:
            raise refuse(token[:2])  # `-kexpr` / `-mexpr`, the attached form
        elif token == "-p" or (token.startswith("-p") and not token.startswith("--")):
            plugin = tokens[index + 1] if token == "-p" and index + 1 < len(tokens) else token[2:]
            if token == "-p":
                index += 1
            if not plugin.startswith("no:"):
                raise refuse("-p " + plugin)
        index += 1
    parsed.ignore = tuple(found["--ignore"])
    parsed.ignore_glob = tuple(found["--ignore-glob"])
    parsed.deselect = tuple(found["--deselect"])
    return parsed


# --------------------------------------------------------------------------
# pytest's own matching rules
# --------------------------------------------------------------------------


def fnmatch_ex(pattern: str, path: str | os.PathLike[str]) -> bool:
    """pytest's `fnmatch_ex`: a pattern with no separator matches the final name, one with a
    separator matches the whole path (with `*/` put in front when the pattern is relative)."""
    path = PurePath(path)
    if sys.platform.startswith("win") and os.sep not in pattern and "/" in pattern:
        pattern = pattern.replace("/", os.sep)
    if os.sep not in pattern:
        name = path.name
    else:
        name = str(path)
        if path.is_absolute() and not os.path.isabs(pattern):
            pattern = f"*{os.sep}{pattern}"
    return fnmatch.fnmatch(name, pattern)


def _absolute(base: Path, value: str) -> Path:
    return Path(os.path.abspath(base / value.replace("/", os.sep)))


# --------------------------------------------------------------------------
# conftest.py, read without importing
# --------------------------------------------------------------------------


def _literal_strings(node: ast.expr) -> list[str] | None:
    if isinstance(node, (ast.List, ast.Tuple)) and all(
        isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts
    ):
        return [e.value for e in node.elts]  # type: ignore[attr-defined]
    return None


def _named(node: ast.expr | None, names: tuple[str, ...]) -> str | None:
    return node.id if isinstance(node, ast.Name) and node.id in names else None


def _apply_literal_form(
    stmt: ast.stmt, names: tuple[str, ...], values: dict[str, list[str] | Unevaluable]
) -> bool:
    """Apply one top-level statement when it is a form that can be read. False when it is not."""
    where = f"line {stmt.lineno}"
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
        name = _named(stmt.targets[0], names)
        value: ast.expr | None = stmt.value
    elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        name = _named(stmt.target, names)
        value = stmt.value
    else:
        name, value = None, None
    if name is not None and value is not None:
        literal = _literal_strings(value)
        values[name] = (
            literal
            if literal is not None
            else Unevaluable(f"{where}: `{name}` is not a literal list of strings")
        )
        return True

    if isinstance(stmt, ast.AugAssign) and isinstance(stmt.op, ast.Add):
        name = _named(stmt.target, names)
        if name is not None:
            literal = _literal_strings(stmt.value)
            current = values.get(name)
            if isinstance(current, list) and literal is not None:
                values[name] = [*current, *literal]
            else:
                values[name] = Unevaluable(f"{where}: `{name} +=` is not a literal onto a literal")
            return True

    call = stmt.value if isinstance(stmt, ast.Expr) else None
    if (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr in ("append", "extend")
        and _named(call.func.value, names)
        and len(call.args) == 1
        and not call.keywords
    ):
        name = call.func.value.id  # type: ignore[attr-defined]
        arg = call.args[0]
        if call.func.attr == "append":
            literal = (
                [arg.value]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                else None
            )
        else:
            literal = _literal_strings(arg)
        current = values.get(name)
        if isinstance(current, list) and literal is not None:
            values[name] = [*current, *literal]
        else:
            values[name] = Unevaluable(
                f"{where}: `{name}.{call.func.attr}` is not a literal onto a literal"
            )
        return True
    return False


def _mention(stmt: ast.stmt, names: tuple[str, ...]) -> str | None:
    for node in ast.walk(stmt):
        candidates: list[str] = []
        if isinstance(node, ast.Name):
            candidates = [node.id]
        elif isinstance(node, ast.alias):
            candidates = [node.name, node.asname or ""]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            candidates = [node.name]
        elif isinstance(node, ast.arg):
            candidates = [node.arg]
        for candidate in candidates:
            if candidate in names:
                return candidate
    return None


def string_lists(tree: ast.Module, names: tuple[str, ...]) -> dict[str, list[str] | Unevaluable]:
    """The value of each named module-level list of strings, evaluated only where it can be
    read statically. A name absent from the result is not defined at all; one that maps to
    `Unevaluable` is defined in a form this refuses to guess at."""
    values: dict[str, list[str] | Unevaluable] = {}
    for stmt in tree.body:
        if _apply_literal_form(stmt, names, values):
            continue
        touched = _mention(stmt, names)
        if touched is not None:
            values[touched] = Unevaluable(
                f"line {stmt.lineno}: `{touched}` is used in a form that is not a plain "
                "top-level literal"
            )
    return values


def collection_hook_problem(tree: ast.Module) -> str | None:
    """Why a conftest's source changes collection in a way the resolver does not model."""
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in COLLECTION_HOOKS
        ):
            return f"defines `{node.name}`"
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            if node.id in COLLECTION_HOOKS:
                return f"assigns `{node.id}`"
            if node.id == "pytest_plugins":
                return "sets `pytest_plugins`"
        if isinstance(node, ast.alias) and (node.asname or node.name) in COLLECTION_HOOKS:
            return f"imports `{node.asname or node.name}`"
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _PLUGIN_REGISTRATION
            and "pluginmanager" in ast.unparse(node.func)
        ):
            return f"registers a plugin through `{ast.unparse(node.func)}` (`pluginmanager`)"
    return None


def conftest_collection_problem(path: Path) -> str | None:
    """Why `path` (a conftest.py) cannot be trusted to leave collection alone, else None."""
    try:
        tree = ast.parse(path.read_bytes(), filename=str(path))
    except SyntaxError as exc:
        return f"does not parse (line {exc.lineno})"
    except (ValueError, UnicodeDecodeError, OSError, MemoryError, RecursionError):
        return "is not readable as python source"
    return collection_hook_problem(tree)


@dataclass
class _Conftest:
    path: Path
    error: str | None = None
    lists: dict[str, list[str] | Unevaluable] = field(default_factory=dict)
    hook_problem: str | None = None


# --------------------------------------------------------------------------
# The rules
# --------------------------------------------------------------------------


class CollectionRules:
    """Everything a bare `pytest` run from the repo root applies when it decides which files
    to collect. One instance per audit; conftest files are parsed once."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.config_file, options = _options(root)
        self.python_files = _args(options, "python_files", DEFAULT_FILES)
        self.python_classes = _args(options, "python_classes", DEFAULT_CLASSES)
        self.python_functions = _args(options, "python_functions", DEFAULT_FUNCTIONS)
        self.norecursedirs = _args(options, "norecursedirs", DEFAULT_NORECURSEDIRS)
        self.testpaths = _args(options, "testpaths", ())
        self.collect_imported_tests = _flag(options, "collect_imported_tests", True)
        addopts = _parse_addopts(
            _args(options, "addopts", ()), self.config_file or "pytest configuration"
        )
        self.ignore = addopts.ignore
        self.ignore_glob = addopts.ignore_glob
        self.deselect = addopts.deselect
        self.collect_in_virtualenv = addopts.collect_in_virtualenv
        self._conftests: dict[Path, _Conftest | None] = {}
        self._roots: list[Path] | None = None
        self._collected: list[Path] | None = None

    # -- conftest files ---------------------------------------------------

    def _conftest(self, directory: Path) -> _Conftest | None:
        if directory not in self._conftests:
            path = directory / "conftest.py"
            found: _Conftest | None = None
            if path.is_file():
                found = _Conftest(path)
                try:
                    tree = ast.parse(path.read_bytes(), filename=str(path))
                except SyntaxError as exc:
                    found.error = f"does not parse (line {exc.lineno})"
                except (ValueError, UnicodeDecodeError, OSError, MemoryError, RecursionError):
                    found.error = "is not readable as python source"
                else:
                    found.lists = string_lists(tree, _CONFTEST_LISTS)
                    found.hook_problem = collection_hook_problem(tree)
            self._conftests[directory] = found
        return self._conftests[directory]

    def _chain(self, directory: Path) -> list[Path]:
        """`directory` and its parents up to the repo root, nearest first."""
        chain = []
        current = directory
        while current == self.root or self.root in current.parents:
            chain.append(current)
            if current == self.root:
                break
            current = current.parent
        return chain

    def _rel(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix() or "."
        except ValueError:
            return str(path)

    def conftest_problem(self, path: Path) -> str | None:
        """Why a conftest above `path` makes the answer untrustworthy, else None."""
        for directory in reversed(self._chain(path.parent)):
            conftest = self._conftest(directory)
            if conftest is None:
                continue
            problem = conftest.error or conftest.hook_problem
            if problem:
                where = self._rel(conftest.path)
                scope = self._rel(directory)
                reach = "anything" if scope == "." else f"anything under {scope}/"
                if conftest.error:
                    return f"{where} {problem}, so pytest collects nothing from {reach}"
                return (
                    f"{where} {problem}, which can change what pytest collects; the resolver "
                    f"cannot evaluate it, so it cannot say pytest collects {reach}"
                )
        return None

    def _nearest(
        self, directory: Path, name: str
    ) -> tuple[_Conftest, list[str] | Unevaluable] | None:
        for candidate in self._chain(directory):
            conftest = self._conftest(candidate)
            if conftest is not None and name in conftest.lists:
                return conftest, conftest.lists[name]
        return None

    # -- the directory run ------------------------------------------------

    def roots(self) -> list[Path]:
        """Where a bare run starts: `testpaths` (globbed, as pytest does), else the repo root.
        Testpaths that match nothing make pytest fall back to the whole tree."""
        if self._roots is None:
            found: list[Path] = []
            for pattern in self.testpaths:
                for match in sorted(glob.glob(pattern, root_dir=self.root, recursive=True)):
                    found.append(Path(os.path.abspath(self.root / match)))
            self._roots = found or [self.root]
        return self._roots

    def collected_files(self) -> list[Path]:
        """Every file a bare run collects, in the order it collects them (pytest scans each
        directory's entries sorted by name, files and directories together)."""
        if self._collected is None:
            found: list[Path] = []
            for start in self.roots():
                if start.is_file():
                    found.append(start)
                    continue
                for directory, subdirs, names in os.walk(start):
                    here = Path(directory)
                    subdirs[:] = [d for d in subdirs if self._ignored(here / d, True) is None]
                    for name in names:
                        path = here / name
                        if (
                            name.endswith(".py")
                            and any(fnmatch_ex(p, path) for p in self.python_files)
                            and self._ignored(path, False) is None
                        ):
                            found.append(path)
            found.sort(key=lambda p: p.relative_to(self.root).parts)
            self._collected = found
        return self._collected

    def under_a_root(self, path: Path) -> bool:
        """Whether a bare run starts at `path` or above it."""
        return any(path == start or start in path.parents for start in self.roots())

    def explicit(self, path: Path) -> bool:
        """True when `path` is itself a testpath: an explicit argument, so `python_files` and
        the exclusions do not apply to it."""
        return self.testpaths != () and path in self.roots() and path != self.root

    def _ignored(self, entry: Path, is_dir: bool) -> str | None:
        rel = self._rel(entry)
        if entry.name == "__pycache__":
            return f"pytest never collects from {rel} (`__pycache__`)"

        listed = self._nearest(entry.parent, "collect_ignore")
        if listed is not None:
            conftest, value = listed
            where = self._rel(conftest.path)
            if isinstance(value, Unevaluable):
                return (
                    f"{where} sets `collect_ignore` in a form the gate cannot evaluate "
                    f"({value.why}), so it cannot say whether pytest collects {rel}"
                )
            for item in value:
                if _absolute(conftest.path.parent, item) == entry:
                    return f"`collect_ignore` in {where} names `{item}`, which excludes {rel}"
        for item in self.ignore:
            if _absolute(self.root, item) == entry:
                return f"`--ignore {item}` in addopts ({self.config_file}) excludes {rel}"

        globbed = self._nearest(entry.parent, "collect_ignore_glob")
        if globbed is not None:
            conftest, value = globbed
            where = self._rel(conftest.path)
            if isinstance(value, Unevaluable):
                return (
                    f"{where} sets `collect_ignore_glob` in a form the gate cannot evaluate "
                    f"({value.why}), so it cannot say whether pytest collects {rel}"
                )
            for item in value:
                if fnmatch.fnmatch(str(entry), str(_absolute(conftest.path.parent, item))):
                    return f"`collect_ignore_glob` in {where} has `{item}`, which excludes {rel}"
        for item in self.ignore_glob:
            if fnmatch.fnmatch(str(entry), str(_absolute(self.root, item))):
                return f"`--ignore-glob {item}` in addopts ({self.config_file}) excludes {rel}"

        if is_dir:
            if not self.collect_in_virtualenv and (
                (entry / "pyvenv.cfg").is_file() or (entry / "conda-meta" / "history").is_file()
            ):
                return (
                    f"{rel} is a virtualenv (it holds pyvenv.cfg or conda-meta/history), which "
                    "pytest skips unless --collect-in-virtualenv is given"
                )
            for pattern in self.norecursedirs:
                if fnmatch_ex(pattern, entry):
                    source = (
                        self.config_file
                        if self.norecursedirs != DEFAULT_NORECURSEDIRS
                        else ("pytest's defaults")
                    )
                    return (
                        f"the norecursedirs pattern `{pattern}` ({source}) excludes the "
                        f"directory {rel}"
                    )
        return None

    def _below(self, start: Path, path: Path) -> str | None:
        current = start
        parts = path.relative_to(start).parts
        for position, part in enumerate(parts):
            current = current / part
            why = self._ignored(current, is_dir=position < len(parts) - 1 or current.is_dir())
            if why:
                return why
        return None

    def excluded(self, path: Path) -> str | None:
        """Why a bare `pytest` run never collects the file `path`, or None when it does."""
        reasons: list[str] = []
        for start in self.roots():
            if path == start:
                return None
            if start in path.parents:
                why = self._below(start, path)
                if why is None:
                    return None
                reasons.append(why)
        if reasons:
            return reasons[0]
        return (
            f"{self._rel(path)} is outside testpaths ({', '.join(self.testpaths)}), which is "
            "where a bare `pytest` run starts"
        )

    def deselected_by(self, nodeid: str) -> str | None:
        for prefix in self.deselect:
            if nodeid.startswith(prefix):
                return f"`--deselect {prefix}` in addopts ({self.config_file}) deselects {nodeid}"
        return None


def load_rules(root: Path) -> CollectionRules:
    return CollectionRules(Path(root))
