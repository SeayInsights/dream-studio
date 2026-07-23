"""WO 2c751184: executable-check gates verify the WO's TARGET repo, not always DS.

The close/verify executable_ac gate must run a work order's TEST-CHECKs in the repo
where the work was done — the WO's project's ``project_path`` — so an external-repo WO
(e.g. Fulcrum) is actually verified, not the Dream Studio repo. These tests prove:

- ``resolve_project_root`` maps a WO to its project's repo (or None to fall back).
- ``_run_one_test_check`` runs with ``cwd=project_root`` (real pytest execution proof).
- the ``cmd:`` form runs the target repo's own command; bare node-ids keep the
  DS-interpreter pytest back-compat; both thread cwd.
- ``run_executable_checks`` propagates project_root to the TEST-CHECK runner.
"""

from __future__ import annotations

import sqlite3
import sys
import types
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders import verify_executor
from core.work_orders.verify_executor import (
    _run_one_test_check,
    resolve_project_root,
    run_executable_checks,
)

PROJ = "p-repoaware-1"
WO = "wo-repoaware-1"
MS = "m-repoaware-1"


@pytest.fixture
def db(tmp_path: Path) -> Path:
    """Authority DB with one project whose project_path is a real external repo dir."""
    target = tmp_path / "studio.db"
    bootstrap_database(target)
    repo = tmp_path / "external_repo"
    repo.mkdir()
    conn = sqlite3.connect(str(target))
    conn.execute(
        "INSERT INTO business_projects (project_id,name,description,status,project_path,created_at,updated_at)"
        " VALUES (?,'Ext','','active',?,'2026-01-01','2026-01-01')",
        (PROJ, str(repo)),
    )
    conn.execute(
        "INSERT INTO business_milestones"
        " (milestone_id,project_id,title,description,status,order_index,created_at,updated_at)"
        " VALUES (?,?,'M','','active',0,'2026-01-01','2026-01-01')",
        (MS, PROJ),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id,project_id,milestone_id,title,description,status,work_order_type,created_at,updated_at)"
        " VALUES (?,?,?,'T','','in_progress','infrastructure','2026-01-01','2026-01-01')",
        (WO, PROJ, MS),
    )
    conn.commit()
    conn.close()
    return target


# ── resolve_project_root ─────────────────────────────────────────────────────


def test_resolve_project_root_returns_the_projects_repo(db: Path, tmp_path: Path):
    assert resolve_project_root(WO, db) == tmp_path / "external_repo"


def test_resolve_project_root_none_when_path_absent_or_missing(db: Path, tmp_path: Path):
    conn = sqlite3.connect(str(db))
    # NULL project_path → None
    conn.execute("UPDATE business_projects SET project_path = NULL WHERE project_id = ?", (PROJ,))
    conn.commit()
    assert resolve_project_root(WO, db) is None
    # A path that does not exist on disk → None (caller falls back to process cwd)
    conn.execute(
        "UPDATE business_projects SET project_path = ? WHERE project_id = ?",
        (str(tmp_path / "does_not_exist"), PROJ),
    )
    conn.commit()
    conn.close()
    assert resolve_project_root(WO, db) is None


def test_resolve_project_root_none_for_unknown_wo(db: Path):
    assert resolve_project_root("wo-nope", db) is None


# ── real execution: cwd is honored (strongest proof) ─────────────────────────


def test_test_check_runs_pytest_in_project_root(tmp_path: Path):
    """A bare pytest node-id runs with cwd=project_root: the test file exists ONLY in
    the target repo, so it can only be collected when cwd is that repo."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "test_only_here.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    passed = _run_one_test_check("test_only_here.py::test_ok", project_root=repo)
    assert passed["passed"] is True, passed

    # Without project_root the runner uses the process cwd (the DS repo), where the
    # file does not exist → pytest errors → fail. Proves cwd threading is load-bearing.
    missing = _run_one_test_check("test_only_here.py::test_ok", project_root=None)
    assert missing["passed"] is False


# ── argv + cwd construction (cross-platform, no external runner needed) ───────


def _fake_run(recorder: dict):
    def _run(argv, **kwargs):
        recorder["argv"] = argv
        recorder["cwd"] = kwargs.get("cwd")
        return types.SimpleNamespace(returncode=0, stdout="ok", stderr="")

    return _run


def test_cmd_form_runs_target_command_with_cwd(monkeypatch, tmp_path: Path):
    rec: dict = {}
    monkeypatch.setattr(verify_executor.subprocess, "run", _fake_run(rec))
    result = _run_one_test_check("cmd: npm test", project_root=tmp_path)
    assert rec["argv"] == ["npm", "test"]
    assert rec["cwd"] == str(tmp_path)
    assert result["passed"] is True


def test_bare_nodeid_uses_ds_interpreter_pytest_backcompat(monkeypatch, tmp_path: Path):
    rec: dict = {}
    monkeypatch.setattr(verify_executor.subprocess, "run", _fake_run(rec))
    _run_one_test_check("tests/unit/test_x.py::test_y", project_root=tmp_path)
    assert rec["argv"] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/unit/test_x.py::test_y",
        "-q",
        "--tb=short",
        "--no-header",
    ]
    assert rec["cwd"] == str(tmp_path)


def test_bare_nodeid_cwd_none_when_no_project_root(monkeypatch):
    rec: dict = {}
    monkeypatch.setattr(verify_executor.subprocess, "run", _fake_run(rec))
    _run_one_test_check("tests/unit/test_x.py::test_y")
    assert rec["cwd"] is None  # falls back to the process cwd (the DS repo)


def test_cmd_empty_is_an_error(tmp_path: Path):
    result = _run_one_test_check("cmd:   ", project_root=tmp_path)
    assert result["passed"] is False
    assert "empty command" in (result["error"] or "")


def test_run_executable_checks_threads_project_root(monkeypatch, tmp_path: Path):
    rec: dict = {}
    monkeypatch.setattr(verify_executor.subprocess, "run", _fake_run(rec))
    tasks = [{"title": "verify", "acceptance_criteria": "TEST-CHECK: cmd: pytest platform/tests"}]
    results = run_executable_checks(tasks, tmp_path / "studio.db", project_root=tmp_path)
    assert results["verify"][0]["kind"] == "TEST-CHECK"
    assert results["verify"][0]["passed"] is True
    assert rec["argv"] == ["pytest", "platform/tests"]
    assert rec["cwd"] == str(tmp_path)
