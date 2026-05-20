"""Integration agent contract boundary tests.

Replaces tests/unit/test_agent_adapter_boundary_contract.py.
Verifies that integrations/ is non-authoritative: no implicit side effects,
explicit mode required, closed scope set, no vendor names in state values.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.health import IntegrationState
from integrations.installer.base import RefusalError
from integrations.installer.claude_code import ClaudeCodeInstaller


@pytest.fixture
def canonical_root(tmp_path):
    root = tmp_path / "canonical"
    skill_dir = root / "skills" / "ds-bootstrap"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# ds-bootstrap", encoding="utf-8")
    return root


@pytest.fixture
def config_root(tmp_path):
    cr = tmp_path / "claude_config"
    cr.mkdir()
    return cr


def test_installer_requires_explicit_mode_not_implicit(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    with pytest.raises(RefusalError):
        installer.install("approve")
    with pytest.raises(RefusalError):
        installer.install("")
    with pytest.raises(RefusalError):
        installer.install("auto")


def test_installer_dry_run_mode_has_no_side_effects(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    result = installer.install("dry_run")
    assert result["files_written"] == []
    assert list(config_root.iterdir()) == []


def test_installer_scope_is_bounded_to_known_values(config_root, canonical_root, ds_home):
    for valid_scope in ("user", "project"):
        installer = ClaudeCodeInstaller(
            config_root, valid_scope, canonical_root=canonical_root, ds_home=ds_home
        )
        result = installer.install("dry_run")
        assert result["scope"] == valid_scope


def test_integration_states_are_provider_neutral_closed_set():
    vendor_names = {"claude", "openai", "codex", "gemini", "copilot", "cursor", "anthropic"}
    for state in IntegrationState:
        for vendor in vendor_names:
            assert (
                vendor not in state.value
            ), f"State {state.value!r} contains vendor name {vendor!r}"
    assert len(list(IntegrationState)) == 9


def test_installer_plan_separates_intent_from_execution(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    plan = installer.plan()
    assert plan.ops, "Plan must have at least one operation"
    for op in plan.ops:
        assert not op.target.exists(), f"plan() must not create files — {op.target} already exists"


def test_installer_does_not_write_outside_config_root(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    result = installer.install("execute")
    for entry in result["files_written"]:
        written_path = Path(entry["path"])
        in_config = False
        in_ds_home = False
        try:
            written_path.relative_to(config_root)
            in_config = True
        except ValueError:
            pass
        try:
            written_path.relative_to(ds_home)
            in_ds_home = True
        except ValueError:
            pass
        assert (
            in_config or in_ds_home
        ), f"File written outside config_root and ds_home: {written_path}"


def test_installer_tool_id_is_provider_neutral(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    result = installer.install("dry_run")
    assert result["tool"] == "claude_code"
    assert "anthropic" not in result["tool"]
    assert "openai" not in result["tool"]
