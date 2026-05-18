"""Tests for WS 8c-1: Global ds Entry Point."""

from __future__ import annotations

import json
import sqlite3
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── ds_entry.py existence and structure ───────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]
DS_ENTRY = REPO_ROOT / "interfaces" / "cli" / "ds_entry.py"


def test_ds_entry_exists():
    assert DS_ENTRY.is_file(), f"ds_entry.py not found at {DS_ENTRY}"


def test_ds_entry_resolves_repo_root_from_file():
    content = DS_ENTRY.read_text(encoding="utf-8")
    assert "Path(__file__).resolve()" in content
    assert "repo_root" in content or "parent.parent" in content


def test_ds_entry_adds_repo_root_to_sys_path():
    content = DS_ENTRY.read_text(encoding="utf-8")
    assert "sys.path" in content


# ── Launcher writing ───────────────────────────────────────────────────────────

def _get_write_global_launcher():
    import sys
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from integrations.installer.claude_code import _write_global_launcher
    return _write_global_launcher


def test_installer_writes_ds_cmd_on_windows(tmp_path):
    ds_home = tmp_path / ".dream-studio"
    write_global_launcher = _get_write_global_launcher()

    with patch("integrations.installer.claude_code.platform.system", return_value="Windows"):
        result = write_global_launcher(ds_home=ds_home)

    launcher_path = Path(result["launcher_path"])
    assert launcher_path.name == "ds.cmd"
    assert launcher_path.exists()


def test_installer_writes_shell_script_on_non_windows(tmp_path):
    import sys as _sys
    ds_home = tmp_path / ".dream-studio"
    write_global_launcher = _get_write_global_launcher()

    with patch("integrations.installer.claude_code.platform.system", return_value="Linux"):
        result = write_global_launcher(ds_home=ds_home)

    launcher_path = Path(result["launcher_path"])
    assert launcher_path.name == "ds"
    assert launcher_path.exists()
    # Executable bit is meaningful on Unix only
    if _sys.platform != "win32":
        file_stat = launcher_path.stat()
        assert file_stat.st_mode & stat.S_IEXEC


def test_ds_cmd_content_contains_repo_root(tmp_path):
    ds_home = tmp_path / ".dream-studio"
    write_global_launcher = _get_write_global_launcher()

    with patch("integrations.installer.claude_code.platform.system", return_value="Windows"):
        result = write_global_launcher(ds_home=ds_home)

    launcher_path = Path(result["launcher_path"])
    content = launcher_path.read_text(encoding="utf-8")
    assert "ds_entry.py" in content or "interfaces" in content


def test_install_output_contains_path_instruction(tmp_path):
    ds_home = tmp_path / ".dream-studio"
    write_global_launcher = _get_write_global_launcher()

    with patch("integrations.installer.claude_code.platform.system", return_value="Windows"):
        result = write_global_launcher(ds_home=ds_home)

    assert "PATH" in result["path_instructions"]


def test_install_output_contains_first_run_guide_when_no_active_project(tmp_path):
    ds_home = tmp_path / ".dream-studio"
    from integrations.installer.claude_code import _first_run_guide
    guide = _first_run_guide(ds_home=ds_home)
    assert guide is not None
    assert "Register your project" in guide or "register" in guide.lower()


def test_install_output_skips_first_run_guide_when_active_project_exists(tmp_path):
    ds_home = tmp_path / ".dream-studio"
    state_dir = ds_home / "state"
    state_dir.mkdir(parents=True)
    sqlite_path = state_dir / "studio.db"

    with sqlite3.connect(str(sqlite_path)) as conn:
        conn.execute(
            "CREATE TABLE ds_projects "
            "(project_id TEXT PRIMARY KEY, name TEXT, status TEXT)"
        )
        conn.execute(
            "INSERT INTO ds_projects VALUES ('test-id', 'TestProject', 'active')"
        )

    from integrations.installer.claude_code import _first_run_guide
    guide = _first_run_guide(ds_home=ds_home)
    assert guide is None


def test_dream_studio_bin_dir_created_by_installer(tmp_path):
    ds_home = tmp_path / ".dream-studio"
    assert not (ds_home / "bin").exists()
    write_global_launcher = _get_write_global_launcher()

    with patch("integrations.installer.claude_code.platform.system", return_value="Windows"):
        write_global_launcher(ds_home=ds_home)

    assert (ds_home / "bin").is_dir()


def test_install_output_contains_ingest_sessions_pointer(tmp_path):
    """Install output should mention ds memory ingest-sessions."""
    from integrations.installer.claude_code import _write_global_launcher
    # The pointer text should be in the installer's execute path.
    # We verify it exists in the module source since the execute path
    # prints it directly.
    import inspect
    import integrations.installer.claude_code as mod
    source = inspect.getsource(mod)
    assert "ingest-sessions" in source


# ── Doctor expanded checks (Slice 9c) ─────────────────────────────────────────

REPO_ROOT_9C = Path(__file__).resolve().parents[2]


def _get_doctor_status():
    import sys
    if str(REPO_ROOT_9C) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT_9C))
    from interfaces.cli.ds import _doctor_status
    return _doctor_status


def _minimal_sqlite(tmp_path: Path) -> Path:
    """Create a minimal studio.db with _schema_version table."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    db_path = state_dir / "studio.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE _schema_version (version INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO _schema_version VALUES (55)")
    return db_path


def test_doctor_checks_dispatcher_hooks_installed(tmp_path):
    """Doctor output includes dispatcher_hooks_installed key."""
    _minimal_sqlite(tmp_path)
    ds_home = tmp_path

    _doctor_status = _get_doctor_status()

    with patch("interfaces.cli.ds.Path") as mock_path_cls:
        # We only need the new check keys to exist — mock resolve_installed_runtime_paths
        pass

    # Direct call with real tmp_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths") as mock_rip:
        mock_rt = MagicMock()
        mock_rt.source_root = REPO_ROOT_9C
        mock_rt.dream_studio_home = ds_home
        mock_rt.sqlite_path = tmp_path / "state" / "studio.db"
        mock_rip.return_value = mock_rt
        with patch("interfaces.cli.ds.Path.home", return_value=tmp_path / "claude"):
            result = _doctor_status(source_root=REPO_ROOT_9C, dream_studio_home=ds_home)

    assert "dispatcher_hooks_installed" in result["checks"]
    assert isinstance(result["checks"]["dispatcher_hooks_installed"], bool)


def test_doctor_checks_skills_installed(tmp_path):
    """Doctor output includes skills_installed key with expected structure."""
    _minimal_sqlite(tmp_path)
    _doctor_status = _get_doctor_status()

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths") as mock_rip:
        mock_rt = MagicMock()
        mock_rt.source_root = REPO_ROOT_9C
        mock_rt.dream_studio_home = tmp_path
        mock_rt.sqlite_path = tmp_path / "state" / "studio.db"
        mock_rip.return_value = mock_rt
        with patch("interfaces.cli.ds.Path.home", return_value=tmp_path / "claude"):
            result = _doctor_status(source_root=REPO_ROOT_9C, dream_studio_home=tmp_path)

    si = result["checks"]["skills_installed"]
    assert "total_expected" in si
    assert "installed" in si
    assert "missing" in si
    assert isinstance(si["missing"], list)


def test_doctor_checks_agents_installed(tmp_path):
    """Doctor output includes agents_installed key with expected structure."""
    _minimal_sqlite(tmp_path)
    _doctor_status = _get_doctor_status()

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths") as mock_rip:
        mock_rt = MagicMock()
        mock_rt.source_root = REPO_ROOT_9C
        mock_rt.dream_studio_home = tmp_path
        mock_rt.sqlite_path = tmp_path / "state" / "studio.db"
        mock_rip.return_value = mock_rt
        with patch("interfaces.cli.ds.Path.home", return_value=tmp_path / "claude"):
            result = _doctor_status(source_root=REPO_ROOT_9C, dream_studio_home=tmp_path)

    ai = result["checks"]["agents_installed"]
    assert "total_expected" in ai
    assert "installed" in ai
    assert "missing" in ai


def test_doctor_checks_failed_events(tmp_path):
    """Doctor output includes failed_events key with count."""
    _minimal_sqlite(tmp_path)
    _doctor_status = _get_doctor_status()

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths") as mock_rip:
        mock_rt = MagicMock()
        mock_rt.source_root = REPO_ROOT_9C
        mock_rt.dream_studio_home = tmp_path
        mock_rt.sqlite_path = tmp_path / "state" / "studio.db"
        mock_rip.return_value = mock_rt
        with patch("interfaces.cli.ds.Path.home", return_value=tmp_path / "claude"):
            result = _doctor_status(source_root=REPO_ROOT_9C, dream_studio_home=tmp_path)

    fe = result["checks"]["failed_events"]
    assert "count" in fe
    assert isinstance(fe["count"], int)


def test_doctor_checks_version_current(tmp_path):
    """Doctor output includes version_current key with repo/installed/current fields."""
    _minimal_sqlite(tmp_path)
    _doctor_status = _get_doctor_status()

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths") as mock_rip:
        mock_rt = MagicMock()
        mock_rt.source_root = REPO_ROOT_9C
        mock_rt.dream_studio_home = tmp_path
        mock_rt.sqlite_path = tmp_path / "state" / "studio.db"
        mock_rip.return_value = mock_rt
        with patch("interfaces.cli.ds.Path.home", return_value=tmp_path / "claude"):
            result = _doctor_status(source_root=REPO_ROOT_9C, dream_studio_home=tmp_path)

    vc = result["checks"]["version_current"]
    assert "repo" in vc
    assert "installed" in vc
    assert "current" in vc
    assert isinstance(vc["current"], bool)


def test_doctor_status_is_fail_when_dispatcher_hooks_not_installed(tmp_path):
    """Doctor status must be 'fail' when dispatcher_hooks_installed is False."""
    _minimal_sqlite(tmp_path)
    _doctor_status = _get_doctor_status()

    from interfaces.cli.ds import _check_dispatcher_hooks, _check_version_current

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths") as mock_rip:
        mock_rt = MagicMock()
        mock_rt.source_root = REPO_ROOT_9C
        mock_rt.dream_studio_home = tmp_path
        mock_rt.sqlite_path = tmp_path / "state" / "studio.db"
        mock_rip.return_value = mock_rt
        with patch("interfaces.cli.ds.Path.home", return_value=tmp_path / "claude"):
            with patch("interfaces.cli.ds._check_dispatcher_hooks", return_value=False):
                with patch("interfaces.cli.ds._check_version_current",
                           return_value={"repo": "2026-05-17", "installed": "2026-05-17", "current": True}):
                    result = _doctor_status(source_root=REPO_ROOT_9C, dream_studio_home=tmp_path)

    assert result["status"] == "fail"


def test_doctor_status_is_fail_when_failed_events_nonzero(tmp_path):
    """Doctor status must be 'fail' when failed_events count > 0."""
    _minimal_sqlite(tmp_path)
    _doctor_status = _get_doctor_status()

    # Create a failed event file
    failed_dir = tmp_path / "events" / "failed"
    failed_dir.mkdir(parents=True, exist_ok=True)
    (failed_dir / "event1.json").write_text("{}", encoding="utf-8")

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths") as mock_rip:
        mock_rt = MagicMock()
        mock_rt.source_root = REPO_ROOT_9C
        mock_rt.dream_studio_home = tmp_path
        mock_rt.sqlite_path = tmp_path / "state" / "studio.db"
        mock_rip.return_value = mock_rt
        with patch("interfaces.cli.ds.Path.home", return_value=tmp_path / "claude"):
            with patch("interfaces.cli.ds._check_dispatcher_hooks", return_value=True):
                with patch("interfaces.cli.ds._check_version_current",
                           return_value={"repo": "2026-05-17", "installed": "2026-05-17", "current": True}):
                    result = _doctor_status(source_root=REPO_ROOT_9C, dream_studio_home=tmp_path)

    assert result["status"] == "fail"
    assert result["checks"]["failed_events"]["count"] == 1


def test_doctor_fix_calls_install_when_skills_missing(tmp_path):
    """doctor --fix should call integrate install when skills are missing."""
    _minimal_sqlite(tmp_path)
    _doctor_status = _get_doctor_status()

    missing_skills = {"total_expected": 1, "installed": 0, "missing": ["ds-bootstrap"]}

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths") as mock_rip:
        mock_rt = MagicMock()
        mock_rt.source_root = REPO_ROOT_9C
        mock_rt.dream_studio_home = tmp_path
        mock_rt.sqlite_path = tmp_path / "state" / "studio.db"
        mock_rip.return_value = mock_rt
        with patch("interfaces.cli.ds.Path.home", return_value=tmp_path / "claude"):
            with patch("interfaces.cli.ds._check_dispatcher_hooks", return_value=True):
                with patch("interfaces.cli.ds._check_skills_installed", return_value=missing_skills):
                    with patch("interfaces.cli.ds._check_version_current",
                               return_value={"repo": "2026-05-17", "installed": "2026-05-17", "current": True}):
                        with patch("subprocess.run") as mock_sub:
                            mock_sub.return_value = MagicMock(returncode=0)
                            result = _doctor_status(
                                source_root=REPO_ROOT_9C,
                                dream_studio_home=tmp_path,
                                fix=True,
                            )

    # Verify subprocess was called with install command
    assert mock_sub.called
    call_args = mock_sub.call_args[0][0]
    assert "integrate" in call_args
    assert "install" in call_args
    assert "fix_actions" in result
