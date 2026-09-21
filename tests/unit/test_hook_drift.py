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

#: The clause edit attribution matches against. Composed the way the real emitter
#: composes it (a blank line before the clause), so the fixture exercises the same
#: format runtime/lib/enforcement.py::boundary_globs parses.
#:
#: `src/` and not `src`: the parser keeps only comma-separated parts containing a `/` or a
#: `.`, so `Module boundary: src` yields [] -- a clause that LOOKS declared and matches
#: nothing, which is the silent-wrong-answer shape. `compose_module_boundary` refuses to
#: store such a clause at the authoring door, but a hand-written one has no such guard, so
#: the trailing slash is load-bearing here.
_WO_DESCRIPTION = "Owns the sources under test." + chr(10) * 2 + "Module boundary: src/."

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
    # DECLARE THE BOUNDARY. These tests exercise the stop hook's re-block and cap
    # behaviour, and that path is only reached when the work order is PROVEN to own the
    # edit. Enforcement no longer blocks on attribution by recency -- it records an
    # observation (rule attribution_by_recency_not_enforced) and allows the stop, because
    # a guess is not evidence and blocking on absent evidence trains a bypass. Without a
    # `Module boundary:` clause the fixture's work order was attributed by recency, so
    # these three tests were silently exercising the allow path and asserting a block.
    # The clause names src/, which is where _seed_source_session edits.
    con.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, title, description, status, started_at, created_at,"
        " sequence_order)"
        " VALUES (?, ?, 'WO-ACTIVE', ?, 'in_progress', '2026-01-01T00:00:00Z',"
        " '2026-01-01T00:00:00Z', 0)",
        (WO_ID, PROJECT_ID, _WO_DESCRIPTION),
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
    # Each test gets its own queue. Without this the hook telemetry file is the
    # operator's real one, so records leak between tests AND into live state.
    monkeypatch.setattr(enforcement, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(enforcement, "TEMP_ROOT", tmp_path / "nonexistent-temp")
    monkeypatch.setattr(enforcement, "DS_HOME", tmp_path / "nonexistent-ds-home")
    monkeypatch.delenv("DS_ENFORCE", raising=False)
    monkeypatch.delenv("DS_ENFORCE_TIER", raising=False)
    return {"tmp": tmp_path, "project": project_dir, "authority": authority}


@pytest.fixture(autouse=True)
def captured(monkeypatch):
    # THE ENFORCE HOOKS NO LONGER WRITE THIS ROW INLINE. Doing so imports the event
    # store (282 modules, 259 ms) inside a hook that BLOCKS the user's action. The
    # record still happens -- it is appended to hookq.jsonl and written by the next
    # UserPromptSubmit or Stop -- so this reads it from where it now lands.
    import json as _json

    class _QueueView(list):
        def _load(self):
            path = enforcement.STATE_DIR / "hookq.jsonl"
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

        def __bool__(self):
            return bool(self._load())

        def __getitem__(self, i):
            return self._load()[i]

    return _QueueView()


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


def test_a_recorded_authority_write_leaves_nothing_outstanding(env):
    """Re-validation on every stop: recording the work clears the block."""
    _seed_source_session(env)
    con = sqlite3.connect(env["authority"])
    con.execute(
        "INSERT INTO business_tasks VALUES ('t1', ?, 'done', ?)",
        (WO_ID, enforcement.now_iso()),
    )
    con.commit()
    con.close()
    assert _stop() == ""  # violations resolved → allowed
