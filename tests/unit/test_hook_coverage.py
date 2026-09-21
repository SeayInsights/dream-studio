"""WO-HOOK-COVERAGE: Bash/MCP write enforcement + module_boundary advisory.

The 2026-08-18 audit found the PreToolUse matcher covered only
Edit|Write|MultiEdit|NotebookEdit — any write via Bash, PowerShell, or an MCP
write tool bypassed enforcement entirely — and module_boundary existed only as
prose, never checked by any code path.
"""

from __future__ import annotations

import io
import json
import re
import runpy
import sqlite3
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EDIT_HOOK = REPO_ROOT / "runtime" / "hooks" / "meta" / "on-edit-enforce.py"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.lib import enforcement  # noqa: E402

PROJECT_ID = "11111111-1111-1111-1111-111111111111"
WO_ID = "22222222-2222-2222-2222-222222222222"

_AUTHORITY_DDL = """
CREATE TABLE business_projects (
    project_id TEXT, name TEXT, status TEXT, project_path TEXT
);
CREATE TABLE business_work_orders (
    work_order_id TEXT, project_id TEXT, title TEXT, description TEXT,
    status TEXT, started_at TEXT, created_at TEXT, sequence_order INTEGER
);
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    (project_dir / "src").mkdir(parents=True)
    (project_dir / "other").mkdir()

    authority = tmp_path / "studio.db"
    con = sqlite3.connect(authority)
    con.executescript(_AUTHORITY_DDL)
    con.execute(
        "INSERT INTO business_projects VALUES (?, 'TestProj', 'active', ?)",
        (PROJECT_ID, str(project_dir)),
    )
    con.commit()
    con.close()

    monkeypatch.setattr(enforcement, "AUTHORITY_DB", authority)
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


def _set_wo_in_progress(authority: Path, description: str = "") -> None:
    con = sqlite3.connect(authority)
    con.execute(
        "INSERT INTO business_work_orders VALUES (?, ?, 'WO-ACTIVE', ?,"
        " 'in_progress', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', 0)",
        (WO_ID, PROJECT_ID, description),
    )
    con.commit()
    con.close()


def _run_hook(payload: dict) -> str:
    stdin, out = sys.stdin, io.StringIO()
    sys.stdin = io.StringIO(json.dumps(payload))
    try:
        with redirect_stdout(out):
            runpy.run_path(str(EDIT_HOOK), run_name="__main__")
    finally:
        sys.stdin = stdin
    return out.getvalue().strip()


def _bash(command: str, session_id: str = "s-cov") -> dict:
    return {"session_id": session_id, "tool_name": "Bash", "tool_input": {"command": command}}


# ── matcher pin ─────────────────────────────────────────────────────────────────


def test_bash_write_matcher_present():
    """hooks.json PreToolUse matcher covers Bash and MCP write tools — the audit's
    CRITICAL bypass (any Bash/PowerShell/MCP write skipped enforcement)."""
    hooks = json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    matcher = hooks["hooks"]["PreToolUse"][0]["matcher"]
    pattern = re.compile(matcher)
    for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Bash"):
        assert pattern.fullmatch(tool) or pattern.match(tool), f"{tool} must match"
    assert pattern.match("mcp__filesystem-mcp__write_file")
    assert pattern.match("mcp__filesystem-mcp__append_file")


# ── Bash write enforcement ──────────────────────────────────────────────────────


def test_bash_write_is_recorded_not_denied(env, captured):
    target = env["project"] / "src" / "main.py"
    # RECORDED, NOT DENIED. The work-order rule produces a record, and a record
    # does not need permission -- see _OBSERVE_ONLY in on-edit-enforce. What must
    # still hold is that the write is SEEN: this hook exists because a Bash/MCP
    # write was a door the Edit matcher did not cover, and that door is still
    # watched, it just no longer slams.
    out = _run_hook(_bash(f'echo broken > "{target}"'))
    assert out == "", "the write is recorded, not denied"
    assert captured, "the write was allowed but nothing was recorded"


def test_bash_write_allowed_with_wo(env):
    _set_wo_in_progress(env["authority"])
    target = env["project"] / "src" / "main.py"
    out = _run_hook(_bash(f'echo ok > "{target}"'))
    assert out == ""  # allowed


def test_bash_read_command_is_noop(env):
    out = _run_hook(_bash("git status && py -m pytest --collect-only"))
    assert out == ""


def test_bash_unparsed_write_emits_visibility_event(env, captured):
    """A write-shaped command with no resolvable target allows — visibly."""
    out = _run_hook(_bash("py -c \"open('x.py', 'w').write('hi')\""))
    assert out == ""  # fail-open stays
    bypasses = [
        c for c in captured if (c.get("trigger_context") or {}).get("rule") == "unparsed_write"
    ]
    assert bypasses, "unparsed write-shaped command must leave a visibility mark"


def test_mcp_write_file_is_recorded_not_denied(env, captured):
    """An MCP write is a door the Edit matcher does not cover, and it is still watched.

    This asserted a deny. The work-order rule now records instead -- see
    _OBSERVE_ONLY in on-edit-enforce -- so what matters here is unchanged and is
    the reason this hook exists: the write is SEEN. A silent MCP write would be
    the coverage hole; a recorded one that proceeds is the design.
    """
    target = env["project"] / "src" / "main.py"
    out = _run_hook(
        {
            "session_id": "s-cov",
            "tool_name": "mcp__filesystem-mcp__write_file",
            "tool_input": {"path": str(target)},
        }
    )
    assert out == "", "the write is recorded, not denied"
    assert captured, "the MCP write was allowed but nothing was recorded"


# ── module_boundary advisory ────────────────────────────────────────────────────


def test_out_of_boundary_edit_emits_event(env, captured):
    """An edit outside the active WO's declared module boundary is allowed but
    recorded (observe tier) — boundary was pure prose before this WO."""
    _set_wo_in_progress(
        env["authority"],
        description="Module boundary: src/main.py, tests/unit/test_main.py. Fix the thing.",
    )
    inside = env["project"] / "src" / "main.py"
    outside = env["project"] / "other" / "stray.py"

    out = _run_hook(
        {"session_id": "s-b", "tool_name": "Edit", "tool_input": {"file_path": str(inside)}}
    )
    assert out == ""
    advisories = [
        c
        for c in captured
        if (c.get("trigger_context") or {}).get("rule") == "module_boundary_advisory"
    ]
    assert advisories == [], "in-boundary edit must not record an advisory"

    out = _run_hook(
        {"session_id": "s-b", "tool_name": "Edit", "tool_input": {"file_path": str(outside)}}
    )
    assert out == ""  # advisory, never a deny
    advisories = [
        c
        for c in captured
        if (c.get("trigger_context") or {}).get("rule") == "module_boundary_advisory"
    ]
    assert advisories, "out-of-boundary edit must record an advisory observation"
    assert WO_ID[:8] in advisories[0]["trigger_context"]["would_deny_reason"]


def test_no_declared_boundary_records_nothing(env, captured):
    _set_wo_in_progress(env["authority"], description="No boundary clause here.")
    out = _run_hook(
        {
            "session_id": "s-b2",
            "tool_name": "Edit",
            "tool_input": {"file_path": str(env["project"] / "other" / "x.py")},
        }
    )
    assert out == ""
    advisories = [
        c
        for c in captured
        if (c.get("trigger_context") or {}).get("rule") == "module_boundary_advisory"
    ]
    assert advisories == []
