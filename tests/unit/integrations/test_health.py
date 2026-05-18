from __future__ import annotations

from pathlib import Path

import pytest

from integrations.health import IntegrationState, doctor


def test_not_detected_when_config_root_missing(tmp_path, ds_home):
    config_root = tmp_path / ".claude_nonexistent"
    result = doctor("claude_code", config_root, ds_home=ds_home)
    assert result["state"] == IntegrationState.NOT_DETECTED.value


def test_detected_not_integrated_when_config_exists_no_manifest(tmp_path, ds_home):
    config_root = tmp_path / ".claude"
    config_root.mkdir()
    canonical_root = tmp_path / "canonical_missing"
    result = doctor("claude_code", config_root, ds_home=ds_home, canonical_root=canonical_root)
    assert result["state"] == IntegrationState.DETECTED_NOT_INTEGRATED.value


def test_plan_available_when_canonical_readable(tmp_path, ds_home):
    config_root = tmp_path / ".claude"
    config_root.mkdir()
    canonical_root = tmp_path / "canonical"
    skill_dir = canonical_root / "skills" / "ds-bootstrap"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Bootstrap", encoding="utf-8")

    result = doctor("claude_code", config_root, ds_home=ds_home, canonical_root=canonical_root)
    assert result["state"] == IntegrationState.PLAN_AVAILABLE.value


def test_installed_verified_when_hashes_match(tmp_path, ds_home):
    from integrations.manifest import build_manifest, compute_hash, write_manifest

    config_root = tmp_path / ".claude"
    config_root.mkdir()
    skill_md = config_root / "skills" / "ds-bootstrap" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("# ds-bootstrap", encoding="utf-8")

    manifest = build_manifest(
        tool="claude_code",
        scope="user",
        ds_version="test",
        files=[{"path": str(skill_md), "operation": "create", "content_hash": compute_hash(b"# ds-bootstrap")}],
    )
    write_manifest("claude_code", manifest, ds_home)

    result = doctor("claude_code", config_root, ds_home=ds_home)
    assert result["state"] == IntegrationState.INSTALLED_VERIFIED.value


def test_installed_drifted_when_hash_differs(tmp_path, ds_home):
    from integrations.manifest import build_manifest, write_manifest

    config_root = tmp_path / ".claude"
    config_root.mkdir()
    skill_md = config_root / "skills" / "ds-bootstrap" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("changed content", encoding="utf-8")

    manifest = build_manifest(
        tool="claude_code",
        scope="user",
        ds_version="test",
        files=[{"path": str(skill_md), "operation": "create", "content_hash": "abc123stale"}],
    )
    write_manifest("claude_code", manifest, ds_home)

    result = doctor("claude_code", config_root, ds_home=ds_home)
    assert result["state"] == IntegrationState.INSTALLED_DRIFTED.value
    assert result["drift"]


def test_broken_when_manifest_corrupt(tmp_path, ds_home):
    from integrations.manifest import get_manifest_path

    config_root = tmp_path / ".claude"
    config_root.mkdir()
    path = get_manifest_path("claude_code", ds_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"schema_version": "garbage"}', encoding="utf-8")

    result = doctor("claude_code", config_root, ds_home=ds_home)
    assert result["state"] == IntegrationState.BROKEN.value


def test_all_states_are_valid_enum_values():
    for state in IntegrationState:
        assert isinstance(state.value, str)
        assert state.value


def test_ingest_verified_when_processed_events_exist(tmp_path, ds_home, monkeypatch):
    from integrations.manifest import build_manifest, compute_hash, write_manifest

    config_root = tmp_path / ".claude"
    config_root.mkdir()
    skill_md = config_root / "skills" / "ds-bootstrap" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("# ds-bootstrap", encoding="utf-8")

    manifest = build_manifest(
        tool="claude_code",
        scope="user",
        ds_version="test",
        files=[{"path": str(skill_md), "operation": "create", "content_hash": compute_hash(b"# ds-bootstrap")}],
    )
    write_manifest("claude_code", manifest, ds_home)

    spool_root = tmp_path / "spool_root"
    processed = spool_root / "processed"
    processed.mkdir(parents=True)
    (processed / "evt-001.json").write_text('{"event_type":"test"}', encoding="utf-8")

    result = doctor("claude_code", config_root, ds_home=ds_home, spool_root=spool_root)
    assert result["state"] == IntegrationState.INGEST_VERIFIED.value
