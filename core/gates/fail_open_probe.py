"""Gate: an optional probe must not be able to answer the whole question.

THE DEFECT THIS EXISTS FOR, measured 2026-09-05. ``runtime/lib/enforcement.py``'s
``authority_write_since`` consults several independent signals -- a completed task, a task
created in the window, an impact-affirmation artifact, a terminal work order, canonical
events -- and wraps them in ONE function-level handler that fails open:

    except sqlite3.Error:
        return True          # a broken DB disables enforcement, never editing

That fail-open is deliberate and correct for the function as a whole. What was not correct
was leaving an individual probe unguarded inside it. A newly added probe selected
``created_at`` from ``business_tasks``; on a schema without that column the query raised
``sqlite3.Error``, the FUNCTION-level handler caught it, and the function returned ``True``
-- reporting "an authority write was recorded" for every work order on that machine. Stop
enforcement was silently disabled while telling the operator its condition was satisfied.

Not "off and complaining". Off and reporting success. Targeted tests never saw it; only a
full-suite run did, and only because one fixture happened to be narrower than production.

THE RULE. Inside a function whose own exception handler returns a permissive constant,
every database call must carry its own handler. Then a probe that cannot run contributes
nothing, instead of answering for all of them. The sibling artifact probe in that same
function already did this; the new one simply did not copy it.

Read-only AST analysis: no imports of the modules it inspects, so it is safe and fast
enough for the blocking pre-push tier.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Directories whose decision functions gate behaviour. Test trees are excluded: a test
#: that swallows an error fails visibly as a test, and fixtures legitimately fake queries.
_SCANNED = ("core", "runtime", "interfaces", "control")

#: Calls that reach a database. A probe is any of these inside a fail-open function.
_DB_CALL_ATTRS = frozenset({"execute", "executescript", "executemany", "fetchone", "fetchall"})


def _display(path: Path, repo_root: Path) -> str:
    """Repo-relative path when possible, absolute otherwise.

    A fixture tree passed by the gate's own tests is not under the repo, and
    ``relative_to`` raises ``ValueError`` there - which crashed an earlier gate.
    """
    try:
        rel = str(path.relative_to(repo_root))
    except ValueError:
        rel = str(path)
    return rel.replace(chr(92), "/")


def _returns_permissive_constant(handler: ast.ExceptHandler) -> bool:
    """True when the handler's body returns a constant that lets the caller proceed.

    ``return True`` in a check means "the condition is satisfied"; ``return None`` in a
    locator means "nothing found", which is the conservative answer and not fail-open.
    Only the permissive direction is flagged.
    """
    for node in handler.body:
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant):
            if node.value.value is True:
                return True
    return False


def _db_calls(node: ast.AST) -> list[ast.Call]:
    found: list[ast.Call] = []
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr in _DB_CALL_ATTRS
        ):
            found.append(child)
    return found


def _call_lines(node: ast.AST) -> set[int]:
    """The distinct SOURCE LINES carrying a database call.

    Lines, not call nodes, because one statement produces several. ``conn.execute(...)
    .fetchall()`` is two ``ast.Call`` nodes that both report the line where ``conn``
    starts, and counting nodes reported every probe twice. One statement is one probe.
    """
    return {call.lineno for call in _db_calls(node)}


def _early_exits(body: list[ast.stmt]) -> int:
    """Count conclusions the try body reaches EARLY, i.e. a return nested in a branch.

    This is what makes a probe "optional": the try holds several independent signals, any
    of which can conclude on its own. A single-probe function has one terminal return
    consuming its one query, and its function-level handler is legitimately that query's
    handler -- so a terminal return at the top level of the try body is not counted.

    Nested functions are skipped. After ``authority_write_since`` was refactored to route
    its five signals through a local ``probe()`` helper, the outer try held NO direct
    database call, and counting only calls made a single bare query added there look
    exempt -- while it could still answer for all five. Signals, not calls.
    """
    total = 0
    for stmt in body:
        if isinstance(stmt, ast.Return):
            continue  # terminal conclusion, not an early exit
        for child in ast.walk(stmt):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Return):
                total += 1
    return total


def _guarded_lines(node: ast.AST) -> set[int]:
    """Lines whose database call sits inside its OWN try block.

    Nested-try membership is what distinguishes a probe that handles its own failure from
    one relying on the function-level handler.
    """
    guarded: set[int] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Try):
            guarded |= _call_lines(ast.Module(body=child.body, type_ignores=[]))
    return guarded


def _offenders_in(path: Path, repo_root: Path) -> list[dict]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []

    offenders: list[dict] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # A function-level fail-open: a try whose handler returns True, and whose body is
        # (essentially) the function body rather than a small nested guard.
        fail_open_tries = [
            t
            for t in func.body
            if isinstance(t, ast.Try) and any(_returns_permissive_constant(h) for h in t.handlers)
        ]
        if not fail_open_tries:
            continue

        for outer in fail_open_tries:
            body = ast.Module(body=outer.body, type_ignores=[])
            probe_lines = _call_lines(body)
            signals = len(probe_lines) + _early_exits(outer.body)
            if signals < 2:
                # One signal IS the whole question. The function-level handler is that
                # query's own handler, and there is no sibling for it to answer on behalf
                # of -- which is the entire harm this gate exists to prevent.
                # ``docstore_record_since`` is the shape: one query, fail open by design.
                continue
            guarded = _guarded_lines(body)
            for line in sorted(probe_lines - guarded):
                offenders.append(
                    {
                        "path": _display(path, repo_root),
                        "function": func.name,
                        "line": line,
                        "message": (
                            f"{func.name}() fails open (its handler returns True), and the"
                            f" database call on line {line} has no handler of its own."
                            " An error there is caught by the function-level handler, which"
                            " then reports the condition SATISFIED for every caller -- the"
                            " check is disabled while claiming success. Wrap this probe in"
                            " its own try/except so a probe that cannot run contributes"
                            " nothing instead of answering for all of them."
                            f" This try holds {signals} independent signals; any one"
                            " of them failing currently answers for all."
                        ),
                    }
                )
    return offenders


def _iter_sources(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for root in _SCANNED:
        base = repo_root / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts or "test" in path.name:
                continue
            files.append(path)
    return files


def run(repo_root: Path = REPO_ROOT) -> dict:
    """Scan repo_root. The parameter exists so the gate's own tests can point it at a
    fixture tree and prove it FAILS on the defect - a gate no test can make fail is
    indistinguishable from a gate that checks nothing."""
    offenders: list[dict] = []
    scanned = 0
    for path in _iter_sources(repo_root):
        scanned += 1
        offenders.extend(_offenders_in(path, repo_root))
    return {
        "status": "fail" if offenders else "pass",
        "files_scanned": scanned,
        "offenders": offenders,
    }


def main() -> int:
    result = run()
    if result["status"] != "pass":
        print(json.dumps(result, indent=2, sort_keys=True))
        print(
            f"\nfail-open-probe: FAILED - {len(result['offenders'])} unguarded database call(s)"
            " inside a fail-open function. Each can disable its check while reporting"
            " success.",
            file=sys.stderr,
        )
        return 1
    print(
        f"fail-open-probe: OK - {result['files_scanned']} file(s) scanned, every database"
        " call inside a fail-open function carries its own handler."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
