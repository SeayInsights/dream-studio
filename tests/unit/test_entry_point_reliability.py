"""Phase 5.1A — Runtime Entry Point Reliability tests.

Covers:
1. Entry-point paths exist (canonical + shim)
2. install.ps1 includes Python version and repo-root validation
3. install.sh includes Python version and repo-root validation
4. setup --help and --check are read-only
5. dashboard --help and --check are read-only
6. Dashboard check paths work via shims
7. launch-dashboard and launch-dashboard.cmd remain aligned
8. hooks/run.cmd includes %PLUGIN_ROOT% in PYTHONPATH
9. hooks/run.sh includes PLUGIN_ROOT in PYTHONPATH (parity reference)
10. statusline-command.sh no longer depends only on Windows py
11. Makefile has setup-check and dashboard-check targets
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[2]


# ── 1. Entry-point paths exist ─────────────────────────────────────────────


class TestEntryPointPathsExist:

    REQUIRED_FILES = [
        "install.ps1",
        "install.sh",
        "interfaces/cli/setup.py",
        "interfaces/cli/ds_dashboard.py",
        "scripts/setup.py",
        "scripts/ds_dashboard.py",
        "hooks/run.cmd",
        "hooks/run.sh",
        "interfaces/cli/statusline-command.sh",
        "launch-dashboard",
        "launch-dashboard.cmd",
        "Makefile",
    ]

    @pytest.mark.parametrize("relpath", REQUIRED_FILES)
    def test_entry_point_exists(self, relpath):
        assert (REPO_ROOT / relpath).is_file(), f"Missing entry point: {relpath}"


# ── 2. install.ps1 validation ──────────────────────────────────────────────


class TestInstallPs1Validation:

    @pytest.fixture(autouse=True)
    def _load(self):
        self.source = (REPO_ROOT / "install.ps1").read_text(encoding="utf-8")

    def test_checks_python_version(self):
        assert "3.11" in self.source or "version_info" in self.source.lower()

    def test_validates_repo_root(self):
        assert "RepoDir" in self.source
        assert "Set-Location" in self.source or "location" in self.source.lower()

    def test_fails_on_missing_python(self):
        assert "exit 1" in self.source or "exit /b 1" in self.source

    def test_delegates_to_canonical_setup(self):
        assert "interfaces.cli.ds" in self.source


# ── 3. install.sh validation ──────────────────────────────────────────────


class TestInstallShValidation:

    @pytest.fixture(autouse=True)
    def _load(self):
        self.source = (REPO_ROOT / "install.sh").read_text(encoding="utf-8")

    def test_checks_python_version(self):
        assert "3.11" in self.source or "version_info" in self.source

    def test_validates_repo_root(self):
        assert "REPO_DIR" in self.source
        assert "cd" in self.source

    def test_fails_on_missing_python(self):
        assert "exit 1" in self.source

    def test_delegates_to_canonical_setup(self):
        assert "interfaces.cli.ds" in self.source

    def test_has_python_picker(self):
        assert "pick_python" in self.source or "python3" in self.source

    def test_version_comparison(self):
        assert "MAJOR" in self.source or "major" in self.source
        assert "MINOR" in self.source or "minor" in self.source


# ── 4. setup --help and --check are read-only ──────────────────────────────


class TestSetupReadOnly:

    def test_canonical_setup_help(self):
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "interfaces" / "cli" / "setup.py"), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0

    def test_canonical_setup_check(self):
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "interfaces" / "cli" / "setup.py"), "--check"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0

    def test_shim_setup_help(self):
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "setup.py"), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0

    def test_shim_setup_check(self):
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "setup.py"), "--check"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0


# ── 5. dashboard --help and --check are read-only ──────────────────────────


class TestDashboardReadOnly:

    def test_canonical_dashboard_help(self):
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "interfaces" / "cli" / "ds_dashboard.py"), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0

    def test_canonical_dashboard_check(self):
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "interfaces" / "cli" / "ds_dashboard.py"), "--check"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        assert "Preflight check" in result.stdout

    def test_check_does_not_mutate(self):
        """--check must not start a server or open a browser."""
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "interfaces" / "cli" / "ds_dashboard.py"), "--check"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        assert "Starting analytics server" not in result.stdout
        assert "Opening" not in result.stdout


# ── 6. Dashboard check paths via shims ─────────────────────────────────────


class TestDashboardShimCheck:

    def test_shim_dashboard_help(self):
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "ds_dashboard.py"), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0

    def test_shim_dashboard_check(self):
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "ds_dashboard.py"), "--check"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        assert "Preflight check" in result.stdout


# ── 7. launch-dashboard and launch-dashboard.cmd alignment ─────────────────


class TestLaunchDashboardAlignment:

    def test_both_use_canonical_bootstrap(self):
        bash = (REPO_ROOT / "launch-dashboard").read_text(encoding="utf-8")
        cmd = (REPO_ROOT / "launch-dashboard.cmd").read_text(encoding="utf-8")
        assert "ds_dashboard" in bash
        assert "ds_dashboard" in cmd

    def test_bash_delegates_to_cli(self):
        source = (REPO_ROOT / "launch-dashboard").read_text(encoding="utf-8")
        assert "interfaces/cli/ds_dashboard.py" in source

    def test_cmd_delegates_to_cli(self):
        source = (REPO_ROOT / "launch-dashboard.cmd").read_text(encoding="utf-8")
        assert "interfaces\\cli\\ds_dashboard.py" in source


# ── 8. hooks/run.cmd includes PLUGIN_ROOT in PYTHONPATH ────────────────────


class TestRunCmdPythonPath:

    @pytest.fixture(autouse=True)
    def _load(self):
        self.source = (REPO_ROOT / "hooks" / "run.cmd").read_text(encoding="utf-8")

    def test_plugin_root_in_pythonpath(self):
        """PYTHONPATH must include %PLUGIN_ROOT% (not just hooks subdirectory)."""
        assert (
            "%PLUGIN_ROOT%;%PLUGIN_ROOT%\\hooks" in self.source
            or "%PLUGIN_ROOT%;%PLUGIN_ROOT%\\hooks;" in self.source
            or "!PLUGIN_ROOT!;!PLUGIN_ROOT!\\hooks" in self.source
            or "!PLUGIN_ROOT!;!PLUGIN_ROOT!\\hooks;" in self.source
        )

    def test_exports_claude_plugin_root(self):
        assert (
            "CLAUDE_PLUGIN_ROOT=%PLUGIN_ROOT%" in self.source
            or "CLAUDE_PLUGIN_ROOT=!PLUGIN_ROOT!" in self.source
        )

    def test_version_pinned_python_preferred(self):
        """run.cmd should try py -3.12 before bare py."""
        assert "py -3.12" in self.source


# ── 9. hooks/run.sh PYTHONPATH parity reference ────────────────────────────


class TestRunShPythonPath:

    @pytest.fixture(autouse=True)
    def _load(self):
        self.source = (REPO_ROOT / "hooks" / "run.sh").read_text(encoding="utf-8")

    def test_plugin_root_in_pythonpath(self):
        assert "${PLUGIN_ROOT}:${PLUGIN_ROOT}/hooks" in self.source

    def test_exports_claude_plugin_root(self):
        assert 'CLAUDE_PLUGIN_ROOT="${PLUGIN_ROOT}"' in self.source


# ── 10. statusline-command.sh cross-platform Python ────────────────────────


class TestStatuslineCrossPlatform:

    @pytest.fixture(autouse=True)
    def _load(self):
        self.source = (REPO_ROOT / "interfaces" / "cli" / "statusline-command.sh").read_text(
            encoding="utf-8"
        )

    def test_no_hardcoded_py_c(self):
        """Must not use bare 'exec py -c' — needs cross-platform picker."""
        lines = self.source.splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.match(r"^exec\s+py\s+-c\b", stripped):
                pytest.fail("statusline-command.sh still uses hardcoded 'exec py -c'")

    def test_has_python_picker(self):
        assert "pick_python" in self.source

    def test_supports_python3(self):
        assert "python3" in self.source

    def test_supports_py_3_12(self):
        assert "py -3.12" in self.source


# ── 11. Makefile targets ───────────────────────────────────────────────────


class TestMakefileTargets:

    @pytest.fixture(autouse=True)
    def _load(self):
        self.source = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    def test_setup_check_target_exists(self):
        assert "setup-check:" in self.source

    def test_dashboard_check_target_exists(self):
        assert "dashboard-check:" in self.source

    def test_setup_check_calls_canonical(self):
        idx = self.source.index("setup-check:")
        block = self.source[idx : idx + 200]
        assert "--check" in block
        assert "setup.py" in block

    def test_dashboard_check_calls_canonical(self):
        idx = self.source.index("dashboard-check:")
        block = self.source[idx : idx + 200]
        assert "--check" in block
        assert "ds_dashboard.py" in block

    def test_targets_in_phony(self):
        phony_line = [l for l in self.source.splitlines() if ".PHONY:" in l][0]
        assert "setup-check" in phony_line
        assert "dashboard-check" in phony_line
