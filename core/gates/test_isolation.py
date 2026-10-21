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

THE SECOND RULE (2026-10-21, GitHub issue #911): a test may not read the machine it runs on.
``core/gates/machine_reads.py`` carries the detector and its reasons. In short: a read of the
operator's home, ``~/.claude``, the Claude Code config root (``CLAUDE_CONFIG_DIR``), a sibling
checkout, or this clone's git refs and history (``origin/main``) must sit in a scope that
redirects the home first, or in a test marked ``install_check``, which is never collected by
default. A test that skips when such a thing is absent cannot fail anywhere that it is absent.
A shrinking allow-list in that module names what is left, each with a reason, and the gate fails
on an entry that no longer matches anything.

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

import argparse
import ast
import json
import sys
from pathlib import Path

from core.gates import machine_reads

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
                "kind": "process-wide-patch",
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


def run(
    repo_root: Path = REPO_ROOT,
    allowlist: dict[tuple[str, str], str] | None = None,
) -> dict:
    """Scan repo_root/tests. Parameterised so this gate's own tests can prove it FAILS.

    ``allowlist`` defaults to the real one when scanning this repository and to nothing when
    scanning any other tree: a fixture tree must not be failed for "stale" entries that name
    files it never had.
    """
    offenders: list[dict] = []
    machine: list[dict] = []
    files = _iter_tests(repo_root)
    for path in files:
        offenders.extend(_offenders_in(path, repo_root))
        machine.extend(machine_reads.scan_file(path, repo_root))
    if allowlist is None:
        allowlist = machine_reads.ALLOWLIST if repo_root == REPO_ROOT else {}
    failing, stale = machine_reads.apply_allowlist(machine, allowlist)
    offenders.extend(failing)
    offenders.extend(stale)
    return {
        "status": "fail" if offenders else "pass",
        "files_scanned": len(files),
        "allowlisted": len(machine) - len(failing),
        "offenders": offenders,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan the tests for process-wide patches and for reads of the machine."
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Scan THIS tree instead of the repo this gate module lives in (D18).",
    )
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else REPO_ROOT

    result = run(repo_root=repo_root)
    if result["status"] != "pass":
        print(json.dumps(result, indent=2, sort_keys=True))
        kinds: dict[str, int] = {}
        for off in result["offenders"]:
            kinds[off.get("kind", "?")] = kinds.get(off.get("kind", "?"), 0) + 1
        summary = ", ".join(f"{n} {kind}" for kind, n in sorted(kinds.items()))
        print(
            f"\ntest-isolation: FAILED - {len(result['offenders'])} finding(s) ({summary}). A"
            " process-wide stdlib patch can make an unrelated test or an autouse guard read a"
            " faked answer; a machine read makes a test's result depend on whose computer runs"
            " it. See core/gates/test_isolation.py and core/gates/machine_reads.py.",
            file=sys.stderr,
        )
        return 1
    print(
        f"test-isolation: OK - {result['files_scanned']} test file(s) scanned, no"
        " fixture-lifetime stdlib instance-method fakes, no unredirected read of the machine"
        f" ({result['allowlisted']} allow-listed, see machine_reads.ALLOWLIST)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
