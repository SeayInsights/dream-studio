"""Reinstalling after `ds uninstall --execute` wires the hooks again.

The executor treated a file as unchanged when the manifest's recorded hash equalled the
new content's hash, without looking at the file: uninstall had removed the hooks from
settings.json, the recorded hash still matched, and the reinstall wrote nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.installed_productization_uninstall import _deregister_claude_hooks
from integrations.installer.claude_code import ClaudeCodeInstaller


def _ds_commands(settings: Path) -> list[str]:
    data = json.loads(settings.read_text(encoding="utf-8"))
    return [h["command"] for es in data.get("hooks", {}).values() for e in es for h in e["hooks"]]


def test_reinstall_after_uninstall_rewires_the_hooks(tmp_path, monkeypatch):
    home, root = tmp_path / "home", tmp_path / "root"
    (home / "state").mkdir(parents=True)
    root.mkdir()
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(home))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(home / "state" / "studio.db"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(root))
    (root / "settings.json").write_text(json.dumps({"theme": "dark"}), encoding="utf-8")

    ClaudeCodeInstaller(root, "user", ds_home=home, hook_mode="module").install("execute")
    assert _ds_commands(root / "settings.json")
    _deregister_claude_hooks(root / "settings.json")
    assert not _ds_commands(root / "settings.json")

    ClaudeCodeInstaller(root, "user", ds_home=home, hook_mode="module").install("execute")
    assert _ds_commands(root / "settings.json"), "the reinstall left settings.json with no hooks"


def test_a_file_edited_on_disk_is_rewritten_even_when_the_manifest_matches(tmp_path, monkeypatch):
    home, root = tmp_path / "home", tmp_path / "root"
    (home / "state").mkdir(parents=True)
    root.mkdir()
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(home))
    ClaudeCodeInstaller(root, "user", ds_home=home, hook_mode="module").install("execute")
    skill = next((root / "skills").rglob("SKILL.md"))
    original = skill.read_bytes()
    skill.write_text("tampered\n", encoding="utf-8")
    ClaudeCodeInstaller(root, "user", ds_home=home, hook_mode="module").install("execute")
    assert skill.read_bytes() == original


def test_a_file_the_plan_installs_is_never_also_deleted_by_it(tmp_path, monkeypatch):
    """The skill sweep deleted the workflow contract installed into ds-workflow, and the
    second install then skipped it as unchanged: every second install lost it."""
    from unittest.mock import patch

    canonical = tmp_path / "canonical"
    for name in ("ds-bootstrap", "workflow"):
        (canonical / "skills" / name).mkdir(parents=True)
        (canonical / "skills" / name / "SKILL.md").write_text(f"# {name}", encoding="utf-8")
    contract = tmp_path / "docs" / "contracts" / "workflow-contract.md"
    contract.parent.mkdir(parents=True)
    contract.write_text("# Workflow contract\n", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    target = root / "skills" / "ds-workflow" / "docs" / "contracts" / "workflow-contract.md"
    with patch("integrations.installer.claude_code_launcher._write_path_to_profile") as prof:
        prof.return_value = {"profile": "x", "action": "skipped"}
        for _ in range(2):
            ClaudeCodeInstaller(
                root, "user", canonical_root=canonical, ds_home=tmp_path / "home"
            ).install("execute")
            assert target.is_file()
