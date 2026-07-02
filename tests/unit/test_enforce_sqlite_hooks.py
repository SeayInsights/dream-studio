"""End-to-end behavioral gate tests for the SQLite enforcement hooks.

Drives runtime/hooks/meta/on-edit-enforce.py and on-stop-enforce.py in-process
(runpy, patched stdin/stdout — no subprocess spawn overhead on Windows) against
hermetic temp authority and files databases.

Covers WO-ENFORCE-SQLITE T6:
1. PreToolUse deny without an in_progress WO (actionable reason)
2. PreToolUse allow with an in_progress WO (+ session recording)
3. Stop block-once on edits without authority writes
4. Stop block-once on unregistered doc artifact + pass after registration
5. Fail-open on corrupted/missing authority DB
6. DS_ENFORCE=0 bypass
"""

from __future__ import annotations

import io
import json
import runpy
import sqlite3
import sys
import uuid
from contextlib import redirect_stdout
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EDIT_HOOK = REPO_ROOT / "runtime" / "hooks" / "meta" / "on-edit-enforce.py"
STOP_HOOK = REPO_ROOT / "runtime" / "hooks" / "meta" / "on-stop-enforce.py"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.lib import enforcement  # noqa: E402

PROJECT_ID = "11111111-1111-1111-1111-111111111111"
WO_IN_PROGRESS = "22222222-2222-2222-2222-222222222222"
WO_CREATED = "33333333-3333-3333-3333-333333333333"

_AUTHORITY_DDL = """
CREATE TABLE business_projects (
    project_id TEXT, name TEXT, status TEXT, project_path TEXT
);
CREATE TABLE business_milestones (milestone_id TEXT, order_index INTEGER);
CREATE TABLE business_work_orders (
    work_order_id TEXT, project_id TEXT, milestone_id TEXT, title TEXT,
    status TEXT, started_at TEXT, closed_at TEXT, created_at TEXT,
    sequence_order INTEGER
);
CREATE TABLE business_tasks (
    task_id TEXT, work_order_id TEXT, status TEXT, updated_at TEXT
);
CREATE TABLE business_canonical_events (
    event_id TEXT, work_order_id TEXT, event_type TEXT,
    event_timestamp TEXT, received_at TEXT
);
"""

_FILES_DDL = "CREATE TABLE ds_files (file_id TEXT, name TEXT, created_at TEXT);"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Hermetic enforcement environment: temp project, authority DB, files DB."""
    project_dir = tmp_path / "proj"
    (project_dir / "src").mkdir(parents=True)
    (project_dir / "docs").mkdir()
    (project_dir / ".planning" / "personal").mkdir(parents=True)
    (project_dir / ".planning" / "audits").mkdir()

    authority = tmp_path / "studio.db"
    con = sqlite3.connect(authority)
    con.executescript(_AUTHORITY_DDL)
    con.execute(
        "INSERT INTO business_projects VALUES (?, 'TestProj', 'active', ?)",
        (PROJECT_ID, str(project_dir)),
    )
    con.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, title, status, created_at, sequence_order)"
        " VALUES (?, ?, 'WO-NEXT: do the thing', 'created', '2026-01-01T00:00:00Z', 1)",
        (WO_CREATED, PROJECT_ID),
    )
    con.commit()
    con.close()

    files_db = tmp_path / "files.db"
    con = sqlite3.connect(files_db)
    con.executescript(_FILES_DDL)
    con.commit()
    con.close()

    monkeypatch.setattr(enforcement, "AUTHORITY_DB", authority)
    monkeypatch.setattr(enforcement, "FILES_DB", files_db)
    monkeypatch.setattr(enforcement, "SESSION_DIR", tmp_path / "enforce")
    # tmp_path lives under the system temp root, which is exempt by default —
    # point the exemption elsewhere so the temp project is enforceable.
    monkeypatch.setattr(enforcement, "TEMP_ROOT", tmp_path / "nonexistent-temp")
    monkeypatch.setattr(enforcement, "DS_HOME", tmp_path / "nonexistent-ds-home")
    monkeypatch.delenv("DS_ENFORCE", raising=False)

    return {"tmp": tmp_path, "project": project_dir, "authority": authority, "files": files_db}


def _set_wo_in_progress(authority: Path) -> None:
    con = sqlite3.connect(authority)
    con.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, title, status, started_at, created_at, sequence_order)"
        " VALUES (?, ?, 'WO-ACTIVE: current work', 'in_progress',"
        " '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', 0)",
        (WO_IN_PROGRESS, PROJECT_ID),
    )
    con.commit()
    con.close()


def _run_hook(hook: Path, payload: dict) -> str:
    """Run a hook script in-process with the payload on stdin; return stdout."""
    stdin, out = sys.stdin, io.StringIO()
    sys.stdin = io.StringIO(json.dumps(payload))
    try:
        with redirect_stdout(out):
            runpy.run_path(str(hook), run_name="__main__")
    finally:
        sys.stdin = stdin
    return out.getvalue().strip()


def _edit_payload(file_path: Path, session_id: str = "sess-test") -> dict:
    return {
        "session_id": session_id,
        "tool_name": "Edit",
        "tool_input": {"file_path": str(file_path)},
    }


def _stop_payload(session_id: str = "sess-test", active: bool = False) -> dict:
    return {"session_id": session_id, "stop_hook_active": active}


def _session_data(session_id: str = "sess-test") -> dict | None:
    return enforcement.load_session(session_id)


class TestPreToolUseEnforcement:
    def test_deny_without_in_progress_wo(self, env):
        out = _run_hook(EDIT_HOOK, _edit_payload(env["project"] / "src" / "main.py"))
        decision = json.loads(out)["hookSpecificOutput"]
        assert decision["permissionDecision"] == "deny"
        assert WO_CREATED in decision["permissionDecisionReason"]
        assert "work-order start" in decision["permissionDecisionReason"]

    def test_allow_with_in_progress_wo_and_records_session(self, env):
        _set_wo_in_progress(env["authority"])
        out = _run_hook(EDIT_HOOK, _edit_payload(env["project"] / "src" / "main.py"))
        assert out == ""
        data = _session_data()
        assert data is not None
        assert data["source_edits"][0]["work_order_id"] == WO_IN_PROGRESS

    def test_exempt_paths_never_denied(self, env):
        for rel in (".planning/personal/notes.md", ".git/config", ".venv/pyvenv.cfg"):
            out = _run_hook(EDIT_HOOK, _edit_payload(env["project"] / Path(rel)))
            assert out == "", rel
        assert _session_data() is None

    def test_doc_artifact_allowed_and_recorded(self, env):
        out = _run_hook(EDIT_HOOK, _edit_payload(env["project"] / "docs" / "guide.md"))
        assert out == ""
        data = _session_data()
        assert data["doc_edits"][0]["path"].endswith("guide.md")

    def test_unregistered_path_allowed(self, env):
        outside = env["tmp"] / "elsewhere" / "file.py"
        assert _run_hook(EDIT_HOOK, _edit_payload(outside)) == ""

    def test_fail_open_on_corrupt_authority(self, env):
        env["authority"].write_bytes(b"this is not a sqlite database at all")
        out = _run_hook(EDIT_HOOK, _edit_payload(env["project"] / "src" / "main.py"))
        assert out == ""

    def test_fail_open_on_missing_authority(self, env, monkeypatch):
        monkeypatch.setattr(enforcement, "AUTHORITY_DB", env["tmp"] / "missing.db")
        out = _run_hook(EDIT_HOOK, _edit_payload(env["project"] / "src" / "main.py"))
        assert out == ""

    def test_ds_enforce_zero_bypasses(self, env, monkeypatch):
        monkeypatch.setenv("DS_ENFORCE", "0")
        out = _run_hook(EDIT_HOOK, _edit_payload(env["project"] / "src" / "main.py"))
        assert out == ""


class TestStopEnforcement:
    def _seed_source_session(self, env) -> None:
        _set_wo_in_progress(env["authority"])
        assert _run_hook(EDIT_HOOK, _edit_payload(env["project"] / "src" / "main.py")) == ""

    def test_block_once_without_authority_write(self, env):
        self._seed_source_session(env)
        out = _run_hook(STOP_HOOK, _stop_payload())
        decision = json.loads(out)
        assert decision["decision"] == "block"
        assert "task-done" in decision["reason"]
        assert _run_hook(STOP_HOOK, _stop_payload()) == ""  # never blocks twice

    def test_pass_with_task_completed_event(self, env):
        self._seed_source_session(env)
        con = sqlite3.connect(env["authority"])
        con.execute(
            "INSERT INTO business_canonical_events VALUES (?, ?, 'task.completed', ?, ?)",
            (str(uuid.uuid4()), WO_IN_PROGRESS, enforcement.now_iso(), enforcement.now_iso()),
        )
        con.commit()
        con.close()
        assert _run_hook(STOP_HOOK, _stop_payload()) == ""
        assert _session_data() is None  # session file cleaned up on pass

    def test_pass_with_done_task_row(self, env):
        self._seed_source_session(env)
        con = sqlite3.connect(env["authority"])
        con.execute(
            "INSERT INTO business_tasks VALUES (?, ?, 'done', ?)",
            (str(uuid.uuid4()), WO_IN_PROGRESS, enforcement.now_iso()),
        )
        con.commit()
        con.close()
        assert _run_hook(STOP_HOOK, _stop_payload()) == ""

    def test_doc_artifact_blocks_then_passes_after_registration(self, env):
        _set_wo_in_progress(env["authority"])
        doc = env["project"] / ".planning" / "audits" / "report.md"
        assert _run_hook(EDIT_HOOK, _edit_payload(doc)) == ""

        out = _run_hook(STOP_HOOK, _stop_payload())
        decision = json.loads(out)
        assert decision["decision"] == "block"
        assert "files add" in decision["reason"]

        # Remediation: register the artifact AFTER the edit (`ds files add`
        # flow) — the registration must postdate the session's last edit.
        con = sqlite3.connect(env["files"])
        con.execute(
            "INSERT INTO ds_files VALUES (?, ?, ?)",
            (str(uuid.uuid4()), ".planning/audits/report.md", enforcement.now_iso()),
        )
        con.commit()
        con.close()
        # Fresh session, no re-edit: the registration now covers the artifact.
        session = enforcement.load_session("sess-test")
        session["stop_blocked_at"] = None
        enforcement.save_session("sess-test", session)
        assert _run_hook(STOP_HOOK, _stop_payload()) == ""

    def test_doc_reedit_after_registration_blocks_again(self, env):
        _set_wo_in_progress(env["authority"])
        doc = env["project"] / ".planning" / "audits" / "report.md"
        con = sqlite3.connect(env["files"])
        con.execute(
            "INSERT INTO ds_files VALUES (?, ?, ?)",
            (str(uuid.uuid4()), ".planning/audits/report.md", enforcement.now_iso()),
        )
        con.commit()
        con.close()
        # Edit lands after the registration — the record is stale for this content.
        assert _run_hook(EDIT_HOOK, _edit_payload(doc)) == ""
        out = _run_hook(STOP_HOOK, _stop_payload())
        assert json.loads(out)["decision"] == "block"

    def test_stop_hook_active_never_blocks(self, env):
        self._seed_source_session(env)
        assert _run_hook(STOP_HOOK, _stop_payload(active=True)) == ""

    def test_no_session_file_allows(self, env):
        assert _run_hook(STOP_HOOK, _stop_payload("never-seen")) == ""

    def test_ds_enforce_zero_bypasses(self, env, monkeypatch):
        self._seed_source_session(env)
        monkeypatch.setenv("DS_ENFORCE", "0")
        assert _run_hook(STOP_HOOK, _stop_payload()) == ""

    def test_fail_open_on_corrupt_authority(self, env):
        self._seed_source_session(env)
        env["authority"].write_bytes(b"garbage")
        assert _run_hook(STOP_HOOK, _stop_payload()) == ""


class TestFilesCliDocstoreWritePath:
    """T3 + WO-FILES-DISPATCH regression: ds files add/list must be reachable
    from the CLI and write through core/files/store.py."""

    @pytest.fixture
    def files_db(self, tmp_path, monkeypatch):
        from core.files import store

        db = tmp_path / "files.db"
        monkeypatch.setattr(store, "files_db_path", lambda: db)
        return db

    def test_files_add_stores_and_list_shows(self, tmp_path, files_db, capsys):
        from interfaces.cli import ds

        artifact = tmp_path / "artifact.md"
        artifact.write_text("evidence content", encoding="utf-8")

        assert ds.main(["files", "add", str(artifact), "--project-id", PROJECT_ID]) == 0
        added = json.loads(capsys.readouterr().out)
        assert added["ok"] is True and added["file_id"]

        assert ds.main(["files", "list", "--project-id", PROJECT_ID]) == 0
        assert "artifact.md" in capsys.readouterr().out

    def test_files_add_invalid_path_fails_cleanly(self, files_db, capsys):
        from interfaces.cli import ds

        assert ds.main(["files", "add", "does/not/exist.md"]) == 1
        out = json.loads(capsys.readouterr().out)
        assert out["ok"] is False and "not a file" in out["error"]
