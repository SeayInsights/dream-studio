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


def _check_version_current(source_root: Path, dream_studio_home: Path) -> dict[str, Any]:
    try:
        repo_file = source_root / "VERSION"
        installed_file = dream_studio_home / "state" / "installed-version"
        repo_ver = repo_file.read_text(encoding="utf-8").strip() if repo_file.is_file() else None
        installed_ver = (
            installed_file.read_text(encoding="utf-8").strip() if installed_file.is_file() else None
        )
        current = repo_ver is not None and repo_ver == installed_ver
        return {"repo": repo_ver, "installed": installed_ver, "current": current}
    except Exception:
        return {"repo": None, "installed": None, "current": False}


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

    stale: list[str] = []
    checked = 0
    for rel in projected_hook_relpaths(source_root):
        canonical = source_root / rel
        deployed = claude_dir / "hooks" / rel
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
    return {"checked": checked, "stale": stale, "ok": not stale}
