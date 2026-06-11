"""Unit tests for Workstream 9d — complete hermetic install."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from integrations.installer.claude_code import (
    ClaudeCodeInstaller,
    _DS_PATH_MARKER,
    _python_cmd,
    _skill_id_from_dir_name,
    _write_global_launcher,
    _write_path_to_profile,
)
from integrations.targets.claude_code.settings_merge import (
    dedup_hooks_by_normalized_command,
    purge_legacy_hooks,
)


def _cmd_has_dispatcher(cmd: str) -> bool:
    """Return True if cmd contains a DS dispatcher hook reference (any format)."""
    return (
        os.path.join("hooks", "dispatch", "hooks.py") in cmd
        or "hooks/dispatch/hooks.py" in cmd  # forward-slash form (new template)
        or "runtime/dispatch/hooks" in cmd
        or "'dispatch'/'hooks.py'" in cmd
    )


def _cmd_has_emitter(cmd: str) -> bool:
    """Return True if cmd contains a DS emitter hook reference (any format)."""
    return (
        os.path.join("hooks", "run.py") in cmd
        or "hooks/run.py" in cmd  # forward-slash form (new template)
        or "emitters/claude_code/run.py" in cmd
        or "/'emitters'/'claude_code'/'run.py'" in cmd
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def canonical_root(tmp_path):
    """Canonical root with full skill directories, agents, workflows, and contract."""
    root = tmp_path / "canonical"
    # Skills — base SKILL.md for all packs
    skill_names = ["ds-bootstrap", "core", "quality", "analyze", "security", "setup", "workflow"]
    for name in skill_names:
        skill_dir = root / "skills" / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"# {name} skill", encoding="utf-8")
    # ds-core gets a representative full directory structure
    core_dir = root / "skills" / "core"
    (core_dir / "config.yml").write_text("pack: ds-core\n", encoding="utf-8")
    (core_dir / "git.md").write_text("# Git reference\n", encoding="utf-8")
    modes_build = core_dir / "modes" / "build"
    modes_build.mkdir(parents=True)
    (modes_build / "SKILL.md").write_text("# Build mode\n", encoding="utf-8")
    (modes_build / "gotchas.yml").write_text("gotchas: []\n", encoding="utf-8")
    refs_dir = core_dir / "references"
    refs_dir.mkdir()
    (refs_dir / "tool-recommendations.md").write_text("# Tool recommendations\n", encoding="utf-8")
    # Agents
    agents_dir = root / "agents"
    agents_dir.mkdir()
    (agents_dir / "README.md").write_text("# Agents", encoding="utf-8")
    for agent in ["accessibility-expert", "data-engineer", "devops-engineer"]:
        (agents_dir / f"{agent}.md").write_text(f"# {agent}", encoding="utf-8")
    # Workflows
    workflows_dir = root / "workflows"
    workflows_dir.mkdir()
    for wf in [
        "idea-to-pr",
        "studio-onboard",
        "feature-research",
        "hotfix",
        "fix-issue",
        "daily-standup",
        "daily-close",
        "hotfix",
        "optimize",
        "prototype",
        "safe-refactor",
        "security-audit",
    ]:
        (workflows_dir / f"{wf}.yaml").write_text(f"name: {wf}\nsteps: []\n", encoding="utf-8")
    (workflows_dir / "README.md").write_text("# Workflows\n", encoding="utf-8")
    # Workflow contract (at source root, not inside canonical/)
    contract_dir = tmp_path / "docs" / "contracts"
    contract_dir.mkdir(parents=True)
    (contract_dir / "workflow-contract.md").write_text("# Workflow Contract\n", encoding="utf-8")

    # Hook source files — at source root (canonical_root.parent = tmp_path)
    src = tmp_path
    (src / "emitters" / "claude_code").mkdir(parents=True, exist_ok=True)
    (src / "emitters" / "claude_code" / "run.py").write_text("# run.py stub\n", encoding="utf-8")
    # statusline.py — canonical/adapters/claude/statusline.py relative to source root
    (src / "canonical" / "adapters" / "claude").mkdir(parents=True, exist_ok=True)
    (src / "canonical" / "adapters" / "claude" / "statusline.py").write_text(
        "# statusline.py stub\ndef _get_plugin_root(): return ''\n", encoding="utf-8"
    )
    (src / "runtime" / "dispatch").mkdir(parents=True, exist_ok=True)
    (src / "runtime" / "dispatch" / "__init__.py").write_text("", encoding="utf-8")
    (src / "runtime" / "dispatch" / "hooks.py").write_text("# hooks.py stub\n", encoding="utf-8")
    (src / "control" / "execution").mkdir(parents=True, exist_ok=True)
    (src / "control" / "__init__.py").write_text("", encoding="utf-8")
    (src / "control" / "execution" / "__init__.py").write_text("", encoding="utf-8")
    (src / "control" / "execution" / "dispatch_tracking.py").write_text(
        "# dispatch_tracking stub\n", encoding="utf-8"
    )
    meta_dir = src / "runtime" / "hooks" / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "__init__.py").write_text("", encoding="utf-8")
    for handler in [
        "on-prompt-dispatch",
        "on-stop-dispatch",
        "on-tool-activity",
        "on-skill-complete",
    ]:
        (meta_dir / f"{handler}.py").write_text(f"# {handler} stub\n", encoding="utf-8")

    return root


@pytest.fixture
def config_root(tmp_path):
    cr = tmp_path / "claude_config"
    cr.mkdir()
    return cr


@pytest.fixture
def source_root_with_version(tmp_path, canonical_root):
    """Source root (parent of canonical) with VERSION file."""
    source_root = canonical_root.parent  # tmp_path
    (source_root / "VERSION").write_text("2026-05-17\n", encoding="utf-8")
    return source_root


# ── _skill_id_from_dir_name ───────────────────────────────────────────────────


def test_skill_id_from_dir_name_adds_ds_prefix():
    assert _skill_id_from_dir_name("core") == "ds-core"
    assert _skill_id_from_dir_name("quality") == "ds-quality"
    assert _skill_id_from_dir_name("workflow") == "ds-workflow"


def test_skill_id_from_dir_name_preserves_ds_prefix():
    assert _skill_id_from_dir_name("ds-bootstrap") == "ds-bootstrap"
    assert _skill_id_from_dir_name("ds-project") == "ds-project"


# ── Plan: all skills ──────────────────────────────────────────────────────────


def test_plan_installs_all_canonical_skills(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    plan = installer.plan()
    skill_ops = [op for op in plan.ops if "skills" in str(op.target)]
    skill_names = {Path(op.target).parent.name for op in skill_ops}
    assert "ds-bootstrap" in skill_names
    assert "ds-core" in skill_names
    assert "ds-quality" in skill_names


def test_plan_skill_ops_are_all_create(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    plan = installer.plan()
    skill_ops = [op for op in plan.ops if "skills" in str(op.target)]
    assert all(op.op == "create" for op in skill_ops)


def test_plan_applies_ds_prefix_to_skill_ids(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    plan = installer.plan()
    skill_ops = [op for op in plan.ops if "skills" in str(op.target)]
    # Extract pack name (second component after "skills/") — not the direct parent which may be a subdir
    skill_packs: set[str] = set()
    for op in skill_ops:
        parts = list(Path(op.target).parts)
        if "skills" in parts:
            idx = parts.index("skills")
            if idx + 1 < len(parts):
                skill_packs.add(parts[idx + 1])
    assert all(name.startswith("ds-") for name in skill_packs)


# ── Plan: agents ──────────────────────────────────────────────────────────────


def test_plan_includes_agent_ops(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    plan = installer.plan()
    agent_ops = [op for op in plan.ops if "agents" in str(op.target)]
    assert len(agent_ops) == 3  # accessibility-expert, data-engineer, devops-engineer


def test_plan_skips_readme_for_agents(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    plan = installer.plan()
    agent_paths = [str(op.target) for op in plan.ops if "agents" in str(op.target)]
    assert not any("README" in p for p in agent_paths)


def test_plan_agent_ops_are_create(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    plan = installer.plan()
    agent_ops = [op for op in plan.ops if "agents" in str(op.target)]
    assert all(op.op == "create" for op in agent_ops)


# ── Plan: installed-version ───────────────────────────────────────────────────


def test_plan_includes_installed_version_when_version_file_exists(
    config_root, source_root_with_version, ds_home
):
    installer = ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=source_root_with_version / "canonical",
        ds_home=ds_home,
    )
    plan = installer.plan()
    version_ops = [op for op in plan.ops if op.target.name == "installed-version"]
    assert len(version_ops) == 1
    assert version_ops[0].op == "create"
    assert "2026-05-17" in version_ops[0].source_content


def test_plan_no_installed_version_when_version_file_absent(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    plan = installer.plan()
    version_ops = [op for op in plan.ops if op.target.name == "installed-version"]
    assert len(version_ops) == 0


# ── Execute: skills written ───────────────────────────────────────────────────


def test_execute_writes_all_skills_to_config_root(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    result = installer.install("execute")
    assert result["ok"] is True
    skills_dir = config_root / "skills"
    assert (skills_dir / "ds-bootstrap" / "SKILL.md").is_file()
    assert (skills_dir / "ds-core" / "SKILL.md").is_file()
    assert (skills_dir / "ds-quality" / "SKILL.md").is_file()


def test_execute_result_lists_skills_installed(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    result = installer.install("execute")
    assert "skills" in result
    s = result["skills"]
    assert s["packs_synced"] > 0
    assert s["files_copied"] > 0
    assert "files_updated" in s
    assert "files_unchanged" in s


# ── Execute: agents written ───────────────────────────────────────────────────


def test_execute_writes_agents_to_config_root(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    agents_dir = config_root / "agents"
    assert (agents_dir / "accessibility-expert.md").is_file()
    assert (agents_dir / "data-engineer.md").is_file()


def test_execute_result_lists_agents_installed(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    result = installer.install("execute")
    assert "agents_installed" in result
    assert "accessibility-expert" in result["agents_installed"]


def test_execute_does_not_write_readme_as_agent(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    assert not (config_root / "agents" / "README.md").is_file()


# ── Execute: dispatcher hooks ─────────────────────────────────────────────────


def test_execute_installs_dispatcher_hooks_in_settings_json(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    settings = json.loads((config_root / "settings.json").read_text(encoding="utf-8"))
    found_dispatcher = any(
        _cmd_has_dispatcher(h.get("command", ""))
        for entry in settings.get("hooks", {}).get("UserPromptSubmit", [])
        for h in entry.get("hooks", [])
    )
    assert found_dispatcher, "Dispatcher hook not found in settings.json UserPromptSubmit"


def test_execute_installs_emitter_hooks_in_settings_json(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    settings = json.loads((config_root / "settings.json").read_text(encoding="utf-8"))
    found_emitter = any(
        _cmd_has_emitter(h.get("command", ""))
        for entry in settings.get("hooks", {}).get("UserPromptSubmit", [])
        for h in entry.get("hooks", [])
    )
    assert found_emitter, "Emitter hook not found in settings.json"


def test_second_install_does_not_duplicate_hooks(config_root, canonical_root, ds_home):
    """Running install twice must not duplicate hooks in settings.json."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    installer.install("execute")
    settings = json.loads((config_root / "settings.json").read_text(encoding="utf-8"))
    dispatcher_count = sum(
        1
        for entry in settings.get("hooks", {}).get("UserPromptSubmit", [])
        for h in entry.get("hooks", [])
        if _cmd_has_dispatcher(h.get("command", ""))
    )
    assert dispatcher_count == 1, f"Dispatcher hook duplicated: found {dispatcher_count}"


# ── Execute: installed-version written ───────────────────────────────────────


def test_execute_writes_installed_version(config_root, source_root_with_version, ds_home):
    installer = ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=source_root_with_version / "canonical",
        ds_home=ds_home,
    )
    installer.install("execute")
    version_file = ds_home / "state" / "installed-version"
    assert version_file.is_file()
    assert version_file.read_text(encoding="utf-8").strip() == "2026-05-17"


def test_dry_run_does_not_write_installed_version(config_root, source_root_with_version, ds_home):
    installer = ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=source_root_with_version / "canonical",
        ds_home=ds_home,
    )
    installer.install("dry_run")
    version_file = ds_home / "state" / "installed-version"
    assert not version_file.exists()


# ── Execute: structured report ────────────────────────────────────────────────


def test_execute_result_includes_validation_key(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    result = installer.install("execute")
    assert "validation" in result
    v = result["validation"]
    assert "skills_found" in v
    assert "agents_found" in v
    assert "dispatcher_hooks_ok" in v
    assert isinstance(v["pass"], bool)


def test_execute_validation_reports_skills_found(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    result = installer.install("execute")
    assert result["validation"]["skills_found"] > 0


def test_execute_validation_reports_agents_found(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    result = installer.install("execute")
    assert result["validation"]["agents_found"] > 0


def test_execute_validation_reports_dispatcher_ok(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    result = installer.install("execute")
    assert result["validation"]["dispatcher_hooks_ok"] is True


# ── Full skill directory sync ─────────────────────────────────────────────────


def test_execute_installs_full_skill_directory(config_root, canonical_root, ds_home):
    """modes/build/SKILL.md must be present after install, not just root SKILL.md."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    assert (config_root / "skills" / "ds-core" / "modes" / "build" / "SKILL.md").is_file()


def test_execute_installs_mode_gotchas_yml(config_root, canonical_root, ds_home):
    """gotchas.yml inside a mode subdir must be synced."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    assert (config_root / "skills" / "ds-core" / "modes" / "build" / "gotchas.yml").is_file()


def test_execute_installs_references_dir(config_root, canonical_root, ds_home):
    """references/ directory inside skill must be synced."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    assert (config_root / "skills" / "ds-core" / "references" / "tool-recommendations.md").is_file()


def test_execute_second_run_skips_unchanged_skills(config_root, canonical_root, ds_home):
    """Second install must skip files whose hash matches the manifest (files_unchanged > 0)."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    result2 = installer.install("execute")
    assert result2["skills"]["files_unchanged"] > 0
    assert result2["skills"]["files_copied"] == 0


def test_execute_new_canonical_file_appears_on_reinstall(config_root, canonical_root, ds_home):
    """A file added to canonical/ after first install must appear after reinstall."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    # Add a new file to the canonical skill tree after first install
    new_file = canonical_root / "skills" / "core" / "modes" / "build" / "new-reference.md"
    new_file.write_text("# New reference\n", encoding="utf-8")
    installer.install("execute")
    assert (config_root / "skills" / "ds-core" / "modes" / "build" / "new-reference.md").is_file()


# ── Workflow YAML install ─────────────────────────────────────────────────────


def test_execute_creates_workflows_directory(config_root, canonical_root, ds_home):
    """~/.claude/workflows/ must be created by the installer."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    assert (config_root / "workflows").is_dir()


def test_execute_installs_workflow_yamls(config_root, canonical_root, ds_home):
    """All workflow YAMLs from canonical/workflows/ must be installed."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    installed = list((config_root / "workflows").glob("*.yaml"))
    canonical_yamls = list((canonical_root / "workflows").glob("*.yaml"))
    assert len(installed) == len(canonical_yamls)


def test_execute_installs_specific_workflows(config_root, canonical_root, ds_home):
    """idea-to-pr.yaml and studio-onboard.yaml must be present after install."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    assert (config_root / "workflows" / "idea-to-pr.yaml").is_file()
    assert (config_root / "workflows" / "studio-onboard.yaml").is_file()


def test_execute_second_run_skips_unchanged_workflows(config_root, canonical_root, ds_home):
    """Second install must skip workflow files whose hash matches manifest."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    result2 = installer.install("execute")
    assert result2["workflows"]["unchanged"] > 0
    assert result2["workflows"]["copied"] == 0


def test_execute_installs_workflow_contract(config_root, canonical_root, ds_home):
    """docs/contracts/workflow-contract.md must be installed inside ds-workflow skill."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    contract_path = (
        config_root / "skills" / "ds-workflow" / "docs" / "contracts" / "workflow-contract.md"
    )
    assert contract_path.is_file()


# ── Hook file installs ────────────────────────────────────────────────────────


def test_execute_installs_run_py_to_hooks_dir(config_root, canonical_root, ds_home):
    """emitters/claude_code/run.py must be copied to hooks/run.py."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    assert (config_root / "hooks" / "run.py").is_file()


def test_execute_installs_dispatch_hooks_to_hooks_dir(config_root, canonical_root, ds_home):
    """runtime/dispatch/hooks.py must be copied to hooks/dispatch/hooks.py."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    assert (config_root / "hooks" / "dispatch" / "hooks.py").is_file()


def test_execute_writes_plugin_root_sidecar(config_root, canonical_root, ds_home):
    """hooks/.plugin-root sidecar must point at the installed hooks dir."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    sidecar = config_root / "hooks" / ".plugin-root"
    assert sidecar.is_file()
    content = sidecar.read_text(encoding="utf-8").strip()
    # WO-RT changed content from repo_root to hooks_dir so _get_plugin_root()
    # resolves handler paths inside the installed runtime, not the repo working tree.
    assert content == str(config_root / "hooks")


def test_execute_installs_meta_handlers(config_root, canonical_root, ds_home):
    """At least one meta handler must be present in hooks/runtime/hooks/meta/."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    meta_dir = config_root / "hooks" / "runtime" / "hooks" / "meta"
    handlers = (
        [f for f in meta_dir.glob("*.py") if f.name != "__init__.py"] if meta_dir.is_dir() else []
    )
    assert len(handlers) >= 1


def test_execute_installs_hook_init_py_files(config_root, canonical_root, ds_home):
    """__init__.py files must be installed for hook package namespaces."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    assert (config_root / "hooks" / "dispatch" / "__init__.py").is_file()
    assert (config_root / "hooks" / "control" / "__init__.py").is_file()


def test_execute_installs_posttooluse_matcher_entries(config_root, canonical_root, ds_home):
    """settings.json PostToolUse section must contain entries with matcher fields."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    settings = json.loads((config_root / "settings.json").read_text(encoding="utf-8"))
    post_tool_entries = settings.get("hooks", {}).get("PostToolUse", [])
    matchers = {entry.get("matcher") for entry in post_tool_entries if "matcher" in entry}
    assert "Skill" in matchers, "PostToolUse must have a 'Skill' matcher entry"
    assert "Edit|Write" in matchers, "PostToolUse must have an 'Edit|Write' matcher entry"
    assert (
        "Read" not in matchers
    ), "PostToolUse must NOT have a 'Read' matcher (overhead with no consumer)"


def test_hook_commands_use_hooks_dir_path(config_root, canonical_root, ds_home):
    """Hook commands must reference the hooks/ dir path, not filesystem-walking one-liners."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    settings = json.loads((config_root / "settings.json").read_text(encoding="utf-8"))
    hooks_dir_posix = (config_root / "hooks").as_posix()
    all_cmds = [
        h.get("command", "")
        for entries in settings.get("hooks", {}).values()
        for entry in entries
        for h in entry.get("hooks", [])
        if isinstance(h, dict)
    ]
    # At least one command must reference the installed hooks_dir (forward-slash normalized)
    assert any(
        hooks_dir_posix in cmd for cmd in all_cmds
    ), f"No command references hooks_dir={hooks_dir_posix!r}. Commands: {all_cmds}"


# ── Legacy hook purge ─────────────────────────────────────────────────────────

_LEGACY_CMD = (
    "python -c \"import os,pathlib,runpy,sys; root=pathlib.Path(os.environ.get('CLAUDE_PLUGIN_ROOT') or os.getcwd()).resolve(); "
    "emitter=next((p/'emitters'/'claude_code'/'run.py' for p in (root,*root.parents) if (p/'emitters'/'claude_code'/'run.py').is_file()),None); "
    "sys.argv=[str(emitter),'UserPromptSubmit']; (runpy.run_path(str(emitter),run_name='__main__') if emitter else None); sys.exit(0)\""
)


def _settings_with_legacy_and_stable(hooks_dir: str) -> dict:
    """Build a settings dict that has both a legacy one-liner and a stable-path entry."""
    return {
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": _LEGACY_CMD}]},
                {
                    "hooks": [
                        {"type": "command", "command": f'py "{hooks_dir}\\run.py" UserPromptSubmit'}
                    ]
                },
            ]
        }
    }


def test_purge_legacy_hooks_removes_one_liner_when_stable_present(tmp_path):
    settings = _settings_with_legacy_and_stable(str(tmp_path / "hooks"))
    cleaned, removed = purge_legacy_hooks(settings)
    cmds = [
        h.get("command", "")
        for entry in cleaned["hooks"]["UserPromptSubmit"]
        for h in entry.get("hooks", [])
    ]
    assert not any("runpy.run_path" in c for c in cmds), "Legacy one-liner not removed"
    assert any(str(tmp_path / "hooks") in c for c in cmds), "Stable entry incorrectly removed"
    assert len(removed) == 1


def test_purge_legacy_hooks_leaves_legacy_when_no_stable_present():
    settings = {
        "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": _LEGACY_CMD}]}]}
    }
    cleaned, removed = purge_legacy_hooks(settings)
    assert len(removed) == 0, "Should not remove when no stable replacement present"
    assert len(cleaned["hooks"]["UserPromptSubmit"]) == 1


def test_execute_install_removes_legacy_hooks_when_stable_present(
    config_root, canonical_root, ds_home
):
    """Second install (stable entries now present) must remove any pre-existing legacy one-liners."""
    # Seed settings.json with a legacy entry before first install
    settings_path = config_root / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": _LEGACY_CMD}]}]
                }
            }
        ),
        encoding="utf-8",
    )

    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    cmds = [
        h.get("command", "")
        for entry in settings.get("hooks", {}).get("UserPromptSubmit", [])
        for h in entry.get("hooks", [])
    ]
    assert not any(
        "runpy.run_path" in c for c in cmds
    ), "Legacy hook survived install despite stable replacement being present"


# ── Platform compatibility (WS 9e-2) ─────────────────────────────────────────


def test_python_cmd_returns_py_on_windows():
    with patch("platform.system", return_value="Windows"):
        assert _python_cmd() == "py"


def test_python_cmd_returns_sys_executable_on_non_windows():
    for system in ("Linux", "Darwin"):
        with patch("platform.system", return_value=system):
            assert _python_cmd() == sys.executable


def test_hook_commands_use_python_cmd_placeholder_resolved(config_root, canonical_root, ds_home):
    """After install, no hook command should still contain the literal {python_cmd} placeholder."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    settings = json.loads((config_root / "settings.json").read_text(encoding="utf-8"))
    all_cmds = [
        h.get("command", "")
        for entries in settings.get("hooks", {}).values()
        for entry in entries
        for h in entry.get("hooks", [])
        if isinstance(h, dict)
    ]
    assert not any(
        "{python_cmd}" in cmd for cmd in all_cmds
    ), "{python_cmd} placeholder was not resolved in hook commands"


def test_hook_commands_use_py_on_windows_mock(config_root, canonical_root, ds_home):
    """When platform is Windows, hook commands must use 'py' as the Python executable."""
    with patch("platform.system", return_value="Windows"):
        installer = ClaudeCodeInstaller(
            config_root, "user", canonical_root=canonical_root, ds_home=ds_home
        )
        with patch(
            "integrations.installer.claude_code._write_path_to_profile",
            return_value={"action": "skipped", "profile": ""},
        ):
            installer.install("execute")
    settings = json.loads((config_root / "settings.json").read_text(encoding="utf-8"))
    all_cmds = [
        h.get("command", "")
        for entries in settings.get("hooks", {}).values()
        for entry in entries
        for h in entry.get("hooks", [])
        if isinstance(h, dict)
    ]
    assert any(
        cmd.startswith("py ") for cmd in all_cmds
    ), "No hook command starts with 'py' on Windows mock"


def test_hook_commands_use_sys_executable_on_linux_mock(config_root, canonical_root, ds_home):
    """When platform is Linux, hook commands must use sys.executable."""
    with patch("platform.system", return_value="Linux"):
        installer = ClaudeCodeInstaller(
            config_root, "user", canonical_root=canonical_root, ds_home=ds_home
        )
        with patch(
            "integrations.installer.claude_code._write_path_to_profile",
            return_value={"action": "skipped", "profile": ""},
        ):
            installer.install("execute")
    settings = json.loads((config_root / "settings.json").read_text(encoding="utf-8"))
    all_cmds = [
        h.get("command", "")
        for entries in settings.get("hooks", {}).values()
        for entry in entries
        for h in entry.get("hooks", [])
        if isinstance(h, dict)
    ]
    assert any(
        sys.executable in cmd for cmd in all_cmds
    ), f"sys.executable ({sys.executable!r}) not found in any hook command"


def test_launcher_cmd_written_on_windows(ds_home):
    """Windows launcher must be ds.cmd."""
    with (
        patch("platform.system", return_value="Windows"),
        patch(
            "integrations.installer.claude_code._write_path_to_profile",
            return_value={"action": "skipped", "profile": ""},
        ),
    ):
        result = _write_global_launcher(ds_home=ds_home)
    assert result["is_windows"] is True
    assert Path(result["launcher_path"]).name == "ds.cmd"


def test_launcher_shell_script_written_on_nonwindows(ds_home):
    """Non-Windows launcher must be 'ds' (no extension)."""
    with (
        patch("platform.system", return_value="Linux"),
        patch(
            "integrations.installer.claude_code._write_path_to_profile",
            return_value={"action": "skipped", "profile": ""},
        ),
    ):
        result = _write_global_launcher(ds_home=ds_home)
    assert result["is_windows"] is False
    assert Path(result["launcher_path"]).name == "ds"


@pytest.mark.skipif(sys.platform == "win32", reason="chmod executable bits not reliable on Windows")
def test_launcher_shell_script_is_executable_on_nonwindows(ds_home):
    """Non-Windows launcher must have executable bit set."""
    import stat as _stat

    with (
        patch("platform.system", return_value="Linux"),
        patch(
            "integrations.installer.claude_code._write_path_to_profile",
            return_value={"action": "skipped", "profile": ""},
        ),
    ):
        result = _write_global_launcher(ds_home=ds_home)
    mode = Path(result["launcher_path"]).stat().st_mode
    assert mode & _stat.S_IEXEC, "Launcher shell script must have executable bit"


def test_path_line_added_to_profile_file(tmp_path):
    """_write_path_to_profile must append the DS PATH line to the profile."""
    bin_dir = tmp_path / "bin"
    with (
        patch("platform.system", return_value="Linux"),
        patch("pathlib.Path.home", return_value=tmp_path),
    ):
        result = _write_path_to_profile(bin_dir)
    assert result["action"] == "appended"
    profile = tmp_path / ".bashrc"
    content = profile.read_text(encoding="utf-8")
    assert _DS_PATH_MARKER in content
    assert ".dream-studio/bin" in content


def test_path_line_not_duplicated_on_second_install(tmp_path):
    """_write_path_to_profile must be idempotent — second call must skip."""
    bin_dir = tmp_path / "bin"
    with (
        patch("platform.system", return_value="Linux"),
        patch("pathlib.Path.home", return_value=tmp_path),
    ):
        result1 = _write_path_to_profile(bin_dir)
        result2 = _write_path_to_profile(bin_dir)
    assert result1["action"] == "appended"
    assert result2["action"] == "skipped"
    profile = tmp_path / ".bashrc"
    content = profile.read_text(encoding="utf-8")
    assert content.count(_DS_PATH_MARKER) == 1


# ── Hook dedup by normalized command ─────────────────────────────────────────


def test_dedup_backslash_and_forward_slash_collapse_to_one():
    """Backslash and forward-slash variants of the same command dedup to one entry."""
    settings = {
        "hooks": {
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'py "C:\\claude\\hooks/run.py" UserPromptSubmit',
                        }
                    ]
                },
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'py "C:\\claude\\hooks\\run.py" UserPromptSubmit',
                        }
                    ]
                },
            ]
        }
    }
    result = dedup_hooks_by_normalized_command(settings)
    entries = result["hooks"]["UserPromptSubmit"]
    assert len(entries) == 1, f"Expected 1 entry after dedup, got {len(entries)}"


def test_dedup_different_matchers_not_removed():
    """Entries with different matchers are never collapsed, even with identical commands."""
    cmd = 'py "C:\\claude\\hooks\\dispatch\\hooks.py" PostToolUse'
    settings = {
        "hooks": {
            "PostToolUse": [
                {"matcher": "Skill", "hooks": [{"type": "command", "command": cmd}]},
                {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": cmd}]},
                {"matcher": "Read", "hooks": [{"type": "command", "command": cmd}]},
            ]
        }
    }
    result = dedup_hooks_by_normalized_command(settings)
    entries = result["hooks"]["PostToolUse"]
    assert len(entries) == 3, f"Expected 3 distinct matcher entries, got {len(entries)}"


def test_dedup_same_matcher_same_command_different_slash_style():
    """Same matcher + slash-variant command collapses to one entry."""
    settings = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "Skill",
                    "hooks": [{"type": "command", "command": 'py "C:\\hooks/run.py"'}],
                },
                {
                    "matcher": "Skill",
                    "hooks": [{"type": "command", "command": 'py "C:\\hooks\\run.py"'}],
                },
            ]
        }
    }
    result = dedup_hooks_by_normalized_command(settings)
    entries = result["hooks"]["PostToolUse"]
    assert len(entries) == 1, f"Expected 1 entry after dedup, got {len(entries)}"


def test_second_install_after_dedup_fix_produces_correct_hook_counts(
    config_root, canonical_root, ds_home
):
    """Reinstall on top of backslash-path settings produces 2/2/2/4 hook entries."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")

    # Mutate all installed hook commands to use backslashes, simulating a prior
    # install that wrote all-backslash paths (different from the mixed/forward-slash
    # paths the template now generates).
    settings_path = config_root / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    for entries in settings.get("hooks", {}).values():
        for entry in entries:
            for h in entry.get("hooks", []):
                if isinstance(h, dict) and "command" in h:
                    h["command"] = h["command"].replace("/", "\\")
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    # Second install — dedup must collapse the backslash+forward-slash duplicates.
    installer.install("execute")
    settings2 = json.loads(settings_path.read_text(encoding="utf-8"))
    hooks = settings2.get("hooks", {})

    ups = len(hooks.get("UserPromptSubmit", []))
    stop = len(hooks.get("Stop", []))
    pc = len(hooks.get("PostCompact", []))
    ptu = len(hooks.get("PostToolUse", []))

    assert ups == 2, f"UserPromptSubmit: expected 2, got {ups}"
    assert stop == 2, f"Stop: expected 2, got {stop}"
    assert pc == 2, f"PostCompact: expected 2, got {pc}"
    assert ptu == 3, f"PostToolUse: expected 3 (Read matcher removed), got {ptu}"


# ── Fix verifications ─────────────────────────────────────────────────────────


def test_packs_yaml_has_ds_website_skill_id():
    """packs.yaml must declare skill: ds-website for the website pack."""
    import yaml

    packs_path = Path(__file__).resolve().parents[3] / "packs.yaml"
    data = yaml.safe_load(packs_path.read_text(encoding="utf-8"))
    website = data["packs"]["website"]
    assert (
        website["skill"] == "ds-website"
    ), f"website pack skill should be ds-website, got {website['skill']!r}"


def test_packs_yaml_has_ds_fullstack_skill_id():
    """packs.yaml must declare skill: ds-fullstack for the fullstack pack."""
    import yaml

    packs_path = Path(__file__).resolve().parents[3] / "packs.yaml"
    data = yaml.safe_load(packs_path.read_text(encoding="utf-8"))
    fullstack = data["packs"]["fullstack"]
    assert (
        fullstack["skill"] == "ds-fullstack"
    ), f"fullstack pack skill should be ds-fullstack, got {fullstack['skill']!r}"


def test_compiled_claude_md_contains_ds_website_row(canonical_root):
    """Compiled CLAUDE.md routing table must contain a ds-website row."""
    from integrations.compiler.claude_code import compile_pack

    pack = compile_pack(canonical_root)
    claude_md = pack["files"]["CLAUDE.md"]
    assert "ds-website" in claude_md, "Compiled CLAUDE.md does not contain ds-website routing row"


def test_compiled_claude_md_contains_ds_fullstack_row(canonical_root):
    """Compiled CLAUDE.md routing table must contain a ds-fullstack row."""
    from integrations.compiler.claude_code import compile_pack

    pack = compile_pack(canonical_root)
    claude_md = pack["files"]["CLAUDE.md"]
    assert (
        "ds-fullstack" in claude_md
    ), "Compiled CLAUDE.md does not contain ds-fullstack routing row"


def test_execute_installs_statusline_py(config_root, canonical_root, ds_home):
    """statusline.py must be copied to hooks/ directory during install."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    assert (
        config_root / "hooks" / "statusline.py"
    ).is_file(), "statusline.py was not installed to hooks/"


def test_execute_settings_contains_statusline_command(config_root, canonical_root, ds_home):
    """settings.json must contain a statusLine.command entry after install."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    settings = json.loads((config_root / "settings.json").read_text(encoding="utf-8"))
    assert "statusLine" in settings, "settings.json missing statusLine key"
    assert settings["statusLine"].get("command"), "statusLine.command is empty or missing"
    assert (
        settings["statusLine"].get("type") == "command"
    ), "statusLine.type must be 'command' (required by Claude Code settings schema)"


def test_execute_statusline_command_has_no_placeholders(config_root, canonical_root, ds_home):
    """statusLine.command must have {hooks_dir} and {python_cmd} resolved after install."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    settings = json.loads((config_root / "settings.json").read_text(encoding="utf-8"))
    cmd = settings.get("statusLine", {}).get("command", "")
    assert "{hooks_dir}" not in cmd, "statusLine.command still contains {hooks_dir} placeholder"
    assert "{python_cmd}" not in cmd, "statusLine.command still contains {python_cmd} placeholder"


def test_statusline_py_contains_get_plugin_root():
    """canonical/adapters/claude/statusline.py must contain _get_plugin_root function."""
    statusline_path = (
        Path(__file__).resolve().parents[3] / "canonical" / "adapters" / "claude" / "statusline.py"
    )
    assert statusline_path.is_file(), "canonical/adapters/claude/statusline.py not found"
    content = statusline_path.read_text(encoding="utf-8")
    assert "_get_plugin_root" in content, "statusline.py missing _get_plugin_root function"


def test_readme_contains_jq_instructions():
    """README.md must contain jq installation instructions."""
    readme_path = Path(__file__).resolve().parents[3] / "README.md"
    content = readme_path.read_text(encoding="utf-8")
    assert "jq" in content, "README.md does not mention jq"
    assert "winget install jqlang.jq" in content, "README.md missing Windows jq install command"


def test_first_run_guide_contains_config_json_step():
    """_FIRST_RUN_GUIDE_TEXT must contain the config.json personalization step."""
    from integrations.installer.claude_code import _FIRST_RUN_GUIDE_TEXT

    assert (
        "config.json" in _FIRST_RUN_GUIDE_TEXT
    ), "_FIRST_RUN_GUIDE_TEXT missing config.json step 0"
    assert (
        "director_name" in _FIRST_RUN_GUIDE_TEXT
    ), "_FIRST_RUN_GUIDE_TEXT missing director_name field reference"


# ── Dispatch consolidation (WO-U) ─────────────────────────────────────────────


def test_purge_all_hook_registrations_removes_hooks_key():
    """purge_all_hook_registrations must strip the hooks section entirely."""
    from integrations.targets.claude_code.settings_merge import purge_all_hook_registrations

    settings = {
        "hooks": {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "py run.py UPS"}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "py run.py Stop"}]}],
        },
        "statusLine": {"type": "command", "command": "py statusline.py"},
        "env": {"MY_VAR": "1"},
    }
    result = purge_all_hook_registrations(settings)
    assert "hooks" not in result, "hooks key must be removed for project scope"
    assert result["statusLine"] == settings["statusLine"], "statusLine must be preserved"
    assert result["env"] == settings["env"], "other keys must be preserved"


def test_purge_all_hook_registrations_is_idempotent():
    """Calling purge_all_hook_registrations twice must produce the same result."""
    from integrations.targets.claude_code.settings_merge import purge_all_hook_registrations

    settings = {
        "hooks": {"UserPromptSubmit": []},
        "statusLine": {"type": "command", "command": "x"},
    }
    once = purge_all_hook_registrations(settings)
    twice = purge_all_hook_registrations(once)
    assert once == twice


def test_project_scope_install_writes_no_hook_registrations(config_root, canonical_root, ds_home):
    """Project-scope install must leave settings.json with no hooks section (dispatch consolidation)."""
    installer = ClaudeCodeInstaller(
        config_root, "project", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    settings_path = config_root / "settings.json"
    assert settings_path.exists(), "settings.json must be written"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "hooks" not in settings, (
        "Project-scope settings.json must not contain hook registrations — "
        "user-global ~/.claude/settings.json is the single dispatch surface"
    )
    assert "statusLine" in settings, "statusLine must still be written in project scope"


def test_user_scope_install_writes_hook_registrations(config_root, canonical_root, ds_home):
    """User-scope install must keep hook registrations in settings.json."""
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    settings = json.loads((config_root / "settings.json").read_text(encoding="utf-8"))
    assert "hooks" in settings, "User-scope settings.json must contain hook registrations"
