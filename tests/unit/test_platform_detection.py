import json
import sys
from pathlib import Path

import pytest

from core.config.platform import (
    PlatformProfile,
    detect_platform,
    ensure_platform_recorded,
    get_platform_profile,
    get_shell,
    is_windows,
    shell_syntax_hint,
)


def test_detect_platform_returns_profile():
    profile = detect_platform()
    assert isinstance(profile, PlatformProfile)
    assert profile.os_name in ("Windows", "Linux", "Darwin")
    assert profile.python_version.count(".") == 2  # e.g. 3.12.8
    assert profile.shell != ""


def test_is_windows_matches_sys_platform():
    assert is_windows() == (sys.platform == "win32")


def test_ensure_platform_recorded_writes_json(tmp_path):
    profile_path = tmp_path / "platform.json"
    profile = ensure_platform_recorded(profile_path)
    assert profile_path.is_file()
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    assert data["os_name"] == profile.os_name
    assert data["shell"] == profile.shell


def test_get_platform_profile_reads_existing(tmp_path):
    profile_path = tmp_path / "platform.json"
    written = ensure_platform_recorded(profile_path)
    read_back = get_platform_profile(profile_path)
    assert written == read_back


def test_get_platform_profile_redetects_on_missing(tmp_path):
    profile_path = tmp_path / "platform.json"
    # Don't write anything; get_platform_profile should detect and record
    profile = get_platform_profile(profile_path)
    assert profile_path.is_file()
    assert isinstance(profile, PlatformProfile)


def test_shell_syntax_hint_returns_known_command():
    hint = shell_syntax_hint("set_env")
    assert hint != ""
    assert "VAR" in hint or "unknown" in hint  # Tolerate unknown shells in CI
