"""WO-SPLIT-HANDOFF: handoff security shared helpers module.

Shared by the three security-handoff builders and the three security-handoff
eval functions; kept dependency-light (only handoff_constants/re/Path/Any) so
it stays a leaf that both build-side and eval-side modules can import.
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import Any

from .handoff_constants import (
    HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION,
    PHASE_TYPE_APPROVED_MUTATION,
)
from .handoff_helpers import _as_list


def _artifact_path_label(path: Path | str | None) -> str:
    return str(path) if path else "unavailable"


def _security_next_recommendation(security_report: dict[str, Any]) -> dict[str, Any]:
    value = security_report.get("next_work_order_recommendation")
    return value if isinstance(value, dict) else {}


def _finding_short_id(finding_id: str) -> str:
    marker = "sec.finding.bill_stack."
    if finding_id.startswith(marker):
        return finding_id[len(marker) :]  # noqa: E203
    return finding_id.split(".")[-1]


def _security_finding_refs(finding_records: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for finding in finding_records:
        finding_id = str(finding.get("finding_id", "")).strip()
        if not finding_id:
            continue
        refs.append(f"{_finding_short_id(finding_id)} ({finding_id})")
    return refs or ["unavailable"]


def _security_finding_ids(finding_records: list[dict[str, Any]]) -> list[str]:
    ids = [str(finding.get("finding_id", "")).strip() for finding in finding_records]
    return [finding_id for finding_id in ids if finding_id]


def _extract_target_path_from_report(source_report_text: str, target_id: str) -> str:
    target_label = re.escape(target_id.replace("-", " "))
    patterns = (
        rf"{target_label}\s+target:\s*([^\n]+)",
        r"Target Repo Path\s*\n([^\n]+)",
        r"Target Repo Path\s*:\s*([^\n]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, source_report_text, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip().strip("`")
            candidate = re.split(r"`?,\s+", candidate, maxsplit=1)[0].strip().strip("`")
            return candidate
    return "not supplied; confirm before any target access"


def _target_branch_head_from_evidence(
    evidence_records: list[dict[str, Any]],
) -> tuple[str, str]:
    for evidence in evidence_records:
        branch_head = evidence.get("branch_head")
        if not isinstance(branch_head, dict):
            continue
        branch = str(branch_head.get("target_branch") or branch_head.get("branch") or "").strip()
        head = str(branch_head.get("target_head") or branch_head.get("head") or "").strip()
        if branch or head:
            return branch or "unknown", head or "unknown"
    return "unknown", "unknown"


def _target_untracked_entries(evidence_records: list[dict[str, Any]]) -> list[str]:
    entries: list[str] = []
    for evidence in evidence_records:
        for key in ("before_status", "after_status", "no_target_mutation_proof"):
            body = str(evidence.get(key, ""))
            for line in body.splitlines():
                match = re.match(r"\s*\?\?\s+(.+?)\s*$", line)
                if match:
                    entries.append(match.group(1).strip())
    deduped: list[str] = []
    for entry in entries:
        if entry and entry not in deduped:
            deduped.append(entry)
    return deduped


def _security_release_gate_decision(
    security_report: dict[str, Any],
    release_gate: dict[str, Any],
) -> str:
    decision = str(release_gate.get("decision", "")).strip()
    if decision:
        return decision
    embedded = security_report.get("release_gate_decision")
    if isinstance(embedded, dict):
        return str(embedded.get("decision", "")).strip() or "HOLD"
    return "HOLD"


def _finding_matches(finding: dict[str, Any], wanted: set[str]) -> bool:
    finding_id = str(finding.get("finding_id", "")).strip()
    return finding_id in wanted or _finding_short_id(finding_id) in wanted


def _selected_security_findings(
    finding_records: list[dict[str, Any]],
    included_finding_ids: list[str] | None,
) -> list[dict[str, Any]]:
    wanted = {item.strip() for item in included_finding_ids or [] if item.strip()}
    if not wanted:
        return finding_records
    return [finding for finding in finding_records if _finding_matches(finding, wanted)]


def _finding_assets(finding_records: list[dict[str, Any]]) -> list[str]:
    assets: list[str] = []
    for finding in finding_records:
        for asset in _as_list(finding.get("affected_assets")):
            text = str(asset).strip()
            if text and text not in assets:
                assets.append(text)
    return assets


def _finding_titles(finding_records: list[dict[str, Any]]) -> list[str]:
    titles: list[str] = []
    for finding in finding_records:
        finding_id = str(finding.get("finding_id", "")).strip()
        title = str(finding.get("title", "")).strip()
        label = _finding_short_id(finding_id)
        if title:
            titles.append(f"{label}: {title}")
        elif label:
            titles.append(label)
    return titles or ["unavailable"]


def _mutation_validation_lines(mutation_evidence: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in _as_list(mutation_evidence.get("focused_validation")):
        if not isinstance(item, dict):
            continue
        command = str(item.get("command", "")).strip()
        result = str(item.get("result", "")).strip()
        if command and result:
            lines.append(f"{command} -> {result}")
    return lines or ["unavailable"]


def _security_eval_result(pass_fail: str, observed: str, evidence: list[str]) -> dict[str, Any]:
    return {
        "pass_fail": pass_fail,
        "observed_behavior": observed,
        "score": 1 if pass_fail == "pass" else 0,
        "evidence": evidence,
    }


def _allowed_commit_authority_leaks(sections: dict[str, str]) -> list[str]:
    allowed_body = sections.get("allowed_actions", "").lower()
    leak_patterns = (
        "commit only",
        "commit scoped",
        "commit changes",
        "stage changes",
        "stage only",
        "stage scoped",
        "stage and commit",
        "stage or commit",
        "git commit",
        "git add",
        "may commit",
        "can commit",
    )
    return [pattern for pattern in leak_patterns if pattern in allowed_body]


def _evaluate_security_no_commit_without_commit_phase(
    prompt_text: str,
    sections: dict[str, str],
) -> dict[str, Any]:
    handoff_type = sections.get("handoff_type", "").strip()
    phase_type = sections.get("phase_type", "").strip()
    is_approved_mutation = (
        handoff_type == HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION
        and phase_type == PHASE_TYPE_APPROVED_MUTATION
    )
    if not is_approved_mutation:
        return _security_eval_result(
            "pass",
            "security commit-boundary eval is not applicable to this non-approved-mutation handoff",
            ["handoff_type", "phase_type"],
        )

    prompt_lower = prompt_text.lower()
    boundary_body = "\n".join(
        sections.get(section, "").lower()
        for section in (
            "capability_boundary",
            "forbidden_actions",
            "approval_artifact_requirement",
            "readiness_rules",
            "before_after_evidence_requirements",
        )
    )
    leaks = _allowed_commit_authority_leaks(sections)
    forbids_stage_commit_push = (
        "do not stage, commit, or push" in boundary_body
        or "forbid stage, commit, and push" in boundary_body
        or (
            "do not stage" in boundary_body
            and "do not commit" in boundary_body
            and "do not push" in boundary_body
        )
    )
    defers_commit_planning = (
        "commit planning" in prompt_lower
        and "later" in prompt_lower
        and "work order" in prompt_lower
    )
    passes = forbids_stage_commit_push and defers_commit_planning and not leaks
    evidence = []
    if not forbids_stage_commit_push:
        evidence.append("missing explicit stage/commit/push prohibition")
    if not defers_commit_planning:
        evidence.append("missing later commit-planning Work Order boundary")
    evidence.extend(f"allowed action leak: {leak}" for leak in leaks)
    return _security_eval_result(
        "pass" if passes else "fail",
        (
            "approved security mutation handoff forbids stage/commit/push and defers commit planning"
            if passes
            else "approved security mutation handoff leaks or omits commit-boundary authority"
        ),
        evidence or ["stage_commit_push_forbidden", "commit_planning_deferred"],
    )
