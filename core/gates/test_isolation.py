"""Gate: a test may not replace a stdlib instance method for the whole process.

THE DEFECT THIS EXISTS FOR, measured 2026-09-06. ``tests/unit/test_game_validate.py``
proved that an oversized file is skipped, by faking the size:

    monkeypatch.setattr(type(f), "stat", lambda self_, **_: mock_stat)

``type(f)`` is ``WindowsPath``. That one line made EVERY path in the process report 20 MB
for the rest of the test -- including the paths the autouse spool guard consults during
teardown, which concluded the session had written into the operator's real
``~/.dream-studio/events`` and aborted the whole run FATAL. The full local suite could not
complete, which is why 45 failures reached ``main`` on a green subset: the only tier that
would have caught them was the one that could not finish.

The test itself passed. It always passed. The damage was entirely to its neighbours.

THE RULE. ``monkeypatch.setattr`` on an INSTANCE method of a stdlib type may not install
an inline fake -- a lambda, a mock, or a constant -- because such a replacement answers
identically for every object in the process and lasts until fixture teardown. Pass a
named function that delegates to the real implementation for anything but the object
under test, and the fake stops leaking:

    real_stat = type(f).stat

    def _stat_only_for_target(self_, **kw):
        if str(self_) == target:
            return oversized
        return real_stat(self_, **kw)

WHAT IS DELIBERATELY NOT BANNED.

* ``Path.home`` / ``Path.cwd`` -- class-level, carrying no per-object state. Redirecting
  them globally is the POINT: it is how ~100 tests point Dream Studio at a temp home
  instead of the operator's real one. Banning that would delete the isolation that keeps
  the suite off live state.
* ``with patch.object(Path, "read_text", side_effect=OSError)`` -- a context manager whose
  blast radius is the statements you can see, and which is unwound before teardown. The
  harm above came from fixture-lifetime patching, which is still installed while autouse
  fixtures run their checks.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Stdlib types whose instance methods are shared by every object in the process.
_STDLIB_TYPES = frozenset(
    {
        "Path",
        "PurePath",
        "PosixPath",
        "WindowsPath",
        "datetime",
        "date",
        "timedelta",
        "dict",
        "list",
        "set",
        "tuple",
        "str",
        "bytes",
        "int",
        "float",
        "Popen",
        "Connection",
        "Cursor",
        "TemporaryDirectory",
    }
)

#: Class-level members that carry no per-object state. Redirecting these globally is the
#: intended mechanism for pointing the suite at a temp home, not a leak.
_STATELESS_MEMBERS = frozenset({"home", "cwd", "now", "utcnow", "today", "fromtimestamp"})


def _patched_type_name(arg: ast.expr) -> str | None:
    """The stdlib type name this patch targets, or None if it targets something else.

    Handles the three shapes that appear in the suite: ``type(f)`` (the shape that broke
    it), a bare ``Path``, and a qualified ``pathlib.Path``.
    """
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) and arg.func.id == "type":
        # `type(x)` cannot be resolved statically, so it is treated as a stdlib type
        # whenever it is patched at all -- which is the conservative and correct default:
        # the object under test is almost always a Path or a datetime.
        return "type(...)"
    if isinstance(arg, ast.Name) and arg.id in _STDLIB_TYPES:
        return arg.id
    if isinstance(arg, ast.Attribute) and arg.attr in _STDLIB_TYPES:
        return arg.attr
    return None


def _is_inline_fake(replacement: ast.expr) -> bool:
    """True when the replacement answers the same way for every object.

    A lambda, a mock, or a constant has no way to tell the object under test from any
    other, so it necessarily answers for all of them. A named function is allowed: a
    function body is where delegation to the real implementation can live, and requiring
    one is what turns an unconditional fake into a scoped one.
    """
    if isinstance(replacement, (ast.Lambda, ast.Constant)):
        return True
    if isinstance(replacement, ast.Call):
        func = replacement.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        # `MagicMock()` / `Mock()` / `mock.MagicMock()` answer uniformly too.
        return "Mock" in name
    return False


def _offenders_in(path: Path, repo_root: Path) -> list[dict]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []

    offenders: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Only fixture-lifetime patching. `with patch.object(...)` is unwound before
        # teardown and is deliberately out of scope -- see the module docstring.
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "setattr"
            and isinstance(func.value, ast.Name)
            and func.value.id == "monkeypatch"
        ):
            continue
        if len(node.args) < 3:
            continue  # the `monkeypatch.setattr("mod.attr", value)` string form

        type_name = _patched_type_name(node.args[0])
        if type_name is None:
            continue
        member = node.args[1]
        if isinstance(member, ast.Constant) and member.value in _STATELESS_MEMBERS:
            continue
        if not _is_inline_fake(node.args[2]):
            continue

        member_name = member.value if isinstance(member, ast.Constant) else "<computed>"
        try:
            rel = str(path.relative_to(repo_root))
        except ValueError:
            rel = str(path)
        offenders.append(
            {
                "path": rel.replace(chr(92), "/"),
                "line": node.lineno,
                "target": f"{type_name}.{member_name}",
                "message": (
                    f"monkeypatch.setattr({type_name}, {member_name!r}, <inline fake>) replaces"
                    f" an instance method for EVERY object of that type in the process, and"
                    " stays installed until fixture teardown -- where autouse guards run."
                    " A lambda, mock, or constant cannot tell the object under test from any"
                    " other, so unrelated code gets the fake answer: this exact shape made"
                    " the spool guard see writes into the operator's real ~/.dream-studio and"
                    " abort the whole suite FATAL, while the test itself passed. Pass a named"
                    " function that delegates to the real implementation for anything but the"
                    " object under test."
                ),
            }
        )
    return offenders


def _iter_tests(repo_root: Path) -> list[Path]:
    base = repo_root / "tests"
    if not base.is_dir():
        return []
    return [p for p in sorted(base.rglob("*.py")) if "__pycache__" not in p.parts]


def run(repo_root: Path = REPO_ROOT) -> dict:
    """Scan repo_root/tests. Parameterised so this gate's own tests can prove it FAILS."""
    offenders: list[dict] = []
    files = _iter_tests(repo_root)
    for path in files:
        offenders.extend(_offenders_in(path, repo_root))
    return {
        "status": "fail" if offenders else "pass",
        "files_scanned": len(files),
        "offenders": offenders,
    }


def main() -> int:
    result = run()
    if result["status"] != "pass":
        print(json.dumps(result, indent=2, sort_keys=True))
        print(
            f"\ntest-isolation: FAILED - {len(result['offenders'])} process-wide stdlib"
            " patch(es). Each can make an unrelated test or an autouse guard read a faked"
            " answer.",
            file=sys.stderr,
        )
        return 1
    print(
        f"test-isolation: OK - {result['files_scanned']} test file(s) scanned, no"
        " fixture-lifetime stdlib instance-method fakes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
