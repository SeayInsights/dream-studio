"""Lesson escalation reads a directory git actually ships.

``_known_skills`` pointed at ``<repo>/skills``, which .gitignore excludes as a generated
projection. Measured on the operator's checkout 2026-09-18: that directory held exactly one
entry, ``__pycache__``, so the known-skill set was ``{"__pycache__"}``, no lesson could match
a skill name, and ``get_escalation_candidates`` returned ``[]`` on every call -- including
from ``runtime/hooks/meta/on-meta-review.py`` and ``control/review/engine.py``, which are the
surfaces that were supposed to say a skill had accumulated enough lessons to be worth reading.

A committed module depending on a path git does not ship is the gitignore-phantom shape. That
gate is diff-scoped and this file had not been touched since it was written.
"""

from __future__ import annotations

from pathlib import Path

import core.event_store.studio_db as studio_db
from core.learning.lesson_threshold import (
    _known_skills,
    get_escalation_candidates,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_known_skills_reads_the_tracked_canonical_tree():
    names = _known_skills()
    assert "quality" in names, "pack names are missing"
    assert "debug" in names, "mode names are missing, and a lesson's source records the mode"
    assert len(names) > 50, f"only {len(names)} names resolved, which is the empty-projection shape"


def test_known_skills_excludes_build_artifacts():
    """The old read returned {'__pycache__'} and nothing else."""
    names = _known_skills()
    assert "__pycache__" not in names
    assert not any(n.startswith(("_", ".")) for n in names)


def test_the_tracked_source_is_what_git_ships():
    """The directory this reads from is committed; the one it used to read from is not."""
    assert (REPO_ROOT / "canonical" / "skills").is_dir()


def _fake_pending(monkeypatch, rows):
    monkeypatch.setattr(studio_db, "get_pending_lessons", lambda **kwargs: rows)


def test_a_declared_skill_id_is_used_verbatim(monkeypatch):
    """raw_lessons carries skill_id; guessing from prose when it is set is needless."""
    _fake_pending(
        monkeypatch,
        [
            {"lesson_id": f"L-{i}", "source": "unrelated prose", "skill_id": "debug"}
            for i in range(3)
        ],
    )
    candidates = get_escalation_candidates(threshold=3)
    assert [c["skill"] for c in candidates] == ["debug"]
    assert candidates[0]["lesson_count"] == 3


def test_the_source_field_still_resolves_when_skill_id_is_absent(monkeypatch):
    _fake_pending(
        monkeypatch,
        [{"lesson_id": f"L-{i}", "source": "review", "skill_id": None} for i in range(4)],
    )
    candidates = get_escalation_candidates(threshold=3)
    assert [c["skill"] for c in candidates] == ["review"]


def test_below_threshold_does_not_escalate(monkeypatch):
    _fake_pending(monkeypatch, [{"lesson_id": "L-1", "source": "review", "skill_id": "review"}])
    assert get_escalation_candidates(threshold=3) == []


def test_an_unreadable_authority_escalates_nothing_rather_than_raising(monkeypatch):
    def _boom(**kwargs):
        raise RuntimeError("authority unavailable")

    monkeypatch.setattr(studio_db, "get_pending_lessons", _boom)
    assert get_escalation_candidates() == []
