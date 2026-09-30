"""WO-P20-TOOL-TARGETS T1: each tool places AGENTS.md in its expected location."""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.installer.agents_target import AgentsTargetInstaller
from integrations.targets.registry import (
    MULTITOOL_IDS,
    TARGET_SPECS,
    agents_md_target_path,
    get_target_spec,
    resolve_scope,
    specialist_agents_target_path,
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


# --------------------------------------------------------------------------
# --scope: real for a tool that declares supported_scopes, refused otherwise
# --------------------------------------------------------------------------
#
# ds integrate install <tool> --scope user was accepted by the CLI's shared argparse
# choices for every tool, then silently dropped several layers downstream for any
# tool whose TargetSpec had not declared "user" reachable -- the CLI reported success
# and wrote to the tool's fixed default location regardless of what was asked for.
# Found by an operator confirming Codex CLI genuinely supports a personal
# ~/.codex/AGENTS.md (CODEX_HOME) alongside the project one.


def test_resolve_scope_returns_the_default_when_none_requested():
    spec = get_target_spec("codex")
    assert resolve_scope(spec, None) == "project"


def test_resolve_scope_honors_a_supported_override():
    spec = get_target_spec("codex")
    assert resolve_scope(spec, "user") == "user"


def test_resolve_scope_refuses_an_unsupported_override():
    """gemini_cli only ever declared "project" -- codex is the one tool verified for
    both, and only codex should ever accept --scope user."""
    spec = get_target_spec("gemini_cli")
    with pytest.raises(ValueError, match="does not support"):
        resolve_scope(spec, "user")


def test_codex_user_scope_agents_md_lands_under_codex_home(tmp_path):
    project = tmp_path / "proj"
    home = tmp_path / "home"
    got = agents_md_target_path("codex", project_root=project, home=home, scope="user")
    assert got == (home / ".codex" / "AGENTS.md").resolve()


def test_codex_project_scope_agents_md_is_unchanged_by_the_new_parameter(tmp_path):
    project = tmp_path / "proj"
    home = tmp_path / "home"
    got = agents_md_target_path("codex", project_root=project, home=home, scope="project")
    assert got == (project / "AGENTS.md").resolve()
    # Same result with scope omitted entirely -- "project" is codex's own default.
    assert agents_md_target_path("codex", project_root=project, home=home) == got


def test_codex_user_scope_specialist_agents_land_under_codex_home(tmp_path):
    project = tmp_path / "proj"
    home = tmp_path / "home"
    got = specialist_agents_target_path("codex", project_root=project, home=home, scope="user")
    assert got == (home / ".codex" / "agents").resolve()


def test_agents_md_target_path_refuses_an_unsupported_scope_for_gemini_cli(tmp_path):
    with pytest.raises(ValueError, match="does not support"):
        agents_md_target_path("gemini_cli", project_root=tmp_path, scope="user")


def test_agents_target_installer_writes_to_codex_home_when_scope_is_user(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()

    installer = AgentsTargetInstaller("codex", project_root=project, home=home, scope="user")
    result = installer.install("execute")
    assert result["written"] is True

    written = home / ".codex" / "AGENTS.md"
    assert written.is_file()
    assert not (project / "AGENTS.md").exists()


def test_agents_target_installer_plan_reports_the_resolved_scope(tmp_path):
    installer = AgentsTargetInstaller(
        "codex", project_root=tmp_path / "proj", home=tmp_path / "home", scope="user"
    )
    assert installer.plan()["scope"] == "user"


def test_agents_target_installer_refuses_an_unsupported_scope_at_construction(tmp_path):
    with pytest.raises(ValueError, match="does not support"):
        AgentsTargetInstaller("gemini_cli", project_root=tmp_path, scope="user")
