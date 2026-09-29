"""A project's own `.ds-review-lanes.yml`: parsed, validated, never silently narrowed.

`load_and_validate` is deliberately strict where `review_rules.py`'s `load_profile` is
deliberately lenient (falls back to the baseline on a bad profile) -- falling back to
*more* rules is safe there; falling back to Dream Studio's bare bench here, silently,
for a project that opted into MORE scrutiny and mistyped a field, is exactly the
"compared-nothing-reported-clean" shape `round_table._lanes()` itself refuses. These
tests hold the honest failure: a present-but-broken marker raises naming the problem,
never returns None or a partial result.
"""

from __future__ import annotations

import pytest
import yaml

from core.work_orders.project_review_lanes import (
    MARKER_NAME,
    load_and_validate,
    marker_path,
)

_VALID_LANE = {
    "id": "a-project-specific-lane",
    "seat": "PCI Scope",
    "question": "Does this change touch anything in the cardholder data environment?",
    "signature": "A file under payments/ or checkout/ changed with no PCI reviewer sign-off noted in the PR body.",
    "precedent": "Filed after an internal audit found three merged PRs touching payment capture with no compliance review recorded anywhere.",
    "measurement": "No automatable predicate exists for 'touches CDE' without a maintained file-ownership map, so this is judgment rather than a detector.",
    "model": "sonnet",
    "judgment": True,
    "why": "No maintained CDE file-ownership map exists yet to turn this into a detector.",
}


def _write_marker(tmp_path, body: str):
    (tmp_path / MARKER_NAME).write_text(body, encoding="utf-8")


def _write_valid_marker(tmp_path, *, mode: str | None = None, lanes=None):
    payload: dict = {"lanes": lanes if lanes is not None else [dict(_VALID_LANE)]}
    if mode is not None:
        payload["mode"] = mode
    _write_marker(tmp_path, yaml.safe_dump(payload, sort_keys=False))


def test_no_marker_returns_none(tmp_path):
    assert load_and_validate(tmp_path) is None


def test_marker_path_resolves_under_the_given_root(tmp_path):
    assert marker_path(tmp_path) == tmp_path / MARKER_NAME


def test_valid_marker_defaults_to_add_mode(tmp_path):
    _write_valid_marker(tmp_path)
    mode, lanes = load_and_validate(tmp_path)
    assert mode == "add"
    assert [lane["id"] for lane in lanes] == ["a-project-specific-lane"]


def test_explicit_replace_mode_is_honored(tmp_path):
    _write_valid_marker(tmp_path, mode="replace")
    mode, _ = load_and_validate(tmp_path)
    assert mode == "replace"


def test_mode_is_case_insensitive(tmp_path):
    _write_valid_marker(tmp_path, mode="ADD")
    mode, _ = load_and_validate(tmp_path)
    assert mode == "add"


def test_an_illegal_mode_raises_naming_the_bad_value(tmp_path):
    _write_valid_marker(tmp_path, mode="delete-everything")
    with pytest.raises(ValueError, match="delete-everything"):
        load_and_validate(tmp_path)


def test_unparseable_yaml_raises(tmp_path):
    _write_marker(tmp_path, "lanes: [this is not: valid: yaml: at all")
    with pytest.raises(ValueError, match="not parseable YAML"):
        load_and_validate(tmp_path)


def test_a_bare_list_instead_of_a_mapping_raises(tmp_path):
    _write_marker(tmp_path, "- just\n- a\n- list\n")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_and_validate(tmp_path)


def test_no_lanes_key_raises(tmp_path):
    _write_marker(tmp_path, "mode: add\n")
    with pytest.raises(ValueError, match="no `lanes:` list"):
        load_and_validate(tmp_path)


def test_empty_lanes_list_raises(tmp_path):
    _write_marker(tmp_path, "mode: add\nlanes: []\n")
    with pytest.raises(ValueError, match="no `lanes:` list"):
        load_and_validate(tmp_path)


def test_a_lane_missing_a_required_field_raises_naming_it(tmp_path):
    """Proves this module actually calls review_lane_registry.validate_lanes rather
    than reimplementing (and potentially under-implementing) its own copy of the
    field checks."""
    broken = dict(_VALID_LANE)
    del broken["measurement"]
    _write_valid_marker(tmp_path, lanes=[broken])
    with pytest.raises(ValueError, match="measurement"):
        load_and_validate(tmp_path)


def test_a_seat_colliding_with_a_reserved_name_raises(tmp_path):
    colliding = dict(_VALID_LANE)
    colliding["seat"] = "Finding integrity"  # a real Dream Studio seat name
    _write_valid_marker(tmp_path, lanes=[colliding])
    with pytest.raises(ValueError, match="collides with one of Dream Studio's own"):
        load_and_validate(tmp_path, reserved_seats=frozenset({"Finding integrity"}))


def test_a_seat_not_colliding_passes_the_collision_check(tmp_path):
    """Guards the guard: the collision test above must be testing the real mechanism,
    not a check that rejects everything regardless of the seat name."""
    _write_valid_marker(tmp_path)
    mode, lanes = load_and_validate(tmp_path, reserved_seats=frozenset({"Finding integrity"}))
    assert lanes[0]["seat"] == "PCI Scope"


def test_a_detector_lane_is_refused_in_v1(tmp_path):
    with_detector = dict(_VALID_LANE)
    del with_detector["judgment"]
    del with_detector["why"]
    with_detector["detector"] = "py -m some_project.checks.pci_scope"
    with_detector["defers"] = []
    _write_valid_marker(tmp_path, lanes=[with_detector])
    with pytest.raises(ValueError, match="judgment-only"):
        load_and_validate(tmp_path)


def test_an_eval_lane_is_refused_in_v1(tmp_path):
    with_eval = dict(_VALID_LANE)
    del with_eval["judgment"]
    del with_eval["why"]
    with_eval["eval"] = "tests/evals/some_project_check.py"
    _write_valid_marker(tmp_path, lanes=[with_eval])
    with pytest.raises(ValueError, match="judgment-only"):
        load_and_validate(tmp_path)


def test_multiple_problems_all_appear_in_one_raised_message(tmp_path):
    """A project author fixing one problem at a time off a partial error message is a
    worse experience than seeing everything wrong in one pass."""
    broken = dict(_VALID_LANE)
    broken["seat"] = "Finding integrity"
    del broken["precedent"]
    _write_valid_marker(tmp_path, lanes=[broken])
    with pytest.raises(ValueError) as exc_info:
        load_and_validate(tmp_path, reserved_seats=frozenset({"Finding integrity"}))
    message = str(exc_info.value)
    assert "collides with one of Dream Studio's own" in message
    assert "precedent" in message


def test_two_lanes_with_the_same_id_are_refused(tmp_path):
    """validate_lanes' own duplicate-id check, exercised through this module -- not
    re-tested for its own sake (that lives in review_lane_registry's own tests), just
    confirmed it is actually reached, not bypassed by this module's own parsing."""
    lane_a = dict(_VALID_LANE)
    lane_b = dict(_VALID_LANE)  # same id as lane_a, deliberately
    _write_valid_marker(tmp_path, lanes=[lane_a, lane_b])
    with pytest.raises(ValueError, match="declared twice"):
        load_and_validate(tmp_path)
