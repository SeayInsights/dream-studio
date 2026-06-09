"""Reconcile installed-state evidence without repeating broad inventory."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

INSTALLED_STATE_PATH = Path.home() / ".dream-studio"
LIVE_DB_PATH = INSTALLED_STATE_PATH / "state" / "studio.db"
META_ROOT = INSTALLED_STATE_PATH / "meta"


@dataclass(frozen=True)
class EvidenceSource:
    path: str
    category: str
    summary: str
    present: bool = True


DEFAULT_EVIDENCE_SOURCES: tuple[EvidenceSource, ...] = (
    EvidenceSource(
        "runtime/manifests/*.json",
        "topology_manifests",
        "Requested runtime topology manifests. They may be absent; prior reports can still answer many inventory questions.",
        present=False,
    ),
    EvidenceSource(
        str(META_ROOT / "audit" / "2026-05-13-current-state-telemetry-integration-audit-report.md"),
        "telemetry_runtime_audit",
        "Audits runtime integration coverage and identifies emitter/read-model gaps.",
    ),
    EvidenceSource(
        str(
            META_ROOT
            / "work-orders"
            / "wo-dream-studio-current-state-telemetry-integration-audit"
            / "evidence"
            / "telemetry_integration_matrix.yaml"
        ),
        "integration_matrix",
        "Maps agents, skills, workflows, hooks, tools, tokens, security, validations, research, decisions, artifacts, outcomes, routes, attention, and Docker module profiles.",
    ),
    EvidenceSource(
        str(
            META_ROOT
            / "work-orders"
            / "wo-dream-studio-execution-telemetry-traceability-spine"
            / "evidence"
            / "database_evidence.yaml"
        ),
        "database_authority",
        "Records migration 037 schema fingerprints, table counts, backup, rehearsal, and live validation.",
    ),
    EvidenceSource(
        str(
            META_ROOT
            / "work-orders"
            / "wo-dream-studio-dashboard-read-models-telemetry-spine"
            / "evidence"
            / "read_model_evidence.yaml"
        ),
        "dashboard_read_models",
        "Confirms derived dashboard read models and live read-only row counts.",
    ),
    EvidenceSource(
        str(
            META_ROOT
            / "work-orders"
            / "wo-dream-studio-validation-security-telemetry-emitters"
            / "evidence"
            / "security_bridge_evidence.yaml"
        ),
        "security_bridge",
        "Defines bounded security bridge and idempotency/file-line support.",
    ),
    EvidenceSource(
        str(
            META_ROOT
            / "work-orders"
            / "wo-dream-studio-workflow-research-decision-telemetry-emitters"
            / "evidence"
            / "research_decision_bridge_evidence.yaml"
        ),
        "research_decision_bridge",
        "Defines research and decision bridge source paths, telemetry targets, and idempotency strategy.",
    ),
    EvidenceSource(
        str(
            META_ROOT
            / "audit"
            / "2026-05-13-install-bootstrap-sqlite-authority-separation-report.md"
        ),
        "install_bootstrap",
        "Separates installable repo bootstrap from the operator live installed state.",
    ),
)


QUESTION_COVERAGE: tuple[dict[str, Any], ...] = (
    {
        "question": "installed_state_inventory_from_topology_manifests",
        "answered_by": ["telemetry_runtime_audit", "integration_matrix"],
        "status": "partial",
        "finding": "Named topology manifests were not found, but the telemetry matrix and reports cover major runtime domains.",
        "gap": "No current generated filesystem/topology manifest snapshot was found in the expected runtime/manifests path.",
    },
    {
        "question": "sqlite_schema_row_count_migration",
        "answered_by": ["database_authority", "install_bootstrap", "dashboard_read_models"],
        "status": "answered",
        "finding": "Migration 037, schema version, table counts, fingerprints, and live read-only row-count samples are already documented.",
        "gap": None,
    },
    {
        "question": "dashboard_api_runtime_dependencies",
        "answered_by": ["dashboard_read_models", "telemetry_runtime_audit"],
        "status": "partial",
        "finding": "Read models exist as derived views; dashboard/API integration was explicitly deferred.",
        "gap": "Actual dashboard surface wiring to read models remains a future bounded integration task.",
    },
    {
        "question": "security_state_file_line",
        "answered_by": ["security_bridge", "integration_matrix"],
        "status": "answered",
        "finding": "Security telemetry supports file/line/severity/status and idempotent bridge behavior.",
        "gap": "SARIF import route remains deferred, not required for this reconciliation.",
    },
    {
        "question": "artifact_file_folder_classification",
        "answered_by": ["integration_matrix", "dashboard_read_models"],
        "status": "partial",
        "finding": "Artifact records and projection/read-model contracts identify artifact authority roles.",
        "gap": "No current filesystem topology manifest was present for exhaustive folder cleanup classification.",
    },
    {
        "question": "relationship_lineage",
        "answered_by": ["database_authority", "integration_matrix"],
        "status": "partial",
        "finding": "Telemetry tables and canonical authority tables define major relationships and source/evidence refs.",
        "gap": "Lineage across old file-backed artifacts needs rehearsal mapping, not new broad inventory.",
    },
    {
        "question": "execution_process_workflow",
        "answered_by": ["integration_matrix", "research_decision_bridge"],
        "status": "answered",
        "finding": "Execution, workflow, research, and decision bridge evidence identifies paths and telemetry targets.",
        "gap": None,
    },
    {
        "question": "rehydration_mappings",
        "answered_by": ["database_authority", "dashboard_read_models", "integration_matrix"],
        "status": "answered",
        "finding": "Canonical authority tables and telemetry spine tables imply the target mapping domains.",
        "gap": None,
    },
    {
        "question": "cleanup_candidates",
        "answered_by": ["install_bootstrap", "dashboard_read_models", "integration_matrix"],
        "status": "partial",
        "finding": "Derived/dashboard state and legacy/raw surfaces can be classified as keep, rehydrate, archive candidate, dedupe candidate, or manual review.",
        "gap": "No cleanup execution is approved; manifest remains draft only.",
    },
)


def reconcile_existing_evidence(
    *,
    evidence_sources: Sequence[EvidenceSource] = DEFAULT_EVIDENCE_SOURCES,
) -> dict[str, Any]:
    """Return a conservative reconciliation from known evidence categories."""

    sources = [
        {
            "path": source.path,
            "category": source.category,
            "summary": source.summary,
            "present": source.present,
        }
        for source in evidence_sources
    ]
    gaps = [
        {
            "question": item["question"],
            "gap": item["gap"],
            "status": item["status"],
        }
        for item in QUESTION_COVERAGE
        if item.get("gap")
    ]
    return {
        "artifact_type": "existing_evidence_reconciliation",
        "broad_inventory_repeated": False,
        "reason_broad_inventory_not_repeated": "Prior database, telemetry, dashboard, and bridge evidence already answers the core rehydration questions; missing topology manifests are recorded as gaps.",
        "installed_state_path": str(INSTALLED_STATE_PATH),
        "live_db_path": str(LIVE_DB_PATH),
        "evidence_sources": sources,
        "question_coverage": list(QUESTION_COVERAGE),
        "remaining_gaps": gaps,
        "live_state_mutation_allowed": False,
        "live_db_mutation_allowed": False,
    }


def validate_evidence_reconciliation(document: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if document.get("broad_inventory_repeated") is not False:
        errors.append("broad inventory must not be repeated")
    if document.get("live_state_mutation_allowed") is not False:
        errors.append("live state mutation must be forbidden")
    if document.get("live_db_mutation_allowed") is not False:
        errors.append("live DB mutation must be forbidden")
    if not document.get("question_coverage"):
        errors.append("question coverage is required")
    return errors
