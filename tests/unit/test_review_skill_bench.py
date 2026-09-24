"""The review skill names the bench the registry defines, and a gate says so.

WHY THIS FILE EXISTS. The review skill's lane listing said "this section is GENERATED
from it", warned in its next line that a hand-maintained copy of a registry is a second
vocabulary that silently disagrees with the first, and was hand-maintained. It announced
29 seats and enumerated four the registry no longer had -- Merge-order steward,
Test-integrity inquisitor, Distributed state and concurrency, Event-substrate custodian --
in the document the dispatch rule points a subagent at.

These hold the listing to the registry and hold the gate to the listing.
"""

from __future__ import annotations

from core.gates import generated_artifacts
from integrations.compiler import review_skill

#: The seats the stale listing still named. Kept as the regression, not as a list of
#: forbidden words: if the registry ever re-seats one of these, the first test below
#: follows the registry and this one should be updated with it.
_RETIRED = (
    "Merge-order steward",
    "Test-integrity inquisitor",
    "Distributed state and concurrency",
    "Event-substrate custodian",
)


def _registry() -> list[dict]:
    from core.gates.round_table import _lanes

    return _lanes()


def test_the_listing_counts_what_the_registry_holds():
    """The numbers are computed. Nobody can write "29 seats" here again."""
    lanes = _registry()
    seats = {str(lane.get("seat")) for lane in lanes}
    block = review_skill.render()
    assert f"**{len(seats)} seats**" in block
    assert f"**{len(lanes)} lanes**" in block


def test_every_registry_lane_is_named_and_no_other():
    """Both halves. The gate-integrity seat showed the second was never checked: a
    generator adding a made-up lane id passed every test here and check() said OK."""
    import re

    block = review_skill.render()
    ids = {str(lane["id"]) for lane in _registry()}
    for lane_id in ids:
        assert f"`{lane_id}`" in block, f"lane {lane_id} missing from the listing"
    table = [line for line in block.splitlines() if line.startswith("| ") and "`" in line]
    named = {m for line in table for m in re.findall(r"`([^`]+)`", line.split("|")[2])}
    assert named == ids, f"listed but not in the registry: {sorted(named - ids)}"


def test_the_retired_seats_are_gone_from_the_skill():
    """The regression itself: the listing a reviewer was told to convene named seats that
    no longer exist."""
    live = {str(lane.get("seat")) for lane in _registry()}
    text = review_skill.SKILL.read_text(encoding="utf-8")
    head, tail = text.find(review_skill.BEGIN), text.find(review_skill.END)
    block = text[head:tail]
    for seat in _RETIRED:
        if seat in live:
            continue  # re-seated since; the registry decides
        assert seat not in block, f"the skill still lists the retired seat {seat!r}"


def test_the_committed_skill_is_fresh():
    ok, detail = review_skill.check()
    assert ok, f"{detail} -- run `py -m integrations.compiler.review_skill --write`"


def test_a_hand_edit_to_the_listing_is_caught(tmp_path, monkeypatch):
    """A check that passes on a drifted file is the defect this replaces, so drift is
    manufactured and the check must refuse it."""
    stale = tmp_path / "SKILL.md"
    text = review_skill.SKILL.read_text(encoding="utf-8")
    stale.write_text(text.replace("seats**", "seats (hand-edited)**", 1), encoding="utf-8")
    monkeypatch.setattr(review_skill, "SKILL", stale)
    ok, detail = review_skill.check()
    assert not ok
    assert "drifted" in detail


def test_missing_markers_are_reported_not_passed(tmp_path, monkeypatch):
    """Deleting the markers must not turn "cannot check" into "clean"."""
    bare = tmp_path / "SKILL.md"
    bare.write_text("# Review\n\nno markers here\n", encoding="utf-8")
    monkeypatch.setattr(review_skill, "SKILL", bare)
    ok, _detail = review_skill.check()
    assert not ok


def test_the_gate_runs_this_check():
    """A generator the gate does not call is a correct check wired to nothing -- which is
    exactly how the listing drifted while claiming to be generated."""
    names = [name for name, _cmd, _check in generated_artifacts.ARTIFACTS]
    assert any("review/SKILL.md" in name for name in names), names
