"""Review lane ``a-channel-outside-the-accounting`` — the Cartographer.

THE FINDING, from a review pass on another project. An archive guard declared caps: bytes
per member, bytes in total, number of members. A reviewer built ten archives, ran them
through `_declaration_members`, and wrote: *"The archive parser holds up, and I tested it
rather than trusting it … Ten for ten, on both container formats… genuinely safe rather
than merely bounded."* PAX headers were reachable the whole time. So was GNU long-name.

WHY TEN REAL TESTS FOUND NOTHING, which is the whole content of this lane. Look at what the
ten cases were: a member over the per-member cap; members summing past the total cap; more
members than the member cap; the wrong container; empty bytes. **Every one is derived from a
limit the guard declares.** The reviewer enumerated the artifact's stated dimensions and
tried to exceed each — which is thorough, and which cannot reach PAX, because PAX is not a
way to exceed a declared cap. It is a byte channel the accounting never counts: `tarfile`
consumes and expands the header internally, then yields only the regular member, so
`member.isfile()` never sees it. To find it you have to stop asking *"can I beat these
caps?"* and ask *"what does tarfile do that isn't a member I would be shown?"* — a question
about the library's behaviour, not the guard's rules, and nothing in the artifact points at
it.

IT IS THE THIRD VARIANT OF ONE LESSON, and the finder's own table is the clearest statement
of the shape:

    verified                             the miss was
    the strict-name rule is enforced     whether the rule was RIGHT
    the hook's state transitions         what actually RENDERS
    the caps the guard declares          a channel outside its ACCOUNTING

Each time the review took its frame from the artifact under review, and the defect sat one
layer outside that frame. Mutation testing, constructed inputs and wire captures all
confirm the code does what it says; none of them asks whether what it says is the whole
surface.

WHY THIS IS NOT THE FALSIFIER. That seat asks whether a green test can go red, and these
ten could — they were real inputs against a real guard, and they passed because the guard
genuinely enforces its caps. Nothing was vacuous. WHY IT IS NOT THE INTERPRETER: that seat
asks whether a value reaches a reader and means the same there, which covers the middle row
and neither of the others.

THREE PASSES MISSED IT, which is what makes it a missing question rather than a lapse: the
author twice, plus a review of this module specifically for security. It was found by
reasoning about `tarfile`.

WHY GRADED, AND THE MEASUREMENT IS UNUSUALLY DECISIVE. A detector was prototyped: for each
format the repo parses in production, does the test corpus mention that format's documented
side channels? It measured 4 formats — csv (5 production sites, 0 of 3 channels named in
tests), json (275 sites, 1 of 4), yaml (43 sites, 3 of 5), zipfile (3 sites, 1 of 4) — so
the count is 4 rows, small enough to act on and not a wall. It was rejected anyway, for a
better reason than volume: **the signal is that a word appears somewhere in the test
corpus, which is a grep standing in for a drive** — the exact substitution
`core/gates/deterministic_evidence.py` exists to report. "The string 'pax' occurs in
tests/" is not evidence that any guard was driven with a PAX header, and a gate built on it
would report coverage this repo does not have. So the count is recorded, the prototype is
not shipped, and the lane is graded.

WHAT THIS TEST CAN HONESTLY ASSERT: that the fixture is a genuine instance — a guard whose
declared caps are all correctly enforced, and a channel that carries bytes past every one of
them — and that inputs derived from the rule list cannot reach it. Not that a grader catches
it; stubbing a grader would only test the stub.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

LANE_ID = "a-channel-outside-the-accounting"
SEAT = "Untrusted input and abuse limits"

#: The guard's declared dimensions. These are exactly what a rule-derived test list covers.
MAX_MEMBER_BYTES = 100
MAX_TOTAL_BYTES = 250
MAX_MEMBERS = 3


def _members(blob: str) -> list[tuple[str, str]]:
    """The parser, standing in for `tarfile`.

    A metadata header is consumed and EXPANDED INTERNALLY, and only regular members are
    yielded. That is the whole mechanism: the caller is never shown the header, so no
    accounting the caller writes can count it.
    """
    out: list[tuple[str, str]] = []
    for chunk in blob.split("|"):
        if not chunk:
            continue
        kind, _, payload = chunk.partition(":")
        if kind == "meta":
            # Consumed here. Never yielded. `tarfile` does this with PAX and GNU long-name.
            continue
        out.append((kind, payload))
    return out


def _guard(blob: str) -> bool:
    """Correctly enforces every cap it declares, over the members it is shown."""
    members = _members(blob)
    if len(members) > MAX_MEMBERS:
        return False
    total = 0
    for kind, payload in members:
        if kind != "file":
            return False
        if len(payload) > MAX_MEMBER_BYTES:
            return False
        total += len(payload)
    return total <= MAX_TOTAL_BYTES


#: THE TEN-STYLE CASES: each derived from one declared limit, and each correctly refused.
RULE_DERIVED_REJECTS = [
    "file:" + "x" * (MAX_MEMBER_BYTES + 1),  # over the per-member cap
    "|".join(["file:" + "x" * 90] * 3),  # summing past the total cap
    "|".join(["file:x"] * (MAX_MEMBERS + 1)),  # more members than the cap
    "dir:whatever",  # wrong member type
]

#: THE CHANNEL OUTSIDE THE ACCOUNTING. One tiny regular member, and a metadata header
#: carrying far more bytes than the total cap allows. The guard is shown one 4-byte file.
PAX_SHAPED = "meta:" + "P" * 5000 + "|file:tiny"


def _lane() -> dict:
    data = yaml.safe_load(
        (REPO_ROOT / "canonical" / "review_lanes.yml").read_text(encoding="utf-8")
    )
    return next(lane for lane in data["lanes"] if lane["id"] == LANE_ID)


def test_every_input_derived_from_the_declared_caps_is_refused():
    """THE GUARD IS NOT BROKEN, and this is why ten real tests reported it safe.

    Each of these exceeds one stated dimension and each is correctly refused. A reviewer who
    enumerates the artifact's rules and tries to exceed every one gets ten green results and
    a true statement: the caps are enforced.
    """
    for blob in RULE_DERIVED_REJECTS:
        assert _guard(blob) is False, blob[:40]

    # And a well-formed archive is accepted, so the guard is not simply refusing everything.
    assert _guard("file:small|file:also-small") is True


def test_the_channel_outside_the_accounting_passes_every_cap():
    """THE FINDING. 5000 bytes ride through a guard whose total cap is 250, and no declared
    limit is violated -- because the bytes are never in a member the guard is shown."""
    assert len(PAX_SHAPED) > MAX_TOTAL_BYTES * 10
    assert _guard(PAX_SHAPED) is True, "the fixture must PASS the guard, or it is not the shape"

    # The tell: the accounting sees one tiny member, and that is all it can ever see.
    shown = _members(PAX_SHAPED)
    assert shown == [("file", "tiny")], shown
    counted = sum(len(payload) for _, payload in shown)
    assert counted == 4, counted
    assert counted < len(PAX_SHAPED) / 1000, (
        "the gap between bytes consumed and bytes counted is the defect; if they were close"
        " the accounting would be roughly right and this would be a different lane"
    )


def test_the_rule_list_cannot_reach_it():
    """WHY THE FRAME MATTERS, asserted rather than asserted-about.

    Every rule-derived case is refused; the capability-derived case is admitted. So no amount
    of enumerating the guard's stated dimensions produces the input that finds this -- which
    is the concrete correction: derive adversarial inputs from the PARSER's capability
    surface, not the guard's rule list.
    """
    assert all(_guard(blob) is False for blob in RULE_DERIVED_REJECTS)
    assert _guard(PAX_SHAPED) is True

    # And the channel is not a member type the guard could simply add to its allow-list:
    # it never appears in what the parser yields at all.
    assert not any(kind == "meta" for kind, _ in _members(PAX_SHAPED))


def test_the_lane_is_registered_and_is_not_the_falsifier():
    lane = _lane()
    assert lane["seat"] == SEAT, lane["seat"]
    assert lane["eval"] == "tests/evals/" + Path(__file__).name
    assert lane["question"].strip().endswith("?"), lane["question"]

    data = yaml.safe_load(
        (REPO_ROOT / "canonical" / "review_lanes.yml").read_text(encoding="utf-8")
    )
    falsifier = next(lane for lane in data["lanes"] if lane["id"] == "a-test-that-cannot-fail")
    assert falsifier["seat"] != SEAT, (
        "these are different questions: the Falsifier asks whether a green test CAN go red,"
        " and every one of the ten archive tests could -- they passed because the guard"
        " really does enforce its caps"
    )

    measurement = " ".join(str(lane["measurement"]).split())
    assert "grep" in measurement.lower(), (
        "the reason the prototype was rejected is that its signal is a grep standing in for"
        " a drive, not that it found too much -- and that reason is the one worth recording"
    )
    assert "4 format" in measurement or "4 formats" in measurement, measurement
