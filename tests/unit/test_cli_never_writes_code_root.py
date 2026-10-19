"""Running `ds` never writes inside the code root.

`ds migrate activate` used to record its activation by rewriting
core/event_store/migrations/.released_version -- an edit to the source tree. The
operator's live checkout carried that edit as a permanent dirty file, and an
installed app would have written into its own site-packages. Activation state now
lives beside the authority it activated (core.config.sqlite_bootstrap
.ACTIVATED_VERSION_FILE).

This runs the CLI from a COPY of the tracked tree whose .released_version is one below
the newest migration, so an activation always has a real pending migration to record
(the test used to depend on the repository having one pending, and tested nothing once
a release caught up). It snapshots every file under that code root, drives the CLI
against a temporary home, and requires the snapshot to be unchanged. Bytecode caches
are excluded: the interpreter, not Dream Studio, writes those, and the subprocess runs
with PYTHONDONTWRITEBYTECODE anyway.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

#: The checkout these tests run from IS the code root (core.config.paths.code_root).
REPO = Path(__file__).resolve().parents[2]

#: Run ds from the code root given in argv[1], isolated so the working directory and
#: PYTHONPATH cannot put the real checkout ahead of it.
_RUN_DS = (
    "import runpy, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "sys.argv = ['ds', *sys.argv[2:]]\n"
    "runpy.run_module('interfaces.cli.ds', run_name='__main__')\n"
)

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


def _code_root_with_a_pending_migration(dest: Path) -> tuple[Path, int]:
    """Copy the tracked tree to *dest* and release every migration but the newest."""
    tracked = (
        subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True)
        .stdout.decode("utf-8")
        .split("\0")
    )
    for rel in filter(None, tracked):
        source = REPO / rel
        if source.is_file():
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    migrations = dest / "core" / "event_store" / "migrations"
    newest = max(int(p.name.split("_", 1)[0]) for p in migrations.glob("[0-9]*.sql"))
    (migrations / ".released_version").write_text(f"{newest - 1}\n", encoding="utf-8")
    return dest, newest


def _ds(
    args: list[str], *, home: Path, cwd: Path, root: Path = REPO
) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("DREAM_STUDIO")}
    env.pop("DS_DREAM_STUDIO_HOME", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(root)
    env["PYTHONIOENCODING"] = "utf-8"
    env["DREAM_STUDIO_DB_PATH"] = str(home / "state" / "studio.db")
    return subprocess.run(
        [sys.executable, "-I", "-c", _RUN_DS, str(root), "--home", str(home), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=cwd,
        env=env,
        timeout=600,
    )


def test_cli_commands_leave_the_code_root_untouched(tmp_path):
    root, newest = _code_root_with_a_pending_migration(tmp_path / "code-root")
    home = tmp_path / "home"
    before = _snapshot(root)

    for args in (
        ["--help"],
        ["validate"],
        ["migrate", "status"],
        ["migrate", "activate", "--confirm"],
    ):
        proc = _ds(args, home=home, cwd=tmp_path, root=root)
        assert proc.returncode == 0, (args, proc.stderr[-2000:])

    after = _snapshot(root)
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    assert not changed, f"`ds` wrote inside the code root {root}: {changed[:20]}"

    from core.config.sqlite_bootstrap import ACTIVATED_VERSION_FILE

    # The pending migration was built above, so the activation always had one to record.
    state = home / "state" / ACTIVATED_VERSION_FILE
    assert state.read_text(encoding="utf-8").strip() == str(newest)
