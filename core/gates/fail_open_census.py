"""Gate: a fail-open exception handler in product code is tracked debt, not a surprise.

WHY THIS EXISTS (H30). ``fail_open_probe.py`` catches one specific, serious shape: a
function-level handler that returns a permissive constant while an INDIVIDUAL database
call inside it has no guard of its own. That is real and worth keeping, but it is
narrower than the actual defect class. Two broader, more common shapes carry the same
risk and this gate carries none of them:

* ``except Exception: pass`` (or any exception type) — the error is caught and
  discarded. Nothing is logged, nothing is re-raised, nothing tells the caller anything
  went wrong.
* An except handler whose last statement returns a falsy sentinel (``None``, bare
  ``return``, ``False``, ``0``, ``""``, ``[]``, ``{}``, ``()``) — the caller cannot tell
  "the operation legitimately found nothing" from "the operation broke and nobody
  noticed", because both render identically at the call site.

Measured 2026-09-21: 484 ``except: pass`` sites and 258 falsy-return handlers in product
code (tests excluded). Both counts move as the tree changes and neither is realistically
zero-able in one pass — plenty of existing instances are deliberate and correct (a
missing optional config file IS legitimately "return None"). Demanding they all be fixed
before this gate can exist would make the gate a wall nobody could turn on. So this is a
RATCHET, identical in spirit to ``lint_baseline.py``'s flake8 baseline: every instance
present when the baseline was written is tracked debt, not a release blocker, and this
gate fails only on a site that is NEW beyond that baseline. Shrinking the baseline (fixing
an existing site) is free and encouraged; growing it blocks the push.

WHAT COUNTS AS A SITE, and what deliberately does not. AST-based, not regex, for the same
reason ``locale_decode_gate``/``security_scan`` are AST-based: a multi-line handler body
has no single line a regex can anchor to, and a handler INSIDE a docstring or comment is
not a handler at all.

* A handler counts once per handler, at its own line — not once per statement inside it.
* A handler with BOTH shapes (bare pass AND ends in a falsy return — impossible, since a
  ``pass``-only body cannot also end in a ``return``) is unambiguous by construction.
* A handler that logs, re-raises, or returns something else before falling through is not
  flagged for that shape; a leading docstring inside a would-be ``except: pass`` handler
  does not exempt it (the docstring explains the silence, it does not undo it).
* Test files are excluded — a test asserting an exception is swallowed, or exercising a
  fallback path, is not the same defect as production code doing it unnoticed.
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = REPO_ROOT / "runtime" / "config" / "release-gates" / "fail-open-baseline.txt"

#: Same product-code scope as fail_open_probe.py — tests legitimately fake/swallow errors
#: to exercise a fallback path, which is not this defect.
_SCANNED = ("core", "runtime", "interfaces", "control")

_FALSY_SHAPES = {
    ast.Constant: lambda n: n.value in (None, False, 0, ""),
    ast.List: lambda n: not n.elts,
    ast.Dict: lambda n: not n.keys,
    ast.Tuple: lambda n: not n.elts,
}


@dataclass(frozen=True)
class FailOpenSite:
    path: str
    line: int
    shape: str  # "bare-except-pass" | "falsy-return"

    @property
    def identity(self) -> str:
        return f"{self.path}|{self.line}|{self.shape}"

    def __str__(self) -> str:
        return f"{self.path}:{self.line} ({self.shape})"


def _is_docstring_expr(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _is_bare_except_pass(handler: ast.ExceptHandler) -> bool:
    body = [s for s in handler.body if not _is_docstring_expr(s)]
    return len(body) == 1 and isinstance(body[0], ast.Pass)


def _is_falsy_literal(node: ast.expr | None) -> bool:
    if node is None:
        return True  # bare `return`
    for node_type, check in _FALSY_SHAPES.items():
        if isinstance(node, node_type):
            return check(node)
    return False


def _is_falsy_return_handler(handler: ast.ExceptHandler) -> bool:
    if not handler.body:
        return False
    last = handler.body[-1]
    return isinstance(last, ast.Return) and _is_falsy_literal(last.value)


def _sites_in(path: Path, repo_root: Path) -> list[FailOpenSite]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return []

    try:
        rel = str(path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        rel = str(path)

    sites: list[FailOpenSite] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if _is_bare_except_pass(node):
            sites.append(FailOpenSite(rel, node.lineno, "bare-except-pass"))
        elif _is_falsy_return_handler(node):
            sites.append(FailOpenSite(rel, node.lineno, "falsy-return"))
    return sites


def _iter_source_files(repo_root: Path):
    for scanned in _SCANNED:
        base = repo_root / scanned
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            name = path.name
            if name.startswith("test_") or name.endswith("_test.py"):
                continue
            if any(part in {"__pycache__", ".venv", "venv"} for part in path.parts):
                continue
            yield path


def scan(repo_root: Path = REPO_ROOT) -> list[FailOpenSite]:
    """Every fail-open site in product code under ``repo_root``."""
    sites: list[FailOpenSite] = []
    for path in _iter_source_files(repo_root):
        sites.extend(_sites_in(path, repo_root))
    return sorted(sites, key=lambda s: (s.path, s.line))


def load_baseline(path: Path) -> list[str]:
    if not path.is_file():
        return []
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


def compare_to_baseline(current: list[FailOpenSite], baseline: list[str]) -> dict[str, object]:
    current_identities = [s.identity for s in current]
    current_counts = Counter(current_identities)
    baseline_counts = Counter(baseline)

    new_counts = current_counts - baseline_counts
    resolved_counts = baseline_counts - current_counts

    new_sites = [s for s in current if new_counts[s.identity] > 0]
    seen: Counter[str] = Counter()
    deduped_new = []
    for site in new_sites:
        seen[site.identity] += 1
        if seen[site.identity] <= new_counts[site.identity]:
            deduped_new.append(site)

    return {
        "status": "pass" if not deduped_new else "fail",
        "current_count": len(current),
        "baseline_count": len(baseline),
        "new_sites": [str(s) for s in deduped_new],
        "new_count": len(deduped_new),
        "resolved_count": sum(resolved_counts.values()),
    }


def write_baseline(path: Path, sites: list[FailOpenSite]) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "# Dream Studio fail-open census baseline (H30).",
        "# Existing sites are tracked debt, not release blockers unless the count grows.",
        "# Each line: <relative/path.py>|<line>|<bare-except-pass|falsy-return>",
        "# Regenerate with: py -m core.gates.fail_open_census --write-baseline",
        "",
    ]
    lines = sorted(s.identity for s in sites)
    path.write_text("\n".join(header + lines) + "\n", encoding="utf-8")
    return {"status": "written", "baseline_count": len(lines)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ratcheted census of fail-open exception handlers in product code (H30)."
    )
    parser.add_argument(
        "--repo-root", default=None, help="Scan THIS tree instead of this gate's own repo."
    )
    parser.add_argument(
        "--baseline", default=None, help="Baseline file path (default: the pinned repo baseline)."
    )
    parser.add_argument(
        "--write-baseline", action="store_true", help="Write the current sites as the new baseline."
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else REPO_ROOT
    baseline_path = Path(args.baseline).resolve() if args.baseline else DEFAULT_BASELINE

    sites = scan(repo_root)

    if args.write_baseline:
        result = write_baseline(baseline_path, sites)
        print(f"fail-open-census: wrote {result['baseline_count']} site(s) to {baseline_path}")
        return 0

    baseline = load_baseline(baseline_path)
    result = compare_to_baseline(sites, baseline)

    if result["status"] != "pass":
        resolved_note = (
            f" ({result['resolved_count']} other site(s) resolved since baseline in the"
            " same run)"
            if result["resolved_count"]
            else ""
        )
        print(
            f"fail-open-census: FAILED - {result['new_count']} new fail-open site(s) beyond"
            f" the {result['baseline_count']}-site baseline{resolved_note}.",
            file=sys.stderr,
        )
        for site in result["new_sites"]:
            print(f"  NEW: {site}", file=sys.stderr)
        print(
            "\n  A bare `except: pass` or an except handler ending in a falsy `return`"
            " tells the caller nothing went wrong. Log it, re-raise it, or return a"
            " signal the caller can act on. If this site is deliberate and reviewed,"
            " regenerate the baseline: py -m core.gates.fail_open_census --write-baseline",
            file=sys.stderr,
        )
        return 1

    resolved_note = (
        f", {result['resolved_count']} resolved since baseline" if result["resolved_count"] else ""
    )
    print(
        f"fail-open-census: OK - {result['current_count']} site(s) tracked in baseline"
        f" ({result['baseline_count']} pinned{resolved_note}), no new ones."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
