"""WO-DETERMINISTIC-FIRST: compute what can be computed, before anyone judges it.

Operator directive 2026-08-21: *anything that can be verified deterministically should
be.* Not because judgement is bad — because spending it on facts leaves less of it for
the claims that need reading, and because computation is available when judgement is
not.

MEASURED, all in this repo on 2026-08-20/21:

- Six consecutive grader timeouts blocked three complete work orders (befde290,
  59c69b58, 6a4c21d1) — 4/4 tasks, pushed, gates green, unclosable. ``claude --print``
  timed out at 360s again the next night.
- Graders were asked questions with exact answers. Verbatim from passing verdicts: "all
  three named TEST-CHECK node IDs exist verbatim"; "the dist/plugin copy matches
  canonical"; "the skill text names the check".
- And they sometimes cannot compute at all: "running pytest was denied by the sandbox";
  "I could not execute pytest in this session (command approval denied), so the
  TEST-CHECK results are unexecuted."

THE BOUNDARY THIS SUITE ALSO PINS. Building the reachability gate produced six defects:
two caught by RUNNING it, four by READING it — a spec contradicting its implementation
behind a misleading test name, a parameter that changed no answer, a comment asserting a
superseded rule, and a guard test incapable of failing. All four sat behind a green
26-test suite. So the rule is not "computation replaces judgement"; it is "compute
everything computable so judgement is spent only where judgement is the only tool", and
a computed layer must never imply coverage it lacks.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from core.gates.deterministic_evidence import (
    GREP_EXEMPT_MARKER,
    UNKNOWN,
    acceptance_criteria_determinism,
    collect_test_check_expressions,
    deterministic_facts,
    facts_prompt_block,
    projection_parity,
    resolve_node_ids,
    source_reading_tests,
)

_REPO = Path(__file__).resolve().parents[2]

# A node id that really exists in this repo, and one that really does not. Using real
# targets rather than invented ones is the same rule this work order is about: read the
# fact, do not recall it.
_REAL_NODE_ID = (
    "tests/unit/test_reachability_gate.py::test_a_new_unreferenced_public_function_is_flagged"
)
_ABSENT_NODE_ID = "tests/unit/test_reachability_gate.py::test_this_node_id_does_not_exist"


def _dedent(source: str) -> str:
    return textwrap.dedent(source).lstrip("\n")


# ── Task 1: the verdict carries computed facts ────────────────────────────────


def test_the_verdict_carries_computed_facts_not_grader_opinions():
    """Every fact here was, until now, a question put to a language model. Driven
    against the real repo, because a fixture would prove the shape and not the answer."""
    facts = deterministic_facts(
        tasks=[
            {"title": "wired", "acceptance_criteria": f"TEST-CHECK: {_REAL_NODE_ID}"},
            {"title": "prose only", "acceptance_criteria": "the guidance reads well"},
        ],
        repo_root=_REPO,
    )

    assert facts["node_ids"]["status"] == "computed"
    assert facts["node_ids"]["checked"] == 1
    assert facts["node_ids"]["unresolved"] == [], "a real node id resolves"

    parity = facts["projection_parity"]
    assert parity["status"] == "computed"
    assert parity["compared"] > 50, f"the parity check must actually compare files: {parity}"
    assert (
        parity["stale"] == []
    ), f"projections are in sync; stale would be a real finding: {parity}"

    criteria = facts["acceptance_criteria"]
    assert criteria["total"] == 2
    assert criteria["executable"] == 1
    assert criteria["prose_only"] == ["prose only"]


def test_an_absent_node_id_is_reported_as_unresolved_not_failed():
    """RESOLUTION IS NOT PASSING. Conflating them sent a real diagnosis down the wrong
    path on 2026-08-19: three TEST-CHECKs read as FAILED for merged, green work purely
    because the working tree was on another branch."""
    result = resolve_node_ids([_REAL_NODE_ID, _ABSENT_NODE_ID])
    assert result["status"] == "computed"
    assert result["checked"] == 2
    unresolved = result["unresolved"]
    assert len(unresolved) == 1, f"exactly the absent one: {unresolved}"
    assert "test_this_node_id_does_not_exist" in unresolved[0]


def test_the_unresolved_target_is_named_in_full():
    """A path with a SPACE in it. This repo lives under "C:\\Users\\Dannis Seay\\...",
    and the first parser captured ``(\\S+)`` — so it reported the missing target as
    "C:\\Users\\Dannis". Found by driving it against real pytest, not by reading it."""
    unresolved = resolve_node_ids([_ABSENT_NODE_ID])["unresolved"]
    assert unresolved, "the absent node id must be named"
    assert unresolved[0].endswith(
        "test_this_node_id_does_not_exist"
    ), f"the name must survive a space in the path, got {unresolved[0]!r}"


def test_a_computed_fact_survives_a_grader_outage():
    """The point of the layer. Six grader timeouts blocked three finished work orders;
    these facts are produced by subprocess and file reads, so a provider outage cannot
    take them with it. Nothing here touches a grader."""
    facts = deterministic_facts(
        tasks=[{"title": "t", "acceptance_criteria": f"TEST-CHECK: {_REAL_NODE_ID}"}],
        repo_root=_REPO,
        check_node_ids=False,  # even with the one subprocess declined
    )
    assert facts["projection_parity"]["status"] == "computed", "file reads still answer"
    assert facts["acceptance_criteria"]["executable"] == 1, "and so does reading the criteria"
    assert facts["node_ids"]["status"] == UNKNOWN
    assert facts["node_ids"]["reason"], "a declined computation states why"


# ── Task 2: the facts reach the grader as established ────────────────────────


def test_the_grader_prompt_states_the_computed_facts():
    """A computed value with no reader is the invisibility defect wearing a new name.
    The completion prompt must carry the block, and the block must say the facts are
    ground truth — the contract SQL-CHECK results already had."""
    import re

    from core.work_orders.verify_prompts import _COMPLETION_PROMPT_TEMPLATE

    assert (
        "{computed_facts}" in _COMPLETION_PROMPT_TEMPLATE
    ), "the completion prompt must have a slot for the computed facts"

    block = facts_prompt_block(
        deterministic_facts(
            tasks=[{"title": "t", "acceptance_criteria": f"TEST-CHECK: {_ABSENT_NODE_ID}"}],
            repo_root=_REPO,
        )
    )
    # Whitespace-collapsed: the block wraps prose at ~80 columns, so a raw substring
    # check asserts the LINE BREAKS as much as the words. Exactly the mistake corrected
    # in the skill-text assertions one work order ago, repeated here.
    flat = re.sub(r"\s+", " ", block)
    assert "ground truth" in flat, "state that these are not to be re-derived"
    assert "take precedence" in flat
    assert "UNRESOLVED" in flat, "and name what did not resolve"
    assert "NOT a test failure" in flat, "misaddressed is not failed"


def test_the_prompt_block_refuses_to_present_unknown_as_a_pass():
    """The whole value of a deterministic layer is that its answers can be trusted. One
    fabricated answer makes it worse than nothing."""
    block = facts_prompt_block({"node_ids": {"status": UNKNOWN, "reason": "pytest unavailable"}})
    assert "not determined" in block
    assert "pytest unavailable" in block, "the reason travels with the unknown"
    assert "do not" in block.lower() and "pass" in block.lower()


def test_the_verify_engine_computes_the_facts_and_records_them():
    """Wiring, not existence. `deterministic_facts` with no call site in verify would be
    the exact dead-on-arrival shape the previous work order built a gate for."""
    import inspect

    from core.work_orders import verify_main

    # deterministic-first: structural assertion — verify_work_order needs a live
    # authority, four grader subprocesses and a git history to drive; the wiring itself
    # has no smaller drivable surface.
    source = inspect.getsource(verify_main)
    assert "deterministic_facts(" in source, "verify must compute the facts"
    assert "computed_facts=" in source, "and pass them into the completion prompt"
    assert '"deterministic": _facts' in source, "and record them on the verdict"


# ── Task 3: per-task determinism, reported and never blocking ─────────────────


def test_prose_only_criteria_are_reported_with_their_task_titles():
    """A count alone is unactionable — an author needs to know WHICH task rests on
    reading."""
    report = acceptance_criteria_determinism(
        [
            {"title": "has a test", "acceptance_criteria": "TEST-CHECK: a::b"},
            {"title": "has a query", "acceptance_criteria": "SQL-CHECK: SELECT 1 WHERE 1"},
            {"title": "has an api check", "acceptance_criteria": "API-CHECK: GET /health -> 200"},
            {"title": "reads well", "acceptance_criteria": "the docs are clear"},
            {"title": "nothing at all", "acceptance_criteria": None},
        ]
    )
    assert report["total"] == 5
    assert report["executable"] == 3
    assert report["prose_only"] == ["reads well", "nothing at all"]
    assert report["coverage"] == 0.6


def test_the_report_does_not_block_a_close():
    """Some claims genuinely cannot be computed — a design judgement, an operator
    attestation — and a gate that demands the impossible is a gate people route around.
    So this is a REPORT: it returns counts and titles, and no failure reason."""
    report = acceptance_criteria_determinism([{"title": "prose", "acceptance_criteria": ""}])
    assert report["prose_only"] == ["prose"]
    assert report["executable"] == 0
    assert (
        "failure" not in report and "blocked" not in report
    ), "this reader must have no way to express a block"

    # And the close path attaches it as an advisory key rather than a gate failure.
    import inspect

    from core.work_orders import close_main

    # deterministic-first: structural assertion — driving close_work_order needs a
    # seeded authority and every gate; the advisory placement is what is under test.
    source = inspect.getsource(close_main.close_work_order)
    assert 'result["prose_only_criteria"]' in source
    assert "gate_failures.append" not in source.split("_criteria_report")[1].split("result[")[0]


def test_an_untitled_task_still_appears_in_the_report():
    """A task with no title is a bookkeeping defect, not a reason to drop it silently."""
    report = acceptance_criteria_determinism([{"title": None, "acceptance_criteria": ""}])
    assert report["prose_only"] == ["(untitled task)"]


def test_no_tasks_yields_no_coverage_rather_than_a_fake_one():
    report = acceptance_criteria_determinism([])
    assert report["total"] == 0
    assert report["coverage"] is None, "0/0 is not 0% and not 100% — it is unknown"


# ── Task 4: a source grep standing in for a drive ────────────────────────────


def test_a_source_grep_standing_in_for_a_drive_is_reported():
    """Judgement caught this twice and would have missed a third. The project-state test
    asserted a name appeared in queries.py instead of driving get_project_state, and its
    verify said: "a grep proves the line was typed, not that the payload carries the
    key"."""
    suspect = _dedent("""
        def test_the_surface_is_wired():
            import inspect

            from interfaces.cli.commands import work_order_query

            src = inspect.getsource(work_order_query)
            assert "merge-check" in src
        """)
    found = source_reading_tests(suspect, path="tests/unit/test_x.py")
    assert len(found) == 1, found
    assert found[0]["test"] == "test_the_surface_is_wired"
    assert found[0]["exempt"] is False
    assert "getsource" in found[0]["reads"]
    assert "grep proves the line was typed" in found[0]["reason"]


def test_a_genuine_text_assertion_is_not_reported():
    """NARROWED BY MEASUREMENT. The first detector treated any file read plus an
    assertion as a suspect and flagged 154 tests across tests/unit — overwhelmingly
    legitimate: reading back written JSON, a temp file, an install script, a doc. An
    unreadable report is the signal-nobody-reads failure this milestone keeps finding,
    so the detector is confined to `getsource`, which can only apply to importable
    Python."""
    legitimate = _dedent("""
        def test_the_output_file_has_the_expected_rows(tmp_path):
            target = tmp_path / "out.json"
            run_export(target)
            assert "rows" in target.read_text(encoding="utf-8")


        def test_the_doc_names_the_command():
            text = (REPO / "docs" / "guide.md").read_text(encoding="utf-8")
            assert "ds work-order close" in text
        """)
    assert source_reading_tests(legitimate, path="tests/unit/test_y.py") == []


def test_a_declared_structural_assertion_is_listed_as_exempt():
    """Some claims have no drivable surface — that a module does NOT import something,
    that a comment says what the code does. Declared with the marker and still LISTED,
    so the exemption is visible rather than silent."""
    declared = _dedent(f'''
        def test_the_module_avoids_a_forbidden_import():
            """Checks structure.

            # {GREP_EXEMPT_MARKER}: an absence has no behaviour to drive
            """
            import inspect

            from core import thing

            assert "forbidden" not in inspect.getsource(thing)
        ''')
    found = source_reading_tests(declared, path="tests/unit/test_z.py")
    assert len(found) == 1
    assert found[0]["exempt"] is True
    assert "no behaviour to drive" in found[0]["exempt_reason"]


def test_a_non_test_function_reading_source_is_not_reported():
    """Helpers read source for all sorts of reasons; the claim under scrutiny is what a
    TEST offers as its evidence."""
    helper = _dedent("""
        def _load(module):
            import inspect

            src = inspect.getsource(module)
            assert src
            return src
        """)
    assert source_reading_tests(helper, path="tests/unit/test_w.py") == []


def test_the_detector_reports_this_repos_real_remaining_cases():
    """Driven against the actual suite, because a detector that only works on fixtures
    proves it runs and not that it is right. The known real case is
    test_merge_readiness's `'"merge-check"' in src`, which its own task said should have
    been an end-to-end drive."""
    text = (_REPO / "tests" / "unit" / "test_merge_readiness.py").read_text(encoding="utf-8")
    found = source_reading_tests(text, path="tests/unit/test_merge_readiness.py")
    names = [f["test"] for f in found if not f["exempt"]]
    assert (
        "test_the_cli_surface_exists_and_is_wired" in names
    ), f"the known real case must be reported, got {names}"


# ── Task 5: the rule ships in canonical skill text ───────────────────────────

_RULE_BEARING = [("core", "ds-core", "build"), ("core", "ds-core", "verify")]

# The two modes carry DIFFERENT halves on purpose: build tells an agent how to prove a
# claim, verify describes what the verdict already carries. Demanding one phrase from
# both was the first version of this test and it failed on correct guidance.
_MODE_PHRASES = {
    "build": ("grep is not a drive", "unknown"),
    "verify": ("computed facts", "unknown"),
}


@pytest.mark.parametrize(("pack", "_projected", "mode"), _RULE_BEARING)
def test_skill_texts_require_computing_what_can_be_computed(pack, _projected, mode):
    """A rule an agent never reads is not enforcement."""
    import re

    path = _REPO / "canonical" / "skills" / pack / "modes" / mode / "SKILL.md"
    assert path.is_file(), f"missing {path}"
    flat = re.sub(r"\s+", " ", path.read_text(encoding="utf-8").lower())
    for phrase in _MODE_PHRASES[mode]:
        assert phrase in flat, f"{mode}: must state {phrase!r}"


@pytest.mark.parametrize(("pack", "projected_pack", "mode"), _RULE_BEARING)
def test_the_projection_carries_the_rule(pack, projected_pack, mode):
    """dist/plugin is what a plugin install actually reads. A rule only in canonical/ is
    a rule no plugin user is bound by."""
    canonical = _REPO / "canonical" / "skills" / pack / "modes" / mode / "SKILL.md"
    projected = _REPO / "dist" / "plugin" / "skills" / projected_pack / "modes" / mode / "SKILL.md"
    assert projected.is_file(), f"projected SKILL.md missing at {projected}"
    assert projected.read_bytes().replace(b"\r\n", b"\n") == canonical.read_bytes().replace(
        b"\r\n", b"\n"
    ), f"dist/plugin {projected_pack}/{mode} is stale — rebuild with build_plugin_dist"


def test_the_close_skill_names_the_reported_key():
    """An engine key with no reader is the defect this milestone keeps finding."""
    text = (
        _REPO / "canonical" / "skills" / "ds-workorder" / "modes" / "close" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "prose_only_criteria" in text
    assert "advisory" in text.lower() or "never blocking" in text.lower()


# ── Task 6: nothing may fabricate certainty ──────────────────────────────────


def test_an_uncomputable_fact_is_recorded_as_unknown_with_a_reason():
    """ "Absent is not fresh" — the lesson the hook-freshness check learned by reporting
    clean on 42 of 45 paths while three were simply not deployed. Every uncomputable
    answer here carries its reason and never reads as a pass."""
    missing_tree = projection_parity(Path("/definitely/not/a/repo"))
    assert missing_tree["status"] == UNKNOWN
    assert "canonical skills tree" in missing_tree["reason"]
    assert "stale" not in missing_tree, "an unknown must not present an empty stale list"

    facts = deterministic_facts(tasks=[], repo_root=Path("/definitely/not/a/repo"))
    assert facts["projection_parity"]["status"] == UNKNOWN
    assert facts["projection_parity"]["reason"]


def test_an_unprojected_canonical_skill_is_reported_not_ignored():
    """Missing and stale have different remedies and neither is 'fine'. This repo has a
    real instance: canonical/skills/ds-bootstrap reaches no plugin install, tracked as
    its own work order rather than silenced with an ignore-list entry."""
    parity = projection_parity(_REPO)
    assert parity["status"] == "computed"
    assert "unprojected" in parity, "the field must exist even when empty"
    assert isinstance(parity["unprojected"], list)


def test_a_cmd_expression_is_not_guessed_at():
    """A `cmd:` criterion is the target repo's own command, not a pytest node id.
    Reporting it as unresolved would be a fabricated failure."""
    result = resolve_node_ids(["cmd: git --version"])
    assert result["unresolved"] == []
    assert result["checked"] == 0
    assert result["undetermined"], "it is undetermined, not resolved and not failed"
    assert "not a pytest node id" in result["undetermined"][0]["reason"]


def test_the_expression_collector_is_not_named_like_a_test():
    """A production helper named `test_*` gets COLLECTED BY PYTEST — that exact mistake
    produced a collection error from a production module earlier in this milestone. The
    collector here is `collect_test_check_expressions` for that reason."""
    assert collect_test_check_expressions.__name__.startswith("collect_")

    from core.gates import deterministic_evidence

    collectable = [
        name
        for name in vars(deterministic_evidence)
        if name.startswith("test") and callable(getattr(deterministic_evidence, name))
    ]
    assert collectable == [], f"pytest would collect these production callables: {collectable}"


def test_an_unparseable_test_file_is_raised_not_skipped():
    """A detector that silently skips what it cannot read reports clean on exactly the
    files most likely to be wrong."""
    from core.gates.reachability import SourceUnreadable

    with pytest.raises(SourceUnreadable):
        source_reading_tests("def broken(:\n    pass\n", path="tests/unit/test_broken.py")
