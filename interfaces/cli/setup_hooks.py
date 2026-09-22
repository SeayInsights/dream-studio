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
import re
import shlex
import sys
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


def resolve_hook_command(command: str) -> str:
    """Replace a leading bare ``python`` with an interpreter that actually resolves.

    hooks/hooks.json is a TEMPLATE and cannot carry a machine-specific path, so every hook in
    it begins with bare ``python``. This merge used to copy that verbatim into the operator's
    settings.json, and on a stock Windows box bare ``python`` is the Microsoft Store App
    Execution Alias -- a zero-byte stub that prints "Python was not found" and exits 9009
    without running anything. Every Dream Studio hook would be silently dead on a machine
    where the alias is left enabled, which is the out-of-the-box state.

    The answer already exists in this repository: ``claude_code_shared._python_cmd`` resolves
    the absolute ``sys.executable`` for the OTHER install path, and its own docstring records
    the same lesson ("the bare ``py`` launcher ... is not reliably resolvable in the hook exec
    environment"). Two install doors disagreed about the interpreter; this one now asks the
    same function rather than carrying a second answer.
    """
    from integrations.installer.claude_code_shared import _python_cmd

    native = _native_enqueue_command(command)
    if native is not None:
        return native

    prefix = "python "
    if not command.startswith(prefix):
        return command
    return _python_cmd() + " " + command[len(prefix) :]  # noqa: E203


#: Built by `cargo build --release` in runtime/hooks/enqueue-native. Optional:
#: when it is absent the Python enqueuer is installed instead and everything
#: works, just 24 ms slower per tool call.
#:
#: The `.exe` suffix is Windows-only, and hardcoding it meant the lookup could
#: never find a binary on Linux or macOS, where cargo emits `ds-enqueue` with no
#: extension. It failed safe -- those platforms silently kept the Python
#: enqueuer -- which is why nobody noticed a speedup that could not engage.
NATIVE_ENQUEUE_BIN = "ds-enqueue.exe" if sys.platform == "win32" else "ds-enqueue"


def _native_enqueue_path() -> Path | None:
    exe = (
        REPO_ROOT
        / "runtime"
        / "hooks"
        / "enqueue-native"
        / "target"
        / "release"
        / NATIVE_ENQUEUE_BIN
    )
    return exe if exe.is_file() else None


def _native_enqueue_command(command: str) -> str | None:
    """Swap the Python enqueue bootstrap for the compiled binary, if it exists.

    Measured per PostToolUse invocation: 267 ms for the original dispatcher,
    51 ms for enqueue.py, 27 ms for this binary. The second step is small next
    to the first because what remains is Windows process creation, not Python.
    """
    if "enqueue.py" not in command:
        return None
    exe = _native_enqueue_path()
    if exe is None:
        return None
    event = ""
    for candidate in ("UserPromptSubmit", "PostToolUse", "PreToolUse", "Stop", "PostCompact"):
        if candidate in command:
            event = candidate
            break
    return f'"{exe.as_posix()}" {event}'.strip()


#: Interpreter file names this module recognizes. A hook whose first token is one of these
#: names an interpreter; anything else (``node``, a shell script) is compared whole.
_PYTHON_NAMES = frozenset({"python", "python3", "py", "pythonw"})


def _split_interpreter(command: str) -> tuple[str, str] | None:
    """Split ``command`` into (interpreter token, the rest), or None if it names no Python.

    ``posix=False`` keeps the quotes on a Windows path, which is what settings.json stores
    and what has to be written back unchanged.
    """
    try:
        tokens = shlex.split(command, posix=False)
    except ValueError:
        return None
    if not tokens:
        return None
    head = tokens[0].strip('"')
    if Path(head).stem.lower() not in _PYTHON_NAMES:
        return None
    return tokens[0], command[len(tokens[0]) :].strip()  # noqa: E203


#: A handler script named anywhere in a command, however it is spelled.
_SCRIPT_RE = re.compile(r"[\w.\-]+\.py")
#: The event the hook handles. Quoted inside a bootstrap
#: (``sys.argv=[str(x),'PostToolUse']``), bare as a resolved argv
#: (``"<script>" PostToolUse``) -- both spellings must read the same.
_EVENT_RE = re.compile(
    r"['\"]?\b(UserPromptSubmit|Stop|PostToolUse|PreToolUse|PostCompact)\b['\"]?"
)


def hook_identity(command: str) -> str:
    """What a hook DOES, independent of how the command is spelled.

    hooks.json ships a self-locating bootstrap -- ``python -c "...runpy.run_path(
    <script>)..."`` -- while what lands in settings.json is the resolved
    ``"<abs python>" "<abs script>" <Event>``. Those two strings share no tail,
    so comparing tails (the previous rule) called them different hooks and the
    merge appended a second group. Verified live on 2026-09-21: re-running the
    installer against an already-clean settings.json re-created a duplicate
    PostToolUse group, which runs the same handlers twice on every tool call.

    Identity is therefore (handler script basename, event). Basename, not a
    longer path suffix, because the installer genuinely relocates these --
    ``emitters/claude_code/run.py`` is installed as ``~/.claude/hooks/run.py``,
    and those are one hook.
    """
    split = _split_interpreter(command)
    tail = split[1] if split else command
    # The native enqueuer IS enqueue.py -- same hook, same queue, same record,
    # 27 ms instead of 51. Without this line the installer would see the Python
    # form and the compiled form as two different hooks and register BOTH, which
    # is the duplicate-registration bug this function exists to prevent.
    tail = tail.replace(NATIVE_ENQUEUE_BIN, "enqueue.py")
    scripts = _SCRIPT_RE.findall(tail)
    if scripts:
        event = _EVENT_RE.search(tail)
        # A bootstrap names its target script repeatedly (the probe and the run);
        # the distinct set keeps that from changing the identity.
        key = "+".join(sorted(set(scripts)))
        return f"{key}:{event.group(1) if event else ''}"
    return " ".join(tail.split())


def _names_a_bare_interpreter(command: str) -> bool:
    """True when the interpreter is an unqualified name -- the form that may not resolve.

    ``python`` on a stock Windows box is the Store alias stub. An ABSOLUTE interpreter is a
    working answer, and possibly the operator's own (a venv, a pinned version), so this
    returns False for it and the merge leaves it alone.
    """
    split = _split_interpreter(command)
    if split is None:
        return False
    head = split[0].strip('"')
    return Path(head).name == head and not Path(head).is_absolute()


def _merge_into_group(existing_groups: list[dict], resolved: dict) -> str:
    """Place one resolved hook: heal a bare twin, keep a deliberate one, else report new.

    Returns "healed", "kept" or "new".
    """
    identity = hook_identity(resolved.get("command", ""))
    for group in existing_groups:
        for hook in group.get("hooks", []):
            existing_command = hook.get("command", "")
            if hook_identity(existing_command) != identity:
                continue
            if existing_command == resolved.get("command", ""):
                return "kept"
            if _names_a_bare_interpreter(existing_command):
                # The template form that may never run. Replace it IN PLACE: appending the
                # resolved command beside it is what produced the duplicate pairs.
                hook["command"] = resolved.get("command", "")
                return "healed"
            # An absolute interpreter already works, and choosing it may have been
            # deliberate. Same hook, so nothing is appended either way.
            return "kept"
    return "new"


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
        healed = 0
        for event_type, source_groups in source_hooks.items():
            existing_groups: list[dict] = settings["hooks"].setdefault(event_type, [])

            for source_group in source_groups:
                # Resolve the interpreter BEFORE the comparison, so a re-run matches what was
                # actually written last time rather than the template form.
                resolved_hooks = [
                    {**hook, "command": resolve_hook_command(hook.get("command", ""))}
                    for hook in source_group.get("hooks", [])
                ]
                # A hook is matched by WHAT IT RUNS, not by the exact string. Comparing whole
                # commands left `python <script>` and `"<abs>/python.exe" <script>` looking
                # unrelated, so both were kept and the handler ran twice per event.
                new_hooks = []
                for hook in resolved_hooks:
                    outcome = _merge_into_group(existing_groups, hook)
                    if outcome == "new":
                        new_hooks.append(hook)
                    elif outcome == "healed":
                        healed += 1
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
                added += len(new_hooks)

        with SETTINGS_JSON.open("w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
            fh.write("\n")

        detail = f"{added} new hook entries merged"
        if healed:
            detail += f", {healed} bare-interpreter entr{'y' if healed == 1 else 'ies'} repaired"
        return StepResult(name, True, detail)
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
