"""WO-HS2: Wire context-pressure -> handoff -> auto-spawn (high-context auto-continuation).

Proves:
  1. handle_handoff() delegates DB write to _write_handoff_packet_to_db
  2. _write_handoff_packet_to_db calls insert_handoff and writes pending-handoff.json pointer
  3. on-context-threshold calls handle_handoff for band=="handoff", not compact_warning
  4. on-context-threshold calls handle_compact_warning for band=="compact", not handle_handoff
  5. _dispatch_handoff_continuation reads pending-handoff.json; spawns `claude "resume:"` (no content)
  6. _dispatch_handoff_continuation discards stale pointers (> 120 s)
  7. find_latest_handoff_db marks the handoff consumed after loading
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.runtime_reliability


# ── helpers ────────────────────────────────────────────────────────────────────


def _hook_path(name: str) -> Path:
    return Path(__file__).resolve().parents[2] / "runtime" / "hooks" / "meta" / name


# ── Task 1: handle_handoff -> DB write ────────────────────────────────────────


def test_handle_handoff_calls_write_packet_to_db(tmp_path: Path) -> None:
    """handle_handoff() must call _write_handoff_packet_to_db when sentinel is absent."""
    projects = tmp_path / "projects"
    projects.mkdir()

    with (
        patch("control.context.monitor._write_handoff_packet_to_db", return_value=42) as mock_db,
        patch("control.context.monitor.write_handoff", return_value=None),
        patch("control.context.monitor.write_recap"),
        patch("control.context.monitor.draft_handoff_lesson"),
        patch("control.context.monitor.git_context", return_value="branch: main"),
    ):
        from control.context import monitor

        monitor.handle_handoff(projects, "sess-001", tmp_path, "~75%", 75.0, True)

    mock_db.assert_called_once_with("sess-001", tmp_path)


def test_write_handoff_packet_inserts_and_writes_pointer(tmp_path: Path) -> None:
    """_write_handoff_packet_to_db must insert into raw_handoffs and write pending-handoff.json."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    with (
        patch("core.event_store.studio_db.insert_handoff", return_value=42) as mock_insert,
        patch(
            "core.sdlc.cwd_resolver.resolve_project_from_cwd",
            return_value=MagicMock(project_id="proj-abc"),
        ),
        patch("core.config.paths.state_dir", return_value=state_dir),
        patch(
            "subprocess.run",
            return_value=MagicMock(stdout="main", returncode=0),
        ),
    ):
        from control.context import monitor

        result = monitor._write_handoff_packet_to_db("sess-001", tmp_path)

    assert result == 42
    assert mock_insert.call_args[0][0] == "sess-001"
    assert mock_insert.call_args[0][2] == "context threshold handoff"

    pointer = state_dir / "pending-handoff.json"
    assert pointer.is_file()
    data = json.loads(pointer.read_text(encoding="utf-8"))
    assert data["handoff_id"] == 42
    assert data["session_id"] == "sess-001"
    assert data["status"] == "pending"


def test_write_handoff_packet_returns_none_on_failure(tmp_path: Path) -> None:
    """_write_handoff_packet_to_db returns None without raising when insert_handoff fails."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    with (
        patch("core.event_store.studio_db.insert_handoff", return_value=None),
        patch("core.sdlc.cwd_resolver.resolve_project_from_cwd", return_value=None),
        patch("core.config.paths.state_dir", return_value=state_dir),
        patch("subprocess.run", return_value=MagicMock(stdout="", returncode=0)),
    ):
        from control.context import monitor

        result = monitor._write_handoff_packet_to_db("sess-fail", tmp_path)

    assert result is None


# ── Task 2+3: threshold hook dispatches handoff band correctly ─────────────────


def test_handoff_band_dispatches_to_handle_handoff(tmp_path: Path) -> None:
    """on-context-threshold calls handle_handoff (not compact_warning) for band=='handoff'."""
    path = _hook_path("on-context-threshold.py")
    if not path.is_file():
        pytest.skip("hook not found")

    from control.execution.dispatch_helpers import load_module

    mock_monitor = MagicMock()
    mock_monitor.read_bridge_pct.return_value = 78.0
    mock_monitor.pct_to_band.return_value = ("handoff", "~78%")
    mock_monitor.projects_dir_for_cwd.return_value = tmp_path / "projects"

    payload = json.dumps({"session_id": "sess-h", "cwd": str(tmp_path)})
    mod = load_module("_on_ctx_thresh_handoff", path)
    with (
        patch("sys.stdin", io.StringIO(payload)),
        patch.object(mod, "_load_monitor", return_value=mock_monitor),
    ):
        mod.main()

    mock_monitor.handle_handoff.assert_called_once()
    mock_monitor.handle_compact_warning.assert_not_called()


def test_compact_band_dispatches_to_compact_warning(tmp_path: Path) -> None:
    """on-context-threshold calls handle_compact_warning (not handle_handoff) for band=='compact'."""
    path = _hook_path("on-context-threshold.py")
    if not path.is_file():
        pytest.skip("hook not found")

    from control.execution.dispatch_helpers import load_module

    mock_monitor = MagicMock()
    mock_monitor.read_bridge_pct.return_value = 72.0
    mock_monitor.pct_to_band.return_value = ("compact", "~72%")
    mock_monitor.projects_dir_for_cwd.return_value = tmp_path / "projects"

    payload = json.dumps({"session_id": "sess-c", "cwd": str(tmp_path)})
    mod = load_module("_on_ctx_thresh_compact", path)
    with (
        patch("sys.stdin", io.StringIO(payload)),
        patch.object(mod, "_load_monitor", return_value=mock_monitor),
    ):
        mod.main()

    mock_monitor.handle_compact_warning.assert_called_once()
    mock_monitor.handle_handoff.assert_not_called()


# ── Task 2: dispatch spawns reference, not content ────────────────────────────


def _load_dispatch_mod(suffix: str) -> object:
    path = _hook_path("on-stop-dispatch.py")
    if not path.is_file():
        pytest.skip("hook not found")
    from control.execution.dispatch_helpers import load_module

    return load_module(f"_on_stop_dispatch_{suffix}", path)


def test_dispatch_spawns_resume_reference(tmp_path: Path) -> None:
    """_dispatch_handoff_continuation spawns `claude "resume:"` — no content in argv."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "pending-handoff.json").write_text(
        json.dumps(
            {
                "handoff_id": 99,
                "session_id": "sess-abc",
                "triggered_at": time.time(),
                "status": "pending",
                "cwd": str(tmp_path),
            }
        ),
        encoding="utf-8",
    )

    spawned: list[str] = []
    mod = _load_dispatch_mod("ref")
    mod.STATE_DIR = state_dir
    mod._spawn_new_session = lambda cmd, cwd: spawned.append(cmd)

    mod._dispatch_handoff_continuation()

    assert spawned == ['claude "resume:"']
    assert not (state_dir / "pending-handoff.json").exists()


def test_dispatch_no_content_in_argv(tmp_path: Path) -> None:
    """Spawned command must not contain 'Continue from handoff' (old content-passing pattern)."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "pending-handoff.json").write_text(
        json.dumps(
            {
                "handoff_id": 55,
                "session_id": "sess-xyz",
                "triggered_at": time.time(),
                "status": "pending",
                "cwd": str(tmp_path),
            }
        ),
        encoding="utf-8",
    )

    spawned: list[str] = []
    mod = _load_dispatch_mod("nocontent")
    mod.STATE_DIR = state_dir
    mod._spawn_new_session = lambda cmd, cwd: spawned.append(cmd)

    mod._dispatch_handoff_continuation()

    assert len(spawned) == 1
    assert "Continue from handoff:" not in spawned[0]


def test_dispatch_discards_stale_pointer(tmp_path: Path) -> None:
    """_dispatch_handoff_continuation must skip and delete a pointer older than 120 s."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    ptr = state_dir / "pending-handoff.json"
    ptr.write_text(
        json.dumps(
            {
                "handoff_id": 77,
                "session_id": "sess-stale",
                "triggered_at": time.time() - 200,
                "status": "pending",
                "cwd": str(tmp_path),
            }
        ),
        encoding="utf-8",
    )

    spawned: list[str] = []
    mod = _load_dispatch_mod("stale")
    mod.STATE_DIR = state_dir
    mod._spawn_new_session = lambda cmd, cwd: spawned.append(cmd)

    mod._dispatch_handoff_continuation()

    assert spawned == []
    assert not ptr.exists()


def test_dispatch_no_spawn_without_handoff_id(tmp_path: Path) -> None:
    """_dispatch_handoff_continuation must not spawn when handoff_id is missing."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "pending-handoff.json").write_text(
        json.dumps({"session_id": "sess-noid", "triggered_at": time.time(), "status": "pending"}),
        encoding="utf-8",
    )

    spawned: list[str] = []
    mod = _load_dispatch_mod("noid")
    mod.STATE_DIR = state_dir
    mod._spawn_new_session = lambda cmd, cwd: spawned.append(cmd)

    mod._dispatch_handoff_continuation()

    assert spawned == []


# ── Task 4: no handoff-latest.json dependency ─────────────────────────────────


def test_dispatch_skips_when_no_pending_file(tmp_path: Path) -> None:
    """_dispatch_handoff_continuation is a no-op when pending-handoff.json is absent."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    # No pending-handoff.json written

    spawned: list[str] = []
    mod = _load_dispatch_mod("nopending")
    mod.STATE_DIR = state_dir
    mod._spawn_new_session = lambda cmd, cwd: spawned.append(cmd)

    mod._dispatch_handoff_continuation()

    assert spawned == []


# ── Task 3: find_latest_handoff_db marks consumed ────────────────────────────


def test_find_latest_handoff_db_marks_consumed() -> None:
    """find_latest_handoff_db must call mark_handoff_consumed after loading a handoff."""
    with (
        patch("interfaces.cli.resume_from_handoff._connect") as mock_connect,
        patch(
            "interfaces.cli.resume_from_handoff.load_handoff_from_db",
            return_value={"handoff_id": 7, "topic": "test"},
        ),
        patch("interfaces.cli.resume_from_handoff.mark_handoff_consumed") as mock_mark,
    ):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (7, "sess-consume-me")
        mock_connect.return_value = conn

        import importlib

        rfh = importlib.import_module("interfaces.cli.resume_from_handoff")
        result = rfh.find_latest_handoff_db()

    assert result is not None
    mock_mark.assert_called_once_with("sess-consume-me")


def test_find_latest_handoff_db_no_mark_when_no_handoff() -> None:
    """find_latest_handoff_db must not call mark_handoff_consumed when no unconsumed handoff exists."""
    with (
        patch("interfaces.cli.resume_from_handoff._connect") as mock_connect,
        patch("interfaces.cli.resume_from_handoff.mark_handoff_consumed") as mock_mark,
    ):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        mock_connect.return_value = conn

        import importlib

        rfh = importlib.import_module("interfaces.cli.resume_from_handoff")
        result = rfh.find_latest_handoff_db()

    assert result is None
    mock_mark.assert_not_called()
