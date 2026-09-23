"""Drive the skill-card gate against a synthetic tree, then pin the real one.

The synthetic cases build a miniature repo (packs.yaml + one mode card + a vocabulary
registry), point the gate's path constants at it, and call ``run`` -- so each case exercises
the validator rather than asserting that a rule was typed into the source.
"""

from __future__ import annotations

import json

import pytest
import yaml

from core.gates import skill_card

VALID_CARD = {
    "skill_id": "ds-demo",
    "pack": "demo",
    "mode": "example",
    "mode_type": "analysis",
    "inputs": ["seed_token"],
    "outputs": ["demo_report"],
    "capabilities_required": ["Read"],
    "model_preference": "sonnet",
    "estimated_duration": "5-10min",
    "write_posture": "read-only",
    "lifecycle": "published",
}


def _build(tmp_path, card, *, invariants=("something holds",), root_inputs=("seed_token",)):
    """Write a miniature repo and return it."""
    packs = {"packs": {"demo": {"skill": "demo", "modes": ["example"]}}}
    if invariants:
        packs["packs"]["demo"]["invariants"] = list(invariants)
    (tmp_path / "packs.yaml").write_text(yaml.safe_dump(packs), encoding="utf-8")

    mode_dir = tmp_path / "canonical" / "skills" / "demo" / "modes" / "example"
    mode_dir.mkdir(parents=True)
    body = "---\n" + yaml.safe_dump({"dream_studio": card}, sort_keys=False) + "---\n\n# Demo\n"
    (mode_dir / "SKILL.md").write_text(body, encoding="utf-8")

    vocab = tmp_path / "canonical" / "skill_vocabulary.json"
    vocab.write_text(json.dumps({"root_inputs": list(root_inputs)}), encoding="utf-8")
    return tmp_path


@pytest.fixture
def gate_at(tmp_path, monkeypatch):
    """Point the gate's path constants at a synthetic repo."""

    def _point(**kwargs):
        root = _build(tmp_path, **kwargs)
        monkeypatch.setattr(skill_card, "REPO_ROOT", root)
        monkeypatch.setattr(skill_card, "PACKS_PATH", root / "packs.yaml")
        monkeypatch.setattr(skill_card, "VOCAB_PATH", root / "canonical" / "skill_vocabulary.json")
        return root

    return _point


def _problems(result, field):
    return [o for o in result["offenders"] if o["field"] == field]


def test_valid_card_passes(gate_at):
    gate_at(card=dict(VALID_CARD))
    result = skill_card.run(scope_all=True)
    assert result["status"] == "pass", result["offenders"]
    assert result["cards_checked"] == ["demo:example"]


def test_missing_write_posture_is_refused(gate_at):
    card = dict(VALID_CARD)
    del card["write_posture"]
    gate_at(card=card)
    result = skill_card.run(scope_all=True)
    assert result["status"] == "fail"
    assert any("write_posture" in o["problem"] for o in result["offenders"])


def test_unknown_write_posture_is_refused(gate_at):
    gate_at(card={**VALID_CARD, "write_posture": "yolo"})
    result = skill_card.run(scope_all=True)
    assert result["status"] == "fail"
    assert any("yolo" in o["problem"] for o in result["offenders"])


def test_unknown_lifecycle_is_refused(gate_at):
    gate_at(card={**VALID_CARD, "lifecycle": "someday"})
    result = skill_card.run(scope_all=True)
    assert result["status"] == "fail"
    assert any("someday" in o["problem"] for o in result["offenders"])


def test_an_input_nothing_produces_is_refused(gate_at):
    gate_at(card={**VALID_CARD, "inputs": ["not_produced_anywhere"]})
    result = skill_card.run(scope_all=True)
    assert result["status"] == "fail"
    assert _problems(result, "inputs")


def test_an_input_another_mode_produces_is_accepted(gate_at):
    """A token absent from the registry still resolves when a mode's outputs carry it."""
    gate_at(card={**VALID_CARD, "inputs": ["demo_report"]}, root_inputs=())
    result = skill_card.run(scope_all=True)
    assert result["status"] == "pass", result["offenders"]


def test_card_misreporting_its_coordinates_is_refused(gate_at):
    gate_at(card={**VALID_CARD, "pack": "somewhere-else"})
    result = skill_card.run(scope_all=True)
    assert result["status"] == "fail"
    assert _problems(result, "pack/mode")


def test_pack_without_invariants_is_refused(gate_at):
    gate_at(card=dict(VALID_CARD), invariants=())
    result = skill_card.run(scope_all=True)
    assert result["status"] == "fail"
    assert _problems(result, "invariants")


def test_an_extra_field_is_refused(gate_at):
    """The card block is closed, so a typo'd field cannot sit there being ignored."""
    gate_at(card={**VALID_CARD, "wrtie_posture": "read-only"})
    result = skill_card.run(scope_all=True)
    assert result["status"] == "fail"


def test_the_real_tree_is_clean():
    """Regression pin: every carded mode in this repo validates and resolves."""
    result = skill_card.run(scope_all=True)
    assert result["status"] == "pass", result["offenders"]
    # 52 BEFORE `website` and `fullstack` moved out of the domains tree. They were
    # modes then and are packs now, and a pack carries no card -- its metadata lives
    # in packs.yaml. Two fewer cards is the move landing, not coverage lost.
    # A floor, not a pin: dissolving a pack removes its cards, and this number has
    # stepped down twice for that reason (51 -> 50 with ds-milestone, 50 -> 49 with
    # ds-project). It exists to catch the gate finding NOTHING, which is the failure
    # mode the file is about.
    assert len(result["cards_checked"]) >= 49


def test_every_real_card_declares_a_known_posture():
    postures = {c.get("write_posture") for _, _, _, c in skill_card._all_cards()}
    assert postures <= {"read-only", "independent", "hitl"}
    assert "hitl" in postures, "no mode records that it stops for the operator"
