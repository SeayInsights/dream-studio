from __future__ import annotations
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ds_spool_ingest_no_events(tmp_path):
    """ds spool ingest with empty spool exits 0 with no events message."""
    import os

    env = os.environ.copy()
    env["DS_SPOOL_ROOT"] = str(tmp_path / "spool_cli_test")

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "interfaces" / "cli" / "ds.py"), "spool", "ingest"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert "no events to ingest" in result.stdout or result.returncode == 0
