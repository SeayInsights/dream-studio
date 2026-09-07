"""A failed review must show what objected, not the paragraph from the role that passed.

MEASURED ON WO 17f20d48, 2026-09-07. The verdict was correct -- completion scored 1.0,
correctness 0.786, quality 0.62, composite 0.8598 -- and the close gate printed:

    independent_review: review failed - Both tasks are implemented end-to-end: ... I ran
    the two TEST-CHECK node ids myself ... both resolve and pass ...

That paragraph is the COMPLETION grader's, the one role with nothing to report. The roles
that failed (correctness, quality) record ``violations`` and write no ``summary`` at all,
so the message quoted the only prose available and read as "review failed: everything is
great". A reader's reasonable conclusion is that the gate is broken -- which is exactly the
conclusion drawn, and twenty minutes spent on it, before the stored verdict was opened.

Two defects, one sentence: the findings list was EMPTY for a verdict whose only objections
were role violations, and nothing named which role had objected or how badly.
"""

from __future__ import annotations

from core.work_orders.close_shared import verdict_evidence, verdict_score_line

# The real shape, reduced: prose only under the passing role, objections only under the
# failing ones. Reproduced from the stored artifact rather than imagined, because a fixture
# invented to match the code is how the previous shape assumption survived.
_VERDICT = {
    "passed": False,
    "scores": {
        "completion_score": 1.0,
        "correctness_score": 0.786,
        "quality_score": 0.62,
        "composite_score": 0.8598,
    },
    "completion": {"passed": True, "summary": "Both tasks are implemented end-to-end."},
    "correctness": {
        "violations": [
            {
                "rule": "Rule 1: TEST COVERAGE FOR CHANGED BEHAVIOUR",
                "file": "config/event_type_registry_entries_business.py",
                "line": "182",
                "detail": "The new entry declares payload_required_keys but the fixture was not updated.",
            }
        ]
    },
    "quality": {"violations": [{"rule": "Rule 3: ERROR HANDLING HONESTY", "detail": "swallows"}]},
    "spawned_work_orders": [
        {"title": "Fix architectural violations", "description": "3 violations detected."}
    ],
}


def test_the_score_line_names_every_role_worst_first():
    line = verdict_score_line(_VERDICT)
    assert line.startswith("quality 0.62"), f"the weakest role must lead: {line}"
    assert "correctness 0.79" in line
    assert "completion 1.00" in line
    assert "composite 0.86" in line


def test_role_violations_are_findings():
    """They were not, so a verdict objecting ONLY through violations had no findings."""
    _, findings = verdict_evidence(_VERDICT)
    details = [f.get("detail") for f in findings if isinstance(f, dict)]
    assert (
        "The new entry declares payload_required_keys but the fixture was not updated." in details
    )
    assert "swallows" in details


def test_a_real_objection_is_reachable_past_the_spawned_work_order():
    """`findings[0]` is a spawned work order carrying no objection text.

    Taking it blindly printed an empty objection, which is how the improvement would have
    silently done nothing.
    """
    _, findings = verdict_evidence(_VERDICT)
    first = next(
        (f for f in findings if isinstance(f, dict) and (f.get("detail") or f.get("rule"))),
        None,
    )
    assert first is not None
    assert first.get("file") == "config/event_type_registry_entries_business.py"


def test_a_verdict_with_no_scores_still_reads_in_declaration_order():
    """`sorted` is stable, so the old behaviour is unchanged where there is nothing to rank.

    Without this the fix would quietly reorder every verdict that predates scoring.
    """
    legacy = {
        "passed": False,
        "completion": {"summary": "completion prose"},
        "correctness": {"summary": "correctness prose"},
    }
    summary, _ = verdict_evidence(legacy)
    assert summary == "completion prose"
    assert verdict_score_line(legacy) == ""


def test_a_top_level_summary_still_wins():
    """Attestations and hand-built verdicts set `summary` directly."""
    summary, _ = verdict_evidence({"summary": "top level", **_VERDICT})
    assert summary == "top level"


def test_a_verdict_objecting_only_through_violations_is_not_an_incomplete_record():
    """The close gate treats "no summary AND no findings" as a record that never finished
    being written, and tells the operator to re-run verify. Before role violations counted
    as findings, a verdict whose objections lived only there hit that path -- a real
    failure softened into "inconclusive", which the same commit called worse than the
    defect."""
    violations_only = {
        "passed": False,
        "correctness": {"violations": [{"rule": "Rule 1", "detail": "no test"}]},
    }
    summary, findings = verdict_evidence(violations_only)
    assert summary == ""
    assert findings, "with no findings the gate reports UNREVIEWABLE and hides the objection"


def test_an_empty_verdict_is_still_reported_as_incomplete():
    """The converse, so the fix above does not disable the incomplete-record detection."""
    summary, findings = verdict_evidence({"passed": False})
    assert summary == ""
    assert findings == []
