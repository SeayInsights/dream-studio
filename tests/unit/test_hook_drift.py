"""WO-HOOK-DRIFT-STOP: full hook-tree drift detection + stop-hook re-block.

The 2026-08-18 audit found (1) the doctor freshness check compared only 2 of
~38 projected files — runtime/lib/enforcement.py, imported by BOTH enforce
hooks, could silently drift — and (2) the stop hook blocked exactly once, so
the weakest remediation for unrecorded work was simply stopping again.
"""

from __future__ import annotations

import io
import json
import runpy
import sqlite3
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EDIT_HOOK = REPO_ROOT / "runtime" / "hooks" / "meta" / "on-edit-enforce.py"
STOP_HOOK = REPO_ROOT / "runtime" / "hooks" / "meta" / "on-stop-enforce.py"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.health.doctor_checks import _check_hook_freshness  # noqa: E402
from core.health.doctor_shared import projected_hook_relpaths  # noqa: E402
from runtime.lib import enforcement  # noqa: E402

PROJECT_ID = "11111111-1111-1111-1111-111111111111"
WO_ID = "22222222-2222-2222-2222-222222222222"


# ── drift manifest ──────────────────────────────────────────────────────────────


def test_manifest_covers_the_whole_projected_tree():
    """The freshness manifest enumerates what the projection sync copies — not
    a hardcoded 2-file list."""
    rels = projected_hook_relpaths(REPO_ROOT)
    assert "runtime/hooks/meta/on-edit-enforce.py" in rels
    assert "runtime/hooks/meta/on-stop-enforce.py" in rels
    assert "runtime/lib/enforcement.py" in rels
    assert "runtime/session_config.py" in rels
    assert len(rels) > 10, f"manifest suspiciously small: {len(rels)} files"


def _mini_tree(root: Path, content: str) -> None:
    (root / "runtime" / "hooks" / "meta").mkdir(parents=True, exist_ok=True)
    (root / "runtime" / "lib").mkdir(parents=True, exist_ok=True)
    (root / "runtime" / "hooks" / "meta" / "on-edit-enforce.py").write_text(
        "# hook\n", encoding="utf-8"
    )
    (root / "runtime" / "lib" / "enforcement.py").write_text(content, encoding="utf-8")


def test_enforcement_lib_drift_detected(tmp_path):
    """A stale deployed runtime/lib/enforcement.py is flagged — previously the
    library both enforce hooks import was excluded from the drift check."""
    source_root = tmp_path / "src"
    claude_dir = tmp_path / "claude"
    _mini_tree(source_root, "CANONICAL = 2\n")
    _mini_tree(claude_dir / "hooks", "CANONICAL = 1\n")  # stale deployed copy

    result = _check_hook_freshness(source_root, claude_dir)
    assert result["ok"] is False
    assert "runtime/lib/enforcement.py" in result["stale"]

    # Sync the copy: check comes back clean (CRLF-insensitive — deployed CRLF
    # vs canonical LF compares equal). Bytes written directly so the platform's
    # newline translation cannot distort the fixture.
    (claude_dir / "hooks" / "runtime" / "lib" / "enforcement.py").write_bytes(b"CANONICAL = 2\r\n")
    (source_root / "runtime" / "lib" / "enforcement.py").write_bytes(b"CANONICAL = 2\n")
    result = _check_hook_freshness(source_root, claude_dir)
    assert result["ok"] is True, result


# ── stop-hook re-block ──────────────────────────────────────────────────────────

_AUTHORITY_DDL = """
CREATE TABLE business_projects (
    project_id TEXT, name TEXT, status TEXT, project_path TEXT
);
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


@pytest.fixture
def env(tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    (project_dir / "src").mkdir(parents=True)

    authority = tmp_path / "studio.db"
    con = sqlite3.connect(authority)
    con.executescript(_AUTHORITY_DDL)
    con.execute(
        "INSERT INTO business_projects VALUES (?, 'TestProj', 'active', ?)",
        (PROJECT_ID, str(project_dir)),
    )
    con.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, title, status, started_at, created_at, sequence_order)"
        " VALUES (?, ?, 'WO-ACTIVE', 'in_progress', '2026-01-01T00:00:00Z',"
        " '2026-01-01T00:00:00Z', 0)",
        (WO_ID, PROJECT_ID),
    )
    con.commit()
    con.close()

    files_db = tmp_path / "files.db"
    con = sqlite3.connect(files_db)
    con.executescript("CREATE TABLE ds_files (file_id TEXT, name TEXT, created_at TEXT);")
    con.commit()
    con.close()

    monkeypatch.setattr(enforcement, "AUTHORITY_DB", authority)
    monkeypatch.setattr(enforcement, "FILES_DB", files_db)
    monkeypatch.setattr(enforcement, "SESSION_DIR", tmp_path / "enforce")
    monkeypatch.setattr(enforcement, "TEMP_ROOT", tmp_path / "nonexistent-temp")
    monkeypatch.setattr(enforcement, "DS_HOME", tmp_path / "nonexistent-ds-home")
    monkeypatch.delenv("DS_ENFORCE", raising=False)
    monkeypatch.delenv("DS_ENFORCE_TIER", raising=False)
    return {"tmp": tmp_path, "project": project_dir, "authority": authority}


@pytest.fixture(autouse=True)
def captured(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        "core.event_store.event_writer.insert_hook_execution",
        lambda **kw: calls.append(kw),
    )
    return calls


def _run_hook(hook: Path, payload: dict) -> str:
    stdin, out = sys.stdin, io.StringIO()
    sys.stdin = io.StringIO(json.dumps(payload))
    try:
        with redirect_stdout(out):
            runpy.run_path(str(hook), run_name="__main__")
    finally:
        sys.stdin = stdin
    return out.getvalue().strip()


def _seed_source_session(env) -> None:
    """Record a source edit (via the edit hook) so the stop hook has work to check."""
    out = _run_hook(
        EDIT_HOOK,
        {
            "session_id": "sess-drift",
            "tool_name": "Edit",
            "tool_input": {"file_path": str(env["project"] / "src" / "main.py")},
        },
    )
    assert out == ""  # allowed under the in_progress WO


def _stop() -> str:
    return _run_hook(STOP_HOOK, {"session_id": "sess-drift", "stop_hook_active": False})


def test_second_stop_reblocks_when_unresolved(env):
    """Unresolved work re-blocks on EVERY stop up to the cap — the old one-shot
    let the second stop through unconditionally."""
    _seed_source_session(env)
    for attempt in (1, 2, 3):
        out = _stop()
        assert out, f"stop attempt {attempt} must re-block while work is unresolved"
        assert json.loads(out)["decision"] == "block"


def test_stop_cap_allows_loudly_with_recorded_bypass(env, captured, capsys):
    """After the cap, the stop is allowed — with a stderr warning and a
    recorded stop_bypassed mark, never silently."""
    _seed_source_session(env)
    for _ in range(3):
        assert _stop()  # three blocks
    out = _stop()  # fourth attempt: allowed loudly
    assert out == ""
    bypasses = [
        c for c in captured if (c.get("trigger_context") or {}).get("rule") == "stop_bypassed"
    ]
    assert bypasses, "capped stop must record stop_bypassed"
    assert "WARNING" in capsys.readouterr().err


def test_stop_allows_once_work_is_recorded(env):
    """Re-validation on every stop: recording the work clears the block."""
    _seed_source_session(env)
    assert _stop()  # blocked
    con = sqlite3.connect(env["authority"])
    con.execute(
        "INSERT INTO business_tasks VALUES ('t1', ?, 'done', ?)",
        (WO_ID, enforcement.now_iso()),
    )
    con.commit()
    con.close()
    assert _stop() == ""  # violations resolved → allowed
