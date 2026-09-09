"""Gate: a per-item wait must be bounded in total, not only per item.

REVIEW LANE ``a-per-item-wait-with-no-aggregate-deadline`` (canonical/review_lanes.yml).

THE FINDING THIS COMES FROM. The Machinist on gw#849, the strongest finding of that review
pass. The module had ALREADY solved unbounded stall for one loop -- its own comment, forty
lines above the new code, says a per-slug ceiling multiplied by an agent's skill count is
loop stall time, and sets ``_LOCK_BATCH_BUDGET_S = 5.0`` for exactly that reason. Lock
waiting was batch-capped. The new per-card retry was not: two sleeps of 0.5s inside
``for sid in ids:`` with no aggregate deadline, which is ~20s at 20 equipped skills, plus
the equip retry's own 1.0s -- scaling linearly past the 30s timeout the module itself
cites.

Every individual wait was bounded. Nothing bounded the product.

THE PREDICATE, AND WHY IT IS THIS ONE. A first cut asked: is there a sleep in a loop, in a
module that defines a budget constant? That found exactly one candidate in this repo --
``core/work_orders/artifacts.py:216`` -- and reading it showed a FALSE POSITIVE:
``_LOCK_ATTEMPTS = 4`` with a 0.15s backoff is 0.90s worst case, on a single artifact write,
not inside any outer per-item loop. Bounded, and not the shape.

What made gw#849 a defect was MULTIPLICATION: the waiting loop sat inside another loop whose
length is data-dependent. So the predicate requires NESTING, and with that requirement this
repo measures 0 -- which is why this gate runs over the whole tree instead of being
diff-scoped like its sibling ``untested-fallback``. A gate that starts at zero can stay at
zero.

WHAT IT CANNOT SEE, stated rather than implied: multiplication through a CALL. A loop that
calls a helper which itself sleeps in a loop is the same defect and is invisible here,
because following that needs a call graph. An audit confirmed this limit is real and that
the docstring was honest about it -- and separately found one that was NOT disclosed, a
comprehension standing in for the inner loop, which is now detected.

The nesting form is the one that appeared in the finding and the one a reviewer can spot.
The call form is why this lane also carries a question for a human to ask.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Names that mean "something is watching the total". A loop consulting any of these has an
#: aggregate bound, whatever it does per item.
_DEADLINE_HINT = re.compile(r"monotonic|perf_counter|deadline|budget|elapsed|time_left", re.I)

#: The wait itself. `sleep` covers time.sleep, asyncio.sleep and any aliased import of
#: either -- the call's name is the signal, not the module it came from.
_WAIT_CALL = re.compile(r"\bsleep\s*\(")

#: An author who has bounded the total some way this cannot see says so on the loop.
_EXEMPTION = re.compile(r"#\s*aggregate-deadline:\s*(?P<reason>\S.*)")

#: Shorter than this is not a reason.
_MIN_REASON_CHARS = 20


def _tracked_python() -> list[str]:
    """Tracked ``.py`` files, excluding tests.

    Tests are excluded because a sleeping loop in a test is a test being slow, not a
    production stall -- and `hanging_detectors` already owns slow tests.
    """
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", "ls-files", "*.py"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    return [
        name.strip().replace("\\", "/")
        for name in (proc.stdout or "").splitlines()
        if name.strip() and not name.strip().startswith("tests/")
    ]


def offenders_in_text(source: str, rel: str) -> list[dict]:
    """Findings for one module's text.

    Public so tests can call it with constructed source -- a nested sleeping loop, the same
    with an outer deadline, a bounded single retry -- rather than editing a real module.
    Mutating a real input tests the input; it does not test the checker.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        # Not this gate's business: `security-scan` owns unparseable Python and reports it.
        return []

    lines = source.splitlines()
    offenders: list[dict] = []
    seen: set[tuple[int, int]] = set()

    for outer in ast.walk(tree):
        if not isinstance(outer, (ast.For, ast.While, ast.AsyncFor)):
            continue
        outer_src = ast.unparse(outer)
        if _DEADLINE_HINT.search(outer_src):
            # The enclosing loop watches the total. Whatever the inner loop does per item,
            # the product is bounded.
            continue
        for inner in ast.walk(outer):
            # A COMPREHENSION ITERATES TOO. `for batch in batches: [sleep(x) for x in sub]`
            # was invisible while only For/While/AsyncFor counted -- found by an audit, and
            # undisclosed at the time, unlike the call-based gap below.
            if inner is outer or not isinstance(
                inner,
                (
                    ast.For,
                    ast.While,
                    ast.AsyncFor,
                    ast.ListComp,
                    ast.SetComp,
                    ast.DictComp,
                    ast.GeneratorExp,
                ),
            ):
                continue
            inner_src = ast.unparse(inner)
            if not _WAIT_CALL.search(inner_src):
                continue
            if _DEADLINE_HINT.search(inner_src):
                continue
            key = (getattr(outer, "lineno", 0), getattr(inner, "lineno", 0))
            if key in seen:
                continue
            seen.add(key)

            reason = _declared_reason(lines, getattr(outer, "lineno", 0))
            if reason is not None and len(reason) >= _MIN_REASON_CHARS:
                continue
            if reason is not None:
                offenders.append(
                    {
                        "file": rel,
                        "line": key[1],
                        "outer_loop_line": key[0],
                        "message": (
                            f"{rel}:{key[1]} is exempted with no usable reason ({reason!r})."
                            " Say what bounds the total, in at least"
                            f" {_MIN_REASON_CHARS} characters."
                        ),
                    }
                )
                continue
            offenders.append(
                {
                    "file": rel,
                    "line": key[1],
                    "outer_loop_line": key[0],
                    "message": (
                        f"{rel}:{key[1]} waits inside a loop that is itself inside the loop"
                        f" at line {key[0]}, and neither bounds the TOTAL. Every wait here"
                        " is bounded per item; nothing bounds the product, so the ceiling"
                        " multiplies by a count the data decides. That is gw#849: a"
                        " per-card retry of 2 x 0.5s inside a loop over equipped skills was"
                        " ~20s at 20 skills, past the 30s timeout the module itself cited,"
                        " in a module that had already batch-capped its other loop for"
                        " exactly this reason. Consult a deadline in the outer loop, or say"
                        " what bounds it: '# aggregate-deadline: <what bounds the total>'."
                    ),
                }
            )
    return offenders


def _declared_reason(lines: list[str], loop_line: int) -> str | None:
    """A declaration on the outer loop's line or the contiguous comment block above it.

    Contiguous on purpose, the same as `security-scan`'s exemption: an unrelated comment
    further up the file must not reach down and excuse a stall.
    """
    index = loop_line - 1
    if 0 <= index < len(lines):
        match = _EXEMPTION.search(lines[index])
        if match:
            return match.group("reason").strip()
    cursor = index - 1
    while 0 <= cursor < len(lines) and lines[cursor].lstrip().startswith("#"):
        match = _EXEMPTION.search(lines[cursor])
        if match:
            return match.group("reason").strip()
        cursor -= 1
    return None


def run() -> dict:
    """Scan every tracked non-test module."""
    offenders: list[dict] = []
    scanned = 0
    for rel in _tracked_python():
        path = REPO_ROOT / rel
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        offenders.extend(offenders_in_text(source, rel))
    return {
        "status": "fail" if offenders else "pass",
        "modules_scanned": scanned,
        "offenders": offenders,
    }


def main() -> int:
    result = run()
    if result["status"] != "pass":
        print(json.dumps(result, indent=2, sort_keys=True))
        print(
            f"\naggregate-deadline: FAILED - {len(result['offenders'])} per-item wait(s)"
            " with nothing bounding the total.",
            file=sys.stderr,
        )
        return 1
    print(
        "aggregate-deadline: OK -"
        f" {result['modules_scanned']} module(s), no unbounded per-item wait."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
