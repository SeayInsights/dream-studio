"""Shared-authority convergence planning helpers.

These helpers are deliberately declarative. They define what Dream Studio owns,
what adapter files are projections, and which legacy sources can be purged only
after migration/reference checks have proved the current authority is complete.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.shared_intelligence.lineage_cleanup import raw_skill_telemetry_status


@dataclass(frozen=True)
class ConfigurationArea:
    area_id: str
    canonical_source: str
    projection_targets: tuple[str, ...]
    owner: str
    lifecycle_status: str
    validation_requirements: tuple[str, ...]
    storage_class: str
    approval_required: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "area_id": self.area_id,
            "canonical_source": self.canonical_source,
            "projection_targets": list(self.projection_targets),
            "owner": self.owner,
            "lifecycle_status": self.lifecycle_status,
            "validation_requirements": list(self.validation_requirements),
            "storage_class": self.storage_class,
            "approval_required": self.approval_required,
        }


def independent_configuration_matrix() -> dict[str, Any]:
    """Return the configuration ownership matrix for adapters and modules."""

    areas = [
        ConfigurationArea(
            "adapter_profiles",
            "sqlite:adapter_authority_profiles",
            ("CLAUDE.md", "AGENTS.md", "Cursor rules", "Copilot instructions"),
            "Dream Studio",
            "canonical",
            ("profiles_exist", "owns_source_of_truth_false", "projection_paths_recorded"),
            "repo_tracked_plus_local_projection",
            True,
        ),
        ConfigurationArea(
            "model_provider_profiles",
            "sqlite:model_provider_profiles",
            ("dashboard model cards", "capability routing", "adapter context packets"),
            "Dream Studio",
            "canonical",
            ("provider_model_unique", "capability_tags_present", "no_secret_values"),
            "local_sqlite",
            True,
        ),
        ConfigurationArea(
            "context_packets",
            "sqlite:shared_context_packets",
            ("Claude packet", "Codex packet", "ChatGPT packet", "MCP packet"),
            "Dream Studio",
            "canonical",
            ("source_authority_sqlite", "model_private_memory_required_false"),
            "local_sqlite_with_exportable_packets",
            False,
        ),
        ConfigurationArea(
            "adapter_results",
            "sqlite:adapter_result_records",
            ("dashboard shared intelligence", "learning feedback", "audit exports"),
            "Dream Studio",
            "canonical",
            ("normalized_status_present", "adapter_id_registered", "evidence_refs_present"),
            "local_sqlite",
            False,
        ),
        ConfigurationArea(
            "skills_workflows_hooks",
            "repo source plus sqlite telemetry/hardening records",
            ("adapter projections", "dashboard component analytics"),
            "Dream Studio",
            "canonical_with_runtime_facts",
            ("source_registry_exists", "telemetry_facts_exist", "hardening_candidates_versioned"),
            "repo_tracked_and_local_sqlite",
            True,
        ),
        ConfigurationArea(
            "dashboard_modules",
            "repo read models plus sqlite telemetry authority",
            ("frontend dashboard", "API responses"),
            "Dream Studio",
            "derived_projection",
            ("derived_view_true", "primary_authority_false", "source_tables_present"),
            "repo_tracked",
            False,
        ),
        ConfigurationArea(
            "docker_runtime_profiles",
            "docs/operations/docker-module-profiles.md plus future module registry fields",
            ("optional scanners", "workers", "adapters", "validation sandboxes"),
            "Dream Studio",
            "optional_boundary",
            ("docker_not_required", "single_sqlite_authority_path", "no_competing_db"),
            "repo_tracked_docs",
            True,
        ),
        ConfigurationArea(
            "local_db_path",
            "core.config.database canonical resolver",
            ("DREAM_STUDIO_DB_PATH override", "dashboard/API runtime", "tests"),
            "Dream Studio",
            "canonical_runtime_config",
            ("no_hardcoded_operator_path", "injected_db_supported", "canonical_default_supported"),
            "repo_tracked_code_plus_local_runtime",
            True,
        ),
        ConfigurationArea(
            "approval_policies",
            "sqlite/file-backed approval and operator decision records",
            ("dashboard attention", "route decisions", "work orders"),
            "Dream Studio",
            "canonical",
            ("operator_boundary_recorded", "route_state_recorded", "evidence_refs_present"),
            "local_sqlite_plus_human_exports",
            True,
        ),
        ConfigurationArea(
            "external_project_boundaries",
            "project registry and paused target records",
            ("dashboard project cards", "validation profiles", "work orders"),
            "Dream Studio",
            "canonical",
            ("project_scope_present", "paused_target_rules_present", "no_unapproved_mutation"),
            "local_sqlite_plus_repo_docs",
            True,
        ),
    ]
    return {
        "model_name": "independent_configuration_matrix",
        "derived_view": True,
        "primary_authority": False,
        "areas": [area.as_dict() for area in areas],
    }


def adapter_surface_classification(
    repo_path: Path, home_path: Path | None = None
) -> list[dict[str, Any]]:
    """Classify known adapter config surfaces without reading secret stores."""

    home = home_path or Path.home()
    surfaces = [
        (repo_path / "CLAUDE.md", "claude", "projection"),
        (repo_path / "AGENTS.md", "codex", "projection"),
        (repo_path / ".claude" / "settings.json", "claude", "projection"),
        (repo_path / "hooks" / "hooks.json", "adapter_hooks", "current_authority_keep"),
        (home / ".claude" / "CLAUDE.md", "claude", "projection"),
        (home / ".claude" / "settings.json", "claude", "projection"),
        (home / ".claude" / ".credentials.json", "claude", "sensitive_manual_review"),
        (home / ".codex" / "AGENTS.md", "codex", "projection"),
        (home / ".codex" / "hooks.json", "codex", "projection"),
        (home / ".codex" / "config.toml", "codex", "sensitive_manual_review"),
        (home / ".codex" / "auth.json", "codex", "sensitive_manual_review"),
    ]
    return [
        {
            "path": str(path),
            "adapter": adapter,
            "classification": classification if path.exists() else "missing_projection_target",
            "exists": path.exists(),
            "source_evidence": "path_metadata_only",
            "secret_contents_read": False,
            "human_approval_required": classification == "sensitive_manual_review",
        }
        for path, adapter, classification in surfaces
    ]


def legacy_source_classification(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Classify legacy tables and purge readiness from current SQLite metadata."""

    rows: list[dict[str, Any]] = []
    raw_skill_status = raw_skill_telemetry_status(conn)
    for source, target, classification in (
        ("raw_skill_telemetry", "skill_invocations", raw_skill_status["classification"]),
        ("raw_token_usage", "token_usage_records", "migrated_then_purge_source"),
        ("pi_dependencies:test_project", "pi_dependencies", "obsolete_purge"),
        ("reg_projects:is_temp", "reg_projects", "obsolete_purge"),
        (
            "_backup_037_reg_projects",
            "_backup_037_reg_projects",
            "rollback_backup_keep_until_final_cleanup_approval",
        ),
    ):
        source_table = source.split(":", 1)[0]
        target_table = target.split(":", 1)[0]
        rows.append(
            {
                "source": source,
                "target": target,
                "classification": classification,
                "source_rows": _count(conn, source_table),
                "target_rows": _count(conn, target_table),
                "migration_status": raw_skill_status if source == "raw_skill_telemetry" else None,
                "delete_requires": (
                    [
                        "fresh_backup",
                        "migration_proof",
                        "reference_check",
                        "dashboard_route_validation",
                    ]
                    if classification in {"migrated_then_purge_source", "obsolete_purge"}
                    else ["manual_review"]
                ),
            }
        )
    return rows


def _count(conn: sqlite3.Connection, table: str) -> int:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table,),
    ).fetchone()
    if exists is None:
        return 0
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] or 0)
