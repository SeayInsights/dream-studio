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

import ast
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

#: Files changed by aad270c, "keep status payloads off the shared hook stdout stream
#: (#738)". It moved on-token-log's status to stderr; its own integration test read stdout
#: and was not selected, because the test loads the hook as handler("on-token-log").
PR_738 = [
    "control/execution/workflow/tracking.py",
    "docs/HOOK_RUNTIME.md",
    "docs/WORKFLOW_RUNTIME.md",
    "interfaces/cli/pulse_collector.py",
    "runtime/hooks/meta/on-context-inject.py",
    "runtime/hooks/meta/on-token-log.py",
    "tests/unit/test_pulse_collector_stdout_contract.py",
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
    """A hand-maintained list is the thing that rots. Sweep discovery holds a pattern and
    walks the tree.

    ALWAYS_RUN is a list, and deliberately so: those files are a third category -- the
    cross-cutting guards that used to be a separate ci.yml step -- and enumeration is what
    they ARE, because nothing about a diff reaches them. So the claim here is the one that
    was always meant: the SWEEP class is discovered, never enumerated, and no test path is
    hardcoded anywhere except inside that one declaration.
    """
    source = Path(gate.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    sweep = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "sweep_tests"
    )
    assert not re.search(
        r"tests/unit/[a-z_/]+\.py", ast.get_source_segment(source, sweep) or ""
    ), "sweep_tests enumerates a test path instead of discovering it"

    # The two declared lists: the cross-cutting guards, and the rule-enforcement pair that a
    # register or pytest-configuration change selects (its subject names no path to select by).
    declared = "".join(
        ast.get_source_segment(source, n) or ""
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and any(
            getattr(t, "id", None) in ("ALWAYS_RUN", "RULE_ENFORCEMENT_TESTS") for t in n.targets
        )
    )
    body = source.split('"""', 2)[-1]  # after the module docstring, which cites examples
    stray = [m for m in re.findall(r"tests/unit/[a-z_/]+\.py", body) if m not in declared]
    assert not stray, f"a test path is hardcoded outside ALWAYS_RUN: {stray}"


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


def test_a_hook_change_reaches_the_test_that_loads_it_by_name():
    """Replay of #738. A hook is not importable -- its stem is hyphenated -- so its module
    token matched nothing, and the one integration test exercising the change was not
    selected. Tests load hooks by stem; the stem is now a token. Thirty-two test files
    load hooks that way."""
    selection = gate.select_tests(PR_738, REPO_ROOT)
    assert "tests/integration/test_hook_on_token_log.py" in selection["dependent_tests"]


def test_a_skill_change_reaches_the_tests_that_name_its_pack():
    """The fourth replay, and the one that put main red twice.

    Tests about skill packs build their paths from parts --
    `REPO_ROOT / "canonical" / "skills" / "website" / "SKILL.md"` -- or name the pack
    alone in a table of surfaces. The repo-relative path never appears as a string, so
    neither the module rule nor the data-file rule reaches them, and they do not glob a
    source tree so the sweep class does not either. Eight tests went red on main across
    the ds-project and ds-workorder dissolutions for exactly this reason: the impact step
    ran, passed, and had selected none of them.
    """
    selection = gate.select_tests(["canonical/skills/website/SKILL.md"], REPO_ROOT)
    assert (
        "tests/unit/test_website_fullstack_packs.py" in selection["dependent_tests"]
    ), "a skill change does not reach the test that names its pack"


def test_the_pack_name_is_matched_quoted_not_as_a_bare_word(tmp_path):
    """Precision is what makes the rule usable rather than a slow way to run everything.

    Measured over 683 test files: the bare word `core` appears in 522 of them and the
    quoted `"core"` in 89, while `"website"` selects 8. Matching bare words would make a
    one-pack edit select most of the suite, and a step everyone distrusts is a step
    nobody reads.
    """
    root = tmp_path
    (root / "canonical" / "skills" / "website").mkdir(parents=True)
    (root / "canonical" / "skills" / "website" / "SKILL.md").write_text("x\n", encoding="utf-8")
    (root / "tests" / "unit").mkdir(parents=True)
    (root / "tests" / "unit" / "test_names_it.py").write_text(
        'PACK = "website"\n\n\ndef test_a():\n    assert PACK\n', encoding="utf-8"
    )
    (root / "tests" / "unit" / "test_mentions_it.py").write_text(
        '"""This test builds a website, in prose, and names no pack."""\n\n\n'
        "def test_b():\n    assert 1\n",
        encoding="utf-8",
    )
    selected = gate.select_tests(["canonical/skills/website/SKILL.md"], root)["dependent_tests"]
    assert "tests/unit/test_names_it.py" in selected
    assert "tests/unit/test_mentions_it.py" not in selected, "a bare word pulled in prose"


def test_the_union_is_never_empty():
    """A step that can go green by finding nothing to run is the failure this gate
    exists to end. With no changed files at all the sweep tests still run."""
    selection = gate.select_tests([], REPO_ROOT)
    assert selection["dependent_tests"] == []
    assert selection["tests"], "an empty change set produced nothing to run"
    # The two sources a change cannot switch off: the sweep class and the always-run
    # guards. A diff of nothing still runs both.
    assert selection["tests"] == sorted(
        set(selection["sweep_tests"]) | set(selection["always_run"])
    )


def test_selection_keeps_provenance_for_the_log():
    """The step prints why each file runs. A reader of a failed run needs to know whether
    the test was reached by the change or always runs, because the remedies differ."""
    selection = gate.select_tests(PR_782, REPO_ROOT)
    for path in selection["tests"]:
        assert (
            path in selection["dependent_tests"]
            or path in selection["sweep_tests"]
            or path in selection["always_run"]
        ), path


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


def test_the_always_run_files_exist_and_are_the_only_hardcoded_list():
    """pr-smoke had TWO places deciding what it runs: the impact step and a hardcoded
    sixteen-file step in ci.yml. The list is here now, so the union is computed once.

    Transcribing it was the risk and it nearly bit: the first pass captured eleven of the
    sixteen, having read the step's first screenful, which would have quietly stopped
    running the locale-decode, fail-open, test-isolation, fixture-parity and payload-seam
    gates. A path that no longer exists is caught here rather than by a step that silently
    runs fewer files than it names.
    """
    missing = [p for p in gate.ALWAYS_RUN if not (REPO_ROOT / p).is_file()]
    assert not missing, f"ALWAYS_RUN names files that are not in the tree: {missing}"
    assert len(gate.ALWAYS_RUN) >= 16, "the always-run list shrank; was that deliberate?"


def test_ci_no_longer_carries_a_second_list_of_tests_to_run():
    """One decider. A second list in the workflow would have to agree with this one by
    inspection, which is the arrangement these gates keep removing."""
    import yaml

    ci = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    steps = ci["jobs"]["pr-smoke"]["steps"]

    # One step may still name files, and it is not a selection. The Store-alias step
    # reruns two hook tests with a stub shadowing bare `python`, which is a SCENARIO --
    # the impact step runs with a working interpreter and cannot express it.
    SCENARIO = "Stock Windows Store-alias state"
    offenders = [
        s.get("name", "(unnamed)")
        for s in steps
        if "pytest" in str(s.get("run", "")) and s.get("name") != SCENARIO
    ]
    assert not offenders, (
        "ci.yml runs pytest directly again, so what pr-smoke runs is decided in two "
        f"places: {offenders}"
    )

    # And the exemption is checked, not granted, or a plain list of tests could take the
    # exempt step's name and walk straight through this gate.
    for step in steps:
        if step.get("name") == SCENARIO:
            assert "store-alias" in str(step.get("run", "")), (
                f"{SCENARIO!r} no longer builds the Store-alias shim, so it is now just a "
                "second list of tests wearing the exemption's name"
            )

    assert any("impact_tests_gate.py" in str(s.get("run", "")) for s in steps)


def test_the_job_budget_matches_the_work():
    """Measured: the impact step took 12m05s on Windows for a 127-file selection, and the
    job's 15-minute budget -- set when it ran sixteen hardcoded files -- cancelled Windows
    mid-step. A cancelled leg reported as a non-pass is exactly the two-of-three green this
    line of work exists to refuse."""
    import yaml

    ci = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    assert ci["jobs"]["pr-smoke"].get("timeout-minutes", 0) >= 25


# ── the rule-enforcement tests follow what decides what a directory run collects ──────

RULE_TESTS = [
    "tests/unit/test_rule_enforcement_bare_run.py",
    "tests/unit/test_rule_enforcement_gate.py",
]


def test_the_bare_run_was_selected_only_by_luck_and_is_now_selected_by_rule():
    """The comparison of the resolver with a bare pytest run is selected by the impact set only
    when the resolver or `tests/helpers` changes. Its subject is the register and pytest's own
    configuration, which it names by no path, so a change to either left it unselected: the
    register, a register-named test, pyproject.toml and a conftest could each go red in a PR the
    job never ran it for."""
    for changed in (
        ["canonical/rules.yml"],
        ["pyproject.toml"],
        ["tests/conftest.py"],
        ["tests/unit/sub/conftest.py"],
        ["conftest.py"],
    ):
        selection = gate.select_tests(changed, REPO_ROOT)
        assert set(RULE_TESTS) <= set(selection["tests"]), changed
        assert selection["rule_enforcement_tests"] == RULE_TESTS, changed


def test_every_pytest_config_file_pytest_reads_selects_them(tmp_path):
    (tmp_path / "canonical").mkdir()
    (tmp_path / "canonical" / "rules.yml").write_text("rules: []\n", encoding="utf-8")
    for name in (
        "pytest.toml",
        ".pytest.toml",
        "pytest.ini",
        ".pytest.ini",
        "pyproject.toml",
        "tox.ini",
        "setup.cfg",
    ):
        assert gate.rule_enforcement_tests([name], tmp_path) == RULE_TESTS, name


def test_a_test_file_the_register_names_selects_them_and_one_it_does_not_name_does_not(tmp_path):
    (tmp_path / "canonical").mkdir()
    (tmp_path / "canonical" / "rules.yml").write_text(
        "rules:\n"
        "  - id: a-rule\n"
        "    enforced_by:\n"
        "      - tests/unit/test_named.py::TestA::test_x\n"
        "      - core/gates/some_gate.py\n"
        "      - tests/unit/test_plain_path.py\n"
        "  - id: no-enforcement\n"
        "    unenforced: gone\n",
        encoding="utf-8",
    )
    for named in ("tests/unit/test_named.py", "tests/unit/test_plain_path.py"):
        assert gate.rule_enforcement_tests([named], tmp_path) == RULE_TESTS, named
    # a path spelled the Windows way is the same file
    assert gate.rule_enforcement_tests(["tests\\unit\\test_named.py"], tmp_path) == RULE_TESTS
    for other in ("tests/unit/test_other.py", "README.md", "core/gates/other.py"):
        assert gate.rule_enforcement_tests([other], tmp_path) == [], other
    assert gate.rule_enforcement_tests([], tmp_path) == []


def test_a_register_that_cannot_be_read_selects_them_rather_than_nothing(tmp_path):
    (tmp_path / "canonical").mkdir()
    (tmp_path / "canonical" / "rules.yml").write_text("rules: [unclosed\n", encoding="utf-8")
    assert gate.rule_enforcement_tests(["tests/unit/test_x.py"], tmp_path) == RULE_TESTS
    assert gate.rule_enforcement_tests(["README.md"], tmp_path) == RULE_TESTS


def test_a_real_register_named_test_selects_them_on_the_real_register():
    register = yaml.safe_load((REPO_ROOT / "canonical" / "rules.yml").read_text(encoding="utf-8"))
    named = sorted(
        {
            ref.split("::")[0]
            for rule in register["rules"]
            for ref in rule.get("enforced_by") or []
            if ref.startswith("tests/") and ref.split("::")[0].endswith(".py")
        }
    )
    assert len(named) > 40
    for path in named:
        assert gate.rule_enforcement_tests([path], REPO_ROOT) == RULE_TESTS, path


def test_the_cost_of_the_rule_selection_is_bounded():
    """Two files whatever the diff, not a file per register entry: the bare run is the slow one
    and is paid once."""
    wide = [f"tests/unit/test_{n}.py" for n in range(300)] + ["canonical/rules.yml"]
    assert gate.rule_enforcement_tests(wide, REPO_ROOT) == RULE_TESTS


def test_the_log_names_why_a_rule_test_was_selected():
    source = Path(gate.__file__).read_text(encoding="utf-8")
    assert '"rule-enforcement"' in source and 'selection["rule_enforcement_tests"]' in source


def test_a_register_named_test_under_any_testpath_selects_them(tmp_path):
    """The code once required a `tests/` prefix while testpaths also names `analytics/tests`,
    so a register-named test there changed and nothing was selected."""
    (tmp_path / "canonical").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["tests", "analytics/tests", "pkg/*/checks"]\n',
        encoding="utf-8",
    )
    (tmp_path / "canonical" / "rules.yml").write_text(
        "rules:\n"
        "  - id: a-rule\n"
        "    enforced_by:\n"
        "      - analytics/tests/test_named.py::test_x\n"
        "      - tests/test_plain.py\n"
        "      - pkg/one/checks/test_glob.py::test_y\n"
        "      - core/gates/enforcer.py\n"
        "      - elsewhere/test_not_under_testpaths.py::test_z\n",
        encoding="utf-8",
    )
    for named in (
        "analytics/tests/test_named.py",
        "tests/test_plain.py",
        "pkg/one/checks/test_glob.py",
    ):
        assert gate.rule_enforcement_tests([named], tmp_path) == RULE_TESTS, named
    for other in (
        "core/gates/enforcer.py",
        "elsewhere/test_not_under_testpaths.py",
        "analytics/tests/test_other.py",
    ):
        assert gate.rule_enforcement_tests([other], tmp_path) == [], other


def test_without_testpaths_a_register_named_file_counts_only_if_it_is_named_like_a_test(tmp_path):
    (tmp_path / "canonical").mkdir()
    (tmp_path / "canonical" / "rules.yml").write_text(
        "rules:\n  - id: a-rule\n    enforced_by:\n      - checks/test_a.py::t\n"
        "      - core/gates/enforcer.py\n",
        encoding="utf-8",
    )
    assert gate.rule_enforcement_tests(["checks/test_a.py"], tmp_path) == RULE_TESTS
    assert gate.rule_enforcement_tests(["core/gates/enforcer.py"], tmp_path) == []


def test_a_pytest_configuration_that_cannot_be_read_selects_them(tmp_path):
    (tmp_path / "canonical").mkdir()
    (tmp_path / "canonical" / "rules.yml").write_text("rules: []\n", encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest\n", encoding="utf-8")
    assert gate.rule_enforcement_tests(["README.md"], tmp_path) == RULE_TESTS


def test_an_empty_diff_selects_nothing_even_when_the_register_cannot_be_read(tmp_path):
    (tmp_path / "canonical").mkdir()
    (tmp_path / "canonical" / "rules.yml").write_text("rules: [unclosed\n", encoding="utf-8")
    assert gate.rule_enforcement_tests([], tmp_path) == []
    assert gate.rule_enforcement_tests(["README.md"], tmp_path) == RULE_TESTS
