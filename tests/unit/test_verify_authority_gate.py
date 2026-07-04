"""WO-FIX-VERIFY-GATE: independent_review certifies from authority+diff, not
commit-message grep.

The verify gate greps git for the WO id/title. A squash merge never carries the
id into the merged commit, so grep-by-id finds nothing and every squash-merged
WO was forced to close with force=True (or a wo-<shortid> branch-pointer hack).
The fix adds two fallbacks before declaring unreviewable:
  1. the branch's working diff vs origin/main (pre-merge — no WO id needed);
  2. the executable AC results (SQL/TEST/API-CHECK) as objective authority proof.
Only genuinely-no-evidence stays unreviewable (no false-done).
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
from core.work_orders.verify import _authority_evidence, _collect_working_diff

NOW = "2026-01-01T00:00:00.000000Z"


def _make_git_repo(tmp_path: Path, messages: list[str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    env = dict(cwd=str(repo), capture_output=True, text=True, check=True)
    subprocess.run(["git", "init", "-q"], **env)
    subprocess.run(["git", "config", "user.email", "t@t"], **env)
    subprocess.run(["git", "config", "user.name", "t"], **env)
    for i, msg in enumerate(messages):
        (repo / f"f{i}.txt").write_text(msg, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], **env)
        subprocess.run(["git", "commit", "-q", "-m", msg], **env)
    return repo


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db_path)
    return db_path


@contextmanager
def _patch_db(db_path: Path):
    fake = MagicMock()
    fake.sqlite_path = db_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake):
        yield


def _seed_wo(db_path: Path, *, work_order_id: str, title: str, ac: str | None) -> None:
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, "Test", "", "active", NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_milestones (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (milestone_id, project_id, "M1", "active", 1, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders (work_order_id, project_id, milestone_id, title,"
        " description, work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
        " VALUES (?,?,?,?,?,?,'in_progress',1,?,?,?)",
        (work_order_id, project_id, milestone_id, title, "desc", "infrastructure", NOW, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_tasks (task_id, work_order_id, project_id, title, description,"
        " status, created_at, updated_at, acceptance_criteria)"
        " VALUES (?,?,?,?,?,'complete',?,?,?)",
        (str(uuid.uuid4()), work_order_id, project_id, "T1", "do it", NOW, NOW, ac),
    )
    conn.commit()
    conn.close()


class TestUnitHelpers:
    def test_authority_evidence_has_passing_when_ac_passes(self):
        tasks = [{"title": "T1", "status": "complete"}]
        ac_results = {"T1": [{"kind": "SQL-CHECK", "expr": "SELECT 1", "passed": True}]}
        text, has_passing = _authority_evidence("abcd1234-0000", tasks, ac_results)
        assert has_passing is True
        assert "SQL-CHECK PASS" in text
        assert "abcd1234" in text

    def test_authority_evidence_no_passing_without_checks(self):
        tasks = [{"title": "T1", "status": "complete"}]
        text, has_passing = _authority_evidence("abcd1234-0000", tasks, {})
        assert has_passing is False  # nothing objective to certify

    def test_authority_evidence_failing_check_is_not_passing(self):
        tasks = [{"title": "T1", "status": "complete"}]
        ac_results = {"T1": [{"kind": "TEST-CHECK", "expr": "tests/x.py", "passed": False}]}
        _, has_passing = _authority_evidence("wo", tasks, ac_results)
        assert has_passing is False

    def test_working_diff_captures_branch_changes(self, tmp_path):
        repo = _make_git_repo(tmp_path, ["base"])
        # Simulate a base ref, branch off, add a change.
        env = dict(cwd=str(repo), capture_output=True, text=True, check=True)
        subprocess.run(["git", "branch", "base-ref"], **env)
        (repo / "feature.py").write_text("print('new work')\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], **env)
        subprocess.run(["git", "commit", "-q", "-m", "feat: work with no WO id"], **env)
        diff = _collect_working_diff(repo, base_ref="base-ref")
        assert diff is not None
        assert "feature.py" in diff
        assert "new work" in diff

    def test_working_diff_none_on_clean_tree(self, tmp_path):
        repo = _make_git_repo(tmp_path, ["only"])
        # HEAD == base-ref, no uncommitted changes → no diff.
        subprocess.run(
            ["git", "branch", "base-ref"], cwd=str(repo), capture_output=True, text=True, check=True
        )
        assert _collect_working_diff(repo, base_ref="base-ref") is None


class TestAuthorityCertification:
    def test_squash_merged_wo_with_passing_ac_certifies_from_authority(self, tmp_path, monkeypatch):
        """No commit references the WO id (squash) and no branch diff (post-merge),
        but a passing SQL-CHECK certifies from authority — NOT unreviewable."""
        monkeypatch.setenv("DREAM_STUDIO_VERIFY_MOCK", "1")  # canned graders
        repo = _make_git_repo(tmp_path, ["chore: unrelated squash commit (#999)"])
        db_path = _make_db(tmp_path)
        wo_id = str(uuid.uuid4())
        _seed_wo(db_path, work_order_id=wo_id, title="WO-SQUASHED - x", ac="SQL-CHECK: SELECT 1")
        # Force both git sources empty so only authority evidence remains.
        monkeypatch.setattr("core.work_orders.verify._collect_git_commits", lambda *a, **k: None)
        monkeypatch.setattr("core.work_orders.verify._collect_working_diff", lambda *a, **k: None)

        with _patch_db(db_path):
            from core.work_orders.verify import verify_work_order

            result = verify_work_order(
                work_order_id=wo_id,
                source_root=repo,
                dream_studio_home=tmp_path,
                planning_root=tmp_path / "planning",
            )

        assert result["ok"] is True
        assert not result.get("unreviewable"), "passing AC should certify, not go unreviewable"
        assert result["certification_basis"] == "authority_evidence"

    def test_no_evidence_at_all_stays_unreviewable(self, tmp_path, monkeypatch):
        """No commit, no branch diff, and NO executable AC → still unreviewable
        (the no-false-done invariant: nothing objective to certify)."""
        monkeypatch.delenv("DREAM_STUDIO_VERIFY_MOCK", raising=False)
        repo = _make_git_repo(tmp_path, ["chore: unrelated"])
        db_path = _make_db(tmp_path)
        wo_id = str(uuid.uuid4())
        _seed_wo(db_path, work_order_id=wo_id, title="WO-NOPE - nothing", ac=None)
        monkeypatch.setattr("core.work_orders.verify._collect_git_commits", lambda *a, **k: None)
        monkeypatch.setattr("core.work_orders.verify._collect_working_diff", lambda *a, **k: None)

        with _patch_db(db_path):
            from core.work_orders.verify import verify_work_order

            result = verify_work_order(
                work_order_id=wo_id,
                source_root=repo,
                dream_studio_home=tmp_path,
                planning_root=tmp_path / "planning",
            )

        assert result["ok"] is True
        assert result["unreviewable"] is True
        assert result["spawned_work_orders"] == []
