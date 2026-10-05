"""`method_requirements:` -- which of the four investigation techniques a lane demands.

The lane registry already says WHAT to ask (`question`, `signature`, `precedent`,
`measurement`); nothing said HOW to investigate it well on code nobody has seen before.
Four techniques (enumerate every paired site, prove the break with a counterfactual,
fetch a tool's own current docs, verify every cited record by opening it) lived only in
reviewers' heads. `method_requirements:` is the closed-vocabulary field a lane uses to
opt into zero or more of them; `core.gates.review_lane_registry.validate_lanes` holds the
REGISTRY to that closed set, and `core.work_orders.review_answers.validate_answers` is the
enforcement side, tested in `tests/unit/test_review_answers.py` instead of here.

These tests hold the schema and the 26-lane annotation, the same split
`test_round_table_seat_models.py` already makes for `model:` -- the gate, the generator,
and a direct read of the committed registry are three readings of one fact, not one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
LANES = REPO_ROOT / "canonical" / "review_lanes.yml"

_BASE_LANE = (
    "    question: >-\n"
    "      A question long enough to clear the forty character minimum this gate checks.\n"
    "    signature: >-\n"
    "      A signature long enough to clear the forty character minimum this gate checks.\n"
    "    precedent: >-\n"
    "      A precedent long enough to clear the forty character minimum this gate checks.\n"
    "    measurement: >-\n"
    "      A measurement long enough to clear the forty character minimum this gate checks.\n"
    "    judgment: true\n"
    "    why: >-\n"
    "      A reason long enough to clear the forty character minimum this gate checks.\n"
)


def _fake_registry(tmp_path, *, method_requirements_yaml: str) -> Path:
    fake = tmp_path / "review_lanes.yml"
    fake.write_text(
        "version: 2\n"
        "lanes:\n"
        "  - id: a-fake-lane\n"
        '    seat: "Chair and verdict owner"\n'
        "    model: sonnet\n" + _BASE_LANE + method_requirements_yaml,
        encoding="utf-8",
    )
    return fake


def _lanes() -> list[dict]:
    data = yaml.safe_load(LANES.read_text(encoding="utf-8"))
    return [lane for lane in data["lanes"] if isinstance(lane, dict)]


# ── the gate's own shape check ──────────────────────────────────────────────


def test_a_lane_with_no_method_requirements_is_accepted():
    """Optional, unlike the enforcement key: most lanes name none of the four."""
    import core.gates.review_lane_registry as reg

    assert (
        reg.validate_lanes(
            [
                {
                    "id": "a-fake-lane",
                    "seat": "Chair and verdict owner",
                    "model": "sonnet",
                    "question": "A question long enough to clear the forty character minimum.",
                    "signature": "A signature long enough to clear the forty character minimum.",
                    "precedent": "A precedent long enough to clear the forty character minimum.",
                    "measurement": "A measurement long enough to clear the forty character minimum.",
                    "judgment": True,
                    "why": "A reason long enough to clear the forty character minimum this gate.",
                }
            ],
            closed_seats=reg.SEATS,
        )
        == []
    )


def test_the_gate_accepts_a_known_method_requirement(tmp_path, monkeypatch):
    import core.gates.review_lane_registry as reg

    fake = _fake_registry(
        tmp_path,
        method_requirements_yaml='    method_requirements:\n      - "prove_the_break"\n',
    )
    monkeypatch.setattr(reg, "REGISTRY", fake)
    result = reg.run()
    assert result["status"] == "pass", result["errors"]


def test_the_gate_rejects_an_unknown_method_requirement(tmp_path, monkeypatch):
    import core.gates.review_lane_registry as reg

    fake = _fake_registry(
        tmp_path,
        method_requirements_yaml='    method_requirements:\n      - "guess_and_check"\n',
    )
    monkeypatch.setattr(reg, "REGISTRY", fake)
    result = reg.run()
    assert result["status"] == "fail"
    assert any("guess_and_check" in e for e in result["errors"]), result["errors"]


def test_the_gate_rejects_a_non_list_method_requirements(tmp_path, monkeypatch):
    import core.gates.review_lane_registry as reg

    fake = _fake_registry(
        tmp_path,
        method_requirements_yaml='    method_requirements: "prove_the_break"\n',
    )
    monkeypatch.setattr(reg, "REGISTRY", fake)
    result = reg.run()
    assert result["status"] == "fail"
    assert any("must be a list" in e for e in result["errors"]), result["errors"]


# ── the real registry, read directly ────────────────────────────────────────


def test_every_real_lanes_method_requirements_are_known():
    """Guards the committed registry directly, independent of the gate that also checks
    it -- two readings of the same fact, same discipline `test_every_lane_declares_a_model`
    already holds for `model:`."""
    from core.work_orders.review_answers import METHOD_VOCABULARY

    lanes = _lanes()
    assert lanes, "no lanes found -- has the registry been truncated?"
    checked = 0
    for lane in lanes:
        methods = lane.get("method_requirements")
        if methods is None:
            continue
        checked += 1
        assert isinstance(methods, list), f"{lane['id']}: method_requirements is not a list"
        unknown = set(methods) - set(METHOD_VOCABULARY)
        assert not unknown, f"{lane['id']}: unknown method_requirements {unknown}"
    assert checked > 0, "no lane declares method_requirements -- was the annotation pass lost?"


def test_not_every_lane_is_padded_with_every_technique():
    """The annotation is honest, not reflexive: at least one real lane (the detector lane,
    and the lanes whose own question is about already-produced findings or external
    mission judgement rather than fresh code investigation) declares none of the four."""
    lanes = _lanes()
    undeclared = [lane["id"] for lane in lanes if not lane.get("method_requirements")]
    assert undeclared, "every lane declaring something suggests padding, not judgement"


def test_the_detector_lane_requires_no_investigation_technique():
    """`docs-style-and-attribution` is answered by a mechanical detector -- `convene()`
    runs it directly and no reviewer is ever dispatched it to answer -- so a
    method_requirements entry there would bind nobody."""
    [lane] = [ln for ln in _lanes() if ln["id"] == "docs-style-and-attribution"]
    assert lane.get("detector")
    assert not lane.get("method_requirements")


# ── the generator: table keys must name real lanes ──────────────────────────


def test_seat_lanes_data_method_requirements_keys_are_real_lane_ids():
    """A typo'd key in the generator's METHOD_REQUIREMENTS table is not a rendering
    error -- `_block()` looks it up by the lane id passed in and a miss just renders
    nothing, so a stale or misspelled key silently drops its annotation rather than
    failing. This is the check that would catch it."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import seat_lanes_data as gen

    real_ids = {lane["id"] for lane in _lanes()}
    stale = set(gen.METHOD_REQUIREMENTS) - real_ids
    assert not stale, f"METHOD_REQUIREMENTS names lane ids that do not exist: {stale}"


def test_seat_lanes_data_method_requirements_values_are_all_known():
    from core.work_orders.review_answers import METHOD_VOCABULARY

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import seat_lanes_data as gen

    for lane_id, methods in gen.METHOD_REQUIREMENTS.items():
        unknown = set(methods) - set(METHOD_VOCABULARY)
        assert not unknown, f"{lane_id}: {unknown} not in METHOD_VOCABULARY"


def test_seat_lanes_data_is_the_source_for_method_requirements_too():
    """The freshness half: a change to METHOD_REQUIREMENTS that was never re-rendered
    fails here, the same guarantee `test_seat_lanes_data_is_the_source_scripts_check_agrees`
    already holds for the registry as a whole -- reasserted narrowly so a failure here
    names this feature rather than "something in the render disagrees"."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import seat_lanes_data as gen

    rendered = {lane["id"]: lane.get("method_requirements") for lane in _lanes()}
    for lane_id, methods in gen.METHOD_REQUIREMENTS.items():
        assert rendered.get(lane_id) == list(methods), (
            f"{lane_id}: registry has {rendered.get(lane_id)}, generator table has"
            f" {list(methods)} -- run `py scripts/seat_lanes_data.py` to refresh it"
        )


# ── lane_method_requirements(): the reader review_answers.py actually uses ──


def test_lane_method_requirements_reads_the_real_registry():
    from core.work_orders.review_answers import lane_method_requirements

    reqs = lane_method_requirements()
    assert reqs["a-test-that-cannot-fail"] == ["prove_the_break"]
    assert reqs["the-other-half-enforced-by-nothing"] == [
        "enumerate_paired_sites",
        "prove_the_break",
    ]


def test_lane_method_requirements_omits_lanes_with_none():
    """Absence, not an empty list -- `validate_answers` treats a missing key as "nothing
    required", and a stray empty-list entry would be indistinguishable from that at the
    call site while meaning something different at the registry (a lane that was
    considered and padded with nothing, versus one nobody annotated at all)."""
    from core.work_orders.review_answers import lane_method_requirements

    reqs = lane_method_requirements()
    assert "chair-and-verdict-owner" not in reqs
    assert "mission-domain-consequence" not in reqs
    assert "docs-style-and-attribution" not in reqs
