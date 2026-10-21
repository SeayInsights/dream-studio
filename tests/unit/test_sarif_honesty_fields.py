"""The SARIF importer records only the honesty fields a SARIF file genuinely states.

A SARIF result can carry `properties.precision` (on the result or on its rule), and a run
can say its invocation did not execute successfully. Those map to confidence and to
partial coverage. Nothing else does: `rank` is importance, not certainty, and a successful
invocation is not proof of complete coverage. Everything unstated stays NULL (unknown).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from projections.parsers import sarif_parser
from projections.parsers.sarif_parser import _honesty_from_sarif, parse_sarif_file


def _run(rules=None, invocations=None) -> dict:
    run: dict = {"tool": {"driver": {"name": "t", "rules": rules or []}}}
    if invocations is not None:
        run["invocations"] = invocations
    return run


@pytest.mark.parametrize(
    "precision,expected",
    [("very-high", "high"), ("HIGH", "high"), ("medium", "medium"), ("low", "low")],
)
def test_precision_on_the_rule_maps_to_confidence(precision, expected):
    run = _run(rules=[{"id": "r1", "properties": {"precision": precision}}])
    assert _honesty_from_sarif({"ruleId": "r1", "ruleIndex": 0}, run) == {"confidence": expected}


def test_precision_on_the_result_wins_over_the_rule():
    run = _run(rules=[{"id": "r1", "properties": {"precision": "low"}}])
    result = {"ruleId": "r1", "properties": {"precision": "high"}}
    assert _honesty_from_sarif(result, run) == {"confidence": "high"}


def test_the_rule_is_found_by_id_when_there_is_no_index():
    run = _run(rules=[{"id": "other"}, {"id": "r1", "properties": {"precision": "medium"}}])
    assert _honesty_from_sarif({"ruleId": "r1"}, run) == {"confidence": "medium"}


@pytest.mark.parametrize("junk", ["certain", "", None, 3, ["high"], {"a": 1}])
def test_unrecognised_precision_stays_unknown(junk):
    run = _run(rules=[{"id": "r1", "properties": {"precision": junk}}])
    assert _honesty_from_sarif({"ruleId": "r1"}, run) == {}


def test_rank_and_level_are_not_confidence():
    run = _run(rules=[{"id": "r1", "defaultConfiguration": {"rank": 99}}])
    result = {"ruleId": "r1", "rank": 99, "level": "error", "kind": "fail"}
    assert _honesty_from_sarif(result, run) == {}


def test_a_failed_invocation_makes_the_run_partial_and_says_why():
    honesty = _honesty_from_sarif(
        {"ruleId": "r"}, _run(invocations=[{"executionSuccessful": False}])
    )
    assert honesty["coverage"] == "partial"
    assert honesty["limitations"] and "executionSuccessful=false" in honesty["limitations"][0]


def test_a_successful_invocation_is_not_read_as_complete():
    run = _run(invocations=[{"executionSuccessful": True}])
    assert _honesty_from_sarif({"ruleId": "r"}, run) == {}


@pytest.mark.parametrize(
    "run",
    [
        {},
        {"tool": "x"},
        {"tool": {"driver": "x"}},
        {"tool": {"driver": {"rules": "x"}}, "invocations": "x"},
        {"tool": {"driver": {"rules": [3, None]}}, "invocations": [3, None]},
    ],
)
def test_a_malformed_run_yields_nothing_rather_than_raising(run):
    assert _honesty_from_sarif({"ruleId": "r", "properties": "x", "rule": 5}, run) == {}


def _write_sarif(tmp_path: Path, run: dict) -> Path:
    path = tmp_path / "scan.sarif"
    path.write_text(json.dumps({"version": "2.1.0", "runs": [run]}), encoding="utf-8")
    return path


def _result(rule_id: str) -> dict:
    return {
        "ruleId": rule_id,
        "level": "error",
        "message": {"text": "m"},
        "locations": [
            {"physicalLocation": {"artifactLocation": {"uri": "a.py"}, "region": {"startLine": 3}}}
        ],
    }


def test_parse_sarif_file_passes_what_the_file_states_to_record_finding(tmp_path):
    run = _run(
        rules=[{"id": "r1", "properties": {"precision": "high"}}],
        invocations=[{"executionSuccessful": False}],
    )
    run["results"] = [_result("r1"), _result("unlisted")]
    seen: list[dict] = []
    with (
        patch.object(sarif_parser, "_record_finding", lambda **kw: seen.append(kw) or "id"),
        patch.object(sarif_parser, "_check_duplicate", lambda *a: False),
    ):
        assert parse_sarif_file(str(_write_sarif(tmp_path, run))) == 2
    stated, unstated = seen
    assert stated["confidence"] == "high" and stated["coverage"] == "partial"
    assert "limitations" in stated
    assert "confidence" not in unstated, "no precision stated, so none passed"
    assert unstated["coverage"] == "partial", "the run, not the rule, is what was incomplete"


#: Two rules with different precision, so a wrong lookup is visible in the answer.
_TWO_RULES = [
    {"id": "someone-else", "properties": {"precision": "very-high"}},
    {"id": "r1", "properties": {"precision": "low"}},
]


def _confidence(result: dict, rules=None) -> str | None:
    return _honesty_from_sarif(result, _run(rules=rules or _TWO_RULES)).get("confidence")


def test_a_ruleindex_that_matches_the_rule_id_is_used():
    assert _confidence({"ruleId": "r1", "ruleIndex": 1}) == "low"


def test_a_ruleindex_pointing_at_another_rule_is_not_trusted_and_the_id_lookup_wins():
    """The file says rule 0 (very-high) but the result is r1 (low): the id decides."""
    assert _confidence({"ruleId": "r1", "ruleIndex": 0}) == "low"


def test_a_mismatched_ruleindex_with_no_rule_of_that_id_leaves_confidence_unknown():
    """Neither resolves, so nothing is claimed: never the indexed rule's very-high."""
    assert _confidence({"ruleId": "ghost", "ruleIndex": 0}) is None


def test_a_ruleindex_is_used_when_the_result_carries_no_ruleid():
    assert _confidence({"ruleIndex": 1}) == "low"


def test_the_result_rule_index_form_is_checked_the_same_way():
    assert _confidence({"ruleId": "r1", "rule": {"index": 0}}) == "low"
    assert _confidence({"ruleId": "ghost", "rule": {"index": 0}}) is None


def test_a_missing_ruleindex_finds_the_rule_by_id():
    assert _confidence({"ruleId": "r1"}) == "low"


def test_a_negative_ruleindex_does_not_index_from_the_end_of_the_list():
    # -1 would be rules[-1], r1 (low). With ruleId someone-else the id lookup says very-high,
    # and with no ruleId a negative index resolves to nothing at all.
    assert _confidence({"ruleId": "someone-else", "ruleIndex": -1}) == "high"
    assert _confidence({"ruleIndex": -1}) is None
    assert _confidence({"ruleIndex": -2}) is None


@pytest.mark.parametrize("index", [2, 99, 10**12])
def test_an_out_of_range_ruleindex_falls_back_to_the_id_and_never_crashes(index):
    assert _confidence({"ruleId": "r1", "ruleIndex": index}) == "low"
    assert _confidence({"ruleIndex": index}) is None


@pytest.mark.parametrize("index", [True, False, 1.0, 0.0, "1", "0", None, [1], {"a": 1}])
def test_a_ruleindex_that_is_not_an_int_is_ignored(index):
    """True is 1 and 1.0 == 1 in Python; neither is a SARIF index. The id still resolves."""
    assert _confidence({"ruleId": "r1", "ruleIndex": index}) == "low"
    assert _confidence({"ruleIndex": index}) is None


def test_a_mismatched_file_is_not_given_the_indexed_rules_confidence_end_to_end(tmp_path):
    run = _run(rules=_TWO_RULES)
    run["results"] = [dict(_result("r1"), ruleIndex=0)]
    seen: list[dict] = []
    with (
        patch.object(sarif_parser, "_record_finding", lambda **kw: seen.append(kw) or "id"),
        patch.object(sarif_parser, "_check_duplicate", lambda *a: False),
    ):
        assert parse_sarif_file(str(_write_sarif(tmp_path, run))) == 1
    assert seen[0]["confidence"] == "low"


def test_a_consistent_file_maps_exactly_as_before():
    run = _run(
        rules=[{"id": "a", "properties": {"precision": "very-high"}}, {"id": "b"}],
        invocations=[{"executionSuccessful": False}],
    )
    assert _honesty_from_sarif({"ruleId": "a", "ruleIndex": 0}, run) == {
        "confidence": "high",
        "coverage": "partial",
        "limitations": ["the scanner reported executionSuccessful=false for this run"],
    }
    assert _honesty_from_sarif({"ruleId": "b", "ruleIndex": 1}, run) == {
        "coverage": "partial",
        "limitations": ["the scanner reported executionSuccessful=false for this run"],
    }


@pytest.mark.parametrize(
    "invocation",
    [{}, {"executionSuccessful": None}, {"executionSuccessful": 0}, {"executionSuccessful": "false"}],
)
def test_a_missing_or_non_boolean_executionsuccessful_is_not_a_failure(invocation):
    """Only an explicit false says the run was incomplete; absence says nothing."""
    assert _honesty_from_sarif({"ruleId": "r"}, _run(invocations=[invocation])) == {}


def test_parse_sarif_file_passes_nothing_when_the_file_states_nothing(tmp_path):
    run = _run()
    run["results"] = [_result("r1")]
    seen: list[dict] = []
    with (
        patch.object(sarif_parser, "_record_finding", lambda **kw: seen.append(kw) or "id"),
        patch.object(sarif_parser, "_check_duplicate", lambda *a: False),
    ):
        assert parse_sarif_file(str(_write_sarif(tmp_path, run))) == 1
    assert not {"confidence", "coverage", "limitations"} & seen[0].keys()
