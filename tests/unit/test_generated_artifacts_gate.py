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
    # WAS `>= 5`, ASSERTING A BACKLOG. The seven pinned in KNOWN_UNVERIFIABLE below
    # were each resolved (a generator, a reworded claim, or -- for the two field-
    # label false positives -- a scanner fix) rather than left as permanent debt, so
    # the live count is whatever KNOWN_UNVERIFIABLE says, not a floor asserting there
    # must always be some.
    assert len(claims) == len(KNOWN_UNVERIFIABLE)
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
#:
#: WAS SEVEN. Each was read in full, not just its matched banner phrase, and resolved
#: on its own merits rather than mechanically:
#:   STRUCTURE.md, accessibility/gotchas.yml, security-review-scan-catalog.yaml --
#:     genuinely hand-authored, and each already said so once you read past the
#:     phrase that matched (a "Last reviewed" trail, "verbatim from ... agent",
#:     "draft_status: structured_draft"). Reworded to say that plainly instead of
#:     claiming generation.
#:   docs/reference/adapters.md -- one sentence used the "generated from" banner
#:     idiom to describe a DIFFERENT file (.claude/CLAUDE.md); reworded to the
#:     "projection" vocabulary the rest of the doc already uses for exactly that.
#:   output-format.md, findings-report.md, layer-map.md -- never a real claim. Each
#:     matched inside a FENCED example: a rendered template or an architecture
#:     diagram describing what some OTHER, actually-generated file contains. Fixed
#:     in the scanner (`_drop_fenced_examples`), not the content, which was already
#:     accurate.
#: None needed a generator: none had a code source whose drift a render could catch,
#: only prose, a judgment call, or a description of a different file.
KNOWN_UNVERIFIABLE: set[str] = set()


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


def test_a_rendered_examples_field_label_is_not_a_banner():
    """`output-format.md` and `findings-report.md` are templates a human wrote to show
    what an actually-generated document (a PRD, a review report) looks like once
    produced. Both open a fenced example whose first line is "Generated: <something>"
    -- the same field label this codebase's own generators write for real
    (`control/analysis/synthesis.py`, `core/work_orders/start_context.py`). That is
    true of the OUTPUT the template renders, not a claim that the template itself is
    generated, and the two are indistinguishable to `_BANNER` without knowing they
    sit inside a fence."""
    from core.gates.generated_artifacts import _BANNER, _drop_fenced_examples

    example = "Display template for analysis results.\n\n" "```\nPRD Generated: {prd_path}\n```\n"
    assert _BANNER.search(example), "the raw text still reads as a banner match"
    assert not _BANNER.search(_drop_fenced_examples(example))


def test_a_diagram_about_another_file_is_not_a_banner():
    """`layer-map.md`'s architecture diagram states, correctly, that
    `.claude/CLAUDE.md` is generated from the adapter authority -- inside a fenced
    box-drawing diagram of the whole layer stack, not a claim about layer-map.md."""
    from core.gates.generated_artifacts import _BANNER, _drop_fenced_examples

    diagram = (
        "## Layer Stack\n\n```\n"
        "Projection: .claude/CLAUDE.md (generated from canonical/adapter_authority)\n"
        "```\n"
    )
    assert _BANNER.search(diagram)
    assert not _BANNER.search(_drop_fenced_examples(diagram))


def test_an_unclosed_fence_at_the_read_boundary_still_strips():
    """`unverifiable_generated_claims` only reads a 600-character prefix of each file,
    so a fence opened inside that prefix is often not yet closed within it. The read
    stopping early does not end the block -- treating the tail as unfenced would
    re-introduce exactly the two false positives this was written to fix."""
    from core.gates.generated_artifacts import _BANNER, _drop_fenced_examples

    truncated = "before the fence\n```\nGenerated: 2026-04-28 15:30\nthis never clos"
    assert _BANNER.search(truncated)
    assert not _BANNER.search(_drop_fenced_examples(truncated))


def test_a_banner_outside_any_fence_is_still_caught():
    """The fence carve-out must not blind the scan to a real banner that sits
    alongside fenced content elsewhere in the same file -- STRUCTURE.md's own
    (now-fixed) claim opened outside its directory-tree fence, ahead of it."""
    from core.gates.generated_artifacts import _BANNER, _drop_fenced_examples

    doc = (
        "<!-- auto-generated from packs.yaml -- do not edit manually -->\n"
        "## Layout\n\n```text\nsome/example/tree\n```\n"
    )
    assert _BANNER.search(_drop_fenced_examples(doc)), "a real banner outside the fence was lost"


def test_the_report_is_not_wired_into_the_verdict():
    """Deliberate, and recorded in task_criteria_measure.py: a ratchet gate over the
    platform's own bookkeeping was one of nine that got deleted. The gate passes while
    files remain on the list.

    WAS `assert unverifiable_generated_claims(), "nothing left to report -- rewrite
    this test"`, borrowing the real repo's backlog to prove it. That backlog reaching
    zero -- resolving the seven pinned in KNOWN_UNVERIFIABLE -- is exactly the event
    that comment warned about, so the property is proven with a planted claim instead
    of a live one that can run out.
    """
    from core.gates.generated_artifacts import main

    import sys
    from unittest import mock

    with mock.patch.object(
        gate, "unverifiable_generated_claims", return_value=["some/planted/claim.md"]
    ):
        assert gate.run()["status"] == "pass"
        # main() parses sys.argv, which under pytest holds pytest's own arguments.
        with mock.patch.object(sys, "argv", ["generated-artifacts"]):
            assert main() == 0
