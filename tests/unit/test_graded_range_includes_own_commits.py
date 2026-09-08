"""A narrowed range with no ownership evidence must not claim to be the work order's own.

WO d33f9f95. WO 0a7abdfe's review refused to grade its diff on 2026-09-07: "the stated
range 52eba5e5..HEAD contains 22 commits, but only three were shown, all belonging to other
work orders, while this work order's own implementing commits sit inside the range and were
omitted; grading the shown slice alone would have reported ten false misses."

THAT SPECIFIC INSTANCE NO LONGER REPRODUCES, and saying so matters: the work order's
ownership record has since grown to 22 commits through task-done calls, and
``attribute_range`` now returns 27 own of 32 for that range. The SHAPE is intact, though,
and it is what these tests pin.

Exclusion is one-sided. A commit is removed only when ANOTHER work order recorded it, and
``mine`` -- this work order's own record -- is the only thing that defends against that. So
a work order with an empty or out-of-range record can defend nothing: every commit a
neighbour claims is removed and it receives whatever is left over, reported in the same
words as ownership. Ownership is written AT TASK-DONE, so a work order whose commits landed
before its first task-done is exactly this case.

"Commits this work order recorded" and "commits nobody else claimed" are different facts.
Only one of them supports a verdict about whether the work is present.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from core.work_orders.range_attribution import attribute_range


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repo with three commits, so ranges are real ranges."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "T")
    for name in ("a", "b", "c"):
        (root / f"{name}.txt").write_text(name, encoding="utf-8")
        _git(root, "add", ".")
        _git(root, "commit", "-q", "-m", f"commit {name}")
    return root


@pytest.fixture
def db(tmp_path: Path) -> Path:
    from core.config.sqlite_bootstrap import bootstrap_database

    path = tmp_path / "studio.db"
    bootstrap_database(path)
    return path


def _record_ownership(db_path: Path, work_order_id: str, shas: list[str]) -> None:
    """Write an ownership artifact the way read_owned_commits reads it."""
    import json

    from core.work_orders.artifacts import set_wo_artifact
    from core.work_orders.range_attribution import OWNERSHIP_KEY, OWNERSHIP_KIND

    # The kind, the instance key and the payload key are all read from the module rather
    # than spelled here. The first version of this helper invented all three -- kind
    # "impact_affirmation" and a payload keyed by OWNERSHIP_KEY instead of "commits" --
    # so nothing was ever recorded, the excluded map came back empty, and four assertions failed
    # for a reason that had nothing to do with the code under test. A fixture invented to
    # match the code is how a shape assumption survives.
    set_wo_artifact(
        work_order_id,
        OWNERSHIP_KIND,
        json.dumps({"commits": shas}),
        instance_key=OWNERSHIP_KEY,
        db_path=db_path,
    )


def _shas(repo: Path) -> list[str]:
    return _git(repo, "log", "--format=%H").splitlines()


def test_a_range_missing_its_own_commits_fails_loudly(repo, db):
    """The symptom check for WO d33f9f95.

    A neighbour claims a commit in range; this work order recorded nothing. Before the fix
    the note read "Range narrowed to this work order's commits" over a set that carried no
    claim of its own at all.
    """
    shas = _shas(repo)
    _record_ownership(db, "wo-neighbour", [shas[0]])

    attribution = attribute_range("wo-mine", f"{shas[2]}..HEAD", repo_root=repo, db_path=db)

    assert attribution.own, "the range should still yield the unclaimed commits"
    assert (
        attribution.own_evidence is False
    ), "this work order recorded no commit in range, so nothing here carries its claim"
    assert attribution.unevidenced is True
    assert "NOT narrowed to this work order's own commits" in attribution.note
    assert "no OTHER work order claimed" in attribution.note
    assert "weaker basis" in attribution.note, (
        "the note must say the basis is weaker, not merely describe the arithmetic --"
        " grading it can report a miss for work that is present but attributed elsewhere"
    )


def test_a_range_with_its_own_commits_reports_ownership(repo, db):
    """The control. Without it the fix would pass equally against a note that ALWAYS warns,
    which is the always-red counterpart and just as useless."""
    shas = _shas(repo)
    _record_ownership(db, "wo-mine", [shas[0]])
    _record_ownership(db, "wo-neighbour", [shas[1]])

    attribution = attribute_range("wo-mine", f"{shas[2]}..HEAD", repo_root=repo, db_path=db)

    assert attribution.own_evidence is True
    assert attribution.unevidenced is False
    assert "Range narrowed to this work order's commits" in attribution.note


def test_an_unnarrowed_range_is_not_reported_as_unevidenced(repo, db):
    """Nothing was excluded, so there is no narrowing to be suspicious of.

    `unevidenced` must mean "narrowed with nothing of its own", not merely "recorded
    nothing" -- otherwise every pre-ownership range would carry a warning about a
    narrowing that never happened.
    """
    shas = _shas(repo)

    attribution = attribute_range("wo-mine", f"{shas[2]}..HEAD", repo_root=repo, db_path=db)

    assert attribution.excluded == {}
    assert attribution.unevidenced is False
    assert "Range NOT narrowed" in attribution.note


def test_its_own_record_still_wins_over_a_neighbours_claim(repo, db):
    """The pre-existing rule, pinned alongside: a commit both sides claim is graded here.

    Dropping it would hide delivered work, and the new evidence flag must not weaken it.
    """
    shas = _shas(repo)
    _record_ownership(db, "wo-mine", [shas[0]])
    _record_ownership(db, "wo-neighbour", [shas[0]])

    attribution = attribute_range("wo-mine", f"{shas[2]}..HEAD", repo_root=repo, db_path=db)

    assert shas[0] in attribution.own
    assert shas[0] not in attribution.excluded
    assert attribution.own_evidence is True


def test_an_empty_range_is_reported_without_a_claim(repo, db):
    attribution = attribute_range("wo-mine", "HEAD..HEAD", repo_root=repo, db_path=db)
    assert attribution.own == []
    assert attribution.note == ""


def test_the_note_names_the_other_work_orders(repo, db):
    """A reader has to know WHERE the removed commits went to judge the narrowing."""
    shas = _shas(repo)
    _record_ownership(db, "wo-neighbour", [shas[0]])

    attribution = attribute_range("wo-mine", f"{shas[2]}..HEAD", repo_root=repo, db_path=db)
    assert "wo-neigh" in attribution.note
