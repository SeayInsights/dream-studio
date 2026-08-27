"""WO-EVIDENCE-BACKED-OUTPUT: nothing goes to GitHub as a claim without its evidence.

Operator ruling 2026-08-27: "any comment or review being pushed to github has to be backed
by evidence and show all evidence and everything has to be verified. it should be detailed
and based on facts and show all facts so no one is ever guessing."

THE FIXTURES BELOW ARE REAL. Every string in ``_REAL_UNBACKED`` was written by me into a
pull-request body in the session that produced this gate, and three of those pull requests
were merged carrying it. Inventing fixtures is the mistake that let the unreviewable-gap
filter ship broken earlier in the same milestone: the real stored value was
``rule = "N/A: independent review unverifiable - no diff provided"`` and the test asserted
against ``"N/A"``, a simplification I made up. Driven against the real value, the old filter
reproduced the nonsense work order verbatim.
"""

from __future__ import annotations

from pathlib import Path

from core.gates.evidence_backed_output import audit_file, audit_text

NL = chr(10)


# Verbatim from PR bodies authored 2026-08-27. All four carried the first line.
_REAL_UNBACKED = [
    "- [x] PR smoke is expected to pass",
    "Queue drained via a now-referenced drain, and the milestone should pass now",
    "I believe the three platforms will be green",
]

# Also verbatim from the same PR bodies -- these carry their evidence.
_REAL_BACKED = [
    "- **306 passed, 0 failed, 4 xfailed** across the full blast radius, 18m50s",
    "Local heavy gate passed - all 21 pre-push gates, `Overall: PASS`",
    "commit 5612a02f PASSED the pre-push gate and was pushed",
    "`test_verify_gap_resolution.py::test_closed_spawn_resolves_completion_gap`",
    'close_gates.py:431 reads that list and prints "Gap WOs"',
]


# -- The property --------------------------------------------------------------


def test_an_unbacked_claim_is_flagged():
    """A claim that cites nothing a reader can check is a guess, however confident."""
    report = audit_text("The change is complete and the suite should pass." + NL)

    assert not report.passed
    assert len(report.unbacked) == 1
    assert "should pass" in report.unbacked[0].trigger


def test_a_backed_claim_passes():
    """The gate is worthless if it cries wolf -- a flagged-everything gate gets bypassed
    and then protects nothing."""
    for line in _REAL_BACKED:
        report = audit_text(line + NL)
        assert report.passed, f"a cited claim was flagged: {line!r} -> {report.unbacked}"


def test_the_real_unbacked_claims_from_this_session_are_caught():
    """Driven against the ACTUAL strings, not invented ones.

    "- [x] PR smoke is expected to pass" appeared in all four PR bodies written the day
    this gate was built, three of them already merged. A prediction inside a CHECKED box:
    the box asserts the item is done while the words admit it is not.
    """
    for line in _REAL_UNBACKED:
        report = audit_text(line + NL)
        assert not report.passed, f"a real unbacked claim slipped through: {line!r}"

    box_report = audit_text(_REAL_UNBACKED[0] + NL)
    assert box_report.unbacked[0].kind == "checked-box", (
        "a checked box that hedges must be reported as the self-contradiction it is, "
        "not as ordinary prose"
    )


def test_a_hedge_with_evidence_on_the_next_line_passes():
    """Evidence often sits beneath its claim -- a command, then its output. Requiring it on
    the same line would flag correctly-evidenced writing."""
    text = (
        "The suite should pass on all three platforms."
        + NL
        + "    306 passed, 0 failed in 1130.89s"
        + NL
    )
    assert audit_text(text).passed


def test_an_unchecked_box_is_not_a_claim():
    """An unchecked box asserts nothing -- it is an admission. Flagging it would push an
    author toward checking it instead of leaving it honest."""
    assert audit_text("- [ ] PR smoke is expected to pass" + NL).passed


# -- The report holds itself to the same standard ------------------------------


def test_the_report_shows_the_evidence_found():
    """ "Unbacked claim at line 12" is half an answer. An author needs to see what the
    document DOES carry to know what the gap is -- the same standard the rule imposes on
    them."""
    text = (
        "306 passed, 0 failed"
        + NL
        + "See `core/gates/reachability.py` and commit 7eca2f1c."
        + NL
        + "The rest should work."
        + NL
    )
    report = audit_text(text)

    assert not report.passed, "the unbacked line must still be reported"
    assert report.evidence, "the evidence actually present must be listed"
    joined = " ".join(report.evidence)
    assert "306 passed" in joined
    assert "7eca2f1c" in joined
    rendered = report.render()
    assert "evidence present" in rendered


def test_a_document_with_no_evidence_at_all_says_so_explicitly():
    """The worst case deserves naming rather than an empty section: claims about verified
    work with not one citation is exactly what this gate exists for."""
    report = audit_text("Everything works. It should be fine to merge." + NL)
    rendered = report.render()

    assert "evidence present: NONE" in rendered
    assert "this gate exists for" in rendered


def test_a_clean_document_reports_ok_and_still_lists_its_evidence():
    """A passing document should show its receipts too, so a reviewer can see the basis
    rather than trusting the verdict."""
    report = audit_text("Verified: 306 passed, 0 failed at commit 7eca2f1c." + NL)

    assert report.passed
    rendered = report.render()
    assert "OK" in rendered
    assert "evidence present" in rendered


# -- Bounds and honesty about the detector ------------------------------------


def test_an_empty_document_is_not_a_failure():
    """Nothing claimed, nothing unbacked. A gate that fails on an empty body would block
    a draft."""
    assert audit_text("").passed
    assert audit_text(NL * 3).passed


def test_ordinary_prose_is_not_flagged():
    """Uncertainty about opinion is not a claim about state. The hedge list is deliberately
    narrow -- it targets assertions about whether work is done, not hesitant writing."""
    for line in (
        "I think this reads better as two paragraphs.",
        "This is probably the clearest phrasing available.",
        "It seems worth splitting the module eventually.",
    ):
        report = audit_text(line + NL)
        # These MAY be flagged (probably/I think/seems are in the list); what must not
        # happen is a crash or a claim about the wrong line.
        for claim in report.unbacked:
            assert claim.line == 1
            assert claim.text


def test_auditing_a_real_file_works(tmp_path: Path):
    """The gate runs against a file on disk -- a PR body path is what the pre-push hook
    has to hand."""
    body = tmp_path / "pr.md"
    body.write_text(
        "## Summary" + NL * 2 + "- [x] PR smoke is expected to pass" + NL, encoding="utf-8"
    )
    report = audit_file(body)
    assert not report.passed
    assert report.unbacked[0].line == 3


# -- Quotations: evidence of a defect, not an instance of one -------------------


def test_a_quoted_hedge_on_one_line_is_not_a_claim():
    """Quoting the offending line is how a document EXPLAINS the rule. Flagging it made
    the gate refuse this module's own docstring, the pre-push manifest entry, and the
    commits that introduced the rule."""
    text = "The bad line was `- [x] PR smoke is expected to pass` and it shipped." + NL
    assert audit_text(text).passed


def test_a_quotation_split_across_lines_is_still_a_quotation():
    """MULTI-LINE QUOTATION IS THE NORMAL CASE, NOT AN EDGE CASE. Commit messages wrap at
    72 characters, so a quoted line almost always splits:

        four PR bodies written the day this was built carried "- [x] PR smoke is
        expected to pass", a forecast inside a checked box

    The single-line check saw a closing quote after the hedge and no opening one before it,
    so it reported the quotation as a claim -- and the gate refused two of the commits that
    introduced it. Fixed by double-quote parity over the preceding lines.
    """
    text = (
        'four PR bodies written the day this was built carried "- [x] PR smoke is'
        + NL
        + 'expected to pass", a forecast inside a checked box, three already merged.'
        + NL
    )
    report = audit_text(text)
    assert report.passed, f"a split quotation was read as a claim: {report.unbacked}"


def test_an_unclosed_quote_does_not_swallow_the_rest_of_the_document():
    """Parity is only correct for well-formed text. A stray unmatched quote makes every
    later line read as quoted -- so this pins the blast radius of that failure rather than
    pretending it cannot happen.

    An author who leaves a dangling quote gets weaker checking from there on. Accepted:
    the alternative is flagging every wrapped quotation, which made the gate unusable.
    """
    text = 'He said "something unclosed here' + NL + "The suite should pass." + NL
    report = audit_text(text)
    # Documenting the real behaviour: the second line reads as quoted, so it is NOT
    # flagged. If this ever changes to flag it, that is an improvement -- update the test.
    assert report.passed


def test_the_quoting_evasion_hole_is_real_and_visible_here():
    """THE ACCEPTED COST, ASSERTED SO IT IS VISIBLE IN THE SUITE AND NOT ONLY A DOCSTRING.

    An author can wrap their own forecast in quotes and slip it past. That is a genuine
    hole. It is accepted because a quoted claim reads as attribution, and because blocking
    every document that documents the rule is the worse trade.

    Written as a test rather than prose so that anyone tightening the rule finds it here,
    with the reasoning attached, instead of rediscovering it as a surprise.
    """
    evasive = 'Status: "the smoke run is expected to pass".' + NL
    assert audit_text(evasive).passed, (
        "if this now FAILS, the evasion hole has been closed -- delete this test and say "
        "so in the module docstring, which currently documents the hole as accepted"
    )


def test_the_gate_is_in_the_pre_push_set():
    """The rule is only enforced if the gate actually runs on every push."""
    import yaml

    from core.gates.pre_push import DEFAULT_MANIFEST

    manifest = yaml.safe_load(Path(DEFAULT_MANIFEST).read_text(encoding="utf-8"))
    entries = {g["id"]: g for g in (manifest.get("gates") or [])}

    assert (
        "evidence-backed-output" in entries
    ), f"not registered in {DEFAULT_MANIFEST}; registered: {sorted(entries)}"
    entry = entries["evidence-backed-output"]
    assert entry["tier"] == "blocking"
    assert entry["command"] == [
        "py",
        "-m",
        "core.gates.evidence_backed_output",
        "--staged",
    ], entry["command"]

    # THE ENTRY MUST NOT OVERCLAIM. It briefly said it audits "pull-request bodies staged
    # for this push" -- which it cannot, because a PR body is not in the repository. A
    # gate description that asserts a reach it does not have is the very defect this gate
    # exists to catch, in the gate's own registration.
    description = " ".join(entry["description"].split())
    assert "Audits pull-request bodies" not in description
    assert "COMMIT MESSAGES" in description, "it must say what it actually reads"
    assert "does not live" in description, "and admit what it cannot reach"
