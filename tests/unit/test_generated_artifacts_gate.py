"""A checked-in artifact must match the generator that produces it.

This gate exists because of three incidents in one day, all the same shape:

  canonical/review_lanes.yml   a commit deleted 13 gate modules and removed their
                               four lanes from this GENERATED file without
                               touching its generator. A render three weeks later
                               restored exactly the 115 deleted lines, and 1,665
                               lines of detectors were rewritten against them
                               before the history showed the deletion was
                               deliberate.

  AGENTS.md                    `check_agents_md_fresh` existed, worked, and was in
                               no manifest, so nothing ever ran it.

  dist/plugin                  two new analyst seats did not ship because the
                               plugin was not rebuilt.

The cost of drift is not the stale bytes. It is that the next reader cannot tell
a deliberate deletion from an unfinished one, and reasonably rebuilds something
that was removed on purpose.
"""

from __future__ import annotations

from pathlib import Path

from core.gates import generated_artifacts as gate

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_every_registered_artifact_matches_its_generator():
    """The live check. If this fails, regenerate — and edit the generator."""
    result = gate.run()
    assert result["status"] == "pass", result["stale"]


def test_a_hand_edited_artifact_is_caught(tmp_path):
    """THE LOAD-BEARING CASE, and the one that actually happened.

    The edit here is appended text, exactly like the hand-edit that removed four
    lanes from review_lanes.yml — a change that looks applied, survives review,
    and is silently discarded the next time anyone runs the generator.
    """
    path = REPO_ROOT / "canonical" / "review_lanes.yml"
    original = path.read_text(encoding="utf-8")
    try:
        path.write_text(original + "\n# a hand edit\n", encoding="utf-8")
        result = gate.run()
        assert result["status"] == "fail"
        assert any(s["artifact"] == "canonical/review_lanes.yml" for s in result["stale"])
    finally:
        path.write_text(original, encoding="utf-8")

    assert gate.run()["status"] == "pass", "the restore must leave the tree clean"


def test_the_failure_names_the_command_and_says_to_edit_the_generator(tmp_path, capsys):
    """A refusal that does not say how to satisfy it is a wall — and here the
    obvious fix (edit the file) is the wrong one, so the message has to say so."""
    path = REPO_ROOT / "canonical" / "review_lanes.yml"
    original = path.read_text(encoding="utf-8")
    try:
        path.write_text(original + "\n# a hand edit\n", encoding="utf-8")
        assert gate.main([]) == 1
        err = capsys.readouterr().err
        assert "py scripts/seat_lanes_data.py" in err
        assert "EDIT THE GENERATOR" in err
    finally:
        path.write_text(original, encoding="utf-8")


def test_a_check_that_raises_is_a_finding_not_a_pass():
    """A generator that cannot run tells you nothing about the artifact, and
    must never be read as agreement. Reporting clean on a check that blew up is
    the compared-nothing-reported-clean shape."""

    def _boom() -> tuple[bool, str]:
        raise RuntimeError("generator import failed")

    original = gate.ARTIFACTS
    try:
        gate.ARTIFACTS = (("some/artifact", "py -m regenerate", _boom),)
        result = gate.run()
        assert result["status"] == "fail"
        assert "generator import failed" in result["stale"][0]["detail"]
    finally:
        gate.ARTIFACTS = original


def test_unverifiable_claims_are_reported_but_never_fail():
    """Dozens of files assert they are generated while naming no runnable
    command. Each is a real problem — an unverifiable claim of generation is
    worth no more than no claim — but blocking a push on all of them would be a
    wall, so they are a count, not a verdict."""
    claims = gate.unverifiable_generated_claims()
    assert len(claims) > 10, "expected the known backlog of unverifiable banners"
    assert gate.run()["status"] == "pass", "unverifiable claims must not fail the gate"
    # And the registered artifacts are not double-counted as unverifiable.
    registered = {a for a, _, _ in gate.ARTIFACTS}
    assert not (registered & set(claims))
