"""Tests for WS 9e-3 — install scripts and Python preflight."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INSTALL_SH = _REPO_ROOT / "install.sh"
_INSTALL_PS1 = _REPO_ROOT / "install.ps1"
_DS_ENTRY = _REPO_ROOT / "interfaces" / "cli" / "ds_entry.py"


# ── install.sh ────────────────────────────────────────────────────────────────


def test_install_sh_exists():
    assert _INSTALL_SH.is_file(), "install.sh must exist at repo root"


def test_install_sh_contains_python_version_check():
    content = _INSTALL_SH.read_text(encoding="utf-8")
    assert "3" in content and "12" in content, "install.sh must check for Python 3.12+"


def test_install_sh_contains_auto_install_logic():
    content = _INSTALL_SH.read_text(encoding="utf-8")
    # Must try to install Python automatically via brew/apt-get/dnf
    assert (
        "brew" in content or "apt-get" in content or "dnf" in content
    ), "install.sh must contain auto-install logic (brew/apt-get/dnf)"


def test_install_sh_calls_integrate_install():
    content = _INSTALL_SH.read_text(encoding="utf-8")
    assert (
        "integrate install claude_code" in content
    ), "install.sh must call 'integrate install claude_code'"


def test_install_sh_calls_doctor():
    content = _INSTALL_SH.read_text(encoding="utf-8")
    assert "doctor" in content, "install.sh must call 'ds doctor' for health check"


# ── install.ps1 ───────────────────────────────────────────────────────────────


def test_install_ps1_exists():
    assert _INSTALL_PS1.is_file(), "install.ps1 must exist at repo root"


def test_install_ps1_contains_python_version_check():
    content = _INSTALL_PS1.read_text(encoding="utf-8")
    assert "3" in content and "12" in content, "install.ps1 must check for Python 3.12+"


def test_install_ps1_contains_auto_install_logic():
    content = _INSTALL_PS1.read_text(encoding="utf-8")
    # Must try to install Python via winget
    assert "winget" in content, "install.ps1 must contain auto-install logic (winget)"


def test_install_ps1_calls_integrate_install():
    content = _INSTALL_PS1.read_text(encoding="utf-8")
    assert (
        "integrate install claude_code" in content
    ), "install.ps1 must call 'integrate install claude_code'"


def test_install_ps1_calls_doctor():
    content = _INSTALL_PS1.read_text(encoding="utf-8")
    assert "doctor" in content, "install.ps1 must call 'ds doctor' for health check"


# ── Python preflight in ds_entry.py ──────────────────────────────────────────


def test_ds_entry_preflight_rejects_python_311():
    """Preflight block must reject Python < 3.12."""
    content = _DS_ENTRY.read_text(encoding="utf-8")
    # Must check sys.version_info < (3, 12)
    assert "(3, 12)" in content, "ds_entry.py must check for Python 3.12 minimum"
    assert "sys.exit(1)" in content, "ds_entry.py must exit(1) when Python is too old"


def test_ds_entry_preflight_error_message_contains_fix():
    """Preflight error message must tell user how to fix the problem."""
    content = _DS_ENTRY.read_text(encoding="utf-8")
    assert (
        "install.sh" in content or "install.ps1" in content
    ), "ds_entry.py preflight must reference install scripts in the fix message"


def test_ds_entry_preflight_is_at_module_level():
    """Preflight must be at module level (not inside main()), so it runs on import."""
    content = _DS_ENTRY.read_text(encoding="utf-8")
    # The version check must appear before 'def main()'
    version_check_pos = content.find("sys.version_info")
    main_def_pos = content.find("def main()")
    assert version_check_pos != -1, "sys.version_info check not found in ds_entry.py"
    assert main_def_pos != -1, "def main() not found in ds_entry.py"
    assert (
        version_check_pos < main_def_pos
    ), "Version check must appear before def main() (module-level, not inside main)"
