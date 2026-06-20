"""WO-P20-TOOL-TARGETS T1: each tool places AGENTS.md in its expected location."""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.installer.agents_target import AgentsTargetInstaller
from integrations.targets.registry import (
    MULTITOOL_IDS,
    TARGET_SPECS,
    agents_md_target_path,
)


def test_each_target_places_agents_md_correctly(tmp_path):
    """Project-scoped tools place AGENTS.md at the project root; Cursor under
    its user rules dir. Install writes real generated content there."""
    project = tmp_path / "proj"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()

    expected = {
        "codex": project / "AGENTS.md",
        "gemini_cli": project / "AGENTS.md",
        "windsurf": project / "AGENTS.md",
        "aider": project / "AGENTS.md",
        "cursor": home / ".cursor" / "rules" / "AGENTS.md",
    }
    # Every registered target is covered by this test.
    assert set(expected) == set(MULTITOOL_IDS)

    for tool_id, want in expected.items():
        got = agents_md_target_path(tool_id, project_root=project, home=home)
        assert got == want.resolve(), f"{tool_id}: {got} != {want}"

        # Isolate each tool (project-scoped tools share project/AGENTS.md).
        want.unlink(missing_ok=True)

        installer = AgentsTargetInstaller(tool_id, project_root=project, home=home)
        # Dry run writes nothing.
        dry = installer.install("dry_run")
        assert dry["written"] is False
        assert not want.exists()

        # Execute writes the generated universal AGENTS.md.
        res = installer.install("execute")
        assert res["written"] is True
        assert want.is_file(), f"{tool_id}: AGENTS.md not written to {want}"
        content = want.read_text(encoding="utf-8")
        assert "Dream Studio — Universal Agent Instructions" in content
        assert "Pack-Based Routing" in content


def test_unknown_target_rejected():
    with pytest.raises(KeyError):
        agents_md_target_path("not-a-tool", project_root=Path("."))


def test_hooks_only_for_claude():
    """No native-AGENTS.md target claims hook support (hooks are Claude-Code-only)."""
    for spec in TARGET_SPECS.values():
        assert spec.supports_hooks is False, f"{spec.tool_id} must not install hooks"
