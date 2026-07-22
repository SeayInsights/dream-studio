"""dream-studio setup — settings.json hook merge, projection sync, uninstall.

Split from interfaces/cli/setup.py (WO-GF-CLI-split). ``SETTINGS_JSON`` is
defined in this module (not setup_shared) so that ``test_coexistence``'s
self-import patch — ``import interfaces.cli.setup_hooks as _self`` /
``_self.SETTINGS_JSON = tmp_settings`` — rebinds the exact module global that
``step_settings_merge``/``step_uninstall`` read at call time (a bare-name
global lookup resolves against the DEFINING module's ``__dict__``, so the
patch only takes effect when SETTINGS_JSON is defined here, alongside its
patch-sensitive consumers).
"""

from __future__ import annotations

import json
from pathlib import Path

from interfaces.cli.setup_shared import HOOKS_JSON, REPO_ROOT, StepResult

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SETTINGS_JSON = Path.home() / ".claude" / "settings.json"


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------


def _collect_commands(hook_list: list[dict]) -> set[str]:
    """Return all command strings from a hooks event list."""
    commands: set[str] = set()
    for group in hook_list:
        for hook in group.get("hooks", []):
            cmd = hook.get("command")
            if cmd:
                commands.add(cmd)
    return commands


def step_settings_merge() -> StepResult:
    """FR-S03: Non-destructively merge hooks/hooks.json into ~/.claude/settings.json."""
    name = "settings.json hooks merge"
    try:
        # Load source hooks
        if not HOOKS_JSON.exists():
            return StepResult(name, False, f"hooks.json not found at {HOOKS_JSON}")

        with HOOKS_JSON.open(encoding="utf-8") as fh:
            source_data: dict = json.load(fh)
        source_hooks: dict[str, list] = source_data.get("hooks", {})

        # Load or initialise settings.json
        SETTINGS_JSON.parent.mkdir(parents=True, exist_ok=True)
        if SETTINGS_JSON.exists():
            with SETTINGS_JSON.open(encoding="utf-8") as fh:
                settings: dict = json.load(fh)
        else:
            settings = {}

        if "hooks" not in settings:
            settings["hooks"] = {}

        added = 0
        for event_type, source_groups in source_hooks.items():
            existing_groups: list[dict] = settings["hooks"].setdefault(event_type, [])
            existing_commands = _collect_commands(existing_groups)

            for source_group in source_groups:
                # Determine which hook entries in this group are new
                new_hooks = [
                    hook
                    for hook in source_group.get("hooks", [])
                    if hook.get("command") not in existing_commands
                ]
                if not new_hooks:
                    continue

                # Build a group dict preserving optional "matcher" and DS ownership marker.
                new_group: dict = {}
                if "matcher" in source_group:
                    new_group["matcher"] = source_group["matcher"]
                if source_group.get("dream_studio_managed"):
                    new_group["dream_studio_managed"] = True
                new_group["hooks"] = new_hooks

                existing_groups.append(new_group)
                # Update the known-commands set so subsequent groups in the
                # same event don't re-add the same command.
                for hook in new_hooks:
                    existing_commands.add(hook.get("command", ""))
                added += len(new_hooks)

        with SETTINGS_JSON.open("w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
            fh.write("\n")

        return StepResult(name, True, f"{added} new hook entries merged")
    except Exception as exc:  # noqa: BLE001
        return StepResult(name, False, str(exc))


def step_sync_hook_projection() -> StepResult:
    """FR-RT2: Copy runtime/hooks/ subdirs into .claude/hooks/runtime/hooks/ and fix .plugin-root."""
    name = "Hook projection sync"
    try:
        import shutil

        src_base = REPO_ROOT / "runtime" / "hooks"
        dst_base = REPO_ROOT / ".claude" / "hooks" / "runtime" / "hooks"

        if not src_base.exists():
            return StepResult(name, False, f"source not found: {src_base}")

        copied = 0
        for sub in ("quality", "domains", "core", "meta"):
            src_dir = src_base / sub
            dst_dir = dst_base / sub
            if not src_dir.exists():
                continue
            dst_dir.mkdir(parents=True, exist_ok=True)
            for src_file in src_dir.rglob("*.py"):
                if "__pycache__" in src_file.parts:
                    continue
                dst_file = dst_dir / src_file.relative_to(src_dir)
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                copied += 1

        # Also sync session_config.py (imported by on-stop-dispatch via sys.path)
        sc_src = REPO_ROOT / "runtime" / "session_config.py"
        sc_dst = REPO_ROOT / ".claude" / "hooks" / "runtime" / "session_config.py"
        if sc_src.exists():
            sc_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sc_src, sc_dst)
            copied += 1

        # Also sync runtime/lib/ — direct-entry hooks (on-edit-enforce,
        # on-stop-enforce) resolve runtime.lib relative to the plugin root,
        # so the projection must be self-contained.
        lib_src = REPO_ROOT / "runtime" / "lib"
        lib_dst = REPO_ROOT / ".claude" / "hooks" / "runtime" / "lib"
        if lib_src.exists():
            for src_file in lib_src.rglob("*.py"):
                if "__pycache__" in src_file.parts:
                    continue
                dst_file = lib_dst / src_file.relative_to(lib_src)
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                copied += 1
            init_src = REPO_ROOT / "runtime" / "__init__.py"
            init_dst = REPO_ROOT / ".claude" / "hooks" / "runtime" / "__init__.py"
            if init_src.exists():
                shutil.copy2(init_src, init_dst)
                copied += 1

        plugin_root = REPO_ROOT / ".claude" / "hooks" / ".plugin-root"
        plugin_root.write_text(str(REPO_ROOT / ".claude" / "hooks"), encoding="utf-8")

        return StepResult(name, True, f"{copied} files synced, .plugin-root updated")
    except Exception as exc:  # noqa: BLE001
        return StepResult(name, False, str(exc))


def step_uninstall() -> int:
    """Remove Dream Studio hook entries and projection files. Leaves user hooks untouched."""
    import shutil

    print("[dream-studio] Uninstall")
    print()

    removed_hooks: list[str] = []
    kept_hooks: list[str] = []
    removed_files: list[str] = []
    errors: list[str] = []

    # 1 — Remove DS hook groups from ~/.claude/settings.json
    if SETTINGS_JSON.exists():
        try:
            with SETTINGS_JSON.open(encoding="utf-8") as fh:
                settings: dict = json.load(fh)
            hooks_section: dict = settings.get("hooks", {})
            changed = False
            for event_type, groups in list(hooks_section.items()):
                keep = []
                for group in groups:
                    if group.get("dream_studio_managed"):
                        for hook in group.get("hooks", []):
                            removed_hooks.append(f"{event_type}: {hook.get('command', '')[:60]}…")
                        changed = True
                    else:
                        for hook in group.get("hooks", []):
                            kept_hooks.append(f"{event_type}: {hook.get('command', '')[:60]}…")
                        keep.append(group)
                hooks_section[event_type] = keep
            if changed:
                with SETTINGS_JSON.open("w", encoding="utf-8") as fh:
                    json.dump(settings, fh, indent=2)
                    fh.write("\n")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"settings.json: {exc}")
    else:
        print("  settings.json not found — skipping hook removal")

    # 2 — Remove .claude/hooks/ DS projection subdirs (gitignored, DS-owned)
    projection_root = REPO_ROOT / ".claude" / "hooks" / "runtime" / "hooks"
    for sub in ("quality", "domains", "core"):
        sub_dir = projection_root / sub
        if sub_dir.exists():
            try:
                shutil.rmtree(sub_dir)
                removed_files.append(str(sub_dir))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{sub_dir}: {exc}")

    # 3 — Remove .plugin-root
    plugin_root = REPO_ROOT / ".claude" / "hooks" / ".plugin-root"
    if plugin_root.exists():
        try:
            plugin_root.unlink()
            removed_files.append(str(plugin_root))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{plugin_root}: {exc}")

    # Report
    print(f"  Removed {len(removed_hooks)} DS hook entries:")
    for h in removed_hooks:
        print(f"    - {h}")
    print(f"  Kept {len(kept_hooks)} non-DS hook entries intact")
    print(f"  Removed {len(removed_files)} projection files/dirs")
    for f in removed_files:
        print(f"    - {f}")
    if errors:
        print("  Errors:")
        for e in errors:
            print(f"    ✗ {e}")
        return 1

    print()
    print("Uninstall complete. Re-run setup.py to reinstall.")
    return 0


def test_coexistence() -> int:
    """T4: Verify pre-existing user hooks survive install and are not removed on uninstall."""
    import tempfile

    print("[dream-studio] Coexistence test")
    failures: list[str] = []

    # Mock settings.json with a pre-existing hook from another tool
    pre_existing: dict = {
        "model": "claude-opus-4-5",
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "echo 'user-hook-from-other-tool'"}]}
            ]
        },
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_settings = Path(tmpdir) / "settings.json"
        tmp_settings.write_text(json.dumps(pre_existing, indent=2), encoding="utf-8")

        # Temporarily redirect SETTINGS_JSON
        import interfaces.cli.setup_hooks as _self

        orig = _self.SETTINGS_JSON
        _self.SETTINGS_JSON = tmp_settings
        try:
            # --- Install ---
            result = step_settings_merge()
            if not result.passed:
                failures.append(f"install failed: {result.detail}")
            else:
                with tmp_settings.open(encoding="utf-8") as fh:
                    after_install: dict = json.load(fh)

                # Pre-existing hook must still be present
                ups = after_install.get("hooks", {}).get("UserPromptSubmit", [])
                user_cmds = [h.get("command") for g in ups for h in g.get("hooks", [])]
                if "echo 'user-hook-from-other-tool'" not in user_cmds:
                    failures.append("install: pre-existing user hook was removed")

                # model key must be preserved
                if after_install.get("model") != "claude-opus-4-5":
                    failures.append("install: non-hook key 'model' was lost")

                # DS hooks must have been added with marker
                ds_groups = [g for g in ups if g.get("dream_studio_managed")]
                if not ds_groups:
                    failures.append("install: no dream_studio_managed groups written")

                # --- Uninstall (settings only — skip projection file removal in test) ---
                import interfaces.cli.setup_hooks as _self2

                orig_repo = _self2.REPO_ROOT
                # Point REPO_ROOT at a temp dir so projection removal is a no-op
                _self2.REPO_ROOT = Path(tmpdir)
                (Path(tmpdir) / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
                try:
                    uninstall_rc = step_uninstall()
                finally:
                    _self2.REPO_ROOT = orig_repo
                if uninstall_rc != 0:
                    failures.append(f"uninstall returned {uninstall_rc}")
                else:
                    with tmp_settings.open(encoding="utf-8") as fh:
                        after_uninstall: dict = json.load(fh)

                    ups2 = after_uninstall.get("hooks", {}).get("UserPromptSubmit", [])
                    remaining_cmds = [h.get("command") for g in ups2 for h in g.get("hooks", [])]

                    if "echo 'user-hook-from-other-tool'" not in remaining_cmds:
                        failures.append("uninstall: pre-existing user hook was removed")

                    ds_remaining = [g for g in ups2 if g.get("dream_studio_managed")]
                    if ds_remaining:
                        failures.append("uninstall: DS hook groups still present after uninstall")

                    if after_uninstall.get("model") != "claude-opus-4-5":
                        failures.append("uninstall: non-hook key 'model' was lost")
        finally:
            _self.SETTINGS_JSON = orig

    if failures:
        print("  FAIL:")
        for f in failures:
            print(f"    ✗ {f}")
        return 1

    print("  ✓ pre-existing hooks preserved after install")
    print("  ✓ non-hook settings preserved after install")
    print("  ✓ DS hooks written with dream_studio_managed marker")
    print("  ✓ DS hooks removed on uninstall")
    print("  ✓ pre-existing hooks intact after uninstall")
    print("  ✓ non-hook settings preserved after uninstall")
    return 0
