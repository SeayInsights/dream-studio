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
    # WO-BOUNDARY-OPEN-END: this range has NO recorded end, so it runs to a
    # moving HEAD and now says so. Asserting `reason is None` read as though
    # the range were tight when it was open by construction -- measured at
    # 217,524 chars of three other work orders' changes on 3e6cf265.
    assert reason and "no recorded end" in reason
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


# ── Working-tree layer (task 2) ────────────────────────────────────────────────


def _wo_with_boundary(db: Path, repo: Path, boundary: str | None) -> str:
    import sqlite3

    project_id, wo_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = "2026-08-20T00:00:00+00:00"
    desc = f"Module boundary: {boundary}." if boundary else "No boundary declared here"
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
        "  status, created_at, updated_at) VALUES (?,?,NULL,'WO',?,'infrastructure','in_progress',?,?)",
        (wo_id, project_id, desc, now, now),
    )
    conn.commit()
    conn.close()
    return wo_id


def test_uncommitted_work_is_visible(db, tmp_path):
    """Work in progress is still delivered work — grading only committed state is
    why an uncommitted deliverable reads as nothing delivered."""
    from core.work_orders.delivery_boundary import working_tree_changes

    repo, _head = _git_repo(tmp_path / "repo")
    (repo / "core").mkdir()
    (repo / "core" / "thing.py").write_text("x = 1\n", encoding="utf-8")  # untracked
    (repo / "a.txt").write_text("modified\n", encoding="utf-8")  # tracked, dirty

    wo_id = _wo_with_boundary(db, repo, "core/")
    paths, reason = working_tree_changes(wo_id, repo_root=repo, db_path=db)
    assert reason is None
    assert "core/thing.py" in paths, "a brand-new module is exactly what a tracked-only diff misses"
    assert "a.txt" not in paths, "outside the declared boundary"


def test_dirty_files_outside_the_boundary_are_not_attributed(db, tmp_path):
    """The reverse hazard, and worse than the defect it fixes: sweeping in every
    unrelated dirty file would let a WO be certified by work it never did."""
    from core.work_orders.delivery_boundary import working_tree_changes

    repo, _head = _git_repo(tmp_path / "repo")
    (repo / "mine").mkdir()
    (repo / "mine" / "x.py").write_text("1\n", encoding="utf-8")
    (repo / "theirs").mkdir()
    (repo / "theirs" / "y.py").write_text("2\n", encoding="utf-8")

    wo_id = _wo_with_boundary(db, repo, "mine/")
    paths, reason = working_tree_changes(wo_id, repo_root=repo, db_path=db)
    assert reason is None
    assert paths == ["mine/x.py"], f"only the WO's own boundary: {paths}"


def test_no_declared_boundary_attributes_nothing_and_says_why(db, tmp_path):
    """Without a boundary there is no basis for attribution. Returning everything
    would be the certified-by-someone-else's-work failure; returning nothing
    silently would hide it."""
    from core.work_orders.delivery_boundary import working_tree_changes

    repo, _head = _git_repo(tmp_path / "repo")
    (repo / "z.py").write_text("1\n", encoding="utf-8")

    wo_id = _wo_with_boundary(db, repo, None)
    paths, reason = working_tree_changes(wo_id, repo_root=repo, db_path=db)
    assert paths == []
    assert reason and "declares no 'Module boundary:'" in reason


def test_a_clean_tree_is_empty_without_a_reason(db, tmp_path):
    """Nothing uncommitted is a real answer, not a failure to look."""
    from core.work_orders.delivery_boundary import working_tree_changes

    repo, _head = _git_repo(tmp_path / "repo")
    wo_id = _wo_with_boundary(db, repo, "core/")
    paths, reason = working_tree_changes(wo_id, repo_root=repo, db_path=db)
    assert paths == [] and reason is None


def test_git_unavailable_reports_a_reason_rather_than_claiming_clean(db, tmp_path):
    from core.work_orders.delivery_boundary import working_tree_changes

    repo, _head = _git_repo(tmp_path / "repo")
    wo_id = _wo_with_boundary(db, repo, "core/")
    with patch("subprocess.run", side_effect=FileNotFoundError("git")):
        paths, reason = working_tree_changes(wo_id, repo_root=repo, db_path=db)
    assert paths == []
    assert reason == "git not installed", "an unreadable tree must not read as a clean one"


def test_the_boundary_rule_is_the_enforcement_lib_s(db, tmp_path):
    """One boundary rule, one implementation. Two would let the on-edit hook and
    verify disagree about what a WO owns."""
    from core.work_orders import delivery_boundary as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "from runtime.lib.enforcement import boundary_globs" in src
    assert "from runtime.lib.enforcement import path_in_boundary" in src


def test_attribution_fails_closed_where_enforcement_fails_open(db, tmp_path):
    """The same predicate needs opposite defaults on either side of the boundary.

    runtime.lib.enforcement.path_in_boundary returns True for a path it cannot
    resolve — correct for the on-edit hook, whose job is to avoid BLOCKING an edit
    it cannot classify. For attribution that default is inverted: a path we cannot
    place must not be CLAIMED as this WO's delivery, or an unresolvable path
    silently certifies a WO with work it never did.

    Documented here because inheriting the wrong default is invisible: the reused
    helper would simply return more matches, and nothing would look broken.
    """
    from runtime.lib.enforcement import boundary_globs, path_in_boundary

    globs = boundary_globs("Module boundary: mine/.")
    assert globs == ["mine/"]
    # The helper's own behaviour, unchanged: an unplaceable path matches.
    assert path_in_boundary("theirs/y.py", "/definitely/not/here", globs) is True

    # Attribution must not inherit that. A file outside the boundary in a real
    # repo is excluded, and the caller resolves paths before asking.
    from core.work_orders.delivery_boundary import working_tree_changes

    repo, _head = _git_repo(tmp_path / "repo")
    (repo / "mine").mkdir()
    (repo / "mine" / "x.py").write_text("1\n", encoding="utf-8")
    (repo / "theirs").mkdir()
    (repo / "theirs" / "y.py").write_text("2\n", encoding="utf-8")
    wo_id = _wo_with_boundary(db, repo, "mine/")

    paths, reason = working_tree_changes(wo_id, repo_root=repo, db_path=db)
    assert paths == ["mine/x.py"], f"attribution must fail closed: {paths}"
    assert reason is None


# ── Boundary-file fallback (task 3): the layer that needs no VCS ───────────────


def test_boundary_content_is_readable_with_no_git_at_all(db, tmp_path):
    """The layer that makes this foolproof. A non-git target has no range and no
    history to grep, but the boundary files still exist and their content is what
    the WO delivered."""
    from core.work_orders.delivery_boundary import boundary_file_contents

    plain = tmp_path / "no-vcs"
    (plain / "core").mkdir(parents=True)
    (plain / "core" / "thing.py").write_text("def delivered():\n    return 1\n", encoding="utf-8")
    (plain / "unrelated.py").write_text("not mine\n", encoding="utf-8")

    wo_id = _wo_with_boundary(db, plain, "core/")
    text, reason = boundary_file_contents(wo_id, repo_root=plain, db_path=db)
    assert reason is None
    assert "def delivered()" in text
    assert "boundary file core/thing.py" in text
    assert "not mine" not in text, "content outside the boundary is not this WO's delivery"


def test_a_single_file_boundary_reads_that_file(db, tmp_path):
    from core.work_orders.delivery_boundary import boundary_file_contents

    plain = tmp_path / "one"
    (plain / "core").mkdir(parents=True)
    (plain / "core" / "x.py").write_text("MARKER = 1\n", encoding="utf-8")

    wo_id = _wo_with_boundary(db, plain, "core/x.py")
    text, reason = boundary_file_contents(wo_id, repo_root=plain, db_path=db)
    assert reason is None and "MARKER = 1" in text


def test_no_declared_boundary_has_nothing_to_read(db, tmp_path):
    from core.work_orders.delivery_boundary import boundary_file_contents

    plain = tmp_path / "nb"
    plain.mkdir()
    wo_id = _wo_with_boundary(db, plain, None)
    text, reason = boundary_file_contents(wo_id, repo_root=plain, db_path=db)
    assert text == ""
    assert reason and "declares no 'Module boundary:'" in reason


def test_a_missing_boundary_path_is_reported_not_silently_empty(db, tmp_path):
    """A boundary pointing at paths that do not exist is a finding about the WO —
    possibly work that was never done — not an empty read to shrug at."""
    from core.work_orders.delivery_boundary import boundary_file_contents

    plain = tmp_path / "gone"
    plain.mkdir()
    wo_id = _wo_with_boundary(db, plain, "core/never_created.py")
    text, reason = boundary_file_contents(wo_id, repo_root=plain, db_path=db)
    assert text == ""
    assert reason and "exist" in reason
    assert "core/never_created.py" in reason, "name the path that is missing"


def test_truncation_is_reported_as_partial(db, tmp_path):
    """A silently clipped fallback is a partial picture presented as a whole one."""
    from core.work_orders.delivery_boundary import _MAX_FALLBACK_FILES, boundary_file_contents

    plain = tmp_path / "many"
    (plain / "core").mkdir(parents=True)
    for i in range(_MAX_FALLBACK_FILES + 10):
        (plain / "core" / f"f{i}.py").write_text(f"X = {i}\n", encoding="utf-8")

    wo_id = _wo_with_boundary(db, plain, "core/")
    text, reason = boundary_file_contents(wo_id, repo_root=plain, db_path=db)
    assert text, "a truncated read still yields content"
    assert reason and "PARTIAL" in reason


def test_undecodable_bytes_do_not_break_the_read(db, tmp_path):
    """errors='replace' rather than a crash — the same lesson as the codec sweep:
    a reader that dies on odd bytes reports nothing about work that exists."""
    from core.work_orders.delivery_boundary import boundary_file_contents

    plain = tmp_path / "bytes"
    (plain / "core").mkdir(parents=True)
    (plain / "core" / "b.py").write_bytes(b"ok\x8d\xff done\n")

    wo_id = _wo_with_boundary(db, plain, "core/")
    text, reason = boundary_file_contents(wo_id, repo_root=plain, db_path=db)
    assert reason is None
    assert "ok" in text and "done" in text


# ── The locator (task 4): recorded state first, grep as reinforcement ──────────


def test_the_range_diff_is_the_primary_evidence(db, tmp_path):
    """A real commit made after start is found by RANGE, with no mention of the WO
    anywhere in the commit message."""
    from core.work_orders.delivery_boundary import boundary_diff_text, record_delivery_boundary

    repo, _head = _git_repo(tmp_path / "repo")
    wo_id = _wo_with_boundary(db, repo, "core/")
    record_delivery_boundary(wo_id, repo_root=repo, db_path=db)

    # Land work AFTER the boundary, naming the WO nowhere.
    (repo / "core").mkdir()
    (repo / "core" / "feature.py").write_text("def shipped():\n    return 42\n", encoding="utf-8")
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@e",
    }
    for args in (["add", "."], ["commit", "-qm", "totally unrelated subject line"]):
        subprocess.run(
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=30,
        )

    text, note = boundary_diff_text(wo_id, repo_root=repo, db_path=db)
    assert text, f"the range must find the work: note={note}"
    assert "def shipped()" in text
    assert "commit range" in text
    assert wo_id not in text, "found without any reference to the work order at all"


def test_uncommitted_work_appears_when_there_is_no_commit(db, tmp_path):
    from core.work_orders.delivery_boundary import boundary_diff_text, record_delivery_boundary

    repo, _head = _git_repo(tmp_path / "repo")
    wo_id = _wo_with_boundary(db, repo, "core/")
    record_delivery_boundary(wo_id, repo_root=repo, db_path=db)

    (repo / "core").mkdir()
    (repo / "core" / "wip.py").write_text("draft = True\n", encoding="utf-8")

    text, _note = boundary_diff_text(wo_id, repo_root=repo, db_path=db)
    assert text and "core/wip.py" in text
    assert "module boundary" in text


def test_the_no_vcs_floor_is_used_only_when_nothing_else_exists(db, tmp_path):
    """Content shows current state rather than the change, so it must never
    displace a diff that exists."""
    from core.work_orders.delivery_boundary import boundary_diff_text

    plain = tmp_path / "no-vcs"
    (plain / "core").mkdir(parents=True)
    (plain / "core" / "only.py").write_text("FLOOR = 1\n", encoding="utf-8")
    wo_id = _wo_with_boundary(db, plain, "core/")

    text, _note = boundary_diff_text(wo_id, repo_root=plain, db_path=db)
    assert text and "FLOOR = 1" in text
    assert "boundary file core/only.py" in text


def test_nothing_delivered_is_reported_as_a_finding_not_as_missing_metadata(db, tmp_path):
    """The only honest 'nothing to look at': every layer empty. That is a finding
    about the WORK, not the metadata artifact 'unreviewable' used to mean."""
    from core.work_orders.delivery_boundary import boundary_diff_text, record_delivery_boundary

    repo, _head = _git_repo(tmp_path / "repo")
    wo_id = _wo_with_boundary(db, repo, "core/")
    record_delivery_boundary(wo_id, repo_root=repo, db_path=db)
    # No commits after start, nothing uncommitted, boundary path never created.
    text, note = boundary_diff_text(wo_id, repo_root=repo, db_path=db)
    assert text is None
    assert note, "an empty result must always say why"


def test_caveats_are_carried_so_a_partial_view_is_never_presented_as_whole(db, tmp_path):
    from core.work_orders.delivery_boundary import boundary_diff_text

    plain = tmp_path / "nb"
    plain.mkdir()
    wo_id = _wo_with_boundary(db, plain, None)  # no boundary declared
    text, note = boundary_diff_text(wo_id, repo_root=plain, db_path=db)
    assert text is None
    assert note and "Module boundary" in note


# ── No false-unreviewable (task 5) ─────────────────────────────────────────────


def test_the_unreviewable_message_names_every_layer_it_tried(db, tmp_path, monkeypatch):
    """The old wording — "no commits found referencing <id> or '<title>'" — blamed
    the WORK for a bookkeeping miss, sending an operator to look for commits when
    the real problem was often that nothing had recorded where to look. Those two
    have opposite remedies, so the message has to distinguish them.
    """
    import sqlite3
    from unittest.mock import MagicMock

    from core.work_orders.verify_main import verify_work_order

    repo, _head = _git_repo(tmp_path / "repo")
    project_id, wo_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = "2026-08-20T00:00:00+00:00"
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
        "  status, created_at, updated_at)"
        " VALUES (?,?,NULL,'Nothing was delivered here','no boundary','infrastructure',"
        "         'in_progress',?,?)",
        (wo_id, project_id, now, now),
    )
    conn.execute(
        "INSERT INTO business_tasks"
        " (task_id, work_order_id, project_id, title, description, status, created_at, updated_at)"
        " VALUES (?,?,?,'t','d','complete',?,?)",
        (str(uuid.uuid4()), wo_id, project_id, now, now),
    )
    conn.commit()
    conn.close()

    monkeypatch.delenv("DREAM_STUDIO_VERIFY_MOCK", raising=False)
    fake_paths = MagicMock()
    fake_paths.sqlite_path = db
    fake_paths.dream_studio_home = tmp_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        result = verify_work_order(
            work_order_id=wo_id,
            source_root=repo,
            dream_studio_home=tmp_path,
            planning_root=tmp_path / "planning",
        )

    summary = (result.get("summary") or "") + (result.get("warning") or "")
    assert "unreviewable" in summary
    # It must name what was tried, not just what was not found.
    assert "recorded delivery boundary" in summary
    assert "executable checks" in summary
    # And it must offer the two distinct remedies.
    assert "where it landed" in summary
    assert "re-start the work order" in summary


def test_the_locator_is_a_fallback_chain_not_a_concatenation():
    """The recorded range REPLACES the commit grep; it is never joined to it.

    THIS TEST HAS BEEN WRONG TWICE, and the second way was worse.

    First it grepped verify_work_order's SOURCE for "_boundary_diff or
    _collect_git_commits(". A refactor rewrote that `or` into an if/else without touching
    the behaviour, and the guard broke -- a source-text assertion cannot tell a rewrite
    from a regression.

    Then I replaced it with one that patched verify_git.collect_union_evidence and called
    delivery_boundary.boundary_diff_text -- which is NOT the function that chooses. The
    patched collector was never reachable from that call, so `assert called == []` could
    not fail under any code change. I described that as the stronger version. This work
    order's own independent review caught it.

    The choice now lives in verify_git.choose_locator, so it can be driven directly and
    the assertion can actually fail: the collector here raises, and reaching it fails the
    test rather than passing it.

    Concatenating both was tried and rejected -- for any work order whose commits DO
    mention it, both layers return the same commits and the grader input roughly doubles,
    a universal cost for a conditional benefit against a budget that already timed a
    grader out at 360s on 217,524 chars.
    """
    from core.work_orders.verify_git import choose_locator

    def _must_not_run():
        raise AssertionError(
            "the commit grep ran while the recorded range had content -- the range must "
            "REPLACE it, not be concatenated with it"
        )

    _range = "=== commit range ===" + chr(10) + "diff --git a/x b/x"
    diff, provenance, layer = choose_locator(_range, _must_not_run)

    assert diff.startswith("=== commit range ==="), "the range must be the locator"
    assert provenance == [], "no roots were searched, so none may be claimed"
    assert layer == "recorded_delivery_boundary"


def test_the_grep_runs_only_when_the_range_is_empty():
    """The other half: a fallback that never fires is not a fallback."""
    from core.work_orders.verify_git import choose_locator

    diff, provenance, layer = choose_locator(None, lambda: ("grep found this", ["a-root"]))

    assert diff == "grep found this"
    assert provenance == ["a-root"], "the union collector's provenance must survive"
    assert layer == "commit_search_union"


def test_neither_locator_reports_none_rather_than_empty():
    """None means "no evidence" and must never read as a certified pass or an auto-zero."""
    from core.work_orders.verify_git import choose_locator

    diff, _provenance, layer = choose_locator(None, lambda: (None, []))
    assert diff is None
    assert layer == "none"


# -- WO-BOUNDARY-OPEN-END: a boundary needs an end -----------------------------


def _second_commit(root: Path) -> str:
    """Add a commit AFTER the work order's own change, the way later work lands."""
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

    (root / "someone_elses_work.txt").write_text("not this work order", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "a later work order")
    return git("rev-parse", "HEAD")


def test_a_finished_work_order_records_its_end_commit(db, tmp_path):
    """Without an end the range is unbounded BY CONSTRUCTION -- there is nothing to stop
    it, not merely nothing stopping it today."""
    from core.work_orders.delivery_boundary import record_delivery_boundary_end

    root, _head = _git_repo(tmp_path / "repo")
    wo = str(uuid.uuid4())
    record_delivery_boundary(wo, repo_root=root, db_path=db)

    end_sha = _second_commit(root)
    result = record_delivery_boundary_end(wo, repo_root=root, db_path=db)

    assert result.get("end_recorded") is True, f"end not stored: {result}"
    stored = read_delivery_boundary(wo, db_path=db)
    assert stored["end_commit"] == end_sha
    assert stored["ended_at"], "an end with no timestamp cannot be audited"
    assert stored["start_commit"], "stamping an end must not lose the start"


def test_a_finished_boundary_does_not_range_to_head(db, tmp_path):
    """THE DEFECT. Measured on work order 3e6cf265, whose change merged in PR #682: its
    range was 84d26359..HEAD with HEAD thirteen commits later, assembling 217,524 chars of
    three other work orders' changes and timing the grader out at 360s twice. Pinned to
    the merge it actually landed in, the same evidence was 30,149 chars.
    """
    from core.work_orders.delivery_boundary import record_delivery_boundary_end

    root, start = _git_repo(tmp_path / "repo")
    wo = str(uuid.uuid4())
    record_delivery_boundary(wo, repo_root=root, db_path=db)
    end_sha = record_delivery_boundary_end(wo, repo_root=root, db_path=db)["end_commit"]

    # Later work lands AFTER this work order finished.
    later = _second_commit(root)
    assert later != end_sha, "precondition: HEAD has moved past this work order"

    expr, why = boundary_commit_range(wo, db_path=db)

    assert expr == f"{start}..{end_sha}", expr
    assert "HEAD" not in expr, "a finished work order must not range to a moving HEAD"
    assert why is None, "a pinned range carries no open-range caveat"


def test_an_unknown_end_is_reported_not_assumed(db, tmp_path):
    """A work order that finished before end stamping existed has no end. Ranging to HEAD
    is then the only option -- but the caller must be TOLD, because the alternative is a
    range that quietly includes later work while reading as tight.

    In-progress work is the case where ..HEAD is genuinely right, and it is not a fallback:
    the work order is still moving, so HEAD is its end.
    """
    root, start = _git_repo(tmp_path / "repo")
    wo = str(uuid.uuid4())
    record_delivery_boundary(wo, repo_root=root, db_path=db)

    expr, why = boundary_commit_range(wo, db_path=db)

    assert expr == f"{start}..HEAD"
    assert why, "an open range with no caveat is the defect this work order exists to fix"
    assert "no recorded end" in why
    assert "may include work done after" in why


def test_stamping_an_end_on_a_work_order_with_no_boundary_says_so(db, tmp_path):
    """A work order that started before boundaries were stamped has nothing to close.
    Reporting that beats inventing a boundary, which would assert a range nobody recorded.
    """
    from core.work_orders.delivery_boundary import record_delivery_boundary_end

    root, _ = _git_repo(tmp_path / "repo")
    result = record_delivery_boundary_end(str(uuid.uuid4()), repo_root=root, db_path=db)

    assert result.get("recorded") is False
    assert "no delivery boundary to close" in result.get("reason", "")


def test_the_open_range_caveat_reaches_the_caller(db, tmp_path):
    """A caveat computed and dropped is the same defect as a value stored nowhere.

    boundary_diff_text read `why` ONLY when there was no usable range, so a warning
    arriving alongside a working range reached no reader. The open-range warning is
    exactly that shape: it comes back WITH a valid expression.
    """
    from core.work_orders.delivery_boundary import boundary_diff_text

    root, _ = _git_repo(tmp_path / "repo")
    wo = str(uuid.uuid4())
    record_delivery_boundary(wo, repo_root=root, db_path=db)
    _second_commit(root)

    _text, note = boundary_diff_text(wo, repo_root=root, db_path=db)

    assert note, "the open-range caveat must reach the caller"
    assert "no recorded end" in note


# -- The ordering is the point (found by this work order's own review) ---------


def test_the_end_is_stamped_before_close_grades_anything():
    """THE FIRST CUT PUT THE STAMP WHERE IT COULD NOT HELP.

    close_work_order stamped the end after mutating status -- roughly 300 lines below the
    auto-verify -- so the verify that GATES the close still graded an unbounded
    `<start>..HEAD` range. That is the exact failure mode this work order exists to remove,
    reproduced inside its own fix. Its independent review named it: "close runs verify
    (:234) long before it stamps (:528)".

    Asserted on source ORDER rather than behaviour because the ordering IS the property;
    a behavioural test would need a full close with graders to observe it.
    """
    source = Path("core/work_orders/close_main.py").read_text(encoding="utf-8")

    stamp = source.index("record_delivery_boundary_end")
    verify = source.index("_verify_wo(")
    mutate = source.index("SET status = 'closed'")

    assert stamp < verify, (
        "the boundary end must be pinned BEFORE the auto-verify, or the verify that gates "
        "this close grades an unbounded range"
    )
    assert stamp < mutate, "and before the status mutation"
    assert (
        source.count("record_delivery_boundary_end(") == 1
    ), "one call site -- two would let the close stamp twice and disagree with itself"


def test_the_final_task_done_also_pins_the_boundary(db, tmp_path):
    """THE SECOND HALF, which task 1 named and I first shipped without.

    A work order is routinely verified BEFORE it is closed -- `ds work-order verify` is a
    separate command an operator runs to decide whether to close at all. Without a stamp at
    the last task-done, that verify still grades every commit since the work order started.
    """
    import sqlite3

    from core.work_orders.delivery_boundary import (
        read_delivery_boundary,
        record_delivery_boundary,
    )
    from core.work_orders.mutations import mark_task_done

    root, _head = _git_repo(tmp_path / "repo")
    project_id, wo_id = str(uuid.uuid4()), str(uuid.uuid4())
    t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
    now = "2026-08-28T00:00:00+00:00"

    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at, project_path)"
        " VALUES (?,?,?,?,?,?,?)",
        (project_id, "P", "", "active", now, now, str(root)),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at)"
        " VALUES (?,?,NULL,'WO','d','infrastructure','in_progress',?,?)",
        (wo_id, project_id, now, now),
    )
    for tid, title in ((t1, "first"), (t2, "second")):
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description, status,"
            "  created_at, updated_at) VALUES (?,?,?,?,'d','pending',?,?)",
            (tid, wo_id, project_id, title, now, now),
        )
    conn.commit()
    conn.close()

    record_delivery_boundary(wo_id, repo_root=root, db_path=db)
    assert not read_delivery_boundary(wo_id, db_path=db).get("end_commit")

    # mark_task_done derives its db from dream_studio_home; the `db` fixture lives at
    # tmp_path/state/studio.db, which is exactly what _require_db resolves to.
    mark_task_done(
        work_order_id=wo_id, task_id=t1, source_root=tmp_path, dream_studio_home=tmp_path
    )
    assert not read_delivery_boundary(wo_id, db_path=db).get(
        "end_commit"
    ), "an earlier task-done is not the end of the work"

    # mark_task_done emits task.completed and the TaskProjection applies it. In this
    # fixture the projection cannot (FOREIGN KEY constraint failed -- the seeded rows
    # do not satisfy its parents), so t1's status would stay 'pending', the next call
    # would recount 2 remaining, and `remaining == 0` would never hold. Applying the
    # status here is what the projection would have done. Without this the test fails
    # for a reason that has nothing to do with the boundary -- verified by reproducing
    # the same flow outside pytest, where the stamp landed correctly.
    conn = sqlite3.connect(str(db))
    conn.execute("UPDATE business_tasks SET status='complete' WHERE task_id=?", (t1,))
    conn.commit()
    conn.close()

    mark_task_done(
        work_order_id=wo_id, task_id=t2, source_root=tmp_path, dream_studio_home=tmp_path
    )
    boundary = read_delivery_boundary(wo_id, db_path=db)
    assert boundary.get("end_commit"), (
        "the LAST task-done must pin the end, or a pre-close verify grades an unbounded " "range"
    )


# -- WO 80c0e61b: a range is not an attribution ----------------------------------


def _repo(tmp_path: Path):
    """A tiny git repo with a linear history. Returns (root, [sha, ...] oldest first)."""
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    run = lambda *a: subprocess.run(  # noqa: E731
        list(a),
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "T")
    shas = []
    for i in range(6):
        (root / f"f{i}.txt").write_text(str(i), encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", f"c{i}")
        shas.append(
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            ).stdout.strip()
        )
    return root, shas


def _own(db: Path, wo: str, shas: list) -> None:
    import json as _json

    from core.work_orders.artifacts import set_wo_artifact
    from core.work_orders.range_attribution import OWNERSHIP_KEY, OWNERSHIP_KIND

    set_wo_artifact(
        wo, OWNERSHIP_KIND, _json.dumps({"commits": shas}), instance_key=OWNERSHIP_KEY, db_path=db
    )


def test_a_range_containing_a_neighbours_commits_grades_only_its_own(db, tmp_path):
    """THE DEFECT, MEASURED. Work order 1db6de49's range 78b98c1a..38637543 held 10 commits
    belonging to 5 different work orders, because a delivery boundary is contiguous history
    and several work orders had landed on one branch. The grader read the whole diff and
    attributed every finding to one of them: 6 review rounds attached 9, then 29, then 66
    tasks — roughly 30 per run — while each round separately confirmed that work order's own
    tasks had landed. It could not converge.
    """
    from core.work_orders.range_attribution import attribute_range

    root, shas = _repo(tmp_path)
    mine, theirs = "wo-mine", "wo-theirs"
    _own(db, theirs, [shas[2], shas[3]])

    result = attribute_range(mine, f"{shas[0]}..{shas[5]}", repo_root=root, db_path=db)

    assert set(result.own) == {shas[1], shas[4], shas[5]}
    assert set(result.excluded) == {shas[2], shas[3]}
    assert all(wo == theirs for wo in result.excluded.values())


def test_an_overlapping_boundary_alone_never_excludes_a_commit(db, tmp_path):
    """MY FIRST FIX WAS ALSO WRONG, AND MEASURING IT IS WHAT SHOWED THAT.

    It excluded any commit inside another work order's closed boundary. Run against the
    real range that gave 10 -> 1 own, 9 excluded — and two of the nine were the work
    order's OWN commits, dropped because a neighbour's boundary spanned them.

    A boundary is a TIME WINDOW. Two work orders worked on in the same period have
    legitimately overlapping windows, so no subtraction over them can separate interleaved
    work: both windows genuinely contain both sets. A silently narrowed range is exactly as
    dishonest as a silently wide one, and harder to notice, because it hides work.
    """
    import json as _json

    from core.work_orders.artifacts import set_wo_artifact
    from core.work_orders.range_attribution import attribute_range

    root, shas = _repo(tmp_path)
    # A neighbour whose BOUNDARY spans the whole history but which claims no commits.
    set_wo_artifact(
        "wo-neighbour",
        "report",
        _json.dumps({"start_commit": shas[0], "end_commit": shas[5]}),
        instance_key="delivery_boundary",
        db_path=db,
    )

    result = attribute_range("wo-mine", f"{shas[0]}..{shas[5]}", repo_root=root, db_path=db)

    assert result.excluded == {}, (
        "an overlapping boundary excluded commits — interleaved work orders share windows, "
        "so this drops work that really does belong here"
    )
    assert len(result.own) == 5


def test_a_commit_this_work_order_also_claims_is_kept(db, tmp_path):
    """Two work orders can honestly touch the same commit. Dropping it would hide delivered
    work, so this work order's own record wins over a neighbour's."""
    from core.work_orders.range_attribution import attribute_range

    root, shas = _repo(tmp_path)
    _own(db, "wo-theirs", [shas[2], shas[3]])
    _own(db, "wo-mine", [shas[3]])

    result = attribute_range("wo-mine", f"{shas[0]}..{shas[5]}", repo_root=root, db_path=db)

    assert shas[3] in result.own, "a commit this work order claims was dropped"
    assert set(result.excluded) == {shas[2]}


def test_a_verdict_names_what_it_graded(db, tmp_path):
    """The failing verdicts carried graded_commits: [] while the range held 10 commits, so a
    reader could not tell a stale verdict from a live one, nor a wide range from a narrow
    one. The note has to say both counts and, when it did NOT narrow, why not."""
    from core.work_orders.range_attribution import attribute_range

    root, shas = _repo(tmp_path)

    wide = attribute_range("wo-mine", f"{shas[0]}..{shas[5]}", repo_root=root, db_path=db)
    assert "NOT narrowed" in wide.note
    assert "5" in wide.note, "the note must state how many commits are being graded"
    assert "branch neighbour" in wide.note, "and warn that they may not all belong here"

    _own(db, "wo-theirs", [shas[2]])
    narrow = attribute_range("wo-mine", f"{shas[0]}..{shas[5]}", repo_root=root, db_path=db)
    assert "narrowed" in narrow.note
    assert "4 of 5" in narrow.note
    assert "wo-theirs"[:8] in narrow.note, "the note must name who the excluded work belongs to"


def test_ownership_is_recorded_as_work_happens(db, tmp_path):
    """Ownership can only be captured while the work is happening — a commit's owner is not
    recoverable afterwards, which is why every historic range keeps its full width."""
    import subprocess

    from core.work_orders.range_attribution import read_owned_commits, record_commit_ownership

    root, shas = _repo(tmp_path)
    recorded = record_commit_ownership("wo-mine", repo_root=root, db_path=db, since=shas[2])
    assert recorded == [shas[3], shas[4], shas[5]], recorded
    assert read_owned_commits("wo-mine", db_path=db) == recorded

    # A second call after another commit appends only the new one.
    (root / "later.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(root), capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "later"], cwd=str(root), capture_output=True)
    again = record_commit_ownership("wo-mine", repo_root=root, db_path=db)
    assert len(again) == 1
    assert len(read_owned_commits("wo-mine", db_path=db)) == 4


def test_recording_ownership_never_breaks_the_work(db, tmp_path):
    """Best-effort by construction: finishing a task must not fail on bookkeeping. An
    unrecorded commit is merely unattributed, which keeps a range wide rather than wrong."""
    from core.work_orders.range_attribution import record_commit_ownership

    assert record_commit_ownership("wo-mine", repo_root=None, db_path=db) == []
    assert record_commit_ownership("wo-mine", repo_root=tmp_path / "nope", db_path=db) == []


# -- WO e439f287: ownership has to survive the merge that makes the work permanent ---


def _squash_repo(tmp_path: Path):
    """A repo where two commits were squashed into one, GitHub-style.

    The squash commit's body carries each original subject as a ``* `` bullet, which is
    what makes the mapping a RECORDED link rather than an inference.
    """
    import subprocess

    root = tmp_path / "squashrepo"
    root.mkdir()

    def run(*a, **kw):
        return subprocess.run(
            list(a),
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            **kw,
        )

    run("git", "init", "-q")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "T")
    (root / "base.txt").write_text("base", encoding="utf-8")
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", "base")

    # Two commits that will be squashed away.
    originals = []
    for subject in ("feat: the first thing", "fix: the second thing"):
        (root / f"{subject[:8].strip()}.txt").write_text(subject, encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", subject)
        originals.append(run("git", "rev-parse", "HEAD").stdout.strip())

    # Rewind and land them as ONE commit, the way a squash merge does.
    run("git", "reset", "-q", "--hard", "HEAD~2")
    (root / "squashed.txt").write_text("both", encoding="utf-8")
    run("git", "add", "-A")
    body = "chore: land both (#42)\n\n* feat: the first thing\n\n* fix: the second thing\n"
    run("git", "commit", "-q", "-m", body)
    squash = run("git", "rev-parse", "HEAD").stdout.strip()
    return root, originals, squash


def test_ownership_survives_a_squash_merge(db, tmp_path):
    """THE LIMIT THIS FIXES, found while cleaning up after the attribution work shipped.

    record_commit_ownership records BRANCH shas, and this repo squash-merges every PR. So
    the moment a branch lands, the commits a work order claimed stop being ancestors of
    HEAD: `git merge-base --is-ancestor 4a5221cf main` returns non-zero because #687
    squashed 18 commits into 14b8693c. Attribution was therefore correct for in-flight work
    and inert for merged work — half the value, and silently so.

    GitHub's squash writes each original subject into the merge body as a ``* `` bullet.
    That is a recorded link, so the mapping is read rather than guessed.
    """
    from core.work_orders.range_attribution import reachable_ownership, resolve_squashed

    root, originals, squash = _squash_repo(tmp_path)

    assert resolve_squashed(originals[0], repo_root=root) == squash
    reachable, squashed_into, lost = reachable_ownership(originals, repo_root=root)

    assert reachable == [], "the originals should not be reachable after a squash"
    assert set(squashed_into.values()) == {squash}
    assert lost == [], f"a mappable commit was reported lost: {lost}"


def test_a_neighbours_claim_still_applies_after_their_branch_merges(db, tmp_path):
    """The consequence that actually matters. Exclusion reads another work order's recorded
    ownership; if their shas stop resolving the moment they merge, their claim evaporates
    and the range reads as having no neighbours — indistinguishable from a range that
    genuinely has none."""
    import json as _json

    from core.work_orders.artifacts import set_wo_artifact
    from core.work_orders.range_attribution import (
        OWNERSHIP_KEY,
        OWNERSHIP_KIND,
        attribute_range,
    )

    root, originals, squash = _squash_repo(tmp_path)
    set_wo_artifact(
        "wo-neighbour",
        OWNERSHIP_KIND,
        _json.dumps({"commits": originals}),
        instance_key=OWNERSHIP_KEY,
        db_path=db,
    )

    result = attribute_range("wo-mine", f"{squash}~1..{squash}", repo_root=root, db_path=db)

    assert squash in result.excluded, (
        "the neighbour's claim did not follow their commits through the squash, so their "
        "work would be graded against this work order"
    )
    assert result.excluded[squash] == "wo-neighbour"


def test_unreachable_owned_commits_are_reported(db, tmp_path):
    """A squash that cannot be followed is NOT the same as having no neighbours, and the
    two rendered identically before this. Silent degradation to 'not narrowed' is the
    absent-is-not-clean shape again: nothing looked wrong, and the reason was that nothing
    could be seen."""
    import json as _json

    from core.work_orders.artifacts import set_wo_artifact
    from core.work_orders.range_attribution import (
        OWNERSHIP_KEY,
        OWNERSHIP_KIND,
        attribute_range,
    )

    root, originals, squash = _squash_repo(tmp_path)
    # A recorded sha that never existed here: unreachable AND unmappable.
    set_wo_artifact(
        "wo-mine",
        OWNERSHIP_KIND,
        _json.dumps({"commits": ["0" * 40]}),
        instance_key=OWNERSHIP_KEY,
        db_path=db,
    )

    result = attribute_range("wo-mine", f"{squash}~1..{squash}", repo_root=root, db_path=db)

    assert "no longer reachable" in result.note, result.note
    assert "could not be mapped" in result.note


def test_an_ambiguous_squash_is_not_resolved(db, tmp_path):
    """Two merge commits carrying the same subject bullet cannot both be the answer.
    Picking the first would be a guess wearing an answer's clothes, so it returns None and
    the commit is reported unmappable instead."""
    import subprocess

    from core.work_orders.range_attribution import resolve_squashed

    root, originals, _squash = _squash_repo(tmp_path)
    # A SECOND commit claiming the same original subject.
    (root / "again.txt").write_text("again", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(root), capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "chore: land both again (#43)\n\n* feat: the first thing\n"],
        cwd=str(root),
        capture_output=True,
    )

    assert resolve_squashed(originals[0], repo_root=root) is None


def test_an_unmappable_neighbour_claim_is_reported_too(db, tmp_path):
    """AN INDEPENDENT REVIEW CAUGHT THIS ASYMMETRY IN THE SAME DIFF THAT INTRODUCED IT.

    reachable_ownership names unreachable-and-unmappable commits for THIS work order's own
    side. _squash_aware_index dropped a NEIGHBOUR's on the floor, and attribute_range then
    reported "none of the N commits is recorded as belonging to another work order" — an
    absence it had not established.

    Candid on one side and silent on the other is worse than either, because the silence
    is invisible next to the candour: a reader who sees one caveat reasonably assumes the
    other case would also have been named.
    """
    import json as _json

    from core.work_orders.artifacts import set_wo_artifact
    from core.work_orders.range_attribution import (
        OWNERSHIP_KEY,
        OWNERSHIP_KIND,
        attribute_range,
    )

    root, shas = _repo(tmp_path)
    # A neighbour claiming a commit that never existed in this repo: unreachable AND
    # unmappable, so its claim cannot be applied to the range.
    set_wo_artifact(
        "wo-neighbour",
        OWNERSHIP_KIND,
        _json.dumps({"commits": ["f" * 40]}),
        instance_key=OWNERSHIP_KEY,
        db_path=db,
    )

    result = attribute_range("wo-mine", f"{shas[0]}..{shas[5]}", repo_root=root, db_path=db)

    assert "recorded by OTHER work orders" in result.note, result.note
    assert (
        "may be graded here" in result.note
    ), "the range was reported as having no neighbour claims when one could not be located"
