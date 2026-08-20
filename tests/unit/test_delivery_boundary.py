"""WO-VERIFY-GRADES-DELIVERY task 1: record the boundary, do not search for it.

Verify has located a WO's work by grepping history for its uuid or title. That
fails for a squash merge, a reworded title, unpushed work, a commit naming the WO
by its human tag, or a non-git target — and none of those mean nothing was
delivered. Observed live on 758fbedd: "no commits found referencing 758fbedd",
for work that was merged and green on three platforms.

Recording ``start_commit`` at start makes the change set ``start_commit..HEAD``,
which needs no message convention and survives every case above.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.delivery_boundary import (
    boundary_commit_range,
    read_delivery_boundary,
    record_delivery_boundary,
)


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "state" / "studio.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(path)
    return path


def _git_repo(root: Path) -> tuple[Path, str]:
    """A real one-commit repo; returns (root, head_sha)."""
    root.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@e",
    }

    def git(*args: str) -> str:
        out = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=30,
        )
        assert out.returncode == 0, f"git {args}: {out.stderr}"
        return out.stdout.strip()

    git("init", "-q")
    (root / "a.txt").write_text("1", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "first")
    return root, git("rev-parse", "HEAD")


# ── Recording ──────────────────────────────────────────────────────────────────


def test_the_start_commit_is_recorded_and_readable(db, tmp_path):
    repo, head = _git_repo(tmp_path / "repo")
    wo_id = str(uuid.uuid4())

    boundary = record_delivery_boundary(wo_id, repo_root=repo, db_path=db)
    assert boundary["start_commit"] == head
    assert boundary["recorded"] is True

    read_back = read_delivery_boundary(wo_id, db_path=db)
    assert read_back is not None
    assert read_back["start_commit"] == head
    assert read_back["started_at"]


def test_the_range_needs_no_commit_message_convention(db, tmp_path):
    """The whole point: the locator is the recorded sha, not a grep for the uuid."""
    repo, head = _git_repo(tmp_path / "repo")
    wo_id = str(uuid.uuid4())
    record_delivery_boundary(wo_id, repo_root=repo, db_path=db)

    expr, reason = boundary_commit_range(wo_id, db_path=db)
    assert reason is None
    assert expr == f"{head}..HEAD"
    # Nothing in the range refers to the work order at all.
    assert wo_id not in expr


# ── The cases that broke the grep ──────────────────────────────────────────────


def test_a_non_git_project_records_absence_with_a_reason(db, tmp_path):
    """A boundary that exists with start_commit=None ("no git here") is a
    different fact from no boundary at all ("we never looked")."""
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    wo_id = str(uuid.uuid4())

    boundary = record_delivery_boundary(wo_id, repo_root=not_a_repo, db_path=db)
    assert boundary["start_commit"] is None
    assert boundary["start_commit_reason"], "absence must be recorded WITH its reason"

    expr, reason = boundary_commit_range(wo_id, db_path=db)
    assert expr is None
    assert reason and "no commit range" in reason


def test_no_boundary_at_all_is_distinguishable_from_a_recorded_absence(db):
    """A WO that started before boundaries were stamped must not look like a
    non-git project — the first says fall back to the old locator, the second
    says this repo has no commits to range over."""
    assert read_delivery_boundary(str(uuid.uuid4()), db_path=db) is None

    expr, reason = boundary_commit_range(str(uuid.uuid4()), db_path=db)
    assert expr is None
    assert reason and "no delivery boundary recorded" in reason


def test_git_unavailable_does_not_prevent_recording(db, tmp_path):
    """Refusing to start work over a bookkeeping failure would be a worse defect
    than the one this fixes."""
    wo_id = str(uuid.uuid4())
    with patch("subprocess.run", side_effect=FileNotFoundError("git")):
        boundary = record_delivery_boundary(wo_id, repo_root=tmp_path, db_path=db)
    assert boundary["start_commit"] is None
    assert boundary["start_commit_reason"] == "git not installed"
    assert boundary["recorded"] is True, "the absence itself is still recorded"


def test_a_failed_artifact_write_is_reported_not_raised(db, tmp_path):
    repo, _head = _git_repo(tmp_path / "repo")
    wo_id = str(uuid.uuid4())
    with patch(
        "core.work_orders.artifacts.set_wo_artifact", side_effect=RuntimeError("db exploded")
    ):
        boundary = record_delivery_boundary(wo_id, repo_root=repo, db_path=db)
    assert boundary["recorded"] is False
    assert "db exploded" in boundary["record_error"]
    assert boundary["start_commit"], "the sha was still read even though storing failed"


def test_a_corrupt_boundary_reads_as_absent_rather_than_raising(db, tmp_path):
    wo_id = str(uuid.uuid4())
    from core.work_orders.artifacts import set_wo_artifact

    set_wo_artifact(
        wo_id,
        "report",
        "not json at all",
        instance_key="delivery_boundary",
        db_path=db,
        generator="test",
    )
    assert read_delivery_boundary(wo_id, db_path=db) is None
    expr, reason = boundary_commit_range(wo_id, db_path=db)
    assert expr is None and reason


# ── Wired into start ───────────────────────────────────────────────────────────


def test_start_work_order_stamps_the_boundary(db, tmp_path):
    """Driven through the real start path — a boundary recorded only by a direct
    call to the helper would leave the production flow unpinned."""
    from core.work_orders.start_main import start_work_order

    repo, head = _git_repo(tmp_path / "repo")
    project_id, wo_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = "2026-08-20T00:00:00+00:00"

    import sqlite3

    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at, project_path)"
        " VALUES (?,?,?,?,?,?,?)",
        (project_id, "P", "", "active", now, now, str(repo)),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at) VALUES (?,?,NULL,'WO','d','infrastructure','created',?,?)",
        (wo_id, project_id, now, now),
    )
    conn.commit()
    conn.close()

    from unittest.mock import MagicMock

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db
    fake_paths.dream_studio_home = tmp_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        result = start_work_order(
            work_order_id=wo_id,
            source_root=tmp_path,
            dream_studio_home=tmp_path,
            planning_root=tmp_path / "planning",
            accept_no_brief=True,
        )
    assert result.get("ok") is True, result

    boundary = read_delivery_boundary(wo_id, db_path=db)
    assert boundary is not None, "start must stamp the boundary"
    assert boundary["start_commit"] == head, (
        "the boundary must be stamped against the WO's TARGET repo, not against "
        "whatever directory DS is running from"
    )


def test_the_boundary_payload_is_json_and_self_describing(db, tmp_path):
    """Stored under the existing multi-instance `report` kind — no new table, no
    migration. Readable without this module, so a future reader is not locked in."""
    repo, head = _git_repo(tmp_path / "repo")
    wo_id = str(uuid.uuid4())
    record_delivery_boundary(wo_id, repo_root=repo, db_path=db)

    from core.work_orders.artifacts import get_wo_artifact_envelope

    raw, envelope = get_wo_artifact_envelope(
        wo_id, "report", instance_key="delivery_boundary", db_path=db
    )
    assert raw is not None
    payload = json.loads(raw)
    assert payload["work_order_id"] == wo_id
    assert payload["start_commit"] == head
    assert payload["repo_root"] == str(repo)
    assert envelope, "the boundary carries provenance like every other gate artifact"


def test_start_reports_the_boundary_it_stamped(db, tmp_path):
    """A boundary recorded where nobody can see it is the
    engine-key-with-no-reader shape this milestone keeps finding."""
    from unittest.mock import MagicMock

    from core.work_orders.start_main import start_work_order

    repo, head = _git_repo(tmp_path / "repo")
    project_id, wo_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = "2026-08-20T00:00:00+00:00"

    import sqlite3

    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at, project_path)"
        " VALUES (?,?,?,?,?,?,?)",
        (project_id, "P", "", "active", now, now, str(repo)),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at) VALUES (?,?,NULL,'WO','d','infrastructure','created',?,?)",
        (wo_id, project_id, now, now),
    )
    conn.commit()
    conn.close()

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db
    fake_paths.dream_studio_home = tmp_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        result = start_work_order(
            work_order_id=wo_id,
            source_root=tmp_path,
            dream_studio_home=tmp_path,
            planning_root=tmp_path / "planning",
            accept_no_brief=True,
        )
    assert result["delivery_boundary"]["start_commit"] == head
    assert result["delivery_boundary"]["recorded"] is True
    # A clean stamp is quiet — the note exists for the failure case.
    assert "delivery_boundary_note" not in result


def test_start_says_so_when_no_boundary_could_be_stamped(db, tmp_path):
    """The case that matters most: verify will silently fall back to the uuid grep,
    so the operator has to be told why."""
    from unittest.mock import MagicMock

    from core.work_orders.start_main import start_work_order

    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    project_id, wo_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = "2026-08-20T00:00:00+00:00"

    import sqlite3

    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at, project_path)"
        " VALUES (?,?,?,?,?,?,?)",
        (project_id, "P", "", "active", now, now, str(plain)),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at) VALUES (?,?,NULL,'WO','d','infrastructure','created',?,?)",
        (wo_id, project_id, now, now),
    )
    conn.commit()
    conn.close()

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db
    fake_paths.dream_studio_home = tmp_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        result = start_work_order(
            work_order_id=wo_id,
            source_root=tmp_path,
            dream_studio_home=tmp_path,
            planning_root=tmp_path / "planning",
            accept_no_brief=True,
        )
    assert result["delivery_boundary"]["start_commit"] is None
    note = result.get("delivery_boundary_note") or ""
    assert "no start commit was stamped" in note
    assert "commit-message search" in note, "the operator must learn what verify will do instead"
