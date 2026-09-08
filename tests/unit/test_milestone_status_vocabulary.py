"""The milestone status vocabulary has one definition, and every copy agrees with it.

WO fc2916a4. ``business_milestones.status`` holds ``complete`` (45 rows), ``pending`` (43)
and ``deleted`` (2) -- measured on the live authority 2026-09-08 -- while
``core/work_orders/milestones_classify.py`` tested membership of
``{"complete", "completed"}``. ``completed`` is a value the column has never held.

Same trap as ``business_tasks.status`` one table over: ``completed`` reads correctly, it IS
correct in other tables, and it is wrong here. A phantom member is harmless until someone
writes it, at which point every reader omitting it silently disagrees -- and the task
equivalent made a diagnostic report every work order 0-done.

The copies are checked by RUNNING the writers, not by reading them: the projection is
driven and its row inspected, because a source-text assertion would pass against a
projection whose SQL had changed underneath it.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from core.milestones.status import (
    MILESTONE_ABANDONED_STATUSES,
    MILESTONE_COMPLETE,
    MILESTONE_DONE_STATUSES,
    MILESTONE_STATUSES,
    is_complete,
    is_open,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def authority(tmp_path: Path) -> sqlite3.Connection:
    """A real database built by the real migration chain, never a fixture DDL."""
    from core.config.sqlite_bootstrap import bootstrap_database

    db_path = tmp_path / "studio.db"
    bootstrap_database(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _milestone_event(event_type: str, milestone_id: str, **payload) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_timestamp": "2026-09-08T12:00:00+00:00",
        "trace": {},
        "payload": {"milestone_id": milestone_id, **payload},
        "correlation_id": None,
        "project_id": "proj-vocab",
        "milestone_id": milestone_id,
        "_source": "business",
    }


def test_the_copies_agree(authority):
    """Every status the REAL projection writes is one this vocabulary names.

    This is the symptom check for WO fc2916a4: it failed while the vocabulary had no single
    definition and the classifier tested a phantom member.
    """
    from core.projections.milestone_projection import MilestoneProjection

    projection = MilestoneProjection()
    projection.setup_tables(authority)

    written: set[str] = set()
    for event_type, mid in (
        ("milestone.created", "ms-created"),
        ("milestone.completed", "ms-complete"),
        ("milestone.deleted", "ms-deleted"),
    ):
        if event_type != "milestone.created":
            projection.handle(
                _milestone_event("milestone.created", mid, title="T", project_id="proj-vocab"),
                authority,
            )
        projection.handle(_milestone_event(event_type, mid, title="T"), authority)
        row = authority.execute(
            "SELECT status FROM business_milestones WHERE milestone_id = ?", (mid,)
        ).fetchone()
        assert row is not None, f"{event_type} materialized no row"
        written.add(str(row["status"]))

    unknown = sorted(written - set(MILESTONE_STATUSES))
    assert not unknown, (
        f"the projection writes {unknown}, which core/milestones/status.py does not name."
        " A status the vocabulary omits is one every reader switching on it disagrees about."
    )
    assert MILESTONE_COMPLETE in written, "no event produced a completed milestone"


def test_completed_is_not_in_the_vocabulary():
    """The phantom member, pinned absent so nobody 'restores' it for consistency with
    another table."""
    assert "completed" not in MILESTONE_STATUSES
    assert not is_complete("completed")


def test_the_classifier_no_longer_spells_the_vocabulary_inline():
    source = (REPO_ROOT / "core" / "work_orders" / "milestones_classify.py").read_text(
        encoding="utf-8"
    )
    assert (
        '{"complete", "completed"}' not in source
    ), "the inline literal is back, including the phantom 'completed'"
    assert "_milestone_status_is_complete" in source


def test_the_closer_no_longer_spells_the_status_inline():
    source = (REPO_ROOT / "core" / "milestones" / "close.py").read_text(encoding="utf-8")
    assert "MILESTONE_COMPLETE" in source, "close.py stopped importing the vocabulary"


def test_an_unknown_status_counts_as_open_not_complete():
    """The safe direction: absorbing an unrecognised value into 'complete' is what lets a
    milestone close over work nobody did."""
    assert is_open("some_status_added_later")
    assert not is_complete("some_status_added_later")
    assert is_open(None)
    assert not is_complete(None)


def test_abandoned_is_neither_complete_nor_open():
    for status in MILESTONE_ABANDONED_STATUSES:
        assert not is_complete(status)
        assert not is_open(status)


def test_matching_is_case_insensitive():
    """The classifier lowercases before comparing; a caller that forgot would otherwise get
    a silent False."""
    assert is_complete("Complete")
    assert is_complete("  COMPLETE  ")


def test_the_step_vocabulary_is_deliberately_left_alone():
    """`_first_pending_step` tests STEP status, a different domain that happens to share a
    word. Unifying two vocabularies because they overlap is how the wrong one gets applied,
    so this pins the separation rather than leaving it to memory."""
    source = (REPO_ROOT / "core" / "work_orders" / "milestones_classify.py").read_text(
        encoding="utf-8"
    )
    assert '{"complete", "completed", "skipped"}' in source, (
        "the step vocabulary was folded into the milestone one; steps have their own"
        " statuses and 'skipped' is not a milestone status"
    )
    assert "skipped" not in MILESTONE_STATUSES


def test_done_statuses_are_a_subset_of_all_statuses():
    assert set(MILESTONE_DONE_STATUSES) <= set(MILESTONE_STATUSES)
    assert set(MILESTONE_ABANDONED_STATUSES) <= set(MILESTONE_STATUSES)
