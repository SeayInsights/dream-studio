from __future__ import annotations

import sqlite3
from pathlib import Path

from core.shared_intelligence.convergence import (
    adapter_surface_classification,
    independent_configuration_matrix,
    legacy_source_classification,
)
from projections.core.collectors.authority_sources import skill_usage_sql, token_usage_sql
from projections.core.collectors.skill_collector import SkillCollector
from projections.core.collectors.token_collector import TokenCollector


def test_independent_configuration_matrix_declares_projection_boundaries() -> None:
    matrix = independent_configuration_matrix()

    assert matrix["derived_view"] is True
    assert matrix["primary_authority"] is False
    areas = {area["area_id"]: area for area in matrix["areas"]}
    assert areas["adapter_profiles"]["canonical_source"] == "sqlite:adapter_authority_profiles"
    assert areas["adapter_profiles"]["approval_required"] is True
    assert "CLAUDE.md" in areas["adapter_profiles"]["projection_targets"]
    assert areas["context_packets"]["canonical_source"] == "sqlite:shared_context_packets"
    assert areas["dashboard_modules"]["lifecycle_status"] == "derived_projection"
    assert areas["docker_runtime_profiles"]["lifecycle_status"] == "optional_boundary"


def test_adapter_surface_classification_never_marks_sensitive_files_as_read(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    repo.mkdir()
    home.mkdir()
    (repo / "CLAUDE.md").write_text("projection", encoding="utf-8")
    (home / ".codex").mkdir()
    (home / ".codex" / "config.toml").write_text("secret = '<redacted>'", encoding="utf-8")

    surfaces = adapter_surface_classification(repo, home)

    repo_claude = next(item for item in surfaces if Path(item["path"]) == repo / "CLAUDE.md")
    codex_config = next(
        item for item in surfaces if Path(item["path"]) == home / ".codex" / "config.toml"
    )
    assert repo_claude["classification"] == "projection"
    assert codex_config["classification"] == "sensitive_manual_review"
    assert codex_config["secret_contents_read"] is False


def test_legacy_source_classification_keeps_raw_skill_under_manual_review() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE raw_skill_telemetry(id INTEGER)")
        conn.execute("CREATE TABLE skill_invocations(invocation_id TEXT)")
        conn.execute("INSERT INTO raw_skill_telemetry VALUES(1)")
        conn.execute("CREATE TABLE raw_token_usage(id INTEGER)")
        conn.execute("CREATE TABLE token_usage_records(token_usage_id TEXT)")
        conn.execute("CREATE TABLE pi_dependencies(project_id TEXT)")
        conn.execute("CREATE TABLE reg_projects(project_id TEXT)")

        rows = {item["source"]: item for item in legacy_source_classification(conn)}

        assert rows["raw_skill_telemetry"]["classification"] == "not_migrated_manual_review"
        assert rows["raw_token_usage"]["classification"] == "migrated_then_purge_source"
        assert rows["pi_dependencies:test_project"]["classification"] == "obsolete_purge"
    finally:
        conn.close()


def test_dashboard_collectors_read_current_authority_not_raw_tables(
    monkeypatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "current-authority.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE skill_invocations("
            "invocation_id TEXT PRIMARY KEY, project_id TEXT, milestone_id TEXT, task_id TEXT, "
            "process_run_id TEXT, event_id TEXT, skill_id TEXT NOT NULL, status TEXT NOT NULL, "
            "purpose TEXT, metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO skill_invocations(invocation_id, project_id, process_run_id, event_id, skill_id, status, metadata_json, created_at) "
            "VALUES('s1', 'dream-studio', 'run-1', 'event-1', 'ds-core', 'completed', "
            '\'{"execution_time_s": 12, "input_tokens": 10, "output_tokens": 4, "model": "gpt-test"}\', '
            "'2026-05-14T00:00:00Z')"
        )
        conn.execute(
            "CREATE TABLE token_usage_records("
            "token_usage_id TEXT PRIMARY KEY, project_id TEXT, milestone_id TEXT, task_id TEXT, process_run_id TEXT, "
            "agent_id TEXT, skill_id TEXT, workflow_id TEXT, hook_id TEXT, model_id TEXT, provider TEXT, "
            "input_tokens INTEGER, output_tokens INTEGER, cached_tokens INTEGER, total_tokens INTEGER, "
            "estimated_cost REAL, purpose TEXT, created_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO token_usage_records(token_usage_id, project_id, process_run_id, skill_id, model_id, provider, "
            "input_tokens, output_tokens, cached_tokens, total_tokens, estimated_cost, created_at) "
            "VALUES('t1', 'dream-studio', 'run-1', 'ds-core', 'gpt-test', 'openai', 10, 4, 0, 14, 0.01, "
            "'2026-05-14T00:00:00Z')"
        )
        conn.commit()
    finally:
        conn.close()

    from core.config.database import DB_PATH_ENV, DatabaseRuntime

    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    DatabaseRuntime.reset_instance()
    try:
        conn = sqlite3.connect(db_path)
        assert skill_usage_sql(conn) is not None
        assert token_usage_sql(conn) is not None
        conn.close()

        skills = SkillCollector(str(db_path)).collect(days=365)
        tokens = TokenCollector(str(db_path)).collect(days=365)

        assert skills["total_invocations"] == 1
        assert skills["by_skill"]["ds-core"]["success_rate"] == 100.0
        assert skills["source_status"]["source_tables"] == ["skill_invocations"]
        assert tokens["total_tokens"] == 14
        assert tokens["by_project"]["dream-studio"]["total_tokens"] == 14
        assert tokens["source_status"]["source_tables"] == ["token_usage_records"]
    finally:
        DatabaseRuntime.reset_instance()
