"""Admission refuses what nobody can check — and never loses what it refuses.

Operator directive, 2026-09-10: "no stubs, only real registered work ... there needs to be
an independent reviewer of whether or not something can be added."

WHAT THESE TESTS ARE GUARDING AGAINST, stated so a later reader knows which failures
matter. The measured starting point was 1766 of 3278 tasks (53%) with no acceptance
criterion at all, from two unguarded doors: `_attach_gap_tasks` hardcoding
`acceptance_criteria: None`, and `add-task --acceptance` being optional. The rules an
author would assume existed lived in help text.

THE TEST THAT MATTERS MOST IS `test_a_refused_finding_is_reported_not_dropped`. Refusing a
real finding for lacking a criterion, and dropping it, is worse than the stub -- the stub
is at least visible. A suite that only asserted "criterion-less is refused" would pass on
an implementation that silently discarded the finding, which is the one outcome nobody
wants.
"""

from __future__ import annotations

from core.work_orders.admission import _MIN_WHY, admit_task, has_executable_criterion

BOUNDARY = "Do the thing. Module boundary: core/work_orders, tests/unit/test_admission.py."


# ── The Warden: enforce or declare ──────────────────────────────────────────


def test_a_task_with_no_criterion_is_refused():
    verdict = admit_task(title="Fix the thing", acceptance_criteria=None)

    assert verdict["admitted"] is False
    assert [r["seat"] for r in verdict["refusals"]] == ["The Warden"]
    assert verdict["refusals"][0]["lane"] == "a-criterion-nobody-can-run"
    assert "TEST-CHECK" in verdict["refusals"][0]["reason"], "the refusal must say what to do"


def test_a_task_with_an_executable_criterion_is_admitted():
    """The other direction, without which a reviewer that refuses everything would pass."""
    verdict = admit_task(
        title="Fix the thing",
        acceptance_criteria="TEST-CHECK: tests/unit/test_admission.py::test_a_task_with_no_criterion_is_refused",
    )
    assert verdict["admitted"] is True, verdict
    assert verdict["refusals"] == []


def test_prose_that_merely_mentions_a_check_is_still_prose():
    """A criterion is a line the executor matches, not a sentence containing the word."""
    verdict = admit_task(
        title="t", acceptance_criteria="We should probably add a TEST-CHECK for this someday"
    )
    assert verdict["admitted"] is False, verdict


def test_a_declared_reason_admits_what_cannot_be_computed():
    """Enforce-or-declare, not enforce-or-refuse. Some claims genuinely cannot be computed
    -- a design judgement, an operator attestation -- and a gate demanding the impossible
    is one people route around, which is how the guarded door becomes the unused one."""
    verdict = admit_task(
        title="Confirm the operator accepts the residual risk",
        acceptance_criteria=None,
        why="No computation can establish that a person accepted a risk; only they can say so.",
    )
    assert verdict["admitted"] is True, verdict


def test_a_shrug_is_not_a_declared_reason():
    verdict = admit_task(title="t", acceptance_criteria=None, why="n/a")
    assert verdict["admitted"] is False
    assert (
        str(_MIN_WHY) in verdict["refusals"][0]["reason"]
    ), "the refusal must state the bar it missed, or the author is guessing at it"


def test_the_criterion_predicate_is_the_executor_s_own(monkeypatch):
    """THE WARDEN'S LANE, ASKED OF THIS MODULE. Two sites deciding "is this executable" is
    the defect this milestone already paid for twice -- measured at 2 of 6 criteria
    disagreeing in both directions. So admission does not own a predicate; it imports the
    one `run_executable_checks` calls.

    Proved by mutation rather than by retyping the pattern: narrow the executor's predicate
    and admission must narrow with it. `check_token` reads `_CHECK_TOKEN` as a module global
    at call time, so this holds wherever the caller imported the applier.
    """
    import re

    from core.work_orders import verify_executor

    assert has_executable_criterion("TEST-CHECK: a::b")

    monkeypatch.setattr(
        verify_executor, "_CHECK_TOKEN", re.compile(r"^(SQL-CHECK):\s*(.*)", re.IGNORECASE)
    )
    assert not has_executable_criterion("TEST-CHECK: a::b"), "admission kept a predicate of its own"
    assert has_executable_criterion("SQL-CHECK: SELECT 1 WHERE 1")


# ── the constraint: a refusal is a report, not a deletion ───────────────────


def test_a_refused_finding_is_reported_not_dropped():
    """THE ONE OUTCOME WORSE THAN A STUB.

    A stub is a visible claim nobody can check. A finding silently discarded because it
    lacked a criterion is an invisible one. So `admit_task` returns what it refused, with
    the seat and the reason, and it is the caller's job to surface that -- this module has
    no way to delete anything, which is the property under test.
    """
    verdict = admit_task(
        title="The radar renders not_applicable as 0% uptime", acceptance_criteria=None
    )

    assert verdict["admitted"] is False
    assert len(verdict["refusals"]) == 1, "the finding must survive its own refusal"
    refusal = verdict["refusals"][0]
    assert refusal["seat"] and refusal["lane"] and refusal["reason"]

    # And the verdict carries no instruction to discard: the caller decides what to do with
    # a refusal, and cannot mistake this for a deletion.
    assert set(verdict) == {"admitted", "refusals", "unknowns"}, verdict.keys()


# ── The Surveyor: three states, because 89% have no boundary ────────────────


def test_a_finding_outside_the_boundary_is_refused():
    verdict = admit_task(
        title="Fix the drain",
        acceptance_criteria="TEST-CHECK: tests/unit/test_x.py::test_y",
        work_order_description=BOUNDARY,
        target_paths=["core/work_orders/verify_gaps.py", "core/eval/runner.py"],
    )
    # verify_gaps IS inside core/work_orders, so this one is attributable.
    assert verdict["admitted"] is True, verdict

    verdict = admit_task(
        title="Fix the dashboard",
        acceptance_criteria="TEST-CHECK: tests/unit/test_x.py::test_y",
        work_order_description=BOUNDARY,
        target_paths=["projections/api/lib/stack_helpers.py"],
    )
    assert verdict["admitted"] is False, verdict
    assert verdict["refusals"][0]["seat"] == "The Surveyor"
    assert "boundary" in verdict["refusals"][0]["reason"]


def test_no_declared_boundary_reports_unknown_and_does_not_refuse():
    """THE THIRD STATE, and why `path_in_boundary` is not reused for this decision: it
    returns True when no boundary is declared, which would read as "attributable" and admit
    everything. Measured: only 20 of 175 open work orders carry a parseable clause, so that
    default would decide 89% of cases by accident.

    Unknown is not the same as admitted-quietly -- the caller gets something to say.
    """
    verdict = admit_task(
        title="Fix something",
        acceptance_criteria="TEST-CHECK: tests/unit/test_x.py::test_y",
        work_order_description="A work order with no boundary clause at all.",
        target_paths=["core/anything.py"],
    )

    assert verdict["admitted"] is True, "unknown must not refuse"
    assert verdict["refusals"] == []
    assert len(verdict["unknowns"]) == 1
    assert verdict["unknowns"][0]["seat"] == "The Surveyor"
    assert "UNKNOWN" in verdict["unknowns"][0]["reason"]
    assert (
        "--module-boundary" in verdict["unknowns"][0]["reason"]
    ), "an unknown that does not say how to make it knowable is just a shrug"


def test_a_finding_naming_no_path_is_not_judged_on_attribution():
    """Attribution needs a subject. A task naming no file is neither in nor out of a
    boundary, and inventing a verdict for it would be the guess this lane exists to avoid."""
    verdict = admit_task(
        title="t",
        acceptance_criteria="TEST-CHECK: tests/unit/test_x.py::test_y",
        work_order_description=BOUNDARY,
        target_paths=[],
    )
    assert verdict["admitted"] is True
    assert verdict["unknowns"] == []


# ── The Herald: one finding, one row ────────────────────────────────────────


def test_a_duplicate_title_is_refused():
    verdict = admit_task(
        title="Fix the drain",
        acceptance_criteria="TEST-CHECK: tests/unit/test_x.py::test_y",
        existing_titles=["fix the   DRAIN "],
    )
    assert verdict["admitted"] is False
    assert verdict["refusals"][0]["seat"] == "The Herald"


def test_a_new_title_is_not_mistaken_for_a_duplicate():
    verdict = admit_task(
        title="Fix the other drain",
        acceptance_criteria="TEST-CHECK: tests/unit/test_x.py::test_y",
        existing_titles=["Fix the drain"],
    )
    assert verdict["admitted"] is True, verdict


def test_every_refusal_names_a_seat_and_a_lane():
    """A refusal a reviewer cannot attribute is the unreadable signal that gets a gate
    switched off. Asserted across every refusal this module can produce, so a lane added
    later without a seat fails here."""
    verdict = admit_task(
        title="Fix the dashboard",
        acceptance_criteria=None,
        work_order_description=BOUNDARY,
        target_paths=["projections/api/lib/stack_helpers.py"],
        existing_titles=["Fix the dashboard"],
    )
    assert verdict["admitted"] is False
    assert len(verdict["refusals"]) == 3, "all three lanes should have fired"
    for refusal in verdict["refusals"]:
        assert refusal["seat"].startswith("The "), refusal
        assert refusal["lane"] and " " not in refusal["lane"], refusal
        assert len(refusal["reason"]) >= 40, refusal


# ── the human door: the same rule, or the weaker door becomes the policy ────


def _add_task_cli(*args: str, home) -> tuple[int, str]:
    """Drive the real CLI in a subprocess against a throwaway Dream Studio home."""
    import os
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "interfaces.cli.ds", "work-order", "add-task", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        env={
            **os.environ,
            "DREAM_STUDIO_HOME": str(home),
            "DREAM_STUDIO_DB_PATH": str(home / "state" / "studio.db"),
        },
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def test_the_cli_refuses_a_criterion_less_task_without_a_declared_reason(tmp_path):
    """TWO DOORS, ONE ENFORCING, is how the weaker one becomes the policy.

    `add-task` used to create the task and THEN print "No executable acceptance criterion.
    Close cannot verify this task without one" -- the consequence named exactly, and
    enforced by nothing. Measured: 1766 of 3278 tasks in the authority carry none.

    DRIVES THE CLI, not `admit_task`, because the CLI is the door an author uses and the
    wiring between them is the part that can be wrong. Asserted on the exit code as well as
    the text: a refusal that exits 0 is a suggestion, and a script that chains on `&&`
    would carry straight on.
    """
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)

    code, out = _add_task_cli(
        "00000000-0000-0000-0000-000000000000",
        "--title",
        "A task nobody can check",
        home=tmp_path,
    )
    assert code == 1, f"a refusal must fail the command; got {code}\n{out}"
    assert "refused to file this task" in out, out
    assert "The Warden" in out, "the refusal must name the seat that raised it"
    assert "--why" in out, "the refusal must name the escape it will accept"


def test_the_cli_admits_a_task_that_carries_a_criterion(tmp_path):
    """The other direction, and it must get PAST admission rather than be refused for a
    different reason. The work order does not exist in this throwaway home, so creation
    fails downstream -- what this asserts is that the failure is no longer admission's."""
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)

    code, out = _add_task_cli(
        "00000000-0000-0000-0000-000000000000",
        "--title",
        "A task with a real criterion",
        "--acceptance",
        "TEST-CHECK: tests/unit/test_admission.py::test_a_task_with_no_criterion_is_refused",
        home=tmp_path,
    )
    assert "refused to file this task" not in out, f"admission blocked an admissible task\n{out}"
    assert "The Warden" not in out, out
    del code  # whether creation then succeeds is not this test's claim


# ── the Surveyor's reach is a number, not an impression ─────────────────────


def test_the_attribution_lane_reports_its_reach(tmp_path):
    """A LANE WITH UNKNOWN REACH LOOKS LIKE ENFORCEMENT AND IS NOT.

    Attribution needs a declared `Module boundary:` clause, and on the live authority only
    24 of 180 open work orders carry a parseable one -- so the lane judges 13% of cases and
    reports UNKNOWN for the rest. That number has to be reportable, or "the Surveyor passed"
    reads as "attribution was checked" when it usually means "attribution was skipped".

    Driven against a throwaway authority with both populations present, so the counts are
    observed rather than asserted about.
    """
    import sqlite3

    from core.work_orders.admission import attribution_reach

    db = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        "CREATE TABLE business_work_orders ("
        " work_order_id TEXT PRIMARY KEY, description TEXT, status TEXT);"
    )
    conn.executemany(
        "INSERT INTO business_work_orders VALUES (?, ?, ?)",
        [
            ("wo-with", "Do it. Module boundary: core/work_orders.", "in_progress"),
            ("wo-without", "Do it, boundary unstated.", "created"),
            ("wo-closed", "Closed and irrelevant.", "closed"),
        ],
    )
    conn.commit()
    conn.close()

    report = attribution_reach(db)
    assert report["status"] == "computed"
    # The closed one is excluded: a lane's reach is over work that can still receive tasks.
    assert report["open_work_orders"] == 2, report
    assert report["with_boundary"] == 1
    assert report["without_boundary"] == 1
    assert report["reach"] == 0.5
    assert report["undeclared_ids"] == [
        "wo-without"
    ], "naming them is the point -- a count alone tells nobody which scope to declare"


def test_an_unreadable_authority_reports_unknown_rather_than_full_reach(tmp_path):
    """ "I could not look" must not render as "every work order has a boundary". Same
    fail-open shape as the criteria ratchet, and the same refusal to conflate."""
    from core.work_orders.admission import attribution_reach

    report = attribution_reach(tmp_path / "absent.db")
    assert report["status"] == "unknown"
    assert "reach" not in report, "a reach it could not measure must not be reported"


# ── the producer half: a grader that emits nothing admissible files nothing ──


def test_a_grader_finding_with_a_criterion_is_filed_with_it():
    """THE PRODUCER CONTRACT, without which admission refuses everything.

    Measured when admission landed: 0 of 87 gap tasks across 41 stored review verdicts
    carried an acceptance criterion. So every grader finding was refused and reported
    unfiled -- honest, and it made "attach if admitted" attach nothing, converging by
    accident on the option the operator did not choose.

    This asserts the PROMPT asks for it, because the prompt is the only place the grader's
    output shape is specified. It deliberately checks the WORKED EXAMPLE too: a model copies
    the example far more reliably than it follows prose, so an example lacking the field
    would teach the omission regardless of the rule above it.
    """
    from core.work_orders.verify import _COMPLETION_PROMPT_TEMPLATE as template

    assert "CRITERION RULE" in template
    # The schema block offers the field, and the alternative to it.
    assert '"acceptance_criteria": "<ONE line' in template
    assert '"why": "<omit unless acceptance_criteria is omitted' in template

    # The three kinds, spelled as the executor detects them.
    for kind in ("TEST-CHECK:", "SQL-CHECK:", "API-CHECK:"):
        assert kind in template, kind

    # THE WORKED EXAMPLE MUST OBEY THE RULE IT SITS UNDER. The built-in behavioural-AC gap
    # is genuinely uncomputable, so it demonstrates the declared half rather than inventing
    # a node id -- which is the failure the rule warns about.
    example_start = template.index("Add behavioral AC to task descriptions")
    example = template[example_start : example_start + 600]  # noqa: E203
    assert '"why"' in example, "the worked example must carry a criterion or a reason"


def test_the_prompt_forbids_inventing_a_target():
    """THE DANGEROUS FAILURE IS A FABRICATED CRITERION, NOT A MISSING ONE.

    A TEST-CHECK naming a node id that does not exist is worse than none: close RUNS it, the
    run fails, and the failure reads as a defect in the work rather than in the criterion --
    the same conflation that made three TEST-CHECKs read as FAILED for merged, green work.
    """
    from core.work_orders.verify import _COMPLETION_PROMPT_TEMPLATE as template

    assert "NAME ONLY A TARGET YOU CAN SEE" in template
    assert "Do NOT invent" in template
    assert (
        "FAILS CLOSED" in template
    ), "the grader must be told a misspelled kind blocks a close rather than being ignored"


def test_a_grader_task_carrying_a_criterion_is_admitted_and_one_without_is_not():
    """The two shapes a grader can now emit, through the predicate that judges them.

    Drives `admit_task` with the exact dict shape `_attach_gap_tasks` builds from grader
    output, so this fails if the prompt and the intake disagree about the field name -- which
    is the whole risk of specifying a contract in prose.
    """
    admitted = admit_task(
        title="Emit the creation event from the spawn path",
        acceptance_criteria="TEST-CHECK: tests/unit/test_verify_gaps.py::test_it_survives",
    )
    assert admitted["admitted"] is True, admitted

    declared = admit_task(
        title="Rewrite each task description to read as observable behaviour",
        why="Whether prose reads as observable behaviour is a judgement; no query decides it.",
    )
    assert declared["admitted"] is True, declared

    neither = admit_task(title="Fix the thing")
    assert neither["admitted"] is False
    assert neither["refusals"][0]["seat"] == "The Warden"
