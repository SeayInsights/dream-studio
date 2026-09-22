"""pr-smoke runs the tests the blast-radius gate selects, plus the ones it cannot select.

WHY THIS FILE EXISTS. `core.gates.blast_radius.evaluate` computed "the dependent pytest
nodes that must run before merge" and said the set was included "so the matrix step can
run the dependent tests". No step did. pr-smoke ran a fixed ten files -- 105 of 6,747
tests -- while three PRs merged green and left main red.

The replays below are those three PRs' real file lists. Together they show why the step
needs three sources, not one:
  - #782 broke tests that scan source trees by glob and name no module: reference
    selection is structurally blind to them, so the SWEEP class always runs;
  - #784 broke tests by editing canonical/rules.yml, a data file: only .py changes
    produced selection tokens, so a changed DATA file now selects the tests that name it;
  - the module-reference rule that already existed reaches the rest.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from interfaces.cli import impact_tests_gate as gate

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Files changed by 3339860, "Give a task the middle state, so spend can name one (#782)".
#: It left three tests red on main: two in test_status_vocabulary.py, one in
#: test_emitter_tool_normalization.py. None names a module this change touched.
PR_782 = [
    "canonical/skills/ds-workorder/SKILL.md",
    "core/work_orders/mutations.py",
    "dist/plugin/skills/ds-workorder/SKILL.md",
    "emitters/claude_code/token_transcript.py",
    "interfaces/cli/commands/work_order_dispatch.py",
    "tests/unit/test_task_in_progress_state.py",
    "tests/unit/test_token_capture_quality.py",
]

#: The data-file half of 132dc5d, "Dissolve the milestone pack ... (#784)". Editing the
#: registry broke two tests in test_rule_enforcement_gate.py, which names that path.
PR_784_DATA_ONLY = ["canonical/rules.yml"]


# ── the sweep class is discovered, not listed ─────────────────────────────────


def test_the_selection_blind_test_is_found_as_a_sweep_test():
    """The #782 failure the impact set could never have selected: it globs emitters/ for
    sqlite3 imports and never names `emitters.claude_code.token_transcript`."""
    assert "tests/unit/emitters/test_emitter_tool_normalization.py" in gate.sweep_tests(REPO_ROOT)


def test_sweep_discovery_is_by_pattern_not_by_list():
    """A hand-maintained list is the thing that rots. The module holds a pattern and
    walks the tree; it must not carry a literal test path anywhere."""
    source = Path(gate.__file__).read_text(encoding="utf-8")
    body = source.split('"""', 2)[-1]  # after the module docstring, which cites examples
    assert not re.search(r"tests/unit/[a-z_/]+\.py", body), "a test path is hardcoded"


def test_a_test_that_merely_mentions_glob_in_prose_is_not_swept(tmp_path):
    """The pattern matches a call, not the word. A docstring saying 'we glob the tree'
    must not pull a test into every run."""
    root = tmp_path
    (root / "tests" / "unit").mkdir(parents=True)
    (root / "tests" / "unit" / "test_prose.py").write_text(
        '"""This test does not glob anything, it only says so."""\n\n\ndef test_x():\n    assert 1\n',
        encoding="utf-8",
    )
    (root / "tests" / "unit" / "test_sweep.py").write_text(
        "from pathlib import Path\n\n\ndef test_y():\n"
        '    assert list(Path(".").rglob("*.py")) is not None\n',
        encoding="utf-8",
    )
    assert gate.sweep_tests(root) == ["tests/unit/test_sweep.py"]


# ── the three PRs that left main red, replayed ────────────────────────────────


def test_the_782_change_set_reaches_all_three_tests_it_broke():
    """Replay of the real file list. `start_task` spelled a status inline and opened
    sqlite3 from an emitter; the tests that catch both are sweep tests -- they find
    writers and imports by walking the tree -- so the impact set alone held none of them
    and the union must."""
    selection = gate.select_tests(PR_782, REPO_ROOT)
    for broken in (
        "tests/unit/test_status_vocabulary.py",
        "tests/unit/emitters/test_emitter_tool_normalization.py",
    ):
        assert broken in selection["tests"], f"{broken} would not have run"
        assert broken in selection["sweep_tests"], f"{broken} reached only by luck, not by rule"


def test_a_data_file_change_reaches_the_tests_that_name_it():
    """Replay of the #784 registry edit. Before the third selection rule this produced
    fifteen dependent files and neither of the two that failed, because a .yml change
    made no token. The test names `canonical/rules.yml`; the change to it must reach it."""
    selection = gate.select_tests(PR_784_DATA_ONLY, REPO_ROOT)
    assert "tests/unit/test_rule_enforcement_gate.py" in selection["dependent_tests"]


def test_the_union_is_never_empty():
    """A step that can go green by finding nothing to run is the failure this gate
    exists to end. With no changed files at all the sweep tests still run."""
    selection = gate.select_tests([], REPO_ROOT)
    assert selection["dependent_tests"] == []
    assert selection["tests"], "an empty change set produced nothing to run"
    assert selection["tests"] == selection["sweep_tests"]


def test_selection_keeps_provenance_for_the_log():
    """The step prints why each file runs. A reader of a failed run needs to know whether
    the test was reached by the change or always runs, because the remedies differ."""
    selection = gate.select_tests(PR_782, REPO_ROOT)
    for path in selection["tests"]:
        assert path in selection["dependent_tests"] or path in selection["sweep_tests"], path


def test_a_dependent_test_that_no_longer_exists_is_dropped_not_passed_to_pytest(tmp_path):
    """pytest exits 4 on a missing path and runs nothing -- a red step that verified
    nothing, the worst of both. A stale reference is filtered, not forwarded."""
    root = tmp_path
    (root / "core" / "x").mkdir(parents=True)
    (root / "core" / "x" / "__init__.py").write_text("", encoding="utf-8")
    (root / "core" / "x" / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (root / "tests" / "unit").mkdir(parents=True)
    (root / "tests" / "unit" / "test_real.py").write_text(
        "from core.x.mod import f\n\n\ndef test_f():\n    assert f() == 1\n", encoding="utf-8"
    )
    selection = gate.select_tests(["core/x/mod.py"], root)
    assert selection["dependent_tests"] == ["tests/unit/test_real.py"]
    for path in selection["tests"]:
        assert (root / path).is_file(), path


# ── the step is wired, and reuses the one CI test environment ─────────────────


def test_pr_smoke_runs_the_impact_set_step():
    """A gate that exists in no manifest is the defect it was built to catch. This one is
    pinned to the pr-smoke job, after the blast-radius step whose output it consumes."""
    ci = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    steps = ci["jobs"]["pr-smoke"]["steps"]
    runs = [str(s.get("run", "")) for s in steps]
    idx = next((i for i, r in enumerate(runs) if "interfaces/cli/impact_tests_gate.py" in r), None)
    assert idx is not None, "pr-smoke has no step running impact_tests_gate.py"
    blast = next(i for i, r in enumerate(runs) if "core.gates.blast_radius" in r)
    assert idx > blast, "the impact step must come after the blast-radius step it consumes"
    assert "DREAM_STUDIO_BASE_REF" in (steps[idx].get("env") or {}), "no base ref, no diff"


def test_the_gate_reuses_the_ci_test_environment_rather_than_defining_a_second():
    """`ci_gate._isolated_test_env` is the one definition of how CI keeps a pytest run
    off the operator's home. A second copy here is a second place for it to drift."""
    source = Path(gate.__file__).read_text(encoding="utf-8")
    assert "_isolated_test_env" in source
    assert "mkdtemp" not in source, "the gate defines its own isolation instead of reusing"
