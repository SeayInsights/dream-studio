"""Running `ds` never writes inside the code root.

`ds migrate activate` used to record its activation by rewriting
core/event_store/migrations/.released_version -- an edit to the source tree. The
operator's live checkout carried that edit as a permanent dirty file, and an
installed app would have written into its own site-packages. Activation state now
lives beside the authority it activated (core.config.sqlite_bootstrap
.ACTIVATED_VERSION_FILE).

This snapshots every file under the code root, drives the CLI against a temporary
home (including an activation with real pending migrations), and requires the
snapshot to be unchanged. Bytecode caches are excluded: the interpreter, not Dream
Studio, writes those, and the subprocess runs with PYTHONDONTWRITEBYTECODE anyway.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

#: The checkout these tests run from IS the code root (core.config.paths.code_root).
REPO = Path(__file__).resolve().parents[2]

_SKIP_DIRS = {"__pycache__", ".git", ".venv", ".pytest_cache", "node_modules", ".ruff_cache"}


def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    snap: dict[str, tuple[int, int]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            try:
                st = path.stat()
            except OSError:
                continue
            snap[str(path.relative_to(root))] = (st.st_size, st.st_mtime_ns)
    return snap


def _ds(args: list[str], *, home: Path, cwd: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("DREAM_STUDIO")}
    env.pop("DS_DREAM_STUDIO_HOME", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(REPO)
    env["PYTHONIOENCODING"] = "utf-8"
    env["DREAM_STUDIO_DB_PATH"] = str(home / "state" / "studio.db")
    return subprocess.run(
        [sys.executable, "-m", "interfaces.cli.ds", "--home", str(home), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=cwd,
        env=env,
        timeout=600,
    )


def test_cli_commands_leave_the_code_root_untouched(tmp_path):
    root = REPO
    home = tmp_path / "home"
    before = _snapshot(root)

    for args in (
        ["--help"],
        ["validate"],
        ["migrate", "status"],
        ["migrate", "activate", "--confirm"],
    ):
        proc = _ds(args, home=home, cwd=tmp_path)
        assert proc.returncode == 0, (args, proc.stderr[-2000:])

    after = _snapshot(root)
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    assert not changed, f"`ds` wrote inside the code root {root}: {changed[:20]}"

    from core.config.sqlite_bootstrap import (
        ACTIVATED_VERSION_FILE,
        latest_migration_version,
        shipped_released_version,
    )

    if latest_migration_version() > shipped_released_version():
        # There was something to activate: its record is beside the authority.
        state = home / "state" / ACTIVATED_VERSION_FILE
        assert state.read_text(encoding="utf-8").strip() == str(latest_migration_version())
