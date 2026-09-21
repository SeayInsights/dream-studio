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
    description TEXT, status TEXT, started_at TEXT, closed_at TEXT, created_at TEXT,
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
    # STATE_DIR was left pointing at the operator's real ~/.dream-studio/state.
    # It went unnoticed while nothing in the enforce path wrote through it; the
    # queued hook-execution record does, so the gap is closed rather than worked
    # around in the one test that happened to expose it.
    monkeypatch.setattr(enforcement, "STATE_DIR", tmp_path / "state")
    monkeypatch.delenv("DS_ENFORCE", raising=False)

    return {"tmp": tmp_path, "project": project_dir, "authority": authority, "files": files_db}


@pytest.fixture(autouse=True)
def captured_hook_executions(monkeypatch):
    """Read enforce-hook telemetry back off the append-only queue.

    WO-HOOK-ENFORCE-EXEC-STATS wraps both enforce hooks so their executions are
    recorded. This used to patch `insert_hook_execution` and assert on the call.

    THE HOOKS NO LONGER WRITE THAT ROW INLINE. `insert_hook_execution` pulls the
    event store, which pulls pydantic and jsonschema: 282 imports, measured at
    259 ms of the 335 ms that on-edit-enforce spent BLOCKING every Edit and Write.
    The enforcement decision itself is ~55 ms, so four fifths of the wait was the
    hook recording that you had asked. It now appends a finished record to
    hookq.jsonl and the next UserPromptSubmit or Stop writes the row.

    The behaviour under test is unchanged -- each hook still records its own
    execution, with its own name and decision -- so this reads the queue instead
    of the call, and returns the same dict shape the assertions already expect.
    """
    import json as _json

    from runtime.lib import enforcement as _enf

    class _QueueView(list):
        """Materialises on read, so a test can run the hook then inspect."""

        def _load(self):
            # Through the module attribute the env fixture patches, so this reads
            # the tmp state dir and never the operator's real one.
            path = _enf.STATE_DIR / "hookq.jsonl"
            if not path.is_file():
                return []
            out = []
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = _json.loads(line)
                    if rec.get("event") == "hook.execution":
                        out.append(_json.loads(rec["payload"]))
                except (ValueError, KeyError):
                    continue
            return out

        def __iter__(self):
            return iter(self._load())

        def __len__(self):
            return len(self._load())

    return _QueueView()


def _observed() -> bool:
    """Did the stop hook record an observation for the work it did not block?"""
    queue = enforcement.STATE_DIR / "hookq.jsonl"
    if not queue.is_file():
        return False
    return "observe" in queue.read_text(encoding="utf-8", errors="replace")


def _set_wo_in_progress(authority: Path) -> None:
    # DECLARES A BOUNDARY covering the edited file, because attribution by boundary is
    # now what makes the stop hook block. A work order with no boundary can only be
    # attributed by recency -- a guess -- and a guess no longer supports a demand for an
    # authority write. These tests are about the WRITE requirement, not about attribution,
    # so they supply the evidence a real work order now must carry: --module-boundary is
    # required at the create door, so every work order authored from here on has one.
    con = sqlite3.connect(authority)
    con.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, title, status, started_at, created_at,"
        "  sequence_order, description)"
        " VALUES (?, ?, 'WO-ACTIVE: current work', 'in_progress',"
        " '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', 0,"
        " 'Current work. Module boundary: src/.')",
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
    def test_edit_without_an_in_progress_wo_is_recorded_not_denied(self, env):
        """TRACKING, NOT PERMISSION. This asserted a deny.

        The rule exists to produce a RECORD of what the session touched, and a record
        does not need permission -- the hook already knows the file and which work
        orders could claim it. Demanding it produced the opposite: measured across one
        session, eleven blocks on work the operator had directed, and a documented
        remedy of DS_ENFORCE=0, which turns the record off entirely.

        So the edit proceeds AND the observation lands. The second half is the half
        that matters: if this stopped recording, the tracking would be gone and
        nothing would say so.
        """
        out = _run_hook(EDIT_HOOK, _edit_payload(env["project"] / "src" / "main.py"))
        assert out == "", "the edit must not be denied"

        from runtime.lib import enforcement as _enf

        queue = _enf.STATE_DIR / "hookq.jsonl"
        assert queue.is_file(), "the edit was allowed but nothing was recorded"
        blob = queue.read_text(encoding="utf-8", errors="replace")
        assert "observe" in blob, "the observation carries no decision"
        assert "authority_source_edit" in blob, "the rule that fired is not named"

    def test_allow_with_in_progress_wo_and_records_session(self, env):
        _set_wo_in_progress(env["authority"])
        out = _run_hook(EDIT_HOOK, _edit_payload(env["project"] / "src" / "main.py"))
        assert out == ""
        data = _session_data()
        assert data is not None
        assert data["source_edits"][0]["work_order_id"] == WO_IN_PROGRESS

    def test_exempt_paths_never_denied(self, env):
        for rel in (".git/config", ".venv/pyvenv.cfg"):
            out = _run_hook(EDIT_HOOK, _edit_payload(env["project"] / Path(rel)))
            assert out == "", rel
        assert _session_data() is None

    def test_planning_disk_writes_denied_zero_disk(self, env):
        # WO-FILESDB-P3: .planning/** (incl. personal) is docstore-only — disk writes
        # are denied and redirected to `ds files write`, regardless of work-order state.
        for rel in (".planning/personal/notes.md", ".planning/audits/report.md"):
            out = _run_hook(EDIT_HOOK, _edit_payload(env["project"] / Path(rel)))
            decision = json.loads(out)["hookSpecificOutput"]
            assert decision["permissionDecision"] == "deny", rel
            assert "ds files write" in decision["permissionDecisionReason"], rel
        assert _session_data() is None  # denied edits are not recorded

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
        # RECORDED, NOT BLOCKED. This asserted decision == "block".
        # The unrecorded-work rule produces a record; a record does not need
        # permission. What must still hold is that the observation LANDS -- a
        # rule that stopped blocking and also stopped recording would be a
        # silent loss of the tracking, with nothing to say so.
        out = _run_hook(STOP_HOOK, _stop_payload())
        assert out == "", "the stop must not be blocked"
        assert _observed(), "the stop was allowed but nothing was recorded"
        # WO-HOOK-DRIFT-STOP: the old one-shot let the second stop through
        # unconditionally; unresolved work now RE-BLOCKS (capped — see
        # test_hook_drift.py for the cap + loud-allow behavior).
        assert _run_hook(STOP_HOOK, _stop_payload()) == "", "still not blocked"

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
        doc = env["project"] / "docs" / "report.md"
        assert _run_hook(EDIT_HOOK, _edit_payload(doc)) == ""

        # RECORDED, NOT BLOCKED. This asserted decision == "block".
        # The unrecorded-work rule produces a record; a record does not need
        # permission. What must still hold is that the observation LANDS -- a
        # rule that stopped blocking and also stopped recording would be a
        # silent loss of the tracking, with nothing to say so.
        out = _run_hook(STOP_HOOK, _stop_payload())
        assert out == "", "the stop must not be blocked"
        assert _observed(), "the stop was allowed but nothing was recorded"

        # Remediation: register the artifact AFTER the edit (`ds files add`
        # flow) — the registration must postdate the session's last edit.
        con = sqlite3.connect(env["files"])
        con.execute(
            "INSERT INTO ds_files VALUES (?, ?, ?)",
            (str(uuid.uuid4()), "docs/report.md", enforcement.now_iso()),
        )
        con.commit()
        con.close()
        # The first stop resolved the session and deleted it, so there is nothing
        # left to poke -- which is the point: registering the artifact is what the
        # note asked for, and a later stop has no outstanding record to mention.
        assert _run_hook(STOP_HOOK, _stop_payload()) == ""

    def test_doc_reedit_after_registration_blocks_again(self, env):
        _set_wo_in_progress(env["authority"])
        doc = env["project"] / "docs" / "report.md"
        con = sqlite3.connect(env["files"])
        con.execute(
            "INSERT INTO ds_files VALUES (?, ?, ?)",
            (str(uuid.uuid4()), "docs/report.md", enforcement.now_iso()),
        )
        con.commit()
        con.close()
        # Edit lands after the registration — the record is stale for this content.
        assert _run_hook(EDIT_HOOK, _edit_payload(doc)) == ""
        # RECORDED, NOT BLOCKED. This asserted decision == "block".
        # The unrecorded-work rule produces a record; a record does not need
        # permission. What must still hold is that the observation LANDS -- a
        # rule that stopped blocking and also stopped recording would be a
        # silent loss of the tracking, with nothing to say so.
        assert _run_hook(STOP_HOOK, _stop_payload()) == "", "the stop must not be blocked"
        assert _observed(), "the stop was allowed but nothing was recorded"

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


class TestHookExecutionTelemetry:
    """WO-HOOK-ENFORCE-EXEC-STATS: the two directly-wired enforce hooks emit
    system.hook.execution.logged so they surface in the DuckDB hook_executions
    view, without changing their deny/block/allow decision or stdout."""

    def test_edit_hook_logs_execution(self, env, captured_hook_executions):
        # No in-progress WO → deny; the hook still records its own execution.
        # The rule records instead of denying, so the recorded decision is "observe".
        # The hook still logs its own execution either way, which is what this covers.
        out = _run_hook(EDIT_HOOK, _edit_payload(env["project"] / "src" / "main.py"))
        assert out == "", "the edit is recorded, not denied"
        # TWO records now, and both are wanted: the OBSERVATION (what would have been
        # denied, with its rule) and the hook's own EXECUTION log. Under the old deny
        # path only the execution log existed, because record_observation fires solely
        # on the observe tier. Asserting a count of one would now fail for the right
        # thing happening, so this asserts the execution record specifically.
        logged = [c for c in captured_hook_executions if c["hook_name"] == "on_edit_enforce"]
        assert logged, "the hook recorded no execution"
        assert all(c["hook_type"] == "PreToolUse" for c in logged)
        decisions = {c["trigger_context"].get("decision") for c in logged}
        assert "observe" in decisions, decisions
        assert "deny" not in decisions, "the work-order rule must not deny"

    def test_stop_hook_logs_execution(self, env, captured_hook_executions):
        # Unknown session → noop decision; the hook still records its execution.
        _run_hook(STOP_HOOK, _stop_payload("never-seen"))
        logged = [c for c in captured_hook_executions if c["hook_name"] == "on_stop_enforce"]
        assert len(logged) == 1
        assert logged[0]["hook_type"] == "Stop"

    def test_both_enforce_hooks_are_distinct_hook_names(self, env, captured_hook_executions):
        _set_wo_in_progress(env["authority"])
        _run_hook(EDIT_HOOK, _edit_payload(env["project"] / "src" / "main.py"))
        _run_hook(STOP_HOOK, _stop_payload())
        names = {c["hook_name"] for c in captured_hook_executions}
        assert names == {"on_edit_enforce", "on_stop_enforce"}

    def test_ds_enforce_zero_skips_telemetry(self, env, monkeypatch, captured_hook_executions):
        # DS_ENFORCE=0 skips enforcement AND its execution telemetry — but the
        # short-circuit itself leaves a bypass mark (WO-BYPASS-TELEMETRY): the
        # ONLY records emitted are decision=bypass/rule=enforcement_disabled.
        # No execution-stats records (decision allow/deny/observe) may appear.
        monkeypatch.setenv("DS_ENFORCE", "0")
        _run_hook(EDIT_HOOK, _edit_payload(env["project"] / "src" / "main.py"))
        _run_hook(STOP_HOOK, _stop_payload())
        assert captured_hook_executions, "the DS_ENFORCE=0 short-circuit must be recorded"
        for call in captured_hook_executions:
            ctx = call.get("trigger_context") or {}
            assert ctx.get("decision") == "bypass"
            assert ctx.get("rule") == "enforcement_disabled"
