"""`ds self-install`: install Dream Studio into its home as a versioned app.

Before this, every surface -- the `ds` launcher, every Claude Code hook, the MCP
server -- ran code straight out of a git checkout. A branch switch, a dirty
working tree or a half-finished edit in that checkout changed what the live hooks
executed, and the migration-activation state was written back into the tree.

Layout under the home (H):

    H/app/<version>-<sha10>/venv/       one venv per built commit, never edited
    H/app/<version>-<sha10>/app.json    what was built: version, sha, ref, source repo
    H/app/current                       junction (Windows) or symlink to the live app
    H/app/previous                      text: the app id `current` replaced (rollback)
    H/state/installed-version           "<version> <full sha>"
    H/bin/ds.cmd (H/bin/ds elsewhere)   the ONE launcher: current app's ds --home H

The order is what makes it safe. Everything that can fail runs BEFORE anything the
running system reads is touched: the wheel is built from `git archive <ref>` (never
the working tree), installed into a fresh venv, smoke-tested, the authority is
backed up with VACUUM INTO and migrated by the NEW app. Only then does `current`
move. A failure anywhere before that leaves the previous app, launcher and
installed-version exactly as they were. Hooks spell the interpreter through
H/app/current, so a switch or a rollback moves them too.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.config.paths import APP_HOME_MARKER

IS_WINDOWS = platform.system() == "Windows"
APP_DIRNAME = "app"
CURRENT = "current"
PREVIOUS = "previous"
APP_RECORD = "app.json"


class SelfInstallError(RuntimeError):
    """A self-install or rollback step failed; nothing was switched."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise SelfInstallError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")


def venv_ds(venv: Path) -> Path:
    return venv / ("Scripts/ds.exe" if IS_WINDOWS else "bin/ds")


def launcher_path(home: Path) -> Path:
    return home / "bin" / ("ds.cmd" if IS_WINDOWS else "ds")


def launcher_content(home: Path) -> str:
    ds = venv_ds(home / APP_DIRNAME / CURRENT / "venv")
    if IS_WINDOWS:
        return f'@echo off\r\n"{ds}" --home "{home}" %*\r\n'
    return f'#!/bin/sh\nexec "{ds}" --home "{home}" "$@"\n'


def delegating_launchers(home: Path) -> dict[str, str]:
    """Launchers that hand every call to <home>/bin/ds.cmd (or ds): a launcher elsewhere
    on PATH must never pin a checkout or one app version."""
    target = launcher_path(home)
    if IS_WINDOWS:
        return {
            "ds.cmd": f'@echo off\r\ncall "{target}" %*\r\n',
            "ds.ps1": f'& "{target}" @args\r\nexit $LASTEXITCODE\r\n',
        }
    return {"ds": f'#!/bin/sh\nexec "{target}" "$@"\n'}


def stale_path_launchers(home: Path) -> list[Path]:
    """Dream Studio launchers in ~/.local/bin (`ds install-command`) that do not delegate
    to <home>/bin. That directory usually comes first on PATH, so such a launcher keeps
    running a checkout after self-install."""
    local_bin = Path.home() / ".local" / "bin"
    target = str(launcher_path(home))
    stale: list[Path] = []
    for name in ("ds.cmd", "ds.ps1", "ds"):
        path = local_bin / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        owned = (
            "DREAM_STUDIO_SOURCE_ROOT" in text
            or "ds_entry.py" in text
            or ("interfaces" in text and "ds.py" in text)
        )
        if owned and target not in text:
            stale.append(path)
    return stale


def _repoint_launchers(home: Path, log: list[str]) -> list[dict[str, str]]:
    content = delegating_launchers(home)
    repointed = []
    for path in stale_path_launchers(home):
        new = content.get(path.name) or next(iter(content.values()))
        old = path.read_text(encoding="utf-8", errors="replace")
        path.write_text(new, encoding="utf-8", newline="")
        log.append(f"repointed {path} to {launcher_path(home)}")
        repointed.append({"path": str(path), "previous": old})
    return repointed


def _assert_inside(path: Path, parent: Path) -> None:
    """Refuse to delete anything that is not strictly inside *parent*."""
    path = path.resolve()
    parent = parent.resolve()
    if path == parent or parent not in path.parents:
        raise SelfInstallError(f"refusing to remove {path}: not inside {parent}")


def _remove_tree(path: Path, parent: Path) -> None:
    """Remove a directory this module created (build dir, an incomplete app)."""
    _assert_inside(path, parent)
    if path.exists():
        shutil.rmtree(path)


def _read_link(link: Path) -> str | None:
    """The app id `current` points at, or None when there is no link yet."""
    if link.is_symlink() or (IS_WINDOWS and link.is_junction()):
        return Path(os.readlink(link)).name
    return None


def _make_link(link: Path, target: Path) -> None:
    """A directory junction on Windows (no admin needed), a symlink elsewhere."""
    if IS_WINDOWS:
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


def _remove_link(link: Path) -> None:
    """Remove the link itself -- never what it points at."""
    if IS_WINDOWS and link.is_junction():
        os.rmdir(link)
    elif link.is_symlink():
        link.unlink()
    elif link.exists():
        raise SelfInstallError(f"{link} exists and is not a link; refusing to replace it")


def switch_current(app_root: Path, app_id: str) -> None:
    """Point app/current at app/<app_id>: build the new link first, then swap."""
    target = app_root / app_id
    current = app_root / CURRENT
    staged = app_root / f"{CURRENT}.new"
    if staged.is_symlink() or (IS_WINDOWS and staged.is_junction()):
        _remove_link(staged)
    _make_link(staged, target)
    if not IS_WINDOWS:
        os.replace(staged, current)
        return
    # A junction cannot be renamed over another, so the old one goes first; if the rename
    # then fails, the old link is put back rather than leaving no `current` at all.
    old_target = Path(os.readlink(current)) if current.is_junction() else None
    if old_target is not None or current.exists():
        _remove_link(current)
    try:
        os.rename(staged, current)
    except OSError:
        if old_target is not None:
            _make_link(current, old_target)
        raise


def app_record(app_dir: Path) -> dict[str, Any] | None:
    """app.json of a COMPLETE app (record and venv python both present), else None."""
    record = app_dir / APP_RECORD
    if not record.is_file() or not venv_python(app_dir / "venv").is_file():
        return None
    try:
        data = json.loads(record.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SelfInstallError(f"{record} is not valid JSON: {exc}") from exc
    return data if isinstance(data, dict) else None


def backup_authority(db_path: Path, backup_dir: Path) -> Path:
    """VACUUM INTO a consistent copy; `ds restore <dir> --execute` restores it."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / "studio.db"
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True, timeout=30.0)
    try:
        conn.execute("VACUUM INTO ?", (str(dest),))
    finally:
        conn.close()
    return dest


def _run(cmd: list[str], *, env: dict[str, str] | None = None, cwd: Path | None = None) -> str:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(cwd) if cwd else None,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip()[-3000:]
        raise SelfInstallError(f"{' '.join(cmd[:4])} ... failed (exit {proc.returncode}):\n{tail}")
    return proc.stdout


def _app_env(home: Path) -> dict[str, str]:
    """Environment for running the NEW app against *home* -- nothing inherited that could
    point it at a checkout or at another home."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("PYTHON", "DREAM_STUDIO")) and k != "DS_DREAM_STUDIO_HOME"
    }
    env["DREAM_STUDIO_HOME"] = str(home)
    env["DREAM_STUDIO_DB_PATH"] = str(home / "state" / "studio.db")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


_MIGRATE_PROBE = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "from core.config.paths import code_root\n"
    "from core.config.sqlite_bootstrap import bootstrap_database, latest_migration_version\n"
    "db = Path(sys.argv[1])\n"
    "v = bootstrap_database(db)\n"
    "print(json.dumps({'schema_version': v, 'latest': latest_migration_version(),"
    " 'code_root': str(code_root())}))\n"
)

_SCHEMA_PROBE = (
    "import json, sqlite3, sys\n"
    "from core.config.sqlite_bootstrap import latest_migration_version\n"
    "c = sqlite3.connect(sys.argv[1] + '?mode=ro', uri=True)\n"
    "v = c.execute('SELECT MAX(version) FROM _schema_version').fetchone()[0] or 0\n"
    "print(json.dumps({'schema_version': v, 'latest': latest_migration_version()}))\n"
)


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


@dataclass
class SelfInstallPlan:
    home: Path
    repo: Path
    ref: str
    sha: str
    version: str
    config_roots: list[Path] = field(default_factory=list)
    stamp: str = field(default_factory=lambda: datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))

    @property
    def app_id(self) -> str:
        return f"{self.version}-{self.sha[:10]}"

    @property
    def app_root(self) -> Path:
        return self.home / APP_DIRNAME

    @property
    def app_dir(self) -> Path:
        return self.app_root / self.app_id

    @property
    def build_dir(self) -> Path:
        return self.app_root / f".build-{self.app_id}-{self.stamp}"

    @property
    def db_path(self) -> Path:
        return self.home / "state" / "studio.db"

    @property
    def backup_dir(self) -> Path:
        return self.home / "state" / "backups" / f"self-install-{self.app_id}-{self.stamp}"

    def writes(self, *, reuse: bool, db_exists: bool, current: str | None) -> list[dict]:
        """Every write the install makes, in order -- what --dry-run prints."""
        steps: list[dict] = []
        if not reuse:
            steps += [
                {
                    "step": "export",
                    "path": str(self.build_dir / "src"),
                    "detail": f"git archive {self.sha} (tracked files of the commit only)",
                },
                {"step": "build-wheel", "path": str(self.build_dir / "dist")},
                {"step": "create-venv", "path": str(self.app_dir / "venv")},
                {
                    "step": "install",
                    "path": str(self.app_dir / "venv"),
                    "detail": "pip install -r requirements.lock <wheel> (non-editable)",
                },
                {
                    "step": "home-marker",
                    "path": str(self.app_dir / "venv" / APP_HOME_MARKER),
                    "content": str(self.home),
                },
                {
                    "step": "app-record",
                    "path": str(self.app_dir / APP_RECORD),
                    "detail": "written last: an app without it is incomplete and rebuilt",
                },
                {"step": "remove-build-dir", "path": str(self.build_dir)},
            ]
        else:
            steps.append(
                {
                    "step": "reuse-app",
                    "path": str(self.app_dir),
                    "detail": "already built and complete for this commit",
                }
            )
        steps.append(
            {
                "step": "smoke-test",
                "path": str(venv_ds(self.app_dir / "venv")),
                "detail": "ds --help from the new app (writes nothing)",
            }
        )
        if db_exists:
            steps.append(
                {
                    "step": "backup-authority",
                    "path": str(self.backup_dir / "studio.db"),
                    "detail": f"VACUUM INTO from {self.db_path}",
                }
            )
        steps.append(
            {
                "step": "migrate-authority",
                "path": str(self.db_path),
                "detail": "bootstrap_database() run by the NEW app"
                + ("" if db_exists else " (creates it: no authority yet)"),
            }
        )
        steps += [
            {
                "step": "record-previous",
                "path": str(self.app_root / PREVIOUS),
                "content": current or "",
            },
            {
                "step": "switch-current",
                "path": str(self.app_root / CURRENT),
                "detail": f"{'junction' if IS_WINDOWS else 'symlink'} -> {self.app_dir}",
            },
            {
                "step": "installed-version",
                "path": str(self.home / "state" / "installed-version"),
                "content": f"{self.version} {self.sha}",
            },
            {
                "step": "launcher",
                "path": str(launcher_path(self.home)),
                "content": launcher_content(self.home),
            },
            *(
                {
                    "step": "repoint-launcher",
                    "path": str(p),
                    "detail": f"a Dream Studio launcher on PATH that bypasses {launcher_path(self.home)}",
                    "content": delegating_launchers(self.home).get(p.name, ""),
                }
                for p in stale_path_launchers(self.home)
            ),
            {
                "step": "record-counts",
                "path": str(self.home / "state" / "authority-counts.json"),
                "detail": "business row counts: the baseline `ds doctor` warns against",
            },
        ]
        for root in self.config_roots:
            steps.append(
                {
                    "step": "integrate",
                    "path": str(root),
                    "detail": "ds integrate install claude_code --config-root "
                    f"{root} --execute, run by the new app (module-mode hooks)",
                }
            )
        return steps


def resolve_plan(
    *, home: Path, repo: Path, ref: str, config_roots: list[Path] | None = None
) -> SelfInstallPlan:
    """Validate the source and resolve what would be installed. Writes nothing."""
    top = Path(_git(repo, "rev-parse", "--show-toplevel").strip())
    dirty = [
        line
        for line in _git(top, "status", "--porcelain").splitlines()
        if not line.startswith("??")
    ]
    if dirty:
        raise SelfInstallError(
            f"refusing to install from a dirty tree ({top}): {len(dirty)} tracked change(s), "
            f"e.g. {dirty[0].strip()}. Commit or stash them; the app is built from a commit "
            "(git archive), so uncommitted work would silently not be in it."
        )
    sha = _git(top, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()
    version = _git(top, "show", f"{sha}:VERSION").strip()
    if not version:
        raise SelfInstallError(f"VERSION is empty at {sha}")
    return SelfInstallPlan(
        home=home.resolve(),
        repo=top,
        ref=ref,
        sha=sha,
        version=version,
        config_roots=[Path(r).expanduser().resolve() for r in (config_roots or [])],
    )


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------


def export_commit(repo: Path, sha: str, dest: Path, archive: Path) -> None:
    """The tracked files of commit *sha*, via `git archive` -- never the working tree."""
    _git(repo, "archive", "--format=zip", "-o", str(archive), sha)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(dest)


def _build_app(plan: SelfInstallPlan, log: list[str]) -> None:
    plan.app_root.mkdir(parents=True, exist_ok=True)
    # The venv is built where it will live: a venv is not relocatable (its console
    # scripts embed the interpreter's absolute path), so building it elsewhere and
    # renaming it into place leaves every ds.exe pointing at a directory that is gone.
    # app.json is written last; a directory without it is an interrupted build.
    if plan.app_dir.exists():
        _remove_tree(plan.app_dir, plan.app_root)
        log.append(f"removed incomplete {plan.app_dir.name} from an earlier run")
    src = plan.build_dir / "src"
    dist = plan.build_dir / "dist"
    src.mkdir(parents=True)
    try:
        export_commit(plan.repo, plan.sha, src, plan.build_dir / "src.zip")
        log.append(f"exported {plan.sha} to {src}")

        wheel_cmd = [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--quiet",
            "--disable-pip-version-check",
            "-w",
            str(dist),
            str(src),
        ]
        import importlib.util

        if all(importlib.util.find_spec(m) for m in ("setuptools", "wheel")):
            # Build offline with what this interpreter has; otherwise pip's isolated
            # build fetches setuptools itself.
            wheel_cmd.insert(5, "--no-build-isolation")
        _run(wheel_cmd, cwd=plan.build_dir)
        wheel = next(dist.glob("dream_studio-*.whl"))
        log.append(f"built {wheel.name}")

        venv = plan.app_dir / "venv"
        _run([sys.executable, "-m", "venv", str(venv)])
        py = venv_python(venv)
        install = [str(py), "-m", "pip", "install", "--quiet", "--disable-pip-version-check"]
        lock = src / "requirements.lock"
        if lock.is_file():
            install += ["-r", str(lock)]
        _run([*install, str(wheel)], cwd=plan.build_dir)
        log.append(f"installed {wheel.name} into {venv}")

        (venv / APP_HOME_MARKER).write_text(str(plan.home) + "\n", encoding="utf-8")
        (plan.app_dir / APP_RECORD).write_text(
            json.dumps(
                {
                    "app_id": plan.app_id,
                    "version": plan.version,
                    "sha": plan.sha,
                    "ref": plan.ref,
                    "source_repo": str(plan.repo),
                    "wheel": wheel.name,
                    "built_at": datetime.now(UTC).isoformat(),
                    "python": str(py),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        log.append(f"app ready at {plan.app_dir}")
    except Exception:
        if plan.app_dir.exists():
            _remove_tree(plan.app_dir, plan.app_root)
        raise
    finally:
        _remove_tree(plan.build_dir, plan.app_root)


def _activate(
    plan_home: Path,
    app_root: Path,
    app_dir: Path,
    *,
    version: str,
    sha: str,
    current: str | None,
    log: list[str],
) -> None:
    """Switch current, record previous, write installed-version and the launcher."""
    if current and current != app_dir.name:
        (app_root / PREVIOUS).write_text(current + "\n", encoding="utf-8")
    switch_current(app_root, app_dir.name)
    log.append(f"current -> {app_dir.name}")
    state = plan_home / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "installed-version").write_text(f"{version} {sha}\n", encoding="utf-8")
    launcher = launcher_path(plan_home)
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(launcher_content(plan_home), encoding="utf-8", newline="")
    if not IS_WINDOWS:
        launcher.chmod(0o755)
    log.append(f"launcher {launcher}")


def self_install(plan: SelfInstallPlan, *, dry_run: bool) -> dict[str, Any]:
    current = _read_link(plan.app_root / CURRENT)
    reuse = app_record(plan.app_dir) is not None
    db_exists = plan.db_path.exists()
    writes = plan.writes(reuse=reuse, db_exists=db_exists, current=current)
    base = {
        "model_name": "dream_studio_self_install",
        "home": str(plan.home),
        "source_repo": str(plan.repo),
        "ref": plan.ref,
        "sha": plan.sha,
        "version": plan.version,
        "app_id": plan.app_id,
        "current_before": current,
    }
    if dry_run:
        return {**base, "ok": True, "dry_run": True, "writes": writes}

    # A DROP STOPS THE INSTALL. Counts below the recorded baseline mean business data went
    # missing since the last check; installing over that, then recording the smaller
    # numbers as the new baseline, would bury the loss (round-table S4).
    from core.health.authority_data import authority_data_check, drops

    before = authority_data_check(plan.home, plan.db_path)
    if drops(before):
        return {
            **base,
            "ok": False,
            "dry_run": False,
            "switched": False,
            "current_after": current,
            "error": (
                "refusing to install: the authority's business counts dropped since the last "
                f"baseline ({'; '.join(drops(before))}). Restore from a backup, or record the "
                "new counts deliberately with `ds doctor --record-counts --accept-drop`, then "
                "run self-install again."
            ),
        }

    log: list[str] = []
    try:
        if not reuse:
            _build_app(plan, log)
        venv = plan.app_dir / "venv"
        env = _app_env(plan.home)
        _run([str(venv_ds(venv)), "--help"], env=env, cwd=plan.app_root)
        log.append("smoke test: ds --help ok")
        backup = None
        if db_exists:
            backup = backup_authority(plan.db_path, plan.backup_dir)
            log.append(f"authority backed up to {backup}")
        plan.db_path.parent.mkdir(parents=True, exist_ok=True)
        migrated = json.loads(
            _run(
                [str(venv_python(venv)), "-I", "-c", _MIGRATE_PROBE, str(plan.db_path)],
                env=env,
                cwd=plan.app_root,
            )
            .strip()
            .splitlines()[-1]
        )
        log.append(
            f"authority at schema {migrated['schema_version']} (app ships {migrated['latest']})"
        )
    except Exception as exc:
        return {
            **base,
            "ok": False,
            "dry_run": False,
            "switched": False,
            "error": str(exc),
            "log": log,
            "current_after": current,
        }

    _activate(
        plan.home,
        plan.app_root,
        plan.app_dir,
        version=plan.version,
        sha=plan.sha,
        current=current,
        log=log,
    )

    # Record the post-install counts as the baseline `ds doctor` warns against. A drop
    # was refused before anything ran, so this never records over one.
    from core.health.authority_data import record_counts

    authority = authority_data_check(plan.home, plan.db_path)
    if authority["readable"] and not drops(authority):
        authority["recorded"] = record_counts(plan.home, plan.db_path)

    repointed = _repoint_launchers(plan.home, log)

    integrations = []
    for root in plan.config_roots:
        try:
            out = _run(
                [
                    str(venv_python(plan.app_root / CURRENT / "venv")),
                    "-I",
                    "-m",
                    "interfaces.cli.ds",
                    "--home",
                    str(plan.home),
                    "integrate",
                    "install",
                    "claude_code",
                    "--config-root",
                    str(root),
                    "--execute",
                ],
                env=_app_env(plan.home),
                cwd=plan.app_root,
            )
            integrations.append(
                {"config_root": str(root), "ok": True, "output_tail": out.strip()[-800:]}
            )
        except SelfInstallError as exc:
            integrations.append({"config_root": str(root), "ok": False, "error": str(exc)})
    return {
        **base,
        "ok": all(i["ok"] for i in integrations),
        "dry_run": False,
        "switched": True,
        "current_after": plan.app_id,
        "backup": str(backup) if backup else None,
        "migration": migrated,
        "authority_data": authority,
        "repointed_launchers": repointed,
        "integrations": integrations,
        "log": log,
    }


def rollback(home: Path, *, dry_run: bool) -> dict[str, Any]:
    """Switch current back to the app recorded in app/previous."""
    home = home.resolve()
    app_root = home / APP_DIRNAME
    current = _read_link(app_root / CURRENT)
    try:
        previous = (app_root / PREVIOUS).read_text(encoding="utf-8").strip()
    except OSError:
        previous = ""
    base = {
        "model_name": "dream_studio_self_install_rollback",
        "home": str(home),
        "current_before": current,
        "rollback_to": previous or None,
    }
    if not previous:
        return {**base, "ok": False, "error": f"no previous app recorded in {app_root / PREVIOUS}"}
    record = app_record(app_root / previous)
    if record is None:
        return {**base, "ok": False, "error": f"{app_root / previous} is missing or incomplete"}
    db_path = home / "state" / "studio.db"
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    backup_dir = home / "state" / "backups" / f"self-install-rollback-{previous}-{stamp}"
    writes = [
        {
            "step": "check-schema",
            "path": str(db_path),
            "detail": "the previous app must ship every migration the authority has",
        },
        {"step": "backup-authority", "path": str(backup_dir / "studio.db")},
        {"step": "record-previous", "path": str(app_root / PREVIOUS), "content": current or ""},
        {"step": "switch-current", "path": str(app_root / CURRENT), "detail": f"-> {previous}"},
        {
            "step": "installed-version",
            "path": str(home / "state" / "installed-version"),
            "content": f"{record['version']} {record['sha']}",
        },
        {"step": "launcher", "path": str(launcher_path(home)), "content": launcher_content(home)},
    ]
    if dry_run:
        return {**base, "ok": True, "dry_run": True, "writes": writes}
    log: list[str] = []
    backup = None
    if db_path.exists():
        venv = app_root / previous / "venv"
        probe = json.loads(
            _run(
                [str(venv_python(venv)), "-I", "-c", _SCHEMA_PROBE, db_path.resolve().as_uri()],
                env=_app_env(home),
                cwd=app_root,
            )
            .strip()
            .splitlines()[-1]
        )
        if probe["schema_version"] > probe["latest"]:
            return {
                **base,
                "ok": False,
                "switched": False,
                "error": (
                    f"the authority is at schema {probe['schema_version']} but {previous} ships "
                    f"migrations only to {probe['latest']}; it cannot open it. Restore the backup "
                    f"taken before the upgrade (under {home / 'state' / 'backups'}, "
                    "self-install-*) with `ds restore <dir> --execute`, then roll back."
                ),
            }
        backup = backup_authority(db_path, backup_dir)
        log.append(f"authority backed up to {backup}")
    _activate(
        home,
        app_root,
        app_root / previous,
        version=record["version"],
        sha=record["sha"],
        current=current,
        log=log,
    )
    return {
        **base,
        "ok": True,
        "dry_run": False,
        "switched": True,
        "current_after": previous,
        "backup": str(backup) if backup else None,
        "log": log,
    }


def default_repo() -> Path | None:
    """The checkout this `ds` runs from, if it runs from one."""
    from core.config.paths import code_root, is_source_checkout

    return code_root() if is_source_checkout() else None
