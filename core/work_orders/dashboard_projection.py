"""File-backed dashboard projection snapshots for Work Order intelligence.

This module builds display-only read models from caller-provided artifact roots.
It does not inspect target repositories, open the runtime database, or write
projection state.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from compat import UTC

NON_AUTHORITY_NOTICE = (
    "Dashboard projections are read-only views over file-backed artifacts. "
    "They must not run scans, approve risk, mutate repos, stage, commit, push, "
    "or replace Work Order reports, operator decisions, Security Review "
    "reports, eval artifacts, or Handoff Packets."
)

SNAPSHOT_SCHEMA_VERSION = "dashboard_projection_model.v0"


def build_dashboard_projection_snapshot(
    *,
    work_order_root: Path | str,
    audit_root: Path | str | None = None,
    projection_id: str = "dashboard.projection.work_orders",
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a display-only dashboard snapshot from file-backed artifacts."""
    root = Path(work_order_root)
    audit = Path(audit_root) if audit_root is not None else None
    refs: list[str] = []
    stale_or_missing: list[dict[str, str]] = []

    snapshot: dict[str, Any] = {
        "artifact_kind": "DashboardProjectionSnapshot",
        "artifact_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "projection_id": projection_id,
        "generated_at": generated_at or _now(),
        "source_artifact_refs": refs,
        "projection_scope": {
            "target_repo_access": "not_authorized",
            "scan_execution": "not_authorized",
            "dashboard_runtime": "not_authorized",
        },
        "non_authority_notice": NON_AUTHORITY_NOTICE,
        "stale_or_missing_evidence": stale_or_missing,
        "work_orders": [],
        "evals": [],
        "approvals_and_operator_decisions": [],
        "security_reviews": [],
    }

    if not root.is_dir():
        stale_or_missing.append(
            _gap(str(root), "missing", "Work Order root is missing or is not a directory.")
        )
        return snapshot

    if audit is not None:
        if audit.is_dir():
            refs.append(str(audit))
        else:
            stale_or_missing.append(
                _gap(str(audit), "missing", "Audit root is missing or is not a directory.")
            )

    for work_order_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        _append_work_order_projection(
            work_order_dir=work_order_dir,
            snapshot=snapshot,
            refs=refs,
            stale_or_missing=stale_or_missing,
        )

    snapshot["source_artifact_refs"] = sorted(dict.fromkeys(refs))
    return snapshot


def _append_work_order_projection(
    *,
    work_order_dir: Path,
    snapshot: dict[str, Any],
    refs: list[str],
    stale_or_missing: list[dict[str, str]],
) -> None:
    work_order_id = work_order_dir.name
    work_order, work_order_ref = _load_first_mapping(
        [
            work_order_dir / "work_order.json",
            work_order_dir / "work_order.yaml",
            work_order_dir / "work_order.yml",
        ],
        stale_or_missing=stale_or_missing,
        required=False,
        missing_impact="Canonical Work Order artifact is unavailable; projection will use sidecar artifacts where possible.",
    )
    if work_order_ref:
        refs.append(str(work_order_ref))

    approval, approval_ref, approval_status = _load_approval(
        work_order_dir, stale_or_missing=stale_or_missing
    )
    if approval_ref:
        refs.append(str(approval_ref))

    report_ref = _first_existing([work_order_dir / "report.md"])
    if report_ref:
        refs.append(str(report_ref))
    else:
        stale_or_missing.append(
            _gap(str(work_order_dir / "report.md"), "missing", "Work Order report is missing.")
        )

    rendered_refs = sorted((work_order_dir / "rendered").glob("*.md"))
    handoff_ref = str(rendered_refs[-1]) if rendered_refs else "missing"
    refs.extend(str(path) for path in rendered_refs)

    sidecar = _load_sidecar_summary(work_order_dir, refs, stale_or_missing)
    final_decision = _first_text(
        sidecar.get("decision"),
        sidecar.get("final_decision"),
        sidecar.get("verdict"),
        work_order.get("decision"),
        work_order.get("final_decision"),
    )
    phase_name = _first_text(
        sidecar.get("phase"),
        sidecar.get("phase_name"),
        work_order.get("phase"),
        work_order.get("phase_name"),
        _report_heading(report_ref),
        work_order_id,
    )

    blocking_risks = _blocking_risks(
        work_order_dir, sidecar, approval_status, report_ref, rendered_refs
    )
    snapshot["work_orders"].append(
        {
            "work_order_id": work_order_id,
            "phase_name": phase_name,
            "approval_mode": _first_text(
                work_order.get("approval_mode"),
                approval.get("approval_mode"),
                "unknown",
            ),
            "risk_level": _first_text(
                work_order.get("risk_level"), approval.get("risk_level"), "unknown"
            ),
            "readiness": _first_text(sidecar.get("readiness"), work_order.get("status"), "unknown"),
            "verdict": _first_text(sidecar.get("verdict"), sidecar.get("decision"), "unknown"),
            "final_decision": final_decision,
            "next_action": _first_text(
                sidecar.get("next_phase_recommendation"),
                sidecar.get("next_work_order_recommendation"),
                sidecar.get("next_bill_stack_recommended_phase"),
                "unknown",
            ),
            "report_ref": str(report_ref) if report_ref else "missing",
            "handoff_ref": handoff_ref,
            "blocking_risks": blocking_risks,
        }
    )

    snapshot["approvals_and_operator_decisions"].append(
        _approval_decision_projection(work_order_dir, approval_status, approval_ref)
    )
    snapshot["evals"].extend(_eval_projections(work_order_dir, refs, stale_or_missing))
    snapshot["security_reviews"].extend(
        _security_review_projections(work_order_dir, refs, stale_or_missing)
    )


def _load_sidecar_summary(
    work_order_dir: Path,
    refs: list[str],
    stale_or_missing: list[dict[str, str]],
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    candidates = [
        *sorted(work_order_dir.glob("**/*evidence*.yaml")),
        *sorted(work_order_dir.glob("**/*evidence*.yml")),
        *sorted(work_order_dir.glob("**/*plan*.yaml")),
        *sorted(work_order_dir.glob("**/*plan*.yml")),
        *sorted(work_order_dir.glob("**/*review*.yaml")),
        *sorted(work_order_dir.glob("**/*review*.yml")),
        *sorted(work_order_dir.glob("**/*continuity*.yaml")),
        *sorted(work_order_dir.glob("**/*continuity*.yml")),
    ]
    for path in candidates:
        data = _load_mapping(path, stale_or_missing=stale_or_missing, required=False)
        if data is None:
            continue
        refs.append(str(path))
        _merge_known_summary_fields(summary, data)
    return summary


def _merge_known_summary_fields(summary: dict[str, Any], data: dict[str, Any]) -> None:
    for key in (
        "phase",
        "phase_name",
        "decision",
        "final_decision",
        "verdict",
        "readiness",
        "next_phase_recommendation",
        "next_work_order_recommendation",
        "next_bill_stack_recommended_phase",
        "release_gate",
        "current_release_gate",
        "recommended_release_gate",
        "validation_results",
        "validation_interpretation",
        "forbidden_actions_observed",
    ):
        if key in data and key not in summary:
            summary[key] = data[key]


def _eval_projections(
    work_order_dir: Path,
    refs: list[str],
    stale_or_missing: list[dict[str, str]],
) -> list[dict[str, Any]]:
    eval_dir = work_order_dir / "evals"
    if not eval_dir.is_dir():
        stale_or_missing.append(
            _gap(str(eval_dir), "missing", "Eval directory is missing; eval status is unknown.")
        )
        return []

    projections: list[dict[str, Any]] = []
    for path in sorted(eval_dir.glob("*.json")):
        data = _load_mapping(path, stale_or_missing=stale_or_missing, required=False)
        refs.append(str(path))
        if data is None:
            projections.append(
                {
                    "eval_artifact_ref": str(path),
                    "eval_type": path.stem,
                    "pass_fail": "incomplete",
                    "score": "not_applicable",
                    "evidence_refs": [str(path)],
                    "blocking": true_bool(True),
                    "limitations": ["Eval artifact could not be parsed."],
                }
            )
            continue
        pass_fail = _first_text(data.get("pass_fail"), "unknown")
        projections.append(
            {
                "eval_artifact_ref": str(path),
                "eval_type": _first_text(data.get("eval_type"), path.stem),
                "pass_fail": pass_fail,
                "score": data.get("score", "not_applicable"),
                "evidence_refs": _as_string_list(data.get("evidence")) or [str(path)],
                "blocking": pass_fail in {"fail", "incomplete"},
                "limitations": _limitations_from_eval(data),
            }
        )
    return projections


def _approval_decision_projection(
    work_order_dir: Path,
    approval_status: str,
    approval_ref: Path | None,
) -> dict[str, Any]:
    decision_ref = _first_existing(
        [
            work_order_dir / "operator_decision.json",
            work_order_dir / "decisions" / "operator_decision.json",
            work_order_dir / "decisions" / "decision.json",
        ]
    )
    selected_decision = "none"
    reason_present = False
    if decision_ref:
        decision = _load_mapping(decision_ref, stale_or_missing=[], required=False) or {}
        selected_decision = _first_text(
            decision.get("selected_decision"),
            decision.get("decision"),
            decision.get("recommended_decision"),
            "none",
        )
        reason_present = bool(_first_text(decision.get("reason"), decision.get("rationale"), ""))

    return {
        "approval_artifact_ref": str(approval_ref) if approval_ref else "not_applicable",
        "approval_status": approval_status,
        "operator_decision_ref": str(decision_ref) if decision_ref else "not_applicable",
        "selected_decision": selected_decision,
        "reason_required": approval_status == "present",
        "reason_present": reason_present,
        "execution_allowed": approval_status == "present",
    }


def _security_review_projections(
    work_order_dir: Path,
    refs: list[str],
    stale_or_missing: list[dict[str, str]],
) -> list[dict[str, Any]]:
    security_dir = work_order_dir / "security"
    report_paths = sorted(security_dir.glob("**/review_report.yaml")) + sorted(
        security_dir.glob("**/review_report.yml")
    )
    release_paths = sorted(security_dir.glob("**/release_gate*.yaml")) + sorted(
        security_dir.glob("**/release_gate*.yml")
    )
    if not report_paths and not release_paths:
        return []

    report_path = report_paths[-1] if report_paths else None
    release_path = release_paths[-1] if release_paths else None
    report = (
        _load_mapping(report_path, stale_or_missing=stale_or_missing, required=False)
        if report_path
        else {}
    )
    release = (
        _load_mapping(release_path, stale_or_missing=stale_or_missing, required=False)
        if release_path
        else {}
    )
    if report_path:
        refs.append(str(report_path))
    if release_path:
        refs.append(str(release_path))

    finding_paths = sorted((security_dir / "findings").glob("*.yaml")) + sorted(
        (security_dir / "findings").glob("*.yml")
    )
    refs.extend(str(path) for path in finding_paths)
    finding_records = [
        data
        for path in finding_paths
        if (data := _load_mapping(path, stale_or_missing=stale_or_missing, required=False))
    ]

    return [
        {
            "security_review_report_ref": str(report_path) if report_path else "missing",
            "target_id": _first_text(
                report.get("target_id"), report.get("target_repo_path"), "not_applicable"
            ),
            "security_pack_id": _first_text(
                report.get("security_pack_id"), "security_review_profile_pack"
            ),
            "verdict": _first_text(report.get("decision"), report.get("verdict"), "unknown"),
            "release_gate_decision": _first_text(
                release.get("recommended_release_gate"),
                release.get("release_gate"),
                release.get("current_release_gate"),
                report.get("release_gate_recommendation"),
                "unknown",
            ),
            "taxonomy_coverage": report.get("taxonomy_coverage", {}),
            "scan_status_counts": report.get("scan_status_counts", {}),
            "findings_by_severity": _count_by(finding_records, "severity"),
            "findings_by_release_impact": _count_by(finding_records, "release_gate_impact"),
            "blocking_findings": [
                _first_text(item.get("finding_id"), item.get("id"), "unknown")
                for item in finding_records
                if _first_text(item.get("release_gate_impact"), item.get("release_impact"), "")
                in {"block_release", "release_blocking", "REMEDIATE_BEFORE_RELEASE"}
            ],
            "accepted_risks": report.get("accepted_risks", []),
            "deferred_scans": report.get("deferred_scans", []),
            "evidence_inventory_refs": _as_string_list(report.get("evidence_refs")),
            "next_work_order_recommendation": _first_text(
                report.get("next_phase_recommendation"),
                release.get("next_phase_recommendation"),
                "unknown",
            ),
        }
    ]


def _load_approval(
    work_order_dir: Path,
    *,
    stale_or_missing: list[dict[str, str]],
) -> tuple[dict[str, Any], Path | None, str]:
    path = work_order_dir / "approvals" / "approval.json"
    if not path.is_file():
        stale_or_missing.append(
            _gap(str(path), "missing", "Approval artifact is missing; execution is not allowed.")
        )
        return {}, None, "missing"
    data = _load_mapping(path, stale_or_missing=stale_or_missing, required=False)
    if data is None:
        return {}, path, "invalid"
    return data, path, "present"


def _load_first_mapping(
    paths: list[Path],
    *,
    stale_or_missing: list[dict[str, str]],
    required: bool,
    missing_impact: str,
) -> tuple[dict[str, Any], Path | None]:
    for path in paths:
        if path.is_file():
            return (
                _load_mapping(path, stale_or_missing=stale_or_missing, required=required) or {},
                path,
            )
    if required:
        stale_or_missing.append(_gap(str(paths[0]), "missing", missing_impact))
    return {}, None


def _load_mapping(
    path: Path | None,
    *,
    stale_or_missing: list[dict[str, str]],
    required: bool,
) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        if required and path is not None:
            stale_or_missing.append(_gap(str(path), "missing", "Required artifact is missing."))
        return None
    try:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            data = json.loads(text)
        else:
            data = yaml.safe_load(text)
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        stale_or_missing.append(_gap(str(path), "invalid", f"Artifact could not be parsed: {exc}"))
        return None
    if not isinstance(data, dict):
        stale_or_missing.append(_gap(str(path), "invalid", "Artifact did not contain a mapping."))
        return None
    return data


def _blocking_risks(
    work_order_dir: Path,
    sidecar: dict[str, Any],
    approval_status: str,
    report_ref: Path | None,
    rendered_refs: list[Path],
) -> list[str]:
    risks: list[str] = []
    if approval_status != "present":
        risks.append("Approval artifact is not present; execution is not allowed.")
    if report_ref is None:
        risks.append("Work Order report is missing.")
    if not rendered_refs:
        risks.append("Handoff artifact is missing.")
    if sidecar.get("forbidden_actions_observed") is True:
        risks.append("Forbidden action evidence was observed.")
    if (work_order_dir / "continuity" / "paused_work.yaml").is_file():
        risks.append(
            "Paused work is present and must be resumed only by a later approved Work Order."
        )
    return risks or ["none"]


def _limitations_from_eval(data: dict[str, Any]) -> list[str]:
    limitations = _as_string_list(data.get("limitations"))
    if limitations:
        return limitations
    status = _first_text(data.get("pass_fail"), "unknown")
    if status in {"unknown", "incomplete"}:
        return ["Eval status is incomplete or unknown."]
    return []


def _report_heading(report_ref: Path | None) -> str:
    if report_ref is None:
        return ""
    try:
        for line in report_ref.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line.removeprefix("# ").strip()
    except OSError:
        return ""
    return ""


def _count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = _first_text(record.get(key), "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _first_existing(paths: list[Path]) -> Path | None:
    return next((path for path in paths if path.is_file()), None)


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
        if not isinstance(value, (dict, list, tuple, set)):
            text = str(value).strip()
            if text:
                return text
    return "unknown"


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [value]
    return []


def _gap(ref: str, status: str, impact: str) -> dict[str, str]:
    return {"evidence_ref": ref, "status": status, "impact": impact}


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def true_bool(value: bool) -> bool:
    return bool(value)
