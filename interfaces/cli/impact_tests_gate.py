"""Run the tests the blast-radius gate says must run before merge.

THE HALF THAT WAS NEVER WRITTEN. `core.gates.blast_radius.evaluate` computes the impact
set -- "the dependent pytest nodes that must run before merge", in its own words -- and
its docstring says the set "is always included so the matrix step can run the dependent
tests". No matrix step ever did. pr-smoke printed the list and ran a fixed ten files
instead: 105 of 6,747 tests, 1.6% of the suite. Its own failure banner even says "the
pr-smoke subset misses them".

Measured on PR #786, the fix for five failures that three green PRs had landed on main:
the gate computed 36 dependent test files, pr-smoke ran none, and that set contained the
tests for four of the five. Running what the gate already printed would have caught them
before merge, at ~100s.

TWO SOURCES, BECAUSE REFERENCE SELECTION IS BLIND TO ONE KIND OF TEST. The impact set
selects a test when its text names a changed module. A test that scans a source tree by
glob -- `emitters/` must not import sqlite3, every projection must stay read-only --
names no module and can never be selected that way, and that is exactly the fifth
failure. Those are discovered here by the pattern that defines them, not listed by hand,
so the next one written is included without anyone editing this file.

The union can never be empty: the sweep tests always run, so this step cannot go green
by finding nothing to do. The environment comes from `ci_gate._isolated_test_env`, the
one definition of how CI isolates a pytest run from the operator's home.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: A test that walks a source tree rather than importing a module. Each alternative is a
#: spelling found in the suite; the set is what `test_emitter_tool_normalization` and its
#: 17 siblings have in common and nothing else does.
SWEEP_PATTERN = re.compile(
    r"""rglob\(['"]\*\*?/?\*\.py|glob\(['"]\*\*/\*\.py|_python_files\(|\.rglob\("\*\.py"\)"""
)

TEST_ROOTS = ("tests/unit", "tests/integration")

#: Cross-cutting guards that run whatever the diff touches.
#:
#: These were a SEPARATE pr-smoke step -- ten files named in ci.yml -- and they are in
#: neither the impact set nor the sweep class: they do not glob a source tree, and a change
#: to a release gate does not name them. They only ever ran because they were listed, which
#: made ci.yml a second place deciding what pr-smoke runs.
#:
#: They live here now so the union is computed once. A list that must agree with another
#: list by inspection is the arrangement this repo keeps removing.
ALWAYS_RUN = (
    "tests/integration/test_pr_smoke_impact.py",
    "tests/unit/test_contract_atlas_lifecycle.py",
    "tests/unit/test_contract_docs_drift_gate.py",
    "tests/unit/test_ds_update_skill_drift.py",
    "tests/unit/test_fail_open_probe_gate.py",
    "tests/unit/test_fixture_schema_parity_gate.py",
    "tests/unit/test_github_pr_cicd_release_gate.py",
    "tests/unit/test_hanging_detectors.py",
    "tests/unit/test_impact_selection.py",
    "tests/unit/test_locale_decode_gate.py",
    "tests/unit/test_plugin_dist.py",
    "tests/unit/test_release_gate_lint_baseline_policy.py",
    "tests/unit/test_release_gates_dependency_rules.py",
    "tests/unit/test_seam_payload_to_projection.py",
    "tests/unit/test_skill_module_paths_resolve.py",
    "tests/unit/test_test_isolation_gate.py",
)


def sweep_tests(repo_root: Path | str = REPO_ROOT) -> list[str]:
    """Tests that scan source trees, which module-reference selection cannot see."""
    root = Path(repo_root)
    found: list[str] = []
    for rel_root in TEST_ROOTS:
        base = root / rel_root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("test_*.py")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if SWEEP_PATTERN.search(text):
                found.append(path.relative_to(root).as_posix())
    return found


def select_tests(changed_files: list[str], repo_root: Path | str = REPO_ROOT) -> dict[str, Any]:
    """The impact set unioned with the sweep tests, with provenance for the log."""
    from core.gates.blast_radius import compute_impact_set

    root = Path(repo_root)
    impact = compute_impact_set(changed_files, repo_root=root)
    dependent = [t for t in impact["dependent_tests"] if (root / t).is_file()]
    sweep = sweep_tests(root)
    always = [p for p in ALWAYS_RUN if (root / p).is_file()]
    union = sorted(set(dependent) | set(sweep) | set(always))
    return {
        "changed_files": impact["changed_files"],
        "dependent_tests": dependent,
        "sweep_tests": sweep,
        "always_run": always,
        "tests": union,
        # Real import-graph ancestors past IMPORT_GRAPH_MAX_DEPTH -- see that
        # constant's docstring in core/gates/blast_radius.py. Propagated (not
        # recomputed) so this step's log is the one place a human or CI actually
        # reads that says whether the closure was truncated.
        "import_graph_truncated_test_count": impact.get("import_graph_truncated_test_count", 0),
    }


def main() -> int:
    # The same resolution blast_radius uses, imported rather than restated: two gates that
    # disagree about what the diff is would report on two different pull requests.
    from core.gates.blast_radius import _resolve_diff_and_changed

    from interfaces.cli.ci_gate import _isolated_test_env

    base_ref = os.environ.get("DREAM_STUDIO_BASE_REF")
    github_base = os.environ.get("GITHUB_BASE_REF")
    if github_base and not base_ref:
        base_ref = f"origin/{github_base}"
    if not base_ref:
        base_ref = "origin/main"

    _diff, changed = _resolve_diff_and_changed(REPO_ROOT, base_ref)
    selection = select_tests(changed, REPO_ROOT)

    print(
        f"[impact-tests] {len(selection['changed_files'])} changed file(s) -> "
        f"{len(selection['dependent_tests'])} dependent test file(s) + "
        f"{len(selection['sweep_tests'])} sweep + {len(selection['always_run'])} always"
        f" = {len(selection['tests'])} to run"
    )
    for path in selection["tests"]:
        why = "+".join(
            k
            for k, v in (
                ("impact", selection["dependent_tests"]),
                ("sweep", selection["sweep_tests"]),
                ("always", selection["always_run"]),
            )
            if path in v
        )
        print(f"    {why:18s} {path}")
    truncated = selection.get("import_graph_truncated_test_count", 0)
    if truncated:
        print(
            f"    [import-graph] {truncated} real dependent test file(s) sit beyond the "
            "depth bound and were NOT selected -- see IMPORT_GRAPH_MAX_DEPTH in "
            "core/gates/blast_radius.py"
        )
    sys.stdout.flush()

    result = subprocess.run(
        [sys.executable, "-m", "pytest", *selection["tests"], "-q"],
        cwd=REPO_ROOT,
        env=_isolated_test_env(),
        check=False,
    )
    if result.returncode != 0:
        print()
        print("=" * 70)
        print("IMPACT-TESTS GATE: a test the blast-radius gate selected has failed")
        print("=" * 70)
        print("These are the tests this change set reaches. Until now pr-smoke printed")
        print("this list and ran a fixed ten files instead.")
        print("=" * 70)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
