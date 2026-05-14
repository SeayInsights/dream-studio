from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ds_analytics_cli_help_imports_from_plain_checkout() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "interfaces" / "cli" / "ds_analytics" / "main.py"),
            "--help",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "ds-analytics" in result.stdout


def test_ds_analytics_cli_bootstrap_paths_are_repo_and_cli_roots() -> None:
    source = (REPO_ROOT / "interfaces" / "cli" / "ds_analytics" / "main.py").read_text(
        encoding="utf-8"
    )

    assert "parents[3]" in source
    assert "_CLI_ROOT" in source
    assert "sys.path.insert(0, str(_CLI_ROOT))" in source
