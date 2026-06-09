from __future__ import annotations

from pathlib import Path

from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import (
    EXPECTED_ADAPTER_IDS,
    adapter_alignment_summary,
    adapter_projection_policy,
    default_adapter_authority_profiles,
    register_default_adapter_authority_profiles,
)


def _db(tmp_path: Path) -> Path:
    return tmp_path / "adapter-alignment" / "studio.db"


def test_default_adapter_profiles_cover_supported_ai_surfaces() -> None:
    profiles = default_adapter_authority_profiles()
    by_id = {profile["adapter_id"]: profile for profile in profiles}

    assert set(by_id) == set(EXPECTED_ADAPTER_IDS)
    assert by_id["claude"]["adapter_type"] == "claude"
    assert by_id["codex"]["config_projection_path"] == "adapter-projections/codex/AGENTS.md"
    assert by_id["cursor"]["authority_role"] == "projection"
    assert by_id["copilot"]["stale_detection_policy"]["repair_requires_work_order"] is True
    assert by_id["chatgpt"]["supported_context_packets"]
    assert by_id["mcp"]["supported_result_types"]
    assert by_id["local-model"]["adapter_type"] == "local_model"
    assert by_id["shell"]["config_projection_path"].startswith("adapter-projections/")


def test_register_default_adapter_profiles_as_sqlite_projections(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        registration = register_default_adapter_authority_profiles(conn)
        summary = adapter_alignment_summary(conn)

    assert registration["adapter_count"] == len(EXPECTED_ADAPTER_IDS)
    assert registration["adapter_configs_mutated"] is False
    assert registration["live_db_mutated"] is False
    assert summary["derived_view"] is True
    assert summary["primary_authority"] is False
    assert summary["routing_authority"] is False
    assert summary["missing_adapter_ids"] == []
    assert summary["authority_violations"] == []
    assert summary["unsupported_projection_paths"] == []
    assert summary["all_adapters_are_projections"] is True
    assert all(profile["owns_source_of_truth"] == 0 for profile in summary["profiles"])


def test_adapter_alignment_detects_missing_and_authority_violations(tmp_path: Path) -> None:
    profiles = default_adapter_authority_profiles()[:2]
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn, profiles)
        conn.execute("""
            UPDATE adapter_authority_profiles
            SET authority_role = 'executor',
                config_projection_path = 'CLAUDE.md'
            WHERE adapter_id = 'claude'
            """)
        summary = adapter_alignment_summary(conn)

    assert "cursor" in summary["missing_adapter_ids"]
    assert summary["authority_violations"] == ["claude"]
    assert summary["unsupported_projection_paths"] == ["claude"]
    assert summary["all_adapters_are_projections"] is False


def test_adapter_projection_policy_forbids_config_writes_without_future_approval() -> None:
    policy = adapter_projection_policy()

    assert policy["source_authority"] == "sqlite"
    assert policy["adapter_owns_source_of_truth"] is False
    assert policy["configs_are_generated_projections"] is True
    assert policy["config_mutation_authorized"] is False
    assert policy["requires_future_explicit_approval_for_config_writes"] is True


def test_adapter_alignment_uses_temp_db_not_live_db(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    with _connect(db_path) as conn:
        register_default_adapter_authority_profiles(conn)

    assert db_path.is_file()
    assert db_path != live_db
