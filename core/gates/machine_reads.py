"""Detector: a test may not read the machine it happens to run on.

THE DEFECT THIS EXISTS FOR, measured 2026-10-21 (GitHub issue #911, after #904). A test is
supposed to answer one question -- does the code do what it says -- and the answer must be
the same on every machine. These did not:

* ``test_hook_write_accounting`` compared the hook trees under ``~/.claude`` with canonical;
* ``test_round_table`` asserted markers in the installed ``~/.claude/skills`` review skill;
* ``test_dependency_chain`` read ``~/.claude/CLAUDE.md``, ``AGENTS.md`` and ``skills``;
* ``test_audit_dispatcher`` and ``test_launch_orchestration`` audited ``~/builds/dreamysuite``
  when it existed and skipped when it did not;
* ``test_detector`` compared against the real ``~/.claude`` and inherited ``CLAUDE_CONFIG_DIR``;
* ``test_enterprise_aggregation_boundaries`` read a sibling checkout;
* ``test_readmodel_wiring`` unset ``DREAM_STUDIO_HOME`` for the rest of the process, so a
  LATER test reached the operator's real ``~/.dream-studio``.

Each passed on the machine of the person who wrote it, skipped on CI (so it could not fail
there), and failed for a reason no commit caused on a machine whose install was out of date.
A skip because something is absent is the worst of them: a test that cannot fail.

THE RULE. A test (or a helper a test calls) that reads the operator's home, config root or a
sibling checkout must do it in a scope that redirects the home first, or live in a test marked
``install_check`` -- which is never collected by default and says on its face that it is about
one machine. "Reads" means:

* ``Path.home()`` / ``os.path.expanduser`` / ``.expanduser()``;
* ``os.environ`` / ``os.getenv`` of ``HOME``, ``USERPROFILE``, ``APPDATA``, ``LOCALAPPDATA``,
  ``HOMEPATH``, ``HOMEDRIVE`` or an ``XDG_*`` directory;
* ``claude_config_root()`` -- ``CLAUDE_CONFIG_DIR`` else ``~/.claude``;
* a ``~/`` literal handed to ``Path``, ``open`` or an ``os.path`` function;
* ``<REPO_ROOT>.parent / "<name>"`` and ``Path(__file__).parents[N]`` past the repository: a
  sibling checkout or anything else beside this one;
* a ``git`` subprocess with no ``cwd`` or with ``cwd`` the repository itself, which reads this
  clone's refs, tags, history and remotes (``origin/main`` does not exist in a ``--no-tags``
  clone or after ``git remote remove origin``).

"Redirects the home" means evidence in scope: the ``isolated_home`` fixture, a
``monkeypatch.setattr(Path, "home", ...)`` or ``patch("...Path.home")``, ``setenv`` of ``HOME`` or
``USERPROFILE`` (or ``CLAUDE_CONFIG_DIR`` for a config-root read), an ``env`` mapping that
carries them for a subprocess. The scope is the test, the class it sits in, or the module when a
fixture that redirects is ``autouse``; a helper function inherits the module's evidence.

THE ALLOW-LIST IS A DEBT, NOT A LICENCE. Every entry names a (file, function) and a reason, and
the gate FAILS when an entry no longer matches a read -- so fixing the last use forces the entry
out, and the list can only shrink. Do not add to it: redirect the home, build a fixture, or
mark the test ``install_check``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

#: Environment variables that name a user's home or config directory.
_HOME_ENV = frozenset(
    {
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "HOMEPATH",
        "HOMEDRIVE",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "XDG_STATE_HOME",
    }
)

#: Functions that resolve the operator's real config root.
_CONFIG_ROOT_FUNCS = frozenset({"claude_config_root", "claude_config_root_with_reason"})

#: Callables that take a path, so a ``~/`` literal handed to one is a read.
_PATH_CONSUMERS = frozenset(
    {"Path", "PurePath", "open", "expanduser", "exists", "isfile", "isdir", "join", "abspath"}
)

#: A module-level constant that denotes "this repository": ``REPO_ROOT``, ``_REPO``, ``ROOT``,
#: ``PLUGIN_ROOT``. Case-sensitive on purpose: a fixture parameter called ``repo`` is a repository
#: the test built, not this one.
_REPO_NAME = re.compile(r"^_?(?:[A-Z][A-Z0-9]*_)*(?:REPO|ROOT)$")

#: ``Path(__file__)...`` -- the test file itself, as opposed to ``module.__file__``.
_OWN_FILE = re.compile(r"^(?:\w+\.)*_?Path\(__file__\)")

#: Evidence, in the unparsed text of a call, that the home is being redirected.
_REDIRECT_CALL = re.compile(
    r"(Path\b[^()]*,\s*['\"]home['\"])"  # monkeypatch.setattr(Path, "home", ...)
    r"|(\bPath\.home\b)"  # patch("pathlib.Path.home") / patch.object style strings
    r"|(['\"]expanduser['\"])"  # monkeypatch.setattr(os.path, "expanduser", ...)
    r"|(\b(HOME|USERPROFILE|CLAUDE_CONFIG_DIR)\b)"  # setenv / patch.dict / env mapping
)

#: Fixtures that redirect the home (defined in tests/conftest.py).
_REDIRECT_FIXTURES = frozenset({"isolated_home"})

#: git subcommands that do not read this clone's refs, tags, history or remotes: setting up a
#: repository of one's own, and ``ls-files``, which lists the tracked CONTENT of the tree (the
#: same thing ``Path.rglob`` over it would, minus the untracked files).
_GIT_SELF_CONTAINED = frozenset(
    {"init", "config", "version", "--version", "help", "clone", "ls-files"}
)

#: (path relative to the repo root, enclosing function or "<module>") -> why it stays.
#: SHRINKING: the gate fails on an entry that no longer matches, so a fixed use forces its entry
#: out. Adding one needs a reason a reviewer would accept; "the test is old" is not one.
ALLOWLIST: dict[tuple[str, str], str] = {
    (
        "tests/conftest.py",
        "<module>",
    ): "the session guard records the operator's REAL state.db mtime before redirecting the "
    "home, to prove after every test that it did not move; it cannot do that without naming it",
    (
        "tests/conftest.py",
        "guard_real_homedir",
    ): "the autouse guard snapshots the operator's real ~/.dream-studio events, integrations "
    "and state.db mtimes before and after each test and aborts the session if one moved",
    (
        "tests/unit/test_delivery_boundary.py",
        "test_the_live_attribution_does_not_carry_a_standing_neighbour_caveat",
    ): "reads ~/.dream-studio/state/studio.db and origin/main...HEAD of the checkout; rewritten "
    "against a fixture repository and authority by PR #916 (fix/delivery-boundary-test-is-"
    "hermetic), which deletes this function. Remove this entry when that PR merges.",
}

_KIND_MESSAGE = {
    "home-read": (
        "reads the operator's home ({what}). Its answer is a fact about this machine, so it "
        "passes or fails depending on who runs it. Build a temporary home and redirect it "
        "(the isolated_home fixture, or monkeypatch.setattr(Path, 'home', ...) with HOME and "
        "USERPROFILE), or move the check to tests/install_checks under the install_check marker."
    ),
    "config-root-read": (
        "resolves the operator's Claude Code config root ({what}): CLAUDE_CONFIG_DIR, else "
        "~/.claude. Set CLAUDE_CONFIG_DIR (or the home) for the test, or mark it install_check."
    ),
    "sibling-read": (
        "reads outside the repository ({what}): a sibling checkout or a directory beside this "
        "one exists on one machine and not on a CI runner or in a git worktree, so a test that "
        "skips when it is absent can never fail. Build a fixture, or mark it install_check."
    ),
    "git-checkout": (
        "runs git against this checkout ({what}), so refs, tags, history and remotes of the "
        "clone decide the result -- origin/main is absent after `git clone --no-tags` and "
        "`git remote remove origin`. Build a repository in tmp_path (tests/helpers/git_repo.py)."
    ),
}


def _dotted(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001 - an unparsable node is simply not a match
        return ""


def _is_pytest_mark(node: ast.AST, name: str) -> bool:
    text = _dotted(node)
    return text.endswith(f"mark.{name}") or text.startswith(f"pytest.mark.{name}")


def _marks_install_check(decorators: list[ast.expr]) -> bool:
    return any("install_check" in _dotted(d) for d in decorators)


def _module_is_install_check(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets
        ):
            if "install_check" in _dotted(node.value):
                return True
    return False


def _first_str(call: ast.Call) -> str | None:
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


class _Read:
    __slots__ = ("kind", "what", "line")

    def __init__(self, kind: str, what: str, line: int) -> None:
        self.kind, self.what, self.line = kind, what, line


def _reads_in(node: ast.AST, depth: int) -> list[tuple[ast.AST, _Read]]:
    """Every machine read directly in ``node`` (descending into nested functions too)."""
    found: list[tuple[ast.AST, _Read]] = []
    for sub in ast.walk(node):
        read = _classify(sub, depth)
        if read is not None:
            found.append((sub, read))
    return found


def _classify(sub: ast.AST, depth: int) -> _Read | None:
    line = getattr(sub, "lineno", 0)
    if isinstance(sub, ast.Call):
        func = sub.func
        name = _call_name(sub)
        text = _dotted(func)
        # Path.home() / pathlib.Path.home() / _Path.home()
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "home"
            and _dotted(func.value).endswith("Path")
        ):
            return _Read("home-read", "Path.home()", line)
        if name == "expanduser":
            return _Read("home-read", "expanduser", line)
        if text in {"os.getenv", "os.environ.get"}:
            var = _first_str(sub)
            if var and var.upper() in _HOME_ENV:
                return _Read("home-read", f"os.environ[{var!r}]", line)
        if name in _CONFIG_ROOT_FUNCS:
            return _Read("config-root-read", f"{name}()", line)
        # a "~/..." literal handed to something that opens a path
        if name in _PATH_CONSUMERS:
            for arg in sub.args:
                if (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and (arg.value == "~" or arg.value.startswith(("~/", "~\\")))
                ):
                    return _Read("home-read", f"{name}({arg.value!r})", line)
        # git against this checkout
        if text.startswith("subprocess.") and sub.args:
            argv = sub.args[0]
            if (
                isinstance(argv, (ast.List, ast.Tuple))
                and argv.elts
                and isinstance(argv.elts[0], ast.Constant)
                and argv.elts[0].value == "git"
                and all(kw.arg is not None for kw in sub.keywords)  # **opts may carry a cwd
            ):
                tokens = [
                    e.value if isinstance(e, ast.Constant) and isinstance(e.value, str) else None
                    for e in argv.elts
                ]
                sub_cmd = next((t for t in tokens[1:] if t and not t.startswith("-")), "")
                cwd = next((kw.value for kw in sub.keywords if kw.arg == "cwd"), None)
                target: ast.AST | None = cwd
                if "-C" in tokens:
                    at = tokens.index("-C")
                    target = argv.elts[at + 1] if at + 1 < len(argv.elts) else None
                names = (
                    [n.id for n in ast.walk(target) if isinstance(n, ast.Name)]
                    if target is not None
                    else []
                )
                unpinned = target is None
                at_repo = any(_REPO_NAME.match(n) for n in names)
                if (unpinned or at_repo) and sub_cmd not in _GIT_SELF_CONTAINED:
                    return _Read("git-checkout", f"git {sub_cmd}".strip(), line)
    elif isinstance(sub, ast.Subscript):
        # os.environ["HOME"]
        if _dotted(sub.value) == "os.environ" and isinstance(sub.ctx, ast.Load):
            key = sub.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                if key.value.upper() in _HOME_ENV:
                    return _Read("home-read", f"os.environ[{key.value!r}]", line)
        # Path(__file__).resolve().parents[N] with N past the repository
        if isinstance(sub.value, ast.Attribute) and sub.value.attr == "parents":
            idx = sub.slice
            if (
                isinstance(idx, ast.Constant)
                and isinstance(idx.value, int)
                and _OWN_FILE.match(_dotted(sub.value))
                and idx.value > depth
            ):
                return _Read(
                    "sibling-read", f"{_dotted(sub)} (the repository is parents[{depth}])", line
                )
    elif isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Div):
        left, right = sub.left, sub.right
        if (
            isinstance(left, ast.Attribute)
            and left.attr == "parent"
            and isinstance(left.value, ast.Name)
            and _REPO_NAME.match(left.value.id)
            and isinstance(right, ast.Constant)
            and isinstance(right.value, str)
        ):
            return _Read("sibling-read", f"{_dotted(sub)}", line)
    return None


def _has_redirect_evidence(node: ast.AST) -> bool:
    """Does anything under ``node`` redirect the home?"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.arg) and sub.arg in _REDIRECT_FIXTURES:
            return True
        if isinstance(sub, ast.Call):
            name = _call_name(sub)
            if name == "usefixtures":
                if any(
                    isinstance(a, ast.Constant) and a.value in _REDIRECT_FIXTURES for a in sub.args
                ):
                    return True
            if name in {"setattr", "setenv", "patch", "dict", "object", "update", "setitem"}:
                if _REDIRECT_CALL.search(_dotted(sub)):
                    return True
        if isinstance(sub, ast.Assign):
            # env["HOME"] = ... / env["USERPROFILE"] = ... for a subprocess
            for target in sub.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)
                    and target.slice.value in {"HOME", "USERPROFILE", "CLAUDE_CONFIG_DIR"}
                ):
                    return True
        if isinstance(sub, ast.Dict):
            for key in sub.keys:
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and key.value in {"HOME", "USERPROFILE", "CLAUDE_CONFIG_DIR"}
                ):
                    return True
    return False


def _is_autouse_fixture(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in fn.decorator_list:
        text = _dotted(dec)
        if "fixture" in text and "autouse=True" in text:
            return True
    return False


def _function_depth(rel: Path) -> int:
    """How many directories sit between the repository root and the file: ``parents[depth]``
    of ``Path(__file__)`` is the repository root."""
    return len(rel.parts) - 1


def scan_file(path: Path, repo_root: Path) -> list[dict]:
    """Machine reads in one test file that no scope redirects, before the allow-list."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError, ValueError):
        return []
    try:
        rel = path.relative_to(repo_root)
    except ValueError:
        rel = Path(path.name)
    rel_posix = rel.as_posix()
    if rel.parts[:2] == ("tests", "install_checks") or _module_is_install_check(tree):
        return []
    depth = _function_depth(rel)

    # Scopes: module body (outside any def), each top-level def/class and the defs inside.
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    module_autouse = any(
        _is_autouse_fixture(n) and _has_redirect_evidence(n)
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    module_pytestmark = any(
        isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in n.targets)
        and _has_redirect_evidence(n.value)
        for n in tree.body
    )
    module_redirects_anywhere = _has_redirect_evidence(tree)

    offenders: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for node, read in _reads_in(tree, depth):
        chain: list[ast.AST] = []
        cur = node
        while cur in parents:
            cur = parents[cur]
            chain.append(cur)
        funcs = [c for c in chain if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef))]
        classes = [c for c in chain if isinstance(c, ast.ClassDef)]
        owner = funcs[-1].name if funcs else "<module>"  # outermost def names the entry

        if any(_marks_install_check(f.decorator_list) for f in funcs):
            continue
        if any(_marks_install_check(c.decorator_list) for c in classes):
            continue
        redirected = (
            module_autouse
            or module_pytestmark
            or any(_has_redirect_evidence(f) for f in funcs)
            or any(
                _has_redirect_evidence(c)
                and any(
                    isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and _is_autouse_fixture(n)
                    and _has_redirect_evidence(n)
                    for n in c.body
                )
                for c in classes
            )
            or any(
                any(
                    "usefixtures" in _dotted(d) and _has_redirect_evidence(d)
                    for d in c.decorator_list
                )
                for c in classes
            )
        )
        # A helper (not a test, not a fixture) inherits whatever the module redirects: it is
        # called from tests that carry the evidence, which this gate cannot follow.
        if not redirected and funcs:
            outer = funcs[-1]
            is_test = outer.name.startswith("test")
            is_fixture = any("fixture" in _dotted(d) for d in outer.decorator_list)
            if not is_test and not is_fixture and module_redirects_anywhere:
                redirected = True
        if redirected and read.kind in {"home-read", "config-root-read"}:
            continue
        # sibling and git reads are never excused by a home redirect.
        key = (owner, read.line)
        if key in seen:
            continue
        seen.add(key)
        offenders.append(
            {
                "path": rel_posix,
                "function": owner,
                "line": read.line,
                "kind": read.kind,
                "target": read.what,
                "message": f"{rel_posix}:{read.line} in {owner}() "
                + _KIND_MESSAGE[read.kind].format(what=read.what),
            }
        )
    return offenders


def apply_allowlist(
    offenders: list[dict], allowlist: dict[tuple[str, str], str] | None = None
) -> tuple[list[dict], list[dict]]:
    """Split ``offenders`` into those still failing and allow-list entries nothing matches."""
    allow = ALLOWLIST if allowlist is None else allowlist
    matched: set[tuple[str, str]] = set()
    failing: list[dict] = []
    for off in offenders:
        key = (off["path"], off["function"])
        if key in allow:
            matched.add(key)
            continue
        failing.append(off)
    stale = [
        {
            "path": path,
            "function": function,
            "kind": "stale-allowlist-entry",
            "line": 0,
            "target": reason[:80],
            "message": f"allow-list entry ({path}, {function}) matches no machine read any more: "
            "the use was fixed or removed, so delete the entry (the list may only shrink).",
        }
        for (path, function), reason in sorted(allow.items())
        if (path, function) not in matched
    ]
    return failing, stale
