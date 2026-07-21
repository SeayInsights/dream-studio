"""Uninstall flow: adapter teardown and optional state purge.

WO-GF-INSTALLED-PROD: split from ``core/installed_productization.py``. Holds the
uninstall inventory check, the tiered uninstall (integration teardown + optional
state purge), and the per-copy Claude-hook deregistration helper. No logic
changes — extracted verbatim from the original module.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from core.installed_runtime import resolve_installed_runtime_paths

from .installed_productization_backup import backup_runtime
from .installed_productization_shared import DEFAULT_GLOBAL_COMMAND_DIR


def uninstall_runtime_check(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
) -> dict[str, Any]:
    """Return uninstall inventory without deleting anything."""

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    inventory = []
    if paths.dream_studio_home.exists():
        inventory = [
            str(path.relative_to(paths.dream_studio_home))
            for path in paths.dream_studio_home.rglob("*")
            if path.is_file()
        ]
    return {
        "model_name": "dream_studio_runtime_uninstall_check",
        "dream_studio_home": str(paths.dream_studio_home),
        "exists": paths.dream_studio_home.exists(),
        "file_count": len(inventory),
        "sample_inventory": inventory[:20],
        "uninstall_executed": False,
        "delete_authorized": False,
        "requires_operator_approval": True,
    }


def _deregister_claude_hooks(path: Path) -> dict[str, Any]:
    """Remove Dream-Studio hook wiring from one Claude settings.json copy.

    Returns a per-copy report. Missing/foreign files are reported, not mutated.
    """

    from integrations.targets.claude_code.settings_merge import (
        deregister_ds_hooks,
        load_settings,
        settings_to_json,
    )

    path = Path(path)
    if not path.is_file():
        return {"path": str(path), "exists": False, "hooks_removed": 0}
    settings = load_settings(path)
    updated, removed = deregister_ds_hooks(settings)
    if removed:
        path.write_text(settings_to_json(updated) + "\n", encoding="utf-8")
    return {"path": str(path), "exists": True, "hooks_removed": removed}


def uninstall_runtime(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
    claude_settings_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
    command_dir: str | Path | None = None,
    backup_dir: str | Path | None = None,
    execute: bool = False,
    purge_state: bool = False,
    confirm_purge: bool = False,
) -> dict[str, Any]:
    """Uninstall Dream Studio adapter wiring, with an optional state purge.

    Three tiers, all gated behind explicit flags so an accidental invocation
    mutates nothing:

    - Default (``execute=False``): dry-run. Returns the inventory and the
      removed-vs-preserved target plan. Mutates nothing.
    - Integration teardown (``execute=True``): removes the ``.claude`` hook
      wiring from every supplied settings.json copy and the global ``ds``
      launchers. Leaves ``~/.dream-studio`` state intact — reversible by a
      reinstall.
    - State purge (``execute=True, purge_state=True``): everything above, plus a
      wipe of ``~/.dream-studio``. Refuses unless ``confirm_purge=True`` (the
      mandatory second confirmation) and always takes an automatic backup
      OUTSIDE the home directory first.
    """

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    home = paths.dream_studio_home
    launcher_dir = Path(command_dir or DEFAULT_GLOBAL_COMMAND_DIR).resolve()
    launcher_targets = [launcher_dir / "ds.cmd", launcher_dir / "ds.ps1"]
    settings_paths = [Path(p) for p in (claude_settings_paths or [])]

    removed_targets = {
        "claude_hook_wiring": [str(p) for p in settings_paths],
        "global_launchers": [str(p) for p in launcher_targets],
    }
    preserved_targets = {
        "dream_studio_state": str(home),
        "note": "State tier (studio.db, config, adapters, meta, context-packets) is "
        "preserved unless --purge-state is given with its second confirmation.",
    }
    if purge_state:
        # Under a purge the state tier moves from preserved to removed.
        removed_targets["dream_studio_state"] = str(home)
        preserved_targets = {
            "automatic_backup": "A backup is taken outside the home before the wipe.",
        }

    result: dict[str, Any] = {
        "model_name": "dream_studio_runtime_uninstall",
        "dream_studio_home": str(home),
        "command_dir": str(launcher_dir),
        "execute": execute,
        "purge_state": purge_state,
        "confirm_purge": confirm_purge,
        "removed_targets": removed_targets,
        "preserved_targets": preserved_targets,
        "uninstall_check": uninstall_runtime_check(
            source_root=paths.source_root, dream_studio_home=home
        ),
        "hooks_deregistered": [],
        "launchers_removed": [],
        "state_preserved": True,
        "state_purged": False,
        "backup_path": None,
        "uninstall_executed": False,
        "requires_operator_approval": True,
    }

    if not execute:
        # Dry-run: inventory + plan only. Mutate nothing.
        result["status"] = "planned"
        return result

    if purge_state and not confirm_purge:
        # The mandatory second confirmation is missing: refuse, mutate nothing.
        result["status"] = "refused"
        result["error"] = (
            "--purge-state requires a second confirmation (confirm_purge=True). "
            "No changes were made."
        )
        return result

    # Tier 1 — integration teardown (always runs under --execute).
    result["hooks_deregistered"] = [_deregister_claude_hooks(p) for p in settings_paths]
    launchers_removed: list[str] = []
    for target in launcher_targets:
        if target.is_file():
            target.unlink()
            launchers_removed.append(str(target))
    result["launchers_removed"] = launchers_removed
    result["uninstall_executed"] = True
    result["status"] = "uninstalled"

    # Tier 2 — state purge (only with --purge-state and its confirmation).
    if purge_state:
        backup_root = Path(backup_dir or home.parent / f"{home.name}-uninstall-backups").resolve()
        backup = backup_runtime(
            source_root=paths.source_root,
            dream_studio_home=home,
            backup_dir=backup_root,
            execute=True,
        )
        result["backup_path"] = backup["backup_path"]
        if home.exists():
            shutil.rmtree(home)
        result["state_preserved"] = False
        result["state_purged"] = True
        result["status"] = "purged"

    return result
