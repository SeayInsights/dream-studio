"""Blast-radius merge gate (WO-BLAST-RADIUS-GATE).

pr-smoke runs a fixed subset of tests; the full suite that catches stale tests
and contract violations runs only post-merge and blocks nothing. That gap let
main go red for 11 consecutive merges (#347 stale shared-intelligence tests,
#353 handoff signature caller, #354 token_projection ownership violation).

This module closes the gap at merge time. From the diff it:

  1. computes the IMPACT SET — the dependent pytest nodes that must run before
     merge (a changed test runs itself; a changed source module pulls in every
     test that imports/references it), plus the impacted contract domains
     (reusing contract_registry.change_impact_report); and
  2. runs NOTHING-LEFT-HANGING detectors for the blast-radius-bigger-than-fix
     case — stale tests, broken callers, and authority/ownership violations that
     the fix's own change set leaves behind (see hanging_detectors.py).

`compute_impact_set` is pure and deterministic (no DB, no network) so the gate
can run identically in pre-push and in the pr-smoke matrix.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip()


def _is_test_file(path: str) -> bool:
    p = _normalize(path)
    return p.startswith("tests/") and p.endswith(".py") and Path(p).name.startswith("test_")


def _module_tokens(source_path: str) -> set[str]:
    """Dotted module path(s) a source file is importable as.

    ``core/foo/bar.py`` → ``{"core.foo.bar"}``.
    ``core/foo/__init__.py`` → ``{"core.foo.__init__", "core.foo"}``.
    """
    p = _normalize(source_path)
    if not p.endswith(".py"):
        return set()
    mod = p[:-3].replace("/", ".")
    tokens = {mod}
    if mod.endswith(".__init__"):
        tokens.add(mod[: -len(".__init__")])
    return tokens


def _iter_test_files(repo_root: Path) -> Iterable[Path]:
    tests_dir = repo_root / "tests"
    if not tests_dir.is_dir():
        return
    yield from tests_dir.rglob("test_*.py")


def compute_impact_set(
    changed_files: Iterable[str],
    *,
    repo_root: Path | str = REPO_ROOT,
) -> dict[str, Any]:
    """Map changed files to the dependent test set and impacted contract domains.

    Returns a dict::

        {
          "changed_files": [...normalized...],
          "dependent_tests": [...pytest file paths, sorted...],
          "impacted_contract_domains": [...domain_id...],
          "module_tokens": [...dotted modules the source changes expose...],
        }

    Selection rules:
      - a changed test file selects itself;
      - a changed ``.py`` source file selects every ``tests/**/test_*.py`` whose
        text references its dotted module path (word-boundary match, so
        ``core.foo.bar`` does not match ``core.foo.barbaz`` but does match
        ``core.foo.bar.do_thing`` and ``from core.foo.bar import ...``).
    """
    root = Path(repo_root)
    changed = sorted({_normalize(f) for f in changed_files if f})

    dependent: set[str] = set()
    module_tokens: set[str] = set()
    for f in changed:
        if _is_test_file(f):
            dependent.add(f)
        elif f.endswith(".py"):
            module_tokens.update(_module_tokens(f))

    if module_tokens:
        patterns = [re.compile(re.escape(tok) + r"\b") for tok in module_tokens]
        for test_path in _iter_test_files(root):
            rel = _normalize(str(test_path.relative_to(root)))
            if rel in dependent:
                continue
            try:
                text = test_path.read_text(encoding="utf-8")
            except OSError:
                continue
            if any(pat.search(text) for pat in patterns):
                dependent.add(rel)

    impacted_domains: list[str] = []
    try:
        from core.shared_intelligence.contract_registry import change_impact_report

        report = change_impact_report(changed)
        impacted_domains = [d["domain_id"] for d in report["domains"] if d["impacted"]]
    except Exception:
        impacted_domains = []

    return {
        "changed_files": changed,
        "dependent_tests": sorted(dependent),
        "impacted_contract_domains": impacted_domains,
        "module_tokens": sorted(module_tokens),
    }
