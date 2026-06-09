"""Integration tests for Workstream 9d — complete install chain.

Tests run against the real canonical/ tree in the repo.
Never writes to real ~/.claude or ~/.dream-studio — uses tmp_path.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def config_root(tmp_path):
    cr = tmp_path / "claude_config"
    cr.mkdir()
    return cr


def _make_installer(config_root, ds_home):
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from integrations.installer.claude_code import ClaudeCodeInstaller

    return ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=REPO_ROOT / "canonical",
        ds_home=ds_home,
    )


# ── Skills from real canonical tree ──────────────────────────────────────────


def test_install_deploys_all_canonical_skills(config_root, ds_home):
    """All SKILL.md files in canonical/skills/ are installed to config_root/skills/."""
    installer = _make_installer(config_root, ds_home)
    installer.install("execute")

    canonical_skills = REPO_ROOT / "canonical" / "skills"
    for skill_dir in canonical_skills.iterdir():
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").is_file():
            name = skill_dir.name
            skill_id = name if name.startswith("ds-") else f"ds-{name}"
            target = config_root / "skills" / skill_id / "SKILL.md"
            assert target.is_file(), f"Expected skill {skill_id} not installed at {target}"


def test_install_skill_content_matches_canonical(config_root, ds_home):
    """Installed SKILL.md content matches source canonical file."""
    installer = _make_installer(config_root, ds_home)
    installer.install("execute")

    bootstrap_src = REPO_ROOT / "canonical" / "skills" / "ds-bootstrap" / "SKILL.md"
    bootstrap_dst = config_root / "skills" / "ds-bootstrap" / "SKILL.md"
    assert bootstrap_dst.read_text(encoding="utf-8") == bootstrap_src.read_text(encoding="utf-8")


# ── Agents from real canonical tree ──────────────────────────────────────────


def test_install_deploys_all_canonical_agents(config_root, ds_home):
    """All agent *.md files in canonical/agents/ (excluding README) are installed."""
    installer = _make_installer(config_root, ds_home)
    installer.install("execute")

    agents_src = REPO_ROOT / "canonical" / "agents"
    for agent_file in agents_src.glob("*.md"):
        if agent_file.name == "README.md":
            continue
        target = config_root / "agents" / agent_file.name
        assert target.is_file(), f"Agent {agent_file.name} not installed"


def test_install_does_not_write_readme_agent(config_root, ds_home):
    installer = _make_installer(config_root, ds_home)
    installer.install("execute")
    assert not (config_root / "agents" / "README.md").is_file()


def test_installed_agent_count_matches_source(config_root, ds_home):
    installer = _make_installer(config_root, ds_home)
    result = installer.install("execute")

    agents_src = REPO_ROOT / "canonical" / "agents"
    expected = [f for f in agents_src.glob("*.md") if f.name != "README.md"]
    assert len(result["agents_installed"]) == len(expected)


# ── Dispatcher hooks in settings.json ────────────────────────────────────────


def test_install_adds_dispatcher_hook_for_all_events(config_root, ds_home):
    """Dispatcher hook is present for all 4 hook events."""
    installer = _make_installer(config_root, ds_home)
    installer.install("execute")

    settings = json.loads((config_root / "settings.json").read_text(encoding="utf-8"))
    hooks = settings.get("hooks", {})
    for event in ("UserPromptSubmit", "Stop", "PostCompact", "PostToolUse"):
        found = any(
            (
                "runtime/dispatch/hooks" in h.get("command", "")
                or "'dispatch'/'hooks.py'" in h.get("command", "")
                or "hooks/dispatch/hooks.py" in h.get("command", "")  # stable-path format
                or "hooks\\dispatch\\hooks.py" in h.get("command", "")  # stable-path Windows
            )
            for entry in hooks.get(event, [])
            for h in entry.get("hooks", [])
        )
        assert found, f"Dispatcher hook missing for event {event}"


def test_install_adds_emitter_hook_for_all_events(config_root, ds_home):
    """Emitter hook is present for all 4 hook events."""
    installer = _make_installer(config_root, ds_home)
    installer.install("execute")

    settings = json.loads((config_root / "settings.json").read_text(encoding="utf-8"))
    hooks = settings.get("hooks", {})
    for event in ("UserPromptSubmit", "Stop", "PostCompact", "PostToolUse"):
        found = any(
            (
                "'emitters'/'claude_code'" in h.get("command", "")
                or "hooks/run.py" in h.get("command", "")  # stable-path format
                or "hooks\\run.py" in h.get("command", "")  # stable-path Windows
            )
            for entry in hooks.get(event, [])
            for h in entry.get("hooks", [])
        )
        assert found, f"Emitter hook missing for event {event}"


def test_reinstall_does_not_duplicate_hooks(config_root, ds_home):
    """Running install twice does not duplicate any hooks."""
    installer = _make_installer(config_root, ds_home)
    installer.install("execute")
    installer.install("execute")

    settings = json.loads((config_root / "settings.json").read_text(encoding="utf-8"))
    for event in ("UserPromptSubmit", "Stop", "PostCompact", "PostToolUse"):
        disp_count = sum(
            1
            for entry in settings.get("hooks", {}).get(event, [])
            for h in entry.get("hooks", [])
            if (
                "runtime/dispatch/hooks" in h.get("command", "")
                or "'dispatch'/'hooks.py'" in h.get("command", "")
                or "hooks/dispatch/hooks.py" in h.get("command", "")
                or "hooks\\dispatch\\hooks.py" in h.get("command", "")
            )
        )
        # PostToolUse has 2 active matchers (Skill, Edit|Write).
        # Read matcher is intentionally removed by purge_read_posttooluse_matcher
        # (pure overhead — no active consumer).
        expected = 2 if event == "PostToolUse" else 1
        assert disp_count == expected, f"Dispatcher hook count wrong for {event}: {disp_count}"


# ── installed-version written ─────────────────────────────────────────────────


def test_install_writes_installed_version_matching_repo_version(config_root, ds_home):
    """installed-version file matches VERSION file after install."""
    installer = _make_installer(config_root, ds_home)
    installer.install("execute")

    version_src = REPO_ROOT / "VERSION"
    if not version_src.is_file():
        pytest.skip("No VERSION file at repo root")

    version_installed = ds_home / "state" / "installed-version"
    assert version_installed.is_file(), "installed-version file not written"
    assert (
        version_installed.read_text(encoding="utf-8").strip()
        == version_src.read_text(encoding="utf-8").strip()
    )


# ── Post-install validation ───────────────────────────────────────────────────


def test_install_result_validation_passes(config_root, ds_home):
    """Post-install validation in install result reports pass=True."""
    installer = _make_installer(config_root, ds_home)
    result = installer.install("execute")
    v = result["validation"]
    assert v["skills_found"] > 0
    assert v["agents_found"] > 0
    assert v["dispatcher_hooks_ok"] is True
    assert v["pass"] is True


# ── Doctor check after install ────────────────────────────────────────────────


def test_doctor_checks_pass_after_install(config_root, ds_home, tmp_path):
    """After a full install, doctor dispatcher + skills + agents checks should pass."""
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from interfaces.cli.ds import (
        _check_dispatcher_hooks,
        _check_skills_installed,
        _check_agents_installed,
    )

    installer = _make_installer(config_root, ds_home)
    installer.install("execute")

    # _check_dispatcher_hooks reads from config_root (installed ~/.claude dir)
    assert _check_dispatcher_hooks(config_root) is True

    skills_info = _check_skills_installed(config_root, source_root=REPO_ROOT)
    assert skills_info["installed"] > 0
    assert skills_info["missing"] == []

    agents_info = _check_agents_installed(config_root, source_root=REPO_ROOT)
    assert agents_info["installed"] > 0
    assert agents_info["missing"] == []
