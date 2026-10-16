"""Doctor composite checks — dispatcher hooks, agents, events, version, hook freshness.

Split out of doctor.py (WO-GF-CORE-HEALTH-SKILLS): the individual health checks
composed by ``run_doctor_checks`` in doctor_main.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _check_dispatcher_hooks(claude_dir: Path) -> bool:
    import json

    _DISPATCHER_MARKERS = (
        "hooks\\dispatch\\hooks.py",
        "hooks/dispatch/hooks.py",
        "runtime/dispatch/hooks",
        "-m runtime.dispatch.hooks",  # module mode (an installed app)
        "'dispatch'/'hooks.py'",
    )
    try:
        settings_path = claude_dir / "settings.json"
        if not settings_path.is_file():
            return False
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        hooks_section = data.get("hooks", {})
        event_entries = hooks_section.get("UserPromptSubmit", [])
        for entry in event_entries:
            for h in entry.get("hooks", []):
                cmd = h.get("command", "")
                if any(m in cmd for m in _DISPATCHER_MARKERS):
                    return True
        return False
    except Exception:
        return False


def _check_agents_installed(claude_dir: Path, source_root: Path) -> dict[str, Any]:
    try:
        agents_src = source_root / "canonical" / "agents"
        expected = (
            [p.stem for p in agents_src.glob("*.md") if p.name != "README.md"]
            if agents_src.is_dir()
            else []
        )
        agents_dir = claude_dir / "agents"
        installed = [name for name in expected if (agents_dir / f"{name}.md").is_file()]
        missing = [name for name in expected if name not in installed]
        return {"total_expected": len(expected), "installed": len(installed), "missing": missing}
    except Exception:
        return {"total_expected": 0, "installed": 0, "missing": []}


def _check_failed_events(dream_studio_home: Path) -> dict[str, int]:
    try:
        failed_dir = dream_studio_home / "events" / "failed"
        if not failed_dir.is_dir():
            return {"count": 0}
        count = sum(1 for p in failed_dir.iterdir() if p.is_file() and p.suffix == ".json")
        return {"count": count}
    except Exception:
        return {"count": 0}


def _check_handoff_spawner(source_root: Path) -> dict[str, Any]:
    """Verify the handoff-continuation spawner can load session_config.spawn_new_session."""
    import importlib.util

    session_config_path = source_root / "runtime" / "session_config.py"
    if not session_config_path.is_file():
        return {
            "status": "fail",
            "reason": "session_config.py not found",
            "spawn_importable": False,
        }
    try:
        spec = importlib.util.spec_from_file_location(
            "_ds_session_config_check", session_config_path
        )
        if spec is None or spec.loader is None:
            return {
                "status": "fail",
                "reason": "module spec unresolvable",
                "spawn_importable": False,
            }
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        if not hasattr(mod, "spawn_new_session"):
            return {
                "status": "fail",
                "reason": "spawn_new_session missing from session_config",
                "spawn_importable": False,
            }
        return {"status": "pass", "spawn_importable": True}
    except Exception as exc:
        return {"status": "fail", "reason": str(exc), "spawn_importable": False}


def _code_sha(source_root: Path) -> str | None:
    """The commit the code at *source_root* was built from, when that can be known.

    An installed app: the sha in its app.json (<app>/app.json above venv/.../site-packages).
    A git checkout: HEAD. Anything else: None.
    """
    import json
    import shutil
    import subprocess

    for parent in source_root.parents:
        record = parent / "app.json"
        if record.is_file():
            sha = json.loads(record.read_text(encoding="utf-8")).get("sha")
            return sha if isinstance(sha, str) and sha else None
    if not (source_root / ".git").exists() or shutil.which("git") is None:
        return None
    proc = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    sha = proc.stdout.strip()
    return sha if proc.returncode == 0 and len(sha) == 40 else None


def _check_version_current(source_root: Path, dream_studio_home: Path) -> dict[str, Any]:
    """Is the installed Dream Studio the code this doctor runs?

    VERSION is the same string for every commit, so comparing it alone called any older
    install current. When both sides know their commit (installed-version's sha from
    `ds self-install`; app.json or the checkout's HEAD here) the commits are compared.
    When either does not, the answer is None -- unknown -- with the reason, never True.
    """
    from core.config.paths import installed_version

    repo_file = source_root / "VERSION"
    repo_ver = repo_file.read_text(encoding="utf-8").strip() if repo_file.is_file() else None
    installed_ver, installed_sha = installed_version(dream_studio_home)
    code_sha = _code_sha(source_root)
    reason = None
    if repo_ver is None or installed_ver is None:
        current: bool | None = False
        reason = "no VERSION here" if repo_ver is None else "nothing installed in this home"
    elif repo_ver != installed_ver:
        current = False
        reason = f"installed {installed_ver}, this code is {repo_ver}"
    elif installed_sha and code_sha:
        current = installed_sha == code_sha
        if not current:
            reason = f"installed commit {installed_sha[:10]}, this code is {code_sha[:10]}"
    else:
        current = None
        reason = (
            "installed-version records no commit (an install older than ds self-install)"
            if not installed_sha
            else "the commit of this code is unknown"
        )
    return {
        "repo": repo_ver,
        "installed": installed_ver,
        "installed_sha": installed_sha,
        "code_sha": code_sha,
        "current": current,
        "reason": reason,
    }


#: Directories under the Dream Studio home whose ``*.db`` files are expected
#: state rather than ghosts. ``backups/`` is here because
#: ``core/installed_productization_backup.py`` writes productization snapshots
#: to ``dream_studio_home / "backups"`` — flagging those made ``ds doctor``
#: report fail forever against a backup the product authored itself, and a
#: check that cries wolf on correct state teaches the reader to ignore it.
_EXPECTED_DB_DIRNAMES = ("state", "diagnostics", "backups")


def _check_stale_dbs(dream_studio_home: Path) -> dict[str, Any]:
    """Scan ~/.dream-studio/ for .db files outside the expected directories.

    Anything else is unexpected and likely a stale ghost file (e.g. an empty
    authority.db created at the home root by a misconfigured resolver). Flags
    them with a clear delete recommendation so they don't cause false-negative
    task-done reads or other silent authority mismatches.

    Expected directories are listed in ``_EXPECTED_DB_DIRNAMES``; a database
    anywhere else — including at the home root — is still reported.
    """
    try:
        expected = tuple(dream_studio_home / name for name in _EXPECTED_DB_DIRNAMES)
        stale = [
            str(db_file)
            for db_file in dream_studio_home.rglob("*.db")
            if not any(db_file.is_relative_to(d) for d in expected)
        ]
        return {"stale_dbs": stale, "ok": len(stale) == 0}
    except Exception:
        return {"stale_dbs": [], "ok": True}


def _check_hook_freshness(source_root: Path, claude_dir: Path) -> dict[str, Any]:
    """Compare EVERY deployed hook-projection file against canonical runtime.

    WO-HOOK-DRIFT-STOP: previously only the two entry hooks were compared —
    runtime/lib/enforcement.py (imported by both enforce hooks) and the 30+
    other copied files could silently drift, so a stale deployed copy ran
    outdated enforcement undetected by doctor. The manifest now comes from
    ``projected_hook_relpaths`` — the same set the projection sync copies.
    Line endings are normalized so a CRLF install still compares equal.
    """
    from core.health.doctor_shared import projected_hook_relpaths
    from integrations.installer.claude_code_fileops import is_retired_stub

    stale: list[str] = []
    retired: list[str] = []
    checked = 0
    for rel in projected_hook_relpaths(source_root):
        canonical = source_root / rel
        deployed = claude_dir / "hooks" / rel
        # A module-mode install leaves stubs where copied entry points were; they are
        # meant to differ from the source.
        if deployed.is_file() and is_retired_stub(deployed):
            retired.append(rel)
            continue
        if not canonical.is_file() or not deployed.is_file():
            continue
        checked += 1
        try:
            canon_bytes = canonical.read_bytes().replace(b"\r\n", b"\n")
            deployed_bytes = deployed.read_bytes().replace(b"\r\n", b"\n")
        except OSError:
            continue
        if canon_bytes != deployed_bytes:
            stale.append(rel)
    from integrations.targets.claude_code.settings_merge import DS_HOOK_FILES

    for rel in sorted(DS_HOOK_FILES):
        deployed = claude_dir / "hooks" / rel
        if rel not in retired and deployed.is_file() and is_retired_stub(deployed):
            retired.append(rel)
    if retired:
        # The copied tree beside a retired entry point is no longer run: hooks run from
        # the installed app's modules.
        stale = []
    result: dict[str, Any] = {"checked": checked, "stale": stale, "ok": not stale}
    if retired:
        result["retired"] = retired
    return result


def _check_installed_app(dream_studio_home: Path) -> dict[str, Any]:
    """Which code this doctor runs from, against the app `ds self-install` installed.

    A doctor that compares a checkout with itself proves nothing about what the hooks
    and the launcher run. This names the code root in use, the installed app that
    <home>/app/current points at (its app.json), and whether installed-version agrees.
    """
    from core.config.paths import code_root, installed_version, is_source_checkout

    code = code_root()
    current = dream_studio_home / "app" / "current"
    target = current.resolve() if current.exists() else None
    record = None
    if target is not None and (target / "app.json").is_file():
        import json

        record = json.loads((target / "app.json").read_text(encoding="utf-8"))
    version, sha = installed_version(dream_studio_home)
    running_from_app = target is not None and target in code.parents
    warnings: list[str] = []
    if target is not None and not running_from_app:
        warnings.append(f"this ds runs from {code}, not the installed app {target}")
    if record is not None and (record.get("version"), record.get("sha")) != (version, sha):
        warnings.append(
            f"installed-version ({version} {sha}) does not match the current app "
            f"({record.get('version')} {record.get('sha')})"
        )
    return {
        "code_root": str(code),
        "running_from_checkout": is_source_checkout(code),
        "installed_app": str(target) if target is not None else None,
        "installed_app_record": record,
        "running_from_installed_app": running_from_app,
        "installed_version": version,
        "installed_sha": sha,
        "warnings": warnings,
    }
