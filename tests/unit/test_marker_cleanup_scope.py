"""The test suite's marker cleanup acts only on the session home conftest created.

The cleanup fixture and the marker-leak test acted on whatever DREAM_STUDIO_HOME
named, unless it was literally ~/.dream-studio. Run with DREAM_STUDIO_HOME set to an
operator's relocated home, the marker-leak test overwrote that home's
`state/installed-version`. Both now act only on the home conftest made with mkdtemp,
and never overwrite a marker that is already there.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_the_suite_never_writes_a_marker_into_a_home_it_did_not_create(tmp_path):
    operator_home = tmp_path / "operator-home"
    (operator_home / "state").mkdir(parents=True)
    marker = operator_home / "state" / "installed-version"
    marker.write_text("1.2.3 " + "f" * 40 + "\n", encoding="utf-8")
    before = marker.read_bytes()

    env = {k: v for k, v in os.environ.items() if not k.startswith(("DREAM_STUDIO", "DS_"))}
    env.update(
        {
            "DREAM_STUDIO_HOME": str(operator_home),
            "DREAM_STUDIO_DB_PATH": str(tmp_path / "elsewhere" / "studio.db"),
            "PYTHONPATH": str(REPO),
        }
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",
            str(REPO / "tests" / "unit" / "test_install_markers_do_not_leak.py"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO,
        env=env,
        timeout=600,
    )
    assert marker.read_bytes() == before, proc.stdout[-2000:]
    assert marker.exists()
