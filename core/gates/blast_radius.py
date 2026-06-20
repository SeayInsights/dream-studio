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

import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

BLAST_RADIUS_GATE_SCHEMA = "dream_studio.blast_radius_gate.v1"


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


def evaluate(
    diff_text: str,
    changed_files: Iterable[str],
    *,
    repo_root: Path | str = REPO_ROOT,
) -> dict[str, Any]:
    """Run the merge-time blast-radius gate. Pure — no git, no exit.

    Returns a report dict with ``status`` ``"pass"``/``"fail"``. Status is
    ``"fail"`` when any nothing-left-hanging detector fires; the impact set is
    always included so the matrix step can run the dependent tests.
    """
    from core.gates.hanging_detectors import run_all_detectors

    findings = run_all_detectors(diff_text, repo_root=repo_root)
    impact = compute_impact_set(changed_files, repo_root=repo_root)
    return {
        "schema": BLAST_RADIUS_GATE_SCHEMA,
        "status": "fail" if findings else "pass",
        "blocking_finding_count": len(findings),
        "findings": findings,
        "impact_set": impact,
    }


def _git(args: list[str], repo_root: Path) -> str:
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def _resolve_diff_and_changed(repo_root: Path, base_ref: str | None) -> tuple[str, list[str]]:
    """Resolve the unified diff text and changed-file list against the base ref."""
    if base_ref:
        rng = f"{base_ref}...HEAD"
        diff_text = _git(["diff", rng], repo_root)
        names = _git(["diff", "--name-only", rng], repo_root)
        if diff_text or names:
            return diff_text, [ln.strip() for ln in names.splitlines() if ln.strip()]
    # Fallback: staged + working-tree changes.
    diff_text = _git(["diff", "HEAD"], repo_root)
    names = _git(["diff", "--name-only", "HEAD"], repo_root)
    return diff_text, [ln.strip() for ln in names.splitlines() if ln.strip()]


def main() -> int:
    base_ref = os.environ.get("DREAM_STUDIO_BASE_REF")
    github_base = os.environ.get("GITHUB_BASE_REF")
    if github_base and not base_ref:
        base_ref = f"origin/{github_base}"
    if not base_ref:
        base_ref = "origin/main"

    diff_text, changed = _resolve_diff_and_changed(REPO_ROOT, base_ref)
    report = evaluate(diff_text, changed, repo_root=REPO_ROOT)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "pass":
        print()
        print("=" * 70)
        print("BLAST-RADIUS GATE: nothing-left-hanging detector(s) fired")
        print("=" * 70)
        for finding in report["findings"]:
            print(f"  [{finding['detector']}] {finding['message']}")
        print()
        print("These break main post-merge (the pr-smoke subset misses them).")
        print("Fix the dangling reference/ownership, or delete the dead test.")
        print("=" * 70)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
