"""Review lane ``a-produced-value-with-no-reader`` — the Interpreter.

THE FINDING, from a review pass on another project. A fetch hook returned ``{get,
isLoading, stateById}``. Both views destructured only ``get``. So ``isLoading`` and
``stateById`` had no production consumer at all, and a FAILED FETCH rendered the
all-``no_data`` placeholder — a hollow radar chart asserting "measured, nothing found"
when the truth was "the request failed".

WHY EVERY EXISTING SEAT MISSED IT. The Warden compares two predicates and here there is
only one site, because the consumer does not exist. The Machinist asks about runtime and
scale; the hook was fine. The Archivist asks whether the record names the mechanism; it
did. The Surveyor asks about distance from base. The Herald asks whether a caller-visible
CHANGE was enumerated — and nothing changed: the value was never consumed in the first
place.

The finder's own diagnosis names the gap exactly: *"I verified the hook's state
transitions by mutation and stopped at the hook boundary instead of following the values to
the pixels."* Verifying a mechanism at its own boundary and calling it verified is the
failure, and no seat asked the terminus question — does this value reach a reader, and
what does it say there?

THE PART THAT MAKES IT DANGEROUS RATHER THAN UNTIDY, and the part this lane grades: the
default that speaks in the value's place MAKES A POSITIVE CLAIM. ``no_data`` reads as
"measured, and there was nothing" — indistinguishable from a real measurement of nothing.
An absent consumer whose default said "unknown" would be a bug; one whose default asserts
a measurement is the compared-nothing-reported-clean family, which this repo keeps
producing: ``record_gate_bypass`` was unreachable because a filter read ``status`` on
dicts carrying ``freshness_status`` — 350 recorded bypasses, zero for docs-drift (WO
48bd8ab3, found 2026-09-09).

WHY THIS IS AN EVAL AND NOT A DETECTOR — MEASURED, NOT ASSUMED. A prototype collected
every string key returned in a dict literal across ``git ls-files '*.py'`` and subtracted
every key read anywhere as a subscript, ``.get()``/``.pop()``/``.setdefault()`` argument,
or ``in`` test: **2108 distinct keys produced, 588 never read in-tree, spread across 198
files.** Sampling them showed why the number is a wall rather than a finding — most are
API response fields consumed by the dashboard, or keys serialised to JSON for a reader
outside Python entirely. A consumer in another language is invisible to that analysis,
which is precisely the shape of the original instance: a React view reading a hook. 588
findings is a gate someone switches off, so the lane is graded against a fixture instead.

THE FIXTURE IS PYTHON, THE ORIGINAL WAS TYPESCRIPT, and that is deliberate: the shape is
language-independent and a fixture the test can actually parse is worth more than one that
matches the incident's syntax.

WHAT THIS TEST CAN HONESTLY ASSERT: that the fixture is a genuine instance — a producer
emitting a field, no consumer reading it, and a default making a positive claim — and that
the lane is registered to the seat that owns the question. Not that a grader catches it;
stubbing a grader would only test the stub.
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

LANE_ID = "a-produced-value-with-no-reader"
SEAT = "The Interpreter"

#: THE PRODUCER. Three fields, each honestly computed.
PRODUCER = """
def use_agent_health(client):
    state = {}
    loading = True
    try:
        for agent_id, reading in client.fetch_all().items():
            state[agent_id] = reading
        loading = False
    except FetchError:
        loading = False
        state = {}
    return {
        "get": lambda agent_id: state.get(agent_id),
        "isLoading": loading,
        "stateById": state,
    }
"""

#: THE CONSUMER. Destructures one field of three, and its fallback ASSERTS A MEASUREMENT.
CONSUMER = """
def render_radar(hook):
    get = hook["get"]
    spokes = []
    for axis in AXES:
        reading = get(axis)
        if reading is None:
            # Reads as "we measured this axis and found nothing" -- not as "we do not know".
            spokes.append({"axis": axis, "status": "no_data", "value": 0.0})
        else:
            spokes.append({"axis": axis, "status": reading.status, "value": reading.value})
    return spokes
"""


def _lane() -> dict:
    data = yaml.safe_load(
        (REPO_ROOT / "canonical" / "review_lanes.yml").read_text(encoding="utf-8")
    )
    return next(lane for lane in data["lanes"] if lane["id"] == LANE_ID)


def _returned_keys(source: str) -> set[str]:
    tree = ast.parse(source)
    keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            for key in node.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
    return keys


def _read_keys(source: str) -> set[str]:
    tree = ast.parse(source)
    keys: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            keys.add(node.slice.value)
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "get":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    keys.add(arg.value)
    return keys


def test_the_fixture_produces_a_field_no_consumer_reads():
    """The instance, reproduced rather than described: three fields out, one read."""
    produced = _returned_keys(PRODUCER)
    read = _read_keys(CONSUMER)

    assert produced == {"get", "isLoading", "stateById"}, produced
    assert "get" in read, "the consumer must read something, or the fixture proves nothing"

    orphans = produced - read
    assert orphans == {"isLoading", "stateById"}, orphans


def test_the_default_that_speaks_instead_makes_a_positive_claim():
    """THE HARM, and the half a reviewer has to be pointed at.

    A missing consumer whose fallback said "unknown" is untidy. One whose fallback asserts
    ``no_data`` — measured, nothing found — is indistinguishable from a real measurement of
    nothing, so a failed fetch and an empty result render identically. That is what makes
    this lane worth a seat rather than a lint rule.
    """
    tree = ast.parse(CONSUMER)
    statuses = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "no_data" in statuses, "the fixture's fallback must assert a measurement"
    assert not {"unknown", "unavailable", "error"} & statuses, (
        "the fixture must NOT offer an honest absence status — its absence is the finding,"
        " and including one would make the fixture a different, milder shape"
    )

    # And the fallback is reached exactly when the unread field would have said otherwise.
    assert "isLoading" not in _read_keys(CONSUMER)


def test_the_lane_is_registered_to_the_seat_that_owns_the_question():
    lane = _lane()
    assert lane["seat"] == SEAT, lane["seat"]
    assert lane["eval"] == "tests/evals/" + Path(__file__).name
    # `.strip()` because a YAML `>` folded scalar keeps a trailing newline. The
    # question still has to END in one, which is the actual contract -- a lane whose
    # "question" is a statement is a description, not something a reviewer answers.
    assert lane["question"].strip().endswith("?"), lane["question"]
    for field in ("signature", "precedent", "measurement"):
        assert len(lane[field]) >= 40, field


def test_the_registered_measurement_states_why_a_detector_was_rejected():
    """A lane claiming "not detectable" owes its working. The prototype's numbers are the
    reason this is graded, so they belong in the registry where a later author will read
    them before rebuilding the same wall."""
    measurement = " ".join(str(_lane()["measurement"]).split())
    assert "588" in measurement, "the prototype's finding count must be recorded"
    assert "2108" in measurement or "198" in measurement, measurement
    assert "dashboard" in measurement or "another language" in measurement, (
        "the reason the count is a wall -- consumers outside Python are invisible -- is the"
        " load-bearing half of the measurement"
    )
