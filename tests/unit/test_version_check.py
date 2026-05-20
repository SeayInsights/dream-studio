"""Unit tests for _version_check() in emitters/claude_code/run.py (Slice 9c)."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _get_version_check():
    """Import _version_check with module-level reload to pick up any patches."""
    import emitters.claude_code.run as _run

    return _run._version_check


def _get_get_plugin_root():
    import emitters.claude_code.run as _run

    return _run._get_plugin_root


# ── VERSION file ──────────────────────────────────────────────────────────────


def test_version_file_exists_at_repo_root():
    """VERSION file must exist at the repository root."""
    version_file = REPO_ROOT / "VERSION"
    assert version_file.is_file(), f"VERSION file not found at {version_file}"


def test_version_file_is_nonempty():
    version_file = REPO_ROOT / "VERSION"
    content = version_file.read_text(encoding="utf-8").strip()
    assert content, "VERSION file must not be empty"


def test_version_file_format():
    """VERSION must be a YYYY-MM-DD date string."""
    import re

    version_file = REPO_ROOT / "VERSION"
    content = version_file.read_text(encoding="utf-8").strip()
    assert re.match(
        r"^\d{4}-\d{2}-\d{2}$", content
    ), f"VERSION must be YYYY-MM-DD format, got: {content!r}"


# ── _version_check logic ──────────────────────────────────────────────────────


def test_version_check_returns_none_when_versions_match(tmp_path):
    """When repo version == installed version, _version_check returns None."""
    repo_file = tmp_path / "VERSION"
    repo_file.write_text("2026-05-17\n", encoding="utf-8")

    installed_file = tmp_path / "installed-version"
    installed_file.write_text("2026-05-17\n", encoding="utf-8")

    _version_check = _get_version_check()

    with patch("emitters.claude_code.run._get_plugin_root", return_value=tmp_path):
        with patch(
            "emitters.claude_code.project._get_db_path",
            return_value=tmp_path / "state" / "studio.db",
        ):
            # installed_version_file = _get_db_path().parent.parent / "state" / "installed-version"
            # _get_db_path() → tmp_path/state/studio.db
            # .parent.parent → tmp_path
            # / "state" / "installed-version" → tmp_path/state/installed-version
            (tmp_path / "state").mkdir(parents=True, exist_ok=True)
            (tmp_path / "state" / "installed-version").write_text("2026-05-17\n", encoding="utf-8")

            result = _version_check()

    assert result is None


def test_version_check_returns_update_notice_when_versions_differ(tmp_path, monkeypatch):
    """When repo version != installed version, returns update notice string."""
    _version_check = _get_version_check()

    # `_version_check` reads the installed-version file from
    # `Path(USERPROFILE or HOME) / ".dream-studio" / "state" / "installed-version"`,
    # not from `_get_plugin_root()`. Point both home env vars at tmp_path
    # so the test fixture controls what the function sees.
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    (tmp_path / "VERSION").write_text("2026-05-17\n", encoding="utf-8")
    installed_dir = tmp_path / ".dream-studio" / "state"
    installed_dir.mkdir(parents=True, exist_ok=True)
    (installed_dir / "installed-version").write_text("2026-01-01\n", encoding="utf-8")

    with patch("emitters.claude_code.run._get_plugin_root", return_value=tmp_path):
        result = _version_check()

    assert result is not None
    assert "UPDATE AVAILABLE" in result
    assert "2026-01-01" in result
    assert "2026-05-17" in result
    assert "ds update" in result


def test_version_check_returns_install_notice_when_installed_file_absent(tmp_path, monkeypatch):
    """When installed-version file doesn't exist, returns install notice."""
    _version_check = _get_version_check()

    # Point the env vars the function uses at a directory that has no
    # `.dream-studio/state/installed-version` file.
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    (tmp_path / "VERSION").write_text("2026-05-17\n", encoding="utf-8")
    # Do NOT create the installed-version file under .dream-studio/state/.

    with patch("emitters.claude_code.run._get_plugin_root", return_value=tmp_path):
        result = _version_check()

    assert result is not None
    assert "Install not verified" in result
    assert "integrate install" in result


def test_version_check_returns_none_when_version_file_missing(tmp_path):
    """When repo VERSION file is absent, _version_check returns None (fail-open)."""
    _version_check = _get_version_check()

    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    # Do NOT create VERSION file

    with patch("emitters.claude_code.run._get_plugin_root", return_value=tmp_path):
        with patch(
            "emitters.claude_code.project._get_db_path",
            return_value=tmp_path / "state" / "studio.db",
        ):
            result = _version_check()

    assert result is None


def test_version_check_fail_open_on_exception():
    """_version_check must return None on any exception — never raise."""
    _version_check = _get_version_check()

    with patch("emitters.claude_code.run._get_plugin_root", side_effect=RuntimeError("boom")):
        result = _version_check()

    assert result is None


def test_version_check_fail_open_on_io_error(tmp_path):
    """Even if file reads raise OSError, _version_check returns None."""
    import builtins

    _version_check = _get_version_check()
    original_open = builtins.open

    def broken_open(*args, **kwargs):
        raise OSError("disk error")

    with patch("emitters.claude_code.run._get_plugin_root", return_value=tmp_path):
        with patch("builtins.open", broken_open):
            result = _version_check()

    assert result is None


# ── UserPromptSubmit integration ──────────────────────────────────────────────


def test_version_notice_comes_before_enforcement_in_combined_output(tmp_path, capsys):
    """When both version and enforcement messages exist, version comes first."""
    import emitters.claude_code.run as _run

    version_notice = "DREAM STUDIO UPDATE AVAILABLE\nRun: ds update"
    enforcement_notice = "DREAM STUDIO: No active work order."

    with patch("emitters.claude_code.run._version_check", return_value=version_notice):
        with patch("emitters.claude_code.run._enforcement_check", return_value=enforcement_notice):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.read.return_value = '{"prompt": "hello"}'
                with patch("sys.argv", ["run.py", "UserPromptSubmit"]):
                    # Import and call main directly
                    result = _run.main()

    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())
    content = output["content"]

    version_pos = content.find("UPDATE AVAILABLE")
    enforcement_pos = content.find("No active work order")
    assert version_pos < enforcement_pos, "Version notice must come before enforcement"


def test_no_output_when_both_checks_pass():
    """When both checks return None, no JSON message is printed — unit test of the combiner logic."""
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        version_msg = None
        enforcement_msg = None
        parts = [m for m in (version_msg, enforcement_msg) if m]
        if parts:
            combined = "\n\n".join(parts)
            print(json.dumps({"type": "message", "content": combined}))

    assert buf.getvalue() == ""


# ── ds update command ─────────────────────────────────────────────────────────


def _get_update_command():
    from interfaces.cli import ds as _ds

    return _ds._update_command


def test_update_returns_already_current_when_version_matches(tmp_path, capsys):
    """ds update returns already_current when versions match."""
    _update_command = _get_update_command()
    from interfaces.cli.ds import resolve_installed_runtime_paths

    # Set up source root with VERSION
    (tmp_path / "VERSION").write_text("2026-05-17\n", encoding="utf-8")

    # Set up dream_studio_home with installed-version
    ds_home = tmp_path / ".dream-studio"
    (ds_home / "state").mkdir(parents=True, exist_ok=True)
    (ds_home / "state" / "installed-version").write_text("2026-05-17\n", encoding="utf-8")

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths") as mock_paths:
        from unittest.mock import MagicMock

        mock_rt = MagicMock()
        mock_rt.dream_studio_home = ds_home
        mock_paths.return_value = mock_rt

        result = _update_command(source_root=tmp_path, dream_studio_home=ds_home)

    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())
    assert output["ok"] is True
    assert output["status"] == "already_current"
    assert output["version"] == "2026-05-17"
    assert result == 0


def test_update_dry_run_shows_what_would_change(tmp_path, capsys):
    """ds update --dry-run shows update_available without running install."""
    _update_command = _get_update_command()

    (tmp_path / "VERSION").write_text("2026-05-17\n", encoding="utf-8")
    ds_home = tmp_path / ".dream-studio"
    (ds_home / "state").mkdir(parents=True, exist_ok=True)
    (ds_home / "state" / "installed-version").write_text("2026-01-01\n", encoding="utf-8")

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths") as mock_paths:
        from unittest.mock import MagicMock

        mock_rt = MagicMock()
        mock_rt.dream_studio_home = ds_home
        mock_paths.return_value = mock_rt

        with patch("subprocess.run") as mock_sub:
            result = _update_command(source_root=tmp_path, dream_studio_home=ds_home, dry_run=True)
            mock_sub.assert_not_called()

    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())
    assert output["ok"] is True
    assert output["status"] == "update_available"
    assert output["dry_run"] is True
    assert output["from"] == "2026-01-01"
    assert output["to"] == "2026-05-17"


# ── A2.8: in-process ClaudeCodeInstaller call (no subprocess.run) ────────────


def test_update_execute_calls_installer_in_process_without_subprocess(tmp_path, capsys):
    """A2.8: ``ds update`` (execute path) calls ``ClaudeCodeInstaller.install('execute')``
    directly instead of shelling out via ``subprocess.run``."""
    _update_command = _get_update_command()

    (tmp_path / "VERSION").write_text("2026-05-17\n", encoding="utf-8")
    ds_home = tmp_path / ".dream-studio"
    (ds_home / "state").mkdir(parents=True, exist_ok=True)
    (ds_home / "state" / "installed-version").write_text("2026-01-01\n", encoding="utf-8")

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths") as mock_paths:
        from unittest.mock import MagicMock

        mock_rt = MagicMock()
        mock_rt.dream_studio_home = ds_home
        mock_paths.return_value = mock_rt

        mock_installer_cls = MagicMock()
        mock_installer = MagicMock()
        mock_installer.install.return_value = {"ok": True, "applied": ["claude-code"]}
        mock_installer_cls.return_value = mock_installer

        with (
            patch("subprocess.run") as mock_sub,
            patch(
                "integrations.installer.claude_code.ClaudeCodeInstaller",
                mock_installer_cls,
            ),
            patch("integrations.detector.detect_claude_code") as mock_detect,
        ):
            mock_detect.return_value = MagicMock(
                config_root=tmp_path / "claude-config",
                scope="user",
            )
            result = _update_command(source_root=tmp_path, dream_studio_home=ds_home)

    # The subprocess shell-out is gone.
    mock_sub.assert_not_called()
    # The in-process installer was driven with mode='execute'.
    mock_installer.install.assert_called_once_with("execute")
    # Operator output reflects the in-process install result.
    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())
    assert output["ok"] is True
    assert output["status"] == "updated"
    assert output["from"] == "2026-01-01"
    assert output["to"] == "2026-05-17"
    assert result == 0
    # And the installed-version marker is bumped.
    assert (ds_home / "state" / "installed-version").read_text(encoding="utf-8").strip() == (
        "2026-05-17"
    )


def test_update_execute_install_failure_returns_1_without_bumping_version(tmp_path, capsys):
    """If the installer fails, exit 1 and leave the installed-version marker alone."""
    _update_command = _get_update_command()

    (tmp_path / "VERSION").write_text("2026-05-17\n", encoding="utf-8")
    ds_home = tmp_path / ".dream-studio"
    (ds_home / "state").mkdir(parents=True, exist_ok=True)
    (ds_home / "state" / "installed-version").write_text("2026-01-01\n", encoding="utf-8")

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths") as mock_paths:
        from unittest.mock import MagicMock

        mock_rt = MagicMock()
        mock_rt.dream_studio_home = ds_home
        mock_paths.return_value = mock_rt

        with (
            patch("integrations.installer.claude_code.ClaudeCodeInstaller") as mock_installer_cls,
            patch("integrations.detector.detect_claude_code") as mock_detect,
        ):
            mock_installer = MagicMock()
            mock_installer.install.return_value = {"ok": False, "error": "permission denied"}
            mock_installer_cls.return_value = mock_installer
            mock_detect.return_value = MagicMock(
                config_root=tmp_path / "claude-config",
                scope="user",
            )
            result = _update_command(source_root=tmp_path, dream_studio_home=ds_home)

    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())
    assert output["ok"] is False
    assert output["status"] == "install_failed"
    assert result == 1
    # Installed-version marker still on the old value.
    assert (ds_home / "state" / "installed-version").read_text(encoding="utf-8").strip() == (
        "2026-01-01"
    )
