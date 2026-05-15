"""Long-run local dogfood stability evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

REQUIRED_MULTISESSION_CYCLES = (
    "dashboard_authority_inspection",
    "local_dogfood_route",
    "release_gate",
    "installed_command_surface",
    "contract_atlas_docs_drift",
    "security_readiness_classification",
    "adapter_router_status",
    "analytics_only_profile",
)


def evaluate_local_dogfood_stability(
    sessions: Sequence[Mapping[str, Any]],
    *,
    min_sessions: int = 2,
) -> dict[str, Any]:
    """Evaluate dogfood stability from structured session summaries."""

    issues: list[str] = []
    if len(sessions) < min_sessions:
        issues.append("insufficient_session_count")
    for index, session in enumerate(sessions):
        prefix = f"session_{index}"
        if _truthy(session.get("prompt_chaining_detected")):
            issues.append(f"{prefix}_prompt_chaining_detected")
        if _truthy(session.get("hidden_mutation_detected")):
            issues.append(f"{prefix}_hidden_mutation_detected")
        if _truthy(session.get("dashboard_authority_drift_detected")):
            issues.append(f"{prefix}_dashboard_authority_drift_detected")
        if _truthy(session.get("evidence_sprawl_detected")):
            issues.append(f"{prefix}_evidence_sprawl_detected")
        if not _truthy(session.get("validation_passed")):
            issues.append(f"{prefix}_validation_not_passed")
        if not session.get("evidence_refs"):
            issues.append(f"{prefix}_missing_evidence_refs")
    return {
        "evaluation": "local_dogfood_long_run_stability",
        "derived_view": True,
        "primary_authority": False,
        "session_count": len(sessions),
        "stable": not issues,
        "issues": issues,
        "summary": {
            "prompt_chaining_regressions": sum(
                1 for session in sessions if _truthy(session.get("prompt_chaining_detected"))
            ),
            "hidden_mutation_events": sum(
                1 for session in sessions if _truthy(session.get("hidden_mutation_detected"))
            ),
            "dashboard_authority_drift_events": sum(
                1
                for session in sessions
                if _truthy(session.get("dashboard_authority_drift_detected"))
            ),
            "evidence_sprawl_events": sum(
                1 for session in sessions if _truthy(session.get("evidence_sprawl_detected"))
            ),
            "validation_passed_count": sum(
                1 for session in sessions if _truthy(session.get("validation_passed"))
            ),
        },
    }


def build_long_run_multisession_operational_validation(
    cycles: Sequence[Mapping[str, Any]],
    *,
    sqlite_hash_before: str | None = None,
    sqlite_hash_after: str | None = None,
) -> dict[str, Any]:
    """Build the final long-run operational validation closeout.

    The function consumes already-captured evidence summaries. It does not run
    release gates, start dashboards, inspect adapters, mutate SQLite, run Docker,
    or scan external repositories.
    """

    normalized = [_normalize_cycle(cycle) for cycle in cycles]
    present = {cycle["cycle_id"] for cycle in normalized}
    missing = sorted(set(REQUIRED_MULTISESSION_CYCLES) - present)
    failures: list[str] = []
    if missing:
        failures.append("missing_required_cycles")
    if sqlite_hash_before and sqlite_hash_after and sqlite_hash_before != sqlite_hash_after:
        failures.append("live_sqlite_hash_changed")
    for cycle in normalized:
        if cycle["status"] != "pass":
            failures.append(f"{cycle['cycle_id']}_not_passed")
        if not cycle["evidence_refs"]:
            failures.append(f"{cycle['cycle_id']}_missing_evidence_refs")
        if cycle["external_project_mutation"]:
            failures.append(f"{cycle['cycle_id']}_external_project_mutation")
        if cycle["docker_executed"]:
            failures.append(f"{cycle['cycle_id']}_docker_executed_without_approval")
        if cycle["live_sqlite_mutated_unintentionally"]:
            failures.append(f"{cycle['cycle_id']}_unintended_sqlite_mutation")
        if cycle["synthetic_data_leaked"]:
            failures.append(f"{cycle['cycle_id']}_synthetic_data_leaked")

    return {
        "model_name": "dream_studio_long_run_multisession_operational_validation",
        "derived_view": True,
        "primary_authority": False,
        "db_write_authorized": False,
        "required_cycles": list(REQUIRED_MULTISESSION_CYCLES),
        "cycle_count": len(normalized),
        "cycles": normalized,
        "sqlite_hash_before": sqlite_hash_before,
        "sqlite_hash_after": sqlite_hash_after,
        "live_sqlite_hash_unchanged": bool(
            sqlite_hash_before and sqlite_hash_after and sqlite_hash_before == sqlite_hash_after
        ),
        "external_projects_remained_paused": not any(
            cycle["external_project_mutation"] for cycle in normalized
        ),
        "docker_not_executed": not any(cycle["docker_executed"] for cycle in normalized),
        "failures": sorted(dict.fromkeys(failures)),
        "status": "pass" if not failures else "fail",
        "verdict": (
            "LONG_RUN_MULTISESSION_OPERATIONAL_VALIDATION_COMPLETE"
            if not failures
            else "LONG_RUN_MULTISESSION_OPERATIONAL_VALIDATION_BLOCKED"
        ),
    }


def validate_long_run_multisession_report(report: Mapping[str, Any]) -> list[str]:
    """Return invariant violations for a multisession validation report."""

    issues: list[str] = []
    if report.get("derived_view") is not True:
        issues.append("report_must_be_derived_view")
    if report.get("primary_authority") is not False:
        issues.append("report_must_not_be_primary_authority")
    if report.get("db_write_authorized") is not False:
        issues.append("db_write_must_not_be_authorized")
    if report.get("status") == "pass" and report.get("failures"):
        issues.append("pass_report_must_not_have_failures")
    if report.get("status") == "pass" and not _truthy(report.get("live_sqlite_hash_unchanged")):
        issues.append("pass_report_requires_live_sqlite_hash_guard")
    if not report.get("cycles"):
        issues.append("cycles_required")
    return issues


def _normalize_cycle(cycle: Mapping[str, Any]) -> dict[str, Any]:
    cycle_id = str(cycle.get("cycle_id") or cycle.get("id") or "unknown").strip()
    return {
        "cycle_id": cycle_id,
        "status": str(cycle.get("status") or "unknown").strip().lower(),
        "evidence_refs": [str(item) for item in cycle.get("evidence_refs") or []],
        "external_project_mutation": _truthy(cycle.get("external_project_mutation")),
        "docker_executed": _truthy(cycle.get("docker_executed")),
        "live_sqlite_mutated_unintentionally": _truthy(
            cycle.get("live_sqlite_mutated_unintentionally")
        ),
        "synthetic_data_leaked": _truthy(cycle.get("synthetic_data_leaked")),
        "notes": str(cycle.get("notes") or "").strip(),
    }


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "present", "passed"}
    return bool(value)
