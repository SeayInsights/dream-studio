"""WO 726fe42a: the skill telemetry path emitted the specifier, not the skill id.

``core/telemetry/emitters_activity.py`` derived ``skill_id`` straight from the
captured ``skill["name"]``, which the hook records in SPECIFIER form
(``project:scope``). That value was copied verbatim into the canonical envelope's
``trace.skill_id`` by ``execution_spine.py``, where ``spool/ingestor.py`` rejected
it as ``malformed_skill_id`` — and into ``execution_events.skill_id``, which held
673 specifier-form rows and zero canonical ones, so it could not be joined against
the CLI emitter's ``ds-<pack>`` values.

The strictness on the consumer side is deliberate — pinned by
``tests/unit/test_skill_invoke.py::test_ingestor_rejects_skill_id_without_ds_prefix``
— so the producer is the side that was wrong.

The parity test below imports the ingestor's OWN regex rather than restating the
pattern. A test that restates a guard passes the day it is written and then drifts
silently when the guard moves; importing the consumer's guard is what makes this a
parity test rather than a copy of one.
"""

from __future__ import annotations

import pytest

from core.telemetry.emitters_activity import canonical_skill_id

# Every ds pack specifier shape the router actually emits, and what it must become.
DS_PACK_CASES = [
    ("project:scope", "ds-project"),
    ("project:resume", "ds-project"),
    ("core:think", "ds-core"),
    ("core:plan", "ds-core"),
    ("workorder:start", "ds-workorder"),
    ("workorder:close", "ds-workorder"),
    ("milestone:close", "ds-milestone"),
    ("quality:coach", "ds-quality"),
    ("setup:status", "ds-setup"),
    # already carrying the prefix, with and without a mode
    ("ds-project:resume", "ds-project"),
    ("ds-core", "ds-core"),
]

# Names that are not ds packs at all. Left alone deliberately: what a non-ds skill
# should carry is an open operator decision recorded on WO 726fe42a, and inventing
# a "ds-artifact-design" pack would fabricate a pack that does not exist.
NON_DS_NAMES = ["artifact-design", "claude-api", "unknown"]


@pytest.mark.parametrize("specifier,expected", DS_PACK_CASES)
def test_ds_pack_specifier_becomes_canonical_skill_id(specifier: str, expected: str) -> None:
    assert canonical_skill_id(specifier) == expected


def test_emitted_skill_id_passes_the_real_ingestor_regex() -> None:
    """Producer-consumer parity, checked against the consumer's own guard."""
    from spool.ingestor import _SKILL_ID_RE

    for specifier, _ in DS_PACK_CASES:
        produced = canonical_skill_id(specifier)
        assert _SKILL_ID_RE.match(
            produced
        ), f"{specifier!r} produced {produced!r}, which the ingestor would reject"


@pytest.mark.parametrize("name", NON_DS_NAMES)
def test_non_ds_skill_name_is_left_alone_pending_the_operator_decision(name: str) -> None:
    """Pins the KNOWN remaining gap so it stays visible instead of silent.

    These still will not satisfy the ingestor. That is the open question on the
    work order, not an oversight — this test records the gap as a fact so it
    cannot be mistaken for finished work.
    """
    from spool.ingestor import _SKILL_ID_RE

    assert canonical_skill_id(name) == name
    assert not _SKILL_ID_RE.match(name)


def test_blank_name_falls_back_without_raising() -> None:
    """An empty capture must not explode the telemetry path."""
    assert canonical_skill_id("") == "unknown"
    assert canonical_skill_id(None) == "unknown"
