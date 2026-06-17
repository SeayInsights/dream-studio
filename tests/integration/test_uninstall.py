"""Integration tests for the mutating `ds uninstall` command (WO-UNINSTALL).

Covers the three tiers and the blast-radius guarantee:
- dry-run default mutates nothing,
- integration teardown removes hooks + launchers but preserves state,
- both generated .claude copies are cleared,
- --purge-state needs a second confirmation and backs up before wiping.

All tests run against a rehearsal home under tmp_path; the live ~/.dream-studio
is never touched.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.installed_productization import (
    first_run_setup,
    install_global_command_surface,
    uninstall_runtime,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_settings(path: Path) -> None:
    """Write a settings.json carrying DS emitter + dispatcher hooks and one foreign hook."""

    path.parent.mkdir(parents=True, exist_ok=True)
    settings = {
        "model": "sonnet",
        "hooks": {
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {"type": "command", "command": 'py ".claude/hooks/run.py" UserPromptSubmit'}
                    ]
                },
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'py ".claude/hooks/dispatch/hooks.py" UserPromptSubmit',
                        }
                    ]
                },
            ],
            "Stop": [
                {"hooks": [{"type": "command", "command": 'py ".claude/hooks/run.py" Stop'}]},
            ],
            "PostToolUse": [
                # Foreign (non-DS) hook — MUST be preserved.
                {"matcher": "Foo", "hooks": [{"type": "command", "command": "py my-own-hook.py"}]},
            ],
        },
    }
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def _has_ds_hooks(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    return "hooks/run.py" in text or "hooks/dispatch/hooks.py" in text


def _setup_home(tmp_path: Path) -> Path:
    home = tmp_path / "runtime-home"
    first_run_setup(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        profiles=["core", "analytics_only"],
        rehearsal=True,
    )
    return home


def test_default_is_dry_run(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    _write_settings(settings)
    command_dir = tmp_path / "bin"
    install_global_command_surface(
        source_root=REPO_ROOT, dream_studio_home=home, command_dir=command_dir, execute=True
    )

    result = uninstall_runtime(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        claude_settings_paths=[settings],
        command_dir=command_dir,
        execute=False,
    )

    assert result["status"] == "planned"
    assert result["uninstall_executed"] is False
    # Nothing mutated.
    assert _has_ds_hooks(settings)
    assert (command_dir / "ds.cmd").is_file()
    assert (command_dir / "ds.ps1").is_file()
    assert (home / "state" / "studio.db").is_file()


def test_integration_teardown_removes_hooks_preserves_state(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    _write_settings(settings)
    command_dir = tmp_path / "bin"
    install_global_command_surface(
        source_root=REPO_ROOT, dream_studio_home=home, command_dir=command_dir, execute=True
    )

    result = uninstall_runtime(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        claude_settings_paths=[settings],
        command_dir=command_dir,
        execute=True,
    )

    assert result["status"] == "uninstalled"
    assert result["uninstall_executed"] is True
    # DS hooks removed, foreign hook preserved.
    assert not _has_ds_hooks(settings)
    assert "my-own-hook.py" in settings.read_text(encoding="utf-8")
    # Launchers removed.
    assert not (command_dir / "ds.cmd").exists()
    assert not (command_dir / "ds.ps1").exists()
    # State PRESERVED — reversible by reinstall.
    assert result["state_preserved"] is True
    assert result["state_purged"] is False
    assert (home / "state" / "studio.db").is_file()


def test_uninstall_clears_both_claude_copies(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    user_settings = tmp_path / "user" / ".claude" / "settings.json"
    project_settings = tmp_path / "project" / ".claude" / "settings.json"
    _write_settings(user_settings)
    _write_settings(project_settings)

    result = uninstall_runtime(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        claude_settings_paths=[user_settings, project_settings],
        command_dir=tmp_path / "bin",
        execute=True,
    )

    assert result["status"] == "uninstalled"
    # BOTH copies cleared — nothing left hanging.
    assert not _has_ds_hooks(user_settings)
    assert not _has_ds_hooks(project_settings)
    reports = {r["path"]: r for r in result["hooks_deregistered"]}
    assert reports[str(user_settings)]["hooks_removed"] == 3
    assert reports[str(project_settings)]["hooks_removed"] == 3
    # Foreign hooks survive in both.
    assert "my-own-hook.py" in user_settings.read_text(encoding="utf-8")
    assert "my-own-hook.py" in project_settings.read_text(encoding="utf-8")


def test_purge_state_requires_second_confirm_and_backs_up_first(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    _write_settings(settings)

    # Without the second confirmation: refused, state intact.
    refused = uninstall_runtime(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        claude_settings_paths=[settings],
        command_dir=tmp_path / "bin",
        execute=True,
        purge_state=True,
        confirm_purge=False,
    )
    assert refused["status"] == "refused"
    assert refused["state_purged"] is False
    assert (home / "state" / "studio.db").is_file()

    # With the second confirmation: backup taken FIRST (outside home), then wiped.
    purged = uninstall_runtime(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        claude_settings_paths=[settings],
        command_dir=tmp_path / "bin",
        execute=True,
        purge_state=True,
        confirm_purge=True,
    )
    assert purged["status"] == "purged"
    assert purged["state_purged"] is True
    backup_path = Path(purged["backup_path"])
    # Backup exists and survived the wipe (it lives outside the home).
    assert (backup_path / "studio.db").is_file()
    assert not backup_path.is_relative_to(home)
    # State tier is gone.
    assert not home.exists()


def test_end_to_end(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    user_settings = tmp_path / "user" / ".claude" / "settings.json"
    project_settings = tmp_path / "project" / ".claude" / "settings.json"
    _write_settings(user_settings)
    _write_settings(project_settings)
    command_dir = tmp_path / "bin"
    install_global_command_surface(
        source_root=REPO_ROOT, dream_studio_home=home, command_dir=command_dir, execute=True
    )
    settings_paths = [user_settings, project_settings]

    # 1) Dry-run changes nothing.
    plan = uninstall_runtime(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        claude_settings_paths=settings_paths,
        command_dir=command_dir,
        execute=False,
    )
    assert plan["status"] == "planned"
    assert _has_ds_hooks(user_settings) and _has_ds_hooks(project_settings)
    assert (home / "state" / "studio.db").is_file()

    # 2) Full purge with confirmation: both copies cleared, launchers gone, state backed up + wiped.
    done = uninstall_runtime(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        claude_settings_paths=settings_paths,
        command_dir=command_dir,
        execute=True,
        purge_state=True,
        confirm_purge=True,
    )
    assert done["status"] == "purged"
    assert not _has_ds_hooks(user_settings)
    assert not _has_ds_hooks(project_settings)
    assert not (command_dir / "ds.cmd").exists()
    assert not (command_dir / "ds.ps1").exists()
    assert (Path(done["backup_path"]) / "studio.db").is_file()
    assert not home.exists()
