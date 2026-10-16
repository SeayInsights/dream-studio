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
import re
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
#: <version>-<sha10>: what app/previous may name. Anything else (a path, "..") is refused.
APP_ID = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+_]*-[0-9a-f]{10}")


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


_PINNED_HOME = re.compile(
    r"""DREAM_STUDIO_HOME\s*=\s*["']?([^"'\r\n]+?)["']?\s*$|--home\s+["']([^"']+)["']""",
    re.MULTILINE,
)

#: Where self-install records the launchers it repointed, for rollback to restore.
REPOINTED_RECORD = "repointed-launchers.json"


def _same_path(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _launcher_home(text: str) -> Path:
    """The home a launcher runs against: the one it pins, else the default home."""
    match = _PINNED_HOME.search(text)
    if match:
        return Path((match.group(1) or match.group(2)).strip()).expanduser()
    from core.config.paths import default_home

    return default_home()


def _path_launchers(home: Path) -> tuple[list[Path], list[dict[str, str]]]:
    """Dream Studio launchers in ~/.local/bin (`ds install-command`) that do not delegate
    to <home>/bin: (those running THIS home, to repoint; those pinned elsewhere, left).

    That directory usually comes first on PATH, so such a launcher keeps running a
    checkout after self-install. One pinned to ANOTHER home belongs to that home: sending
    it to this home's app would point its operator at a different authority.
    """
    local_bin = Path.home() / ".local" / "bin"
    target = str(launcher_path(home))
    stale: list[Path] = []
    left: list[dict[str, str]] = []
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
        if not owned or target in text:
            continue
        pinned = _launcher_home(text)
        if _same_path(pinned, home):
            stale.append(path)
        else:
            left.append({"path": str(path), "home": str(pinned)})
    return stale, left


def launcher_belongs_to(text: str, home: Path) -> bool:
    """Whether a `ds` launcher's *text* is Dream Studio's, for *home*: a checkout
    launcher pinned to it, or one that hands every call to <home>/bin."""
    if str(launcher_path(home)) in text:
        return True
    owned = (
        "DREAM_STUDIO_SOURCE_ROOT" in text
        or "ds_entry.py" in text
        or ("interfaces" in text and "ds.py" in text)
    )
    return owned and _same_path(_launcher_home(text), home)


def stale_path_launchers(home: Path) -> list[Path]:
    """The ~/.local/bin launchers for THIS home that bypass <home>/bin."""
    return _path_launchers(home)[0]


def _repoint_launchers(home: Path, backup_dir: Path, app_id: str, log: list[str]) -> list[dict]:
    """Repoint this home's PATH launchers to <home>/bin, saving each previous file in the
    install's backup directory and recording it so `--rollback` can put it back."""
    content = delegating_launchers(home)
    repointed = []
    for path in stale_path_launchers(home):
        new = content.get(path.name) or next(iter(content.values()))
        saved = backup_dir / "launchers" / path.name
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, saved)
        path.write_text(new, encoding="utf-8", newline="")
        log.append(f"repointed {path} to {launcher_path(home)} (previous saved at {saved})")
        repointed.append({"path": str(path), "saved": str(saved), "written": new})
    if repointed:
        record = home / "state" / REPOINTED_RECORD
        record.write_text(
            json.dumps({"app_id": app_id, "launchers": repointed}, indent=2), encoding="utf-8"
        )
    return repointed


def _saved_launchers(home: Path) -> list[dict]:
    """The PATH launchers an install repointed, with where each previous file was saved.

    A rollback never puts them back: it always goes to another INSTALLED app, which wants
    the delegating launchers, and a restored checkout launcher would take PATH off the
    app the rollback just made current. They are reported so going back to a checkout
    stays a deliberate, manual step.
    """
    record = home / "state" / REPOINTED_RECORD
    if not record.is_file():
        return []
    return list(json.loads(record.read_text(encoding="utf-8")).get("launchers", []))


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
    # A locking read, not an immutable one: hooks may be writing while the backup runs.
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
        raise SelfInstallError(f"{_shown(cmd)} failed (exit {proc.returncode}):\n{tail}")
    return proc.stdout


def _shown(cmd: list[str]) -> str:
    """The command as an operator can read it: a `-c` program is named, not pasted,
    and every argument after it is kept."""
    shown = []
    for i, part in enumerate(cmd):
        if i > 0 and cmd[i - 1] == "-c":
            shown.append("<inline program>")
        else:
            shown.append(f'"{part}"' if " " in part else part)
    return " ".join(shown)


def _app_env(home: Path) -> dict[str, str]:
    """Environment for running the NEW app against *home* -- nothing inherited that could
    point it at a checkout or at another home."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("PYTHON", "DREAM_STUDIO")) and k != "DS_DREAM_STUDIO_HOME"
    }
    env["DREAM_STUDIO_HOME"] = str(home)
    db = home / "state" / "studio.db"
    env["DREAM_STUDIO_DB_PATH"] = str(db)
    env["PYTHONIOENCODING"] = "utf-8"
    # The one DREAM_STUDIO_* variable passed through: a deliberate, scoped opt-in to
    # create this home's authority (core.config.sqlite_bootstrap.CREATE_AUTHORITY_ENV).
    wanted = os.environ.get("DREAM_STUDIO_CREATE_AUTHORITY")
    if wanted and Path(wanted).expanduser().resolve() == db.resolve():
        env["DREAM_STUDIO_CREATE_AUTHORITY"] = str(db)
    return env


_MIGRATE_PROBE = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "from core.config.paths import code_root\n"
    "from core.config.sqlite_bootstrap import (bootstrap_database, carry_over_activation,"
    " latest_migration_version)\n"
    "db = Path(sys.argv[1])\n"
    "v = bootstrap_database(db)\n"
    "carried = carry_over_activation(db)\n"
    "print(json.dumps({'schema_version': v, 'latest': latest_migration_version(),"
    " 'activation_carried_over': carried, 'code_root': str(code_root())}))\n"
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
        pre_migration = self._pre_migration_backup() if db_exists else None
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
        if pre_migration:
            steps.append(pre_migration)
        steps.append(
            {
                "step": "migrate-authority",
                "path": str(self.db_path),
                "detail": "bootstrap_database() run by the NEW app"
                + (
                    "; records the activation an older install made in its tree, if any"
                    if db_exists
                    else " (creates it: a new home with no authority yet)"
                ),
            }
        )
        carry = self._activation_carry_over() if db_exists else None
        if carry:
            steps.append(carry)
        if current and current != self.app_id:
            steps.append(
                {
                    "step": "record-previous",
                    "path": str(self.app_root / PREVIOUS),
                    "content": current,
                }
            )
        steps += [
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
                    "detail": (
                        f"a Dream Studio launcher on PATH for this home that bypasses "
                        f"{launcher_path(self.home)}; the previous file is saved at "
                        f"{self.backup_dir / 'launchers' / p.name}"
                    ),
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
            steps.append(self._integration_preview(root))
        return steps

    def _git_show(self, rel: str) -> str | None:
        proc = subprocess.run(
            ["git", "-C", str(self.repo), "show", f"{self.sha}:{rel}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return proc.stdout if proc.returncode == 0 else None

    def _pre_migration_backup(self) -> dict | None:
        """The studio-pre-N backup run_migrations itself takes before applying anything
        to a live authority, when the commit being installed ships migrations it lacks."""
        listing = subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
                "ls-tree",
                "--name-only",
                self.sha,
                "core/event_store/migrations/",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.split()
        versions = [
            int(Path(n).name.split("_", 1)[0])
            for n in listing
            if Path(n).name[:1].isdigit() and n.endswith(".sql")
        ]
        if not versions:
            return None
        released_text = self._git_show("core/event_store/migrations/.released_version") or ""
        released = int(released_text.strip()) if released_text.strip().isdigit() else max(versions)
        activated = self.db_path.parent / "migrations-activated-version"
        if activated.is_file() and activated.read_text(encoding="utf-8").strip().isdigit():
            released = max(released, int(activated.read_text(encoding="utf-8").strip()))
        from core.config.sqlite_readonly import connect_read_only

        conn = connect_read_only(self.db_path)
        try:
            has = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='_schema_version'"
            ).fetchone()
            applied = (
                conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0] or 0
                if has
                else 0
            )
        finally:
            conn.close()
        target = min(released, max(versions))
        if applied >= target:
            return None
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        return {
            "step": "pre-migration-backup",
            "path": str(self.home / "state" / "backups" / f"studio-pre-{applied + 1}-{stamp}.db"),
            "detail": f"taken by run_migrations before applying {applied + 1}..{target}",
        }

    def _activation_carry_over(self) -> dict | None:
        """The migrations-activated-version write carry_over_activation() makes, if any:
        an authority past the new app's shipped sentinel with no activation record."""
        activated = self.db_path.parent / "migrations-activated-version"
        if activated.is_file():
            return None
        released_text = (
            self._git_show("core/event_store/migrations/.released_version") or ""
        ).strip()
        if not released_text.isdigit():
            return None
        from core.config.sqlite_readonly import connect_read_only

        conn = connect_read_only(self.db_path)
        try:
            has = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='_schema_version'"
            ).fetchone()
            applied = (
                conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0] or 0
                if has
                else 0
            )
        finally:
            conn.close()
        if applied <= int(released_text):
            return None
        return {
            "step": "carry-over-activation",
            "path": str(activated),
            "content": str(applied),
            "detail": (
                f"the authority is at schema {applied}, past the app's released "
                f"{released_text}, with no activation record: an older install activated it "
                "in its own tree"
            ),
        }

    def _integration_preview(self, root: Path) -> dict:
        """What the new app's `integrate install --config-root <root>` will write.

        Planned here with this ds's installer in module mode, so file lists come from
        this code's canonical tree; the new app plans its own, from its tree, when it runs.
        """
        from collections import Counter

        from integrations.installer.claude_code import ClaudeCodeInstaller
        from integrations.installer.claude_code_fileops import _interpolate_hook_modules
        from integrations.compiler.claude_code import _load_hooks_template
        from integrations.manifest import get_manifest_path

        from integrations.installer.claude_code_installer import will_change

        installer = ClaudeCodeInstaller(root, "user", ds_home=self.home, hook_mode="module")
        plan = installer.plan()
        # Only what the install will change, by the executor's own comparison: counting
        # every managed file planned 652 backups where an install over the same root
        # wrote 5.
        changes = [op for op in plan.ops if will_change(op)]
        python = str(venv_python(self.app_root / CURRENT / "venv")).replace("\\", "/")
        commands = [
            h["command"]
            for e in _interpolate_hook_modules(_load_hooks_template(), f'"{python}"')
            for h in e.get("hooks", [])
        ]
        return {
            "step": "integrate",
            "path": str(root),
            "detail": f"ds integrate install claude_code --config-root {root} --execute, run "
            "by the new app (module-mode hooks)",
            "operations": dict(Counter(op.op for op in changes)),
            "unchanged": len(plan.ops) - len(changes),
            "deletes": [str(op.target) for op in changes if op.op == "delete"],
            "retires": [
                str(op.target)
                for op in changes
                if op.op == "create" and "Retire" in (op.reason or "")
            ],
            "settings": str(root / "settings.json"),
            # backup_before_write copies each file it overwrites or deletes, first.
            "backups": [
                str(
                    self.home / "backups" / "claude_code" / _relative_or_name(Path(op.target), root)
                )
                + ".<UTC timestamp>.bak"
                for op in changes
                if op.backup_required and Path(op.target).exists()
            ],
            "hook_commands": commands,
            "manifest": str(get_manifest_path("claude_code", self.home, root)),
        }


def _relative_or_name(target: Path, root: Path) -> str:
    try:
        return target.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return target.name


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


def _live_app_refusal(plan: SelfInstallPlan) -> str | None:
    """Why the app directory cannot be rebuilt, when it is the live app with no record.

    Never rmtree the app every hook and the launcher are running from: an incomplete
    record on the live app is repaired by moving `current` elsewhere first.
    """
    live = plan.app_root / CURRENT
    if not plan.app_dir.exists():
        return None
    if not (live.exists() or live.is_junction() or live.is_symlink()):
        return None
    if live.resolve() != plan.app_dir.resolve():
        return None
    previous_file = plan.app_root / PREVIOUS
    previous = previous_file.read_text(encoding="utf-8").strip() if previous_file.is_file() else ""
    rollback = (
        f" or roll back to {previous} (`ds --home {plan.home} self-install --rollback --execute`)"
        if previous
        else ""
    )
    return (
        f"{plan.app_dir} is the live app (app/current points at it) but has no {APP_RECORD}; "
        "refusing to remove and rebuild it under running hooks. Move `current` off it first: "
        f"install another commit (`ds --home {plan.home} self-install --ref <ref> --execute`)"
        f"{rollback}; then this commit can be installed again."
    )


def _build_app(plan: SelfInstallPlan, log: list[str]) -> None:
    plan.app_root.mkdir(parents=True, exist_ok=True)
    refusal = _live_app_refusal(plan)
    if refusal:
        raise SelfInstallError(refusal)
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
    # THE GUARD RUNS FIRST, dry run included: a dry run that promised to create an
    # authority the real run then refused to create was a plan nobody could follow.
    from core.config.sqlite_bootstrap import AuthorityRefusedError, assert_may_create_database

    try:
        assert_may_create_database(plan.db_path)
    except AuthorityRefusedError as exc:
        return {
            **base,
            "ok": False,
            "dry_run": dry_run,
            "switched": False,
            "current_after": current,
            "error": (
                f"{exc} self-install never creates an authority in a home that has had one "
                f"(unless DREAM_STUDIO_CREATE_AUTHORITY names {plan.db_path}); it migrates the "
                "one that is there."
            ),
        }
    # EVERY REFUSAL THE REAL RUN MAKES, THE DRY RUN MAKES TOO. A dry run that said ok:true
    # over a drop, or planned a fresh venv where the real run refused to touch the live app,
    # was a plan nobody could follow.
    #
    # A DROP STOPS THE INSTALL. Counts below the recorded baseline mean business data went
    # missing since the last check; installing over that, then recording the smaller
    # numbers as the new baseline, would bury the loss.
    from core.health.authority_data import authority_data_check, drops, empty_without_baseline

    before = authority_data_check(plan.home, plan.db_path)
    refusal = None
    if db_exists and empty_without_baseline(before):
        # What a REPLACED authority looks like. Installing over it and recording zeros as
        # the baseline would make the next doctor say pass. Only a run that creates the
        # authority records its empty counts without asking.
        refusal = (
            "refusing to install: this installed home's authority exists but holds no "
            "projects, work orders, tasks or events, and no counts were ever recorded. If it "
            "had data it was replaced: restore it (`ds --home "
            f"{plan.home} restore <dir> --execute`). If it is meant to be empty, record that "
            f"with `ds --home {plan.home} doctor --record-counts`, then run self-install again."
        )
    elif drops(before):
        refusal = (
            "refusing to install: the authority's business counts dropped since the last "
            f"baseline ({'; '.join(drops(before))}). Restore from a backup, or record the "
            "new counts deliberately with `ds doctor --record-counts --accept-drop`, then "
            "run self-install again."
        )
    elif not reuse:
        refusal = _live_app_refusal(plan)
    if refusal:
        return {
            **base,
            "ok": False,
            "dry_run": dry_run,
            "switched": False,
            "current_after": current,
            "error": refusal,
        }
    try:
        writes = plan.writes(reuse=reuse, db_exists=db_exists, current=current)
    except sqlite3.DatabaseError as exc:
        from core.config.sqlite_bootstrap import unreadable_authority_message

        return {
            **base,
            "ok": False,
            "dry_run": dry_run,
            "switched": False,
            "current_after": current,
            "error": unreadable_authority_message(plan.db_path, exc),
        }
    if dry_run:
        return {**base, "ok": True, "dry_run": True, "writes": writes}

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
            + (
                "; the newer migrations are unreleased: apply them when ready with "
                f"`ds --home {plan.home} migrate activate --confirm`"
                if migrated["schema_version"] < migrated["latest"]
                else ""
            )
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

    repointed = _repoint_launchers(plan.home, plan.backup_dir, plan.app_id, log)
    left = _path_launchers(plan.home)[1]

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
        "left_launchers": left,
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
        return {
            **base,
            "ok": False,
            "error": (
                f"no previous app recorded in {app_root / PREVIOUS}: this home has had one "
                "installed app, so there is nothing to roll back to. To run another version, "
                f"install it: `ds --home {home} self-install --ref <ref> --execute`."
            ),
        }
    if not APP_ID.fullmatch(previous):
        return {
            **base,
            "ok": False,
            "error": f"{app_root / PREVIOUS} does not hold a bare app id: {previous!r}",
        }
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
    saved = _saved_launchers(home)
    if dry_run:
        return {
            **base,
            "ok": True,
            "dry_run": True,
            "writes": writes,
            "saved_launchers": [{"path": i["path"], "saved": i["saved"]} for i in saved],
        }
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
                    f"self-install-*) with `ds --home {home} restore <dir> --execute`, then "
                    "roll back."
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
        "saved_launchers": [{"path": item["path"], "saved": item["saved"]} for item in saved],
        "backup": str(backup) if backup else None,
        "log": log,
    }


def default_repo() -> Path | None:
    """The checkout this `ds` runs from, if it runs from one."""
    from core.config.paths import code_root, is_source_checkout

    return code_root() if is_source_checkout() else None
