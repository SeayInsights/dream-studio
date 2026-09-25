"""The lesson queue reaches an end state, and a mode exists to take it there.

Before this, ``promote_lesson`` was the last step the queue could take: it set a status and a
target and nothing ever edited a skill. Measured on the operator's authority 2026-09-18: 73
lessons, 40 draft, 21 promoted, 0 applied -- 21 rows marked as headed somewhere that nothing
could distinguish from rows that had arrived, so ``lesson_threshold`` kept re-escalating
skills whose lessons had already been read.

These drive the real writers against a temporary authority rather than hand-building
raw_lessons, so the columns are whatever a bootstrapped database actually has.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.event_store.event_reader import get_lessons
from core.event_store.event_writer_lessons import (
    apply_lesson,
    insert_lesson,
    promote_lesson,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def authority(tmp_path):
    """A fresh authority holding one draft lesson."""
    db = tmp_path / "studio.db"
    assert insert_lesson(
        "L-TERMINUS",
        "debug",
        "a symptom worth remembering",
        lesson="check the encoding before trusting the exit code",
        evidence="observed twice",
        db_path=db,
    )
    return db


def _row(db, lesson_id="L-TERMINUS"):
    return next(r for r in get_lessons(db_path=db) if r["lesson_id"] == lesson_id)


def test_a_lesson_starts_as_a_draft(authority):
    assert _row(authority)["status"] == "draft"


def test_promote_does_not_claim_arrival(authority):
    """Promotion records intent. It is not evidence the skill text changed."""
    promote_lesson("L-TERMINUS", "ds-code-health:debug", db_path=authority)
    row = _row(authority)
    assert row["status"] == "promoted"
    assert row["status"] != "applied"


def test_apply_records_arrival_and_where_it_landed(authority):
    promote_lesson("L-TERMINUS", "ds-code-health:debug", db_path=authority)
    landed = "canonical/skills/code-health/modes/debug/gotchas.yml@abc1234"
    assert apply_lesson("L-TERMINUS", landed, db_path=authority)
    row = _row(authority)
    assert row["status"] == "applied"
    assert row["promoted_to"] == landed
    assert row["reviewed_at"]


def test_applied_lessons_are_filterable(authority):
    """The queue can tell a landed lesson from a pending one, which is the whole point."""
    assert insert_lesson("L-STILL-OPEN", "review", "not yet read", db_path=authority)
    promote_lesson("L-TERMINUS", "ds-code-health:debug", db_path=authority)
    apply_lesson("L-TERMINUS", "gotchas.yml@abc1234", db_path=authority)

    applied = get_lessons(status="applied", db_path=authority)
    drafts = get_lessons(status="draft", db_path=authority)
    assert [r["lesson_id"] for r in applied] == ["L-TERMINUS"]
    assert "L-STILL-OPEN" in [r["lesson_id"] for r in drafts]


def test_apply_is_reachable_from_the_cli():
    """The writer has a caller: `lesson_queue apply <id> --to <ref>`."""
    from interfaces.cli import lesson_queue

    parser = lesson_queue.build_parser()
    args = parser.parse_args(["apply", "L-1", "--to", "gotchas.yml@abc"])
    assert args.func is lesson_queue.cmd_apply
    assert args.to == "gotchas.yml@abc"


def test_groom_mode_is_registered_and_routable():
    packs = yaml.safe_load((REPO_ROOT / "packs.yaml").read_text(encoding="utf-8"))["packs"]
    assert "groom" in packs["code-health"]["modes"]

    card_path = REPO_ROOT / "canonical/skills/code-health/modes/groom/SKILL.md"
    assert card_path.is_file()

    router = (REPO_ROOT / "canonical/skills/code-health/SKILL.md").read_text(encoding="utf-8")
    assert "modes/groom/SKILL.md" in router, "groom is registered but the router cannot reach it"


def test_groom_stops_for_the_operator():
    """A mode that edits the text steering every later session does not self-merge."""
    from core.gates.skill_card import _all_cards

    card = next(c for pack, mode, _, c in _all_cards() if (pack, mode) == ("code-health", "groom"))
    assert card["write_posture"] == "hitl"
