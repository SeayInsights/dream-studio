"""Hooks run the installed app's modules; nothing is copied; one manifest per config root.

The files-mode installer copied ~44 hook files into <config_root>/hooks and wrote a
.ds-source-root sidecar that put the git checkout on every hook's sys.path, so the
live hooks executed whatever the checkout held at that moment. It also kept ONE
manifest per home, shared by every Claude Code config root installed from it, and
guessed the config root from the working directory.

Module mode (the default from an installed app) writes settings.json commands of the
form `<app python> -I -X utf8 -m runtime.dispatch.hooks Stop`, copies no hook files, retires
then removes the copies a previous install recorded in this root's manifest, and drops the old
file-path commands so no hook runs twice.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from integrations.installer.claude_code import ClaudeCodeInstaller
from integrations.manifest import get_manifest_path, read_manifest

REPO = Path(__file__).resolve().parents[3]
FOREIGN = {"type": "command", "command": "echo foreign-hook"}


@pytest.fixture
def canonical_root(tmp_path):
    """A minimal canonical tree plus the hook sources a files-mode install copies."""
    root = tmp_path / "src" / "canonical"
    skill = root / "skills" / "ds-bootstrap"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# bootstrap", encoding="utf-8")
    (root / "agents").mkdir()
    src = root.parent
    for rel in (
        "emitters/claude_code/run.py",
        "runtime/dispatch/hooks.py",
        "runtime/dispatch/__init__.py",
        "runtime/__init__.py",
        "runtime/hooks/meta/__init__.py",
        "runtime/hooks/meta/on-edit-enforce.py",
        "runtime/hooks/meta/on-stop-enforce.py",
        "runtime/hooks/meta/on-prompt-dispatch.py",
        "control/execution/dispatch_tracking.py",
    ):
        path = src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {rel}\n", encoding="utf-8")
    return root


def _settings(config_root: Path) -> dict:
    return json.loads((config_root / "settings.json").read_text(encoding="utf-8"))


def _commands(config_root: Path) -> list[str]:
    return [
        h["command"]
        for entries in _settings(config_root).get("hooks", {}).values()
        for e in entries
        for h in e.get("hooks", [])
    ]


def _install(config_root, canonical_root, ds_home, mode):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home, hook_mode=mode
    )
    with patch("integrations.installer.claude_code_launcher._write_path_to_profile") as prof:
        prof.return_value = {"profile": "x", "action": "skipped"}
        return installer.install("execute")


def test_every_template_hook_maps_to_an_installed_module():
    from integrations.installer.claude_code_fileops import MODULE_FOR_HOOK_FILE

    template = json.loads(
        (REPO / "integrations/targets/claude_code/hooks_template.json").read_text("utf-8")
    )
    for entry in template:
        for h in entry["hooks"]:
            rel = h["command"].split('"{hooks_dir}/', 1)[1].split('"', 1)[0]
            module = MODULE_FOR_HOOK_FILE[rel]
            assert (REPO / (module.replace(".", "/") + ".py")).is_file(), module


def test_module_mode_plan_copies_nothing_and_runs_modules(tmp_path, canonical_root, ds_home):
    config_root = tmp_path / "claude"
    config_root.mkdir()
    plan = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home, hook_mode="module"
    ).plan()
    hooks_dir = config_root / "hooks"
    assert not [op for op in plan.ops if hooks_dir in op.target.parents]
    assert not [op for op in plan.ops if op.target.name == "installed-version"]

    settings_op = next(op for op in plan.ops if op.target.name == "settings.json")
    commands = [
        h["command"]
        for entries in json.loads(settings_op.source_content)["hooks"].values()
        for e in entries
        for h in e["hooks"]
    ]
    assert commands
    for cmd in commands:
        assert " -I -X utf8 -m " in cmd, cmd
        assert "{hooks_dir}" not in cmd and "hooks/" not in cmd.replace("\\", "/"), cmd
    assert any("-m runtime.dispatch.hooks UserPromptSubmit" in c for c in commands)
    assert any("-m runtime.hooks.meta.on-edit-enforce" in c for c in commands)


def test_switching_to_module_mode_removes_the_copies_and_the_old_commands(
    tmp_path, canonical_root, ds_home
):
    config_root = tmp_path / "claude"
    config_root.mkdir()
    (config_root / "settings.json").write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [FOREIGN]}]}}), encoding="utf-8"
    )
    _install(config_root, canonical_root, ds_home, "files")
    hooks_dir = config_root / "hooks"
    assert (hooks_dir / ".ds-source-root").is_file()
    assert (hooks_dir / "dispatch" / "hooks.py").is_file()
    stray = hooks_dir / "operator-own-hook.py"
    stray.write_text("# not ours", encoding="utf-8")

    result = _install(config_root, canonical_root, ds_home, "module")
    assert result["hook_mode"] == "module"
    # The first install only retires the copies (a running session still calls them);
    # the next one removes them: see test_installer_round_two.py.
    result = _install(config_root, canonical_root, ds_home, "module")
    assert result["hook_files_removed"] > 0
    assert not (hooks_dir / ".ds-source-root").exists()
    assert not (hooks_dir / ".plugin-root").exists()
    assert not (hooks_dir / "dispatch").exists()
    assert not (hooks_dir / "runtime").exists()
    assert stray.is_file(), "a file the installer never recorded must survive"

    commands = _commands(config_root)
    assert "echo foreign-hook" in commands
    ds_commands = [c for c in commands if c != "echo foreign-hook"]
    assert ds_commands and all(" -I -X utf8 -m " in c for c in ds_commands), ds_commands
    registrations = [
        (event, e.get("matcher"), h["command"])
        for event, entries in _settings(config_root)["hooks"].items()
        for e in entries
        for h in e.get("hooks", [])
    ]
    assert len(registrations) == len(set(registrations)), "a hook is registered twice"


def test_each_config_root_keeps_its_own_manifest(tmp_path, canonical_root, ds_home):
    first, second = tmp_path / "claude-a", tmp_path / "claude-b"
    first.mkdir()
    second.mkdir()
    _install(first, canonical_root, ds_home, "module")
    _install(second, canonical_root, ds_home, "module")

    path_a = get_manifest_path("claude_code", ds_home, first)
    path_b = get_manifest_path("claude_code", ds_home, second)
    assert path_a != path_b and path_a.is_file() and path_b.is_file()
    for root in (first, second):
        manifest = read_manifest("claude_code", ds_home, root)
        assert Path(manifest["config_root"]) == root.resolve()
        assert all(root.resolve() in Path(f["path"]).resolve().parents for f in manifest["files"])


def test_a_legacy_shared_manifest_is_used_only_for_the_root_it_describes(tmp_path, ds_home):
    root = tmp_path / "claude"
    other = tmp_path / "claude-other"
    legacy = get_manifest_path("claude_code", ds_home)
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({"files": [{"path": str(root / "hooks" / "run.py"), "operation": "create"}]}),
        encoding="utf-8",
    )
    assert read_manifest("claude_code", ds_home, root) is not None
    assert read_manifest("claude_code", ds_home, other) is None


def test_cli_config_root_installs_each_root_and_never_a_git_hook(tmp_path):
    """`--config-root` instead of guessing from the cwd -- even when the cwd is a repo."""
    work = tmp_path / "repo"
    (work / ".git" / "hooks").mkdir(parents=True)
    home = tmp_path / "home"
    roots = [tmp_path / "root-a", tmp_path / "root-b"]
    for r in roots:
        r.mkdir()
    env = {
        "PATH": __import__("os").environ["PATH"],
        "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
        "PYTHONPATH": str(REPO),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "DREAM_STUDIO_DB_PATH": str(home / "state" / "studio.db"),
        "USERPROFILE": str(tmp_path / "userhome"),
        "HOME": str(tmp_path / "userhome"),
        "CLAUDE_CONFIG_DIR": str(tmp_path / "default-claude"),
    }
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "interfaces.cli.ds",
            "--home",
            str(home),
            "integrate",
            "install",
            "claude_code",
            "--config-root",
            str(roots[0]),
            "--config-root",
            str(roots[1]),
            "--execute",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=work,
        env=env,
        timeout=900,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    # install() prints guidance before the JSON payload; the payload is the last object.
    start = proc.stdout.rfind("\n{") + 1
    payload = json.loads(proc.stdout[start:])
    assert [i["config_root"] for i in payload["installs"]] == [str(r.resolve()) for r in roots]
    assert not (work / ".git" / "hooks" / "pre-push").exists()
    assert not (tmp_path / "default-claude" / "settings.json").exists()
    for r in roots:
        assert (r / "settings.json").is_file()
        assert get_manifest_path("claude_code", home, r).is_file()
