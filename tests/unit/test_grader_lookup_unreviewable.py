"""Tests for WO-GRADER-LOOKUP: commit lookup by WO title token + unreviewable verdicts.

The correctness grader's diff input came from `git log --grep=<uuid[:8]>`, but
squash-merge commit messages carry the WO name (e.g. 'WO-DEBT-I'), never the
UUID. The grader then saw an empty diff, scored 0.0 with an 'N/A: empty diff'
violation, and close.py spawned an unactionable remediation WO on every close
of a squash-merged work order.

Fix under test:
  1. _collect_git_commits also greps the WO title token when the UUID grep is
     empty, and returns None (sentinel) when neither matches.
  2. verify_work_order short-circuits a None diff into an 'unreviewable'
     verdict: passed=False, unreviewable=True, no gaps, no spawned WOs.
  3. The independent_review close gate passes (with the warning surfaced by
     close_work_order as verify_warning) instead of blocking on unreviewable.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.verify import _collect_git_commits

NOW = "2026-01-01T00:00:00.000000Z"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_git_repo(tmp_path: Path, messages: list[str]) -> Path:
    """Create a throwaway git repo with one commit per message."""
    repo = tmp_path / "repo"
    repo.mkdir()
    env_args = dict(cwd=str(repo), capture_output=True, text=True, check=True)
    subprocess.run(["git", "init", "-q"], **env_args)
    subprocess.run(["git", "config", "user.email", "t@t"], **env_args)
    subprocess.run(["git", "config", "user.name", "t"], **env_args)
    for i, msg in enumerate(messages):
        (repo / f"f{i}.txt").write_text(msg, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], **env_args)
        subprocess.run(["git", "commit", "-q", "-m", msg], **env_args)
    return repo


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db_path)
    return db_path


@contextmanager
def _patch_db(db_path: Path):
    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        yield


def _seed_wo(db_path: Path, *, work_order_id: str, title: str) -> tuple[str, str]:
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, "Test", "", "active", NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_milestones"
        " (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (milestone_id, project_id, "M1", "active", 1, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description,"
        "  work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
        " VALUES (?,?,?,?,?,?,'in_progress',1,?,?,?)",
        (work_order_id, project_id, milestone_id, title, "desc", "cleanup", NOW, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_tasks"
        " (task_id, work_order_id, project_id, title, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,'complete',?,?)",
        (str(uuid.uuid4()), work_order_id, project_id, "T1", "do it", NOW, NOW),
    )
    conn.commit()
    conn.close()
    return project_id, milestone_id


# ---------------------------------------------------------------------------
# _collect_git_commits lookup
# ---------------------------------------------------------------------------


def test_lookup_by_uuid_still_works(tmp_path):
    wo_id = "abcd1234-0000-0000-0000-000000000000"
    repo = _make_git_repo(tmp_path, [f"fix: thing ({wo_id[:8]})"])
    diff = _collect_git_commits(repo, wo_id, title="WO-FAKE-1 - irrelevant")
    assert diff is not None
    assert "=== commit" in diff


def test_lookup_falls_back_to_title_token(tmp_path):
    """Squash-merge shape: commit message has the WO name, not the UUID."""
    repo = _make_git_repo(tmp_path, ["feat: narrow swallow clauses (WO-FAKE-1) (#999)"])
    wo_id = str(uuid.uuid4())
    diff = _collect_git_commits(repo, wo_id, title="WO-FAKE-1 - Swallow narrowing")
    assert diff is not None
    assert "=== commit" in diff


def test_lookup_returns_none_when_nothing_matches(tmp_path):
    repo = _make_git_repo(tmp_path, ["chore: unrelated"])
    diff = _collect_git_commits(repo, str(uuid.uuid4()), title="WO-NOPE-9 - nothing")
    assert diff is None


# ---------------------------------------------------------------------------
# verify_work_order unreviewable short-circuit
# ---------------------------------------------------------------------------


def test_verify_unreviewable_no_score_zero_no_spawned_wos(tmp_path, monkeypatch):
    """No commit evidence → unreviewable verdict, zero remediation WOs spawned."""
    monkeypatch.delenv("DREAM_STUDIO_VERIFY_MOCK", raising=False)
    repo = _make_git_repo(tmp_path, ["chore: unrelated"])
    db_path = _make_db(tmp_path)
    wo_id = str(uuid.uuid4())
    _seed_wo(db_path, work_order_id=wo_id, title="WO-NOPE-9 - nothing matches")
    planning_root = tmp_path / "planning"

    with _patch_db(db_path):
        from core.work_orders.verify import verify_work_order

        result = verify_work_order(
            work_order_id=wo_id,
            source_root=repo,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
        )

    assert result["ok"] is True
    assert result["passed"] is False
    assert result["unreviewable"] is True
    assert result["gaps"] == []
    assert result["spawned_work_orders"] == []
    assert "unreviewable" in result["auto_continue_warning"]

    verdict = json.loads(
        (planning_root / "work-orders" / wo_id / "review-verdict.json").read_text()
    )
    assert verdict["unreviewable"] is True
    assert verdict["spawned_work_orders"] == []

    # No remediation WOs were inserted into the authority.
    conn = sqlite3.connect(str(db_path))
    spawned = conn.execute(
        "SELECT COUNT(*) FROM business_work_orders WHERE title LIKE 'Fix %'"
    ).fetchone()[0]
    conn.close()
    assert spawned == 0


# ---------------------------------------------------------------------------
# independent_review gate treats unreviewable as pass-with-warning
# ---------------------------------------------------------------------------


def test_gate_does_not_pass_on_unreviewable_verdict(tmp_path):
    """WO-REVIEW-TRACEABILITY inverted prior behavior: an unreviewable verdict is no
    longer a certified pass. run_gate_check returns a blocking advisory failure;
    close_work_order bypasses it only when the always-on executable-AC gate passes.
    """
    from core.work_orders.close import run_gate_check

    wo_id = str(uuid.uuid4())
    wo_dir = tmp_path / "work-orders" / wo_id
    wo_dir.mkdir(parents=True)
    (wo_dir / "review-verdict.json").write_text(
        json.dumps({"passed": False, "unreviewable": True, "unreviewable_reason": "no commits"})
    )
    passed, reason = run_gate_check(
        "independent_review",
        planning_root=tmp_path,
        work_order_id=wo_id,
        project_id="p",
        conn=None,
    )
    assert passed is False
    assert reason.startswith("independent_review")
    assert "unreviewable" in reason


def test_spawn_grader_feeds_prompt_via_stdin_not_argv():
    """The prompt must reach the grader via stdin, never argv.

    With a real diff the prompt routinely exceeds Windows' ~32K command-line
    limit and CreateProcess fails with WinError 206 (hit re-verifying
    WO-DEBT-I once the title-token lookup started finding real commits).
    """
    import io

    from core.work_orders import verify as verify_mod
    from core.work_orders import verify_graders as verify_graders_mod

    big_prompt = "x" * 100_000  # far beyond the Windows argv limit
    captured: dict[str, object] = {}

    class _RecordingStdin(io.StringIO):
        def close(self):  # keep the buffer readable after the feeder closes it
            self.closed_by_feeder = True

    class _FakeProc:
        def __init__(self):
            self.stdin = _RecordingStdin()

    def _fake_popen(args, **kwargs):
        captured["args"] = args
        captured["stdin_is_pipe"] = kwargs.get("stdin") == subprocess.PIPE
        return _FakeProc()

    with patch.object(verify_graders_mod.subprocess, "Popen", _fake_popen):
        proc = verify_mod._spawn_grader(big_prompt)
        proc._ds_feeder.join(timeout=10)

    assert captured["args"] == ["claude", "--print"], "prompt must not be an argv element"
    assert captured["stdin_is_pipe"] is True
    assert proc.stdin.getvalue() == big_prompt


def test_gate_still_fails_on_reviewable_failed_verdict(tmp_path):
    from core.work_orders.close import run_gate_check

    wo_id = str(uuid.uuid4())
    wo_dir = tmp_path / "work-orders" / wo_id
    wo_dir.mkdir(parents=True)
    (wo_dir / "review-verdict.json").write_text(
        json.dumps({"passed": False, "summary": "real failure"})
    )
    passed, reason = run_gate_check(
        "independent_review",
        planning_root=tmp_path,
        work_order_id=wo_id,
        project_id="p",
        conn=None,
    )
    assert passed is False
    assert "review failed" in reason
