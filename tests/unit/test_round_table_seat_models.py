"""Every round-table seat declares the model its reviewer runs on.

`integrations/compiler/reviewers.py` used to write `model: sonnet` into every compiled
`review-*` agent unconditionally -- a string literal in the compiler, not a property of the
seat it was compiling. `scripts/seat_lanes_data.py`'s `SEAT_MODELS` is where that fact
actually lives now, and `canonical/review_lanes.yml` carries it on every lane so an operator
can read it, diff it, and override one seat without touching the compiler. These tests hold
that the registry, its generator, and the gate that checks it all agree.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
LANES = REPO_ROOT / "canonical" / "review_lanes.yml"


def _lanes() -> list[dict]:
    data = yaml.safe_load(LANES.read_text(encoding="utf-8"))
    return [lane for lane in data["lanes"] if isinstance(lane, dict)]


def test_every_lane_declares_a_model():
    """Guards the registry directly, independent of the gate that also checks it --
    two readings of the same fact, not one."""
    from integrations.compiler.agents import ALLOWED_MODEL_ALIASES

    lanes = _lanes()
    assert lanes, "no lanes found -- has the registry been truncated?"
    for lane in lanes:
        model = str(lane.get("model") or "").strip()
        assert model, f"{lane.get('id')}: no model declared"
        assert model in ALLOWED_MODEL_ALIASES or model.startswith(
            "claude-"
        ), f"{lane.get('id')}: model {model!r} is neither a known alias nor a claude-* id"


def test_every_lane_belonging_to_one_seat_agrees_on_its_model():
    """One seat compiles to one reviewer agent, so it can only run on one model. A lane
    declaring a different model than its own seat's other lanes would be asking which of
    them the compiler should believe."""
    by_seat: dict[str, set[str]] = {}
    for lane in _lanes():
        by_seat.setdefault(str(lane["seat"]), set()).add(str(lane.get("model")))
    disagreeing = {seat: models for seat, models in by_seat.items() if len(models) > 1}
    assert not disagreeing, f"seats whose own lanes disagree on the model: {disagreeing}"


def test_seat_lanes_data_is_the_source_scripts_check_agrees():
    """The registry is generated; this is the freshness half `scripts/seat_lanes_data.py
    --check` already enforces in CI, asserted here too so a change to `_model_for` that
    was never re-rendered fails locally rather than only in the drift gate."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import seat_lanes_data as gen

    current = LANES.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert current == gen.render(), (
        "canonical/review_lanes.yml does not match scripts/seat_lanes_data.py's render --"
        " run `py scripts/seat_lanes_data.py` to refresh it."
    )


def test_model_for_falls_back_to_default_for_an_unlisted_seat():
    """A new seat that forgets to declare a model ships on the safe default rather than
    raising out of the render -- the registry gate is where that omission is caught."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import seat_lanes_data as gen

    assert gen._model_for("A Seat Nobody Declared A Model For") == gen.DEFAULT_MODEL


def test_model_for_follows_the_seat_merge():
    """`_model_for` is looked up by the FINAL seat, same as `seat:` in the rendered
    registry -- a raw declared name that merged into another seat must run its reviewer
    on that seat's model, not a model nobody set for a name nothing compiles under."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import seat_lanes_data as gen

    merged_raw = next(iter(gen.SEAT_MERGES))
    final = gen.SEAT_MERGES[merged_raw]
    assert gen._model_for(merged_raw) == gen._model_for(final)


def test_the_gate_rejects_a_lane_with_no_model(tmp_path, monkeypatch):
    import core.gates.review_lane_registry as reg

    fake = tmp_path / "review_lanes.yml"
    fake.write_text(
        "version: 2\n"
        "lanes:\n"
        "  - id: a-lane-with-no-model\n"
        '    seat: "Chair and verdict owner"\n'
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
        "      A reason long enough to clear the forty character minimum this gate checks.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(reg, "REGISTRY", fake)
    result = reg.run()
    assert result["status"] == "fail"
    assert any("no `model`" in e for e in result["errors"]), result["errors"]


def test_the_gate_rejects_a_lane_with_an_illegal_model(tmp_path, monkeypatch):
    import core.gates.review_lane_registry as reg

    fake = tmp_path / "review_lanes.yml"
    fake.write_text(
        "version: 2\n"
        "lanes:\n"
        "  - id: a-lane-with-a-fake-model\n"
        '    seat: "Chair and verdict owner"\n'
        "    model: gpt-4\n"
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
        "      A reason long enough to clear the forty character minimum this gate checks.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(reg, "REGISTRY", fake)
    result = reg.run()
    assert result["status"] == "fail"
    assert any("is neither an alias" in e for e in result["errors"]), result["errors"]
