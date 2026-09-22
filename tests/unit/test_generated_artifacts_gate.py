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


# ---------------------------------------------------------------------------
# The unverifiable-claims report has to be a worklist (E22)
# ---------------------------------------------------------------------------

#: THE FOURTEEN, BY NAME. Pinned as names rather than a count because a count that
#: moved would say only "something changed"; a name says which file, and fixing one is
#: deleting its line here. A fifteenth fails this test carrying its own path.
#:
#: NOT A BLOCKING GATE. `core/work_orders/task_criteria_measure.py` records that a
#: ratchet gate over the platform's own bookkeeping was deleted -- "one of nine gates
#: whose subject was the platform's own bookkeeping rather than whether Dream Studio
#: works" -- and that the COUNTING survived as measurement asserted by behavioural
#: tests. This follows that, deliberately: the measurement is pinned here, not turned
#: into a tenth such gate.
KNOWN_UNVERIFIABLE = {
    "STRUCTURE.md",
    "canonical/skills/analyze/modes/intelligence/reference/output-format.md",
    "canonical/skills/core/modes/review/templates/output-formats/findings-report.md",
    "canonical/skills/quality/modes/accessibility/gotchas.yml",
    "docs/audits/2026-05-22-full-stock/00c-mechanical-inventory-final.md",
    "docs/contracts/security-review-scan-catalog.yaml",
    "docs/publication/docs_publication_readiness_report.md",
    "docs/publication/final_history_rewrite_branch_classification_report.md",
    "docs/publication/history_rewrite_force_push_plan.md",
    "docs/publication/history_rewrite_rehearsal_report.md",
    "docs/reference/adapters.md",
    "docs/reference/layer-map.md",
    "tools/_ta0c_activity_log_inventory.md",
    "tools/_ta4_hardcoded_project_id_inventory.md",
}


def test_the_worklist_is_exactly_the_files_that_need_a_generator():
    """A worklist naming 96 files when 14 are real is not a worklist.

    Before this, the report returned 96. 42 were under `canonical/agents` or
    `dist/plugin` -- directories this gate DOES verify -- and 40 were the bare word
    "generated" in prose about a different file. The fourteen genuine ones were
    invisible inside that for as long as the report existed.
    """
    from core.gates.generated_artifacts import unverifiable_generated_claims

    reported = set(unverifiable_generated_claims())
    new = reported - KNOWN_UNVERIFIABLE
    fixed = KNOWN_UNVERIFIABLE - reported
    assert not new, f"new unverifiable generation claim(s): {sorted(new)}"
    assert not fixed, (
        f"these no longer claim generation without a generator -- delete them from"
        f" KNOWN_UNVERIFIABLE: {sorted(fixed)}"
    )


def test_a_file_the_gate_already_checks_is_never_reported():
    """`known` compared exact paths against entries that are DIRECTORIES, so every file
    under a registered directory was reported as unchecked by the gate that checks it."""
    from core.gates.generated_artifacts import ARTIFACTS, unverifiable_generated_claims

    registered = [a.rstrip("/") for a, _, _ in ARTIFACTS]
    assert any("/" not in r or r.count("/") >= 1 for r in registered)
    for reported in unverifiable_generated_claims():
        for entry in registered:
            assert not reported.startswith(entry + "/"), (
                f"{reported} is under the registered artifact {entry}, which this gate"
                " verifies -- reporting it as unverifiable is the gate contradicting itself"
            )


def test_prose_about_another_files_generation_is_not_a_banner():
    """`docs/tools/CURSOR.md` opens "Dream Studio installs its generated AGENTS.md".
    That is a sentence about AGENTS.md, not a claim about CURSOR.md."""
    from core.gates.generated_artifacts import _BANNER

    assert not _BANNER.search("Cursor reads `AGENTS.md` natively. Dream Studio installs its")
    assert not _BANNER.search("the generated projection is written by the installer")
    # `generated from` is KEPT even though prose can contain it: it is a real banner
    # idiom (`GENERATED FROM canonical/packs.yaml`) and the phrase is rare in running
    # text, unlike the bare adjective. Dropping it to win this one sentence would lose
    # real banners, which is the direction that reports clean by not looking.


def test_a_real_banner_is_still_detected():
    """Tightening must not turn the reporter into one that reports nothing -- which
    would look exactly like success."""
    from core.gates.generated_artifacts import _BANNER

    for banner in (
        "# DO NOT EDIT -- generated",
        "# AUTO-GENERATED FILE",
        "# GENERATED BY scripts/render.py",
        "# GENERATED FROM canonical/packs.yaml",
        "<!-- GENERATED: do not hand-edit -->",
        "Regenerate with `py -m integrations.compiler.agents --write`",
        "GENERATED\nthis file is built",
    ):
        assert _BANNER.search(banner), f"missed a real banner: {banner!r}"


def test_the_report_is_not_wired_into_the_verdict():
    """Deliberate, and recorded in task_criteria_measure.py: a ratchet gate over the
    platform's own bookkeeping was one of nine that got deleted. The gate passes while
    files remain on the list."""
    from core.gates.generated_artifacts import main, unverifiable_generated_claims

    import sys
    from unittest import mock

    assert unverifiable_generated_claims(), "nothing left to report -- rewrite this test"
    # main() parses sys.argv, which under pytest holds pytest's own arguments.
    with mock.patch.object(sys, "argv", ["generated-artifacts"]):
        assert main() == 0
