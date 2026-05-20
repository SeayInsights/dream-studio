"""Integration tests for clean-install guarantees (WS 9e-6).

These tests simulate the Docker clean-install scenario locally using tmp_path
to ensure every component creates its required directories and handles
missing config gracefully.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# ── Issue 3: settings.json missing on clean install ──────────────────────────


def test_merge_settings_handles_missing_settings_json(tmp_path):
    """merge_settings() must handle a non-existent settings.json gracefully."""
    from integrations.targets.claude_code.settings_merge import load_settings, merge_settings

    missing = tmp_path / "nonexistent" / "settings.json"
    existing = load_settings(missing)
    # Should return empty dict, not raise
    assert existing == {}

    # And merge_settings must produce valid output from empty input
    merged, _skip = merge_settings(existing, [])
    assert isinstance(merged, dict)


def test_install_creates_settings_json_when_missing(tmp_path, canonical_root_minimal):
    """Installer must create settings.json from scratch when none exists."""
    from integrations.installer.claude_code import ClaudeCodeInstaller

    config_root = tmp_path / "claude_config"
    config_root.mkdir()
    ds_home = tmp_path / "ds_home"

    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root_minimal, ds_home=ds_home
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            "integrations.installer.claude_code._write_path_to_profile",
            lambda *a, **kw: {"action": "skipped", "profile": ""},
        )
        installer.install("execute")

    assert (config_root / "settings.json").is_file()
    data = json.loads((config_root / "settings.json").read_text(encoding="utf-8"))
    assert "hooks" in data


# ── Issue 4: ~/.dream-studio missing on clean install ─────────────────────────


def test_ingestor_creates_all_required_directories(tmp_path):
    """ingest() must create spool/, processing/, processed/, failed/ if they don't exist."""
    from spool.ingestor import ingest

    # spool_root doesn't exist yet — ingestor must create it
    spool_root = tmp_path / "events"
    db_path = tmp_path / "test.db"
    result = ingest(root=spool_root, db_path=db_path)
    assert result.processed == 0
    assert result.failed == 0
    # All subdirs must now exist
    from spool.states import SpoolState

    for state in SpoolState:
        assert (spool_root / state.value).is_dir(), f"Missing: {state.value}/"


def test_ingestor_failed_reasons_dir_created_on_first_failure(tmp_path):
    """failed/reasons/ must be created automatically on the first failed event."""
    from spool.ingestor import ingest
    from spool.states import SpoolState, state_dir

    spool_root = tmp_path / "events"
    spool_dir = state_dir(SpoolState.SPOOL, spool_root)
    spool_dir.mkdir(parents=True, exist_ok=True)

    bad_file = spool_dir / "bad.json"
    bad_file.write_text(json.dumps({"no_required_fields": True}), encoding="utf-8")

    db_path = tmp_path / "test.db"
    ingest(root=spool_root, db_path=db_path)

    reasons_dir = spool_root / "failed" / "reasons"
    assert reasons_dir.is_dir(), "failed/reasons/ must be created on first failure"


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest.fixture
def canonical_root_minimal(tmp_path):
    """Minimal canonical root for clean-install tests (no hook source files needed)."""
    root = tmp_path / "canonical"
    skill_dir = root / "skills" / "ds-bootstrap"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# bootstrap\n", encoding="utf-8")
    agents_dir = root / "agents"
    agents_dir.mkdir()
    (agents_dir / "test-agent.md").write_text("# test agent\n", encoding="utf-8")
    workflows_dir = root / "workflows"
    workflows_dir.mkdir()
    (workflows_dir / "idea-to-pr.yaml").write_text("name: idea-to-pr\n", encoding="utf-8")
    # Source root (canonical's parent = tmp_path) needs VERSION
    (tmp_path / "VERSION").write_text("2026-05-17\n", encoding="utf-8")
    return root
