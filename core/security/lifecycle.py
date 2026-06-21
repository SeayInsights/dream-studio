"""Security-by-default development lifecycle read models.

This module turns the existing 47-control security review catalog into a
non-executing lifecycle policy surface. It classifies applicability and routing;
it does not run scans, mutate repositories, inspect secrets, or write SQLite.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SOURCE_LIST = Path("docs/contracts/security-review-source-47-enterprise-scans.md")
CROSSWALK = Path("docs/contracts/security-review-47-scan-crosswalk.md")
CATALOG = Path("docs/contracts/security-review-scan-catalog.yaml")

FULL_REVIEW_EVENTS = {
    "project_intake",
    "release",
    "merge",
    "release_merge",
    "publication",
    "deployment",
    "live_cutover",
    "dependency_change",
    "runtime_change",
    "security_change",
    "database_change",
    "docker_change",
    "major_architecture_change",
    "external_project_onboarding",
    "scheduled_dogfood_gate",
}

CATEGORY_BY_SOURCE_NUMBER = {
    **dict.fromkeys(range(1, 15), "source_code_analysis"),
    **dict.fromkeys(range(15, 21), "dependency_supply_chain"),
    **dict.fromkeys(range(21, 25), "secrets_credentials"),
    **dict.fromkeys(range(25, 30), "container_image_security"),
    **dict.fromkeys(range(30, 36), "infrastructure_as_code"),
    **dict.fromkeys(range(36, 42), "dynamic_runtime_testing"),
    **dict.fromkeys(range(42, 48), "compliance_governance_operational"),
}

IMPACT_FILE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("dependency_supply_chain", ("requirements", "package.json", "lock", "pyproject.toml")),
    ("runtime_change", ("runtime/", "hooks/", "interfaces/cli", "core/installed_runtime.py")),
    ("container_image_security", ("dockerfile", "compose", "container", "image")),
    ("infrastructure_as_code", ("terraform", ".tf", "k8s", "kubernetes", "helm", "cloud")),
    ("database_change", ("migration", "sqlite", "database", "studio_db", ".sql")),
    ("security_change", ("security", "auth", "secret", "credential", "crypto", "token")),
    ("dynamic_runtime_testing", ("api", "routes", "endpoint", "websocket", "dashboard")),
    ("publication", ("publication", "readme", "license", "docs/publication")),
    ("compliance_governance_operational", ("ci", "release", "workflow", ".github")),
)

SKILL_CONTROL_MAPPING = [
    {
        "skill_mode": "security:review",
        "maps_to": ["source_code_analysis", "secrets_credentials", "dynamic_runtime_testing"],
        "source_item_range": "1-14, 21-24, targeted 36-41 where API/runtime logic changes",
        "behavior": "Static diff/code review with high-confidence findings only.",
    },
    {
        "skill_mode": "security:scan",
        "maps_to": ["source_code_analysis", "dependency_supply_chain", "secrets_credentials"],
        "source_item_range": "1-24",
        "behavior": "Baseline scan orchestration when approved by Work Order scope.",
    },
    {
        "skill_mode": "security:dast",
        "maps_to": ["dynamic_runtime_testing"],
        "source_item_range": "36-41",
        "behavior": "Runtime/web/API testing only after target and credential scope approval.",
    },
    {
        "skill_mode": "security:binary-scan",
        "maps_to": ["container_image_security", "dependency_supply_chain"],
        "source_item_range": "15, 20, 25",
        "behavior": "Binary/image artifact review when artifact scope is approved.",
    },
    {
        "skill_mode": "security:mitigate",
        "maps_to": ["all_findings"],
        "source_item_range": "all applicable controls with open findings",
        "behavior": "Remediation planning and patch guidance after findings are confirmed current.",
    },
    {
        "skill_mode": "security:comply",
        "maps_to": ["compliance_governance_operational", "data_handling_privacy"],
        "source_item_range": "42-47 plus data/privacy-related catalog controls",
        "behavior": "Compliance evidence mapping without claiming certification.",
    },
    {
        "skill_mode": "security:dashboard",
        "maps_to": ["all_findings"],
        "source_item_range": "all applicable controls with evidence",
        "behavior": "Reporting/export surface; it is derived and not authority.",
    },
]


@dataclass(frozen=True)
class SourceControl:
    item_number: int
    name: str
    domain: str
    category_id: str


def build_security_lifecycle_gate(
    *,
    repo_root: Path | None = None,
    changed_files: list[str] | None = None,
    lifecycle_event: str = "code_change",
    project_id: str = "dream-studio",
    conn: sqlite3.Connection | None = None,
    open_finding_count: int | None = None,
) -> dict[str, Any]:
    """Build the security lifecycle gate read model."""

    root = _security_contract_root(repo_root)
    source_controls = _read_source_controls(root)
    crosswalk = _read_crosswalk(root)
    catalog = _read_catalog(root)
    impact = classify_security_impact(changed_files or [], lifecycle_event=lifecycle_event)
    full_review_required = lifecycle_event in FULL_REVIEW_EVENTS or any(
        category in impact["impact_categories"]
        for category in {
            "dependency_supply_chain",
            "runtime_change",
            "container_image_security",
            "infrastructure_as_code",
            "database_change",
            "security_change",
            "publication",
        }
    )
    applicability = _applicability_rows(
        source_controls=source_controls,
        crosswalk=crosswalk,
        impact_categories=set(impact["impact_categories"]),
        full_review_required=full_review_required,
    )
    status_counts = Counter(row["status"] for row in applicability)
    open_findings = (
        open_finding_count
        if open_finding_count is not None
        else _security_open_finding_count(conn, project_id=project_id) if conn else 0
    )
    unknown_count = status_counts["unknown"]
    manual_review_count = status_counts["manual_review_required"]
    blocking_count = unknown_count + manual_review_count + int(open_findings > 0)
    if open_findings:
        security_status = "blocked_by_open_findings"
        release_readiness_effect = "block_open_findings"
    elif unknown_count:
        security_status = "unknown_requires_review"
        release_readiness_effect = "hold_unknown_controls"
    elif manual_review_count:
        security_status = "needs_manual_review"
        release_readiness_effect = "hold_manual_review"
    else:
        security_status = "ready"
        release_readiness_effect = "pass"
    return {
        "model_name": "security_by_default_development_lifecycle_gate",
        "project_id": project_id,
        "lifecycle_event": lifecycle_event,
        "derived_view": True,
        "primary_authority": False,
        "execution_authorized": False,
        "db_write_authorized": False,
        "source_framework": {
            "source_list_ref": SOURCE_LIST.as_posix(),
            "source_control_count": len(source_controls),
            "crosswalk_ref": CROSSWALK.as_posix(),
            "catalog_ref": CATALOG.as_posix(),
            "catalog_scan_count": len(catalog["scans"]),
            "canonical_framework": "47_enterprise_security_controls",
        },
        "impact_classification": impact,
        "full_review_required": full_review_required,
        "full_review_triggers": sorted(FULL_REVIEW_EVENTS),
        "security_status": security_status,
        "release_readiness_effect": release_readiness_effect,
        "dashboard_attention_required": security_status != "ready",
        "applicability_summary": {
            "applicable": status_counts["applicable"],
            "not_applicable": status_counts["not_applicable"],
            "manual_review_required": status_counts["manual_review_required"],
            "unknown": status_counts["unknown"],
            "source_control_count": len(source_controls),
        },
        "applicability": applicability,
        "targeted_controls": [
            row
            for row in applicability
            if row["status"] in {"applicable", "manual_review_required"}
        ],
        "security_skill_control_mapping": SKILL_CONTROL_MAPPING,
        "finding_schema_requirements": [
            "project_id",
            "file_path",
            "line",
            "severity",
            "control_id",
            "status",
            "evidence",
            "remediation_path",
        ],
        "finding_normalization_policy": {
            "synthetic_demo_findings_in_live_operator_views": False,
            "unknown_controls_route": "manual_review_or_dashboard_attention",
            "not_applicable_requires_reason": True,
        },
        "project_security_status": {
            "open_findings": open_findings,
            "blocking_count": blocking_count,
            "release_readiness": release_readiness_effect,
            "health_effect": "degrades_project_health_when_blocking_or_open_findings",
        },
    }


def classify_security_impact(
    changed_files: list[str],
    *,
    lifecycle_event: str = "code_change",
) -> dict[str, Any]:
    """Classify change impact without reading file contents."""

    categories: set[str] = set()
    matched_files: list[dict[str, str]] = []
    for raw in changed_files:
        lowered = raw.replace("\\", "/").lower()
        for category, patterns in IMPACT_FILE_PATTERNS:
            if any(pattern in lowered for pattern in patterns):
                categories.add(category)
                matched_files.append({"file": raw, "impact_category": category})
    if lifecycle_event in {"release", "merge", "release_merge"}:
        categories.add("compliance_governance_operational")
    if lifecycle_event == "publication":
        categories.add("publication")
    if lifecycle_event in {"runtime_change", "live_cutover"}:
        categories.add("runtime_change")
    if lifecycle_event in {"database_change"}:
        categories.add("database_change")
    if lifecycle_event in {"docker_change", "deployment"}:
        categories.add("container_image_security")
    if lifecycle_event in {"security_change"}:
        categories.add("security_change")
    if lifecycle_event in {"dependency_change"}:
        categories.add("dependency_supply_chain")
    if lifecycle_event in {"project_intake", "external_project_onboarding"}:
        categories.update(CATEGORY_BY_SOURCE_NUMBER.values())
    return {
        "classification": "security_relevant" if categories else "lightweight_no_direct_signal",
        "changed_file_count": len(changed_files),
        "impact_categories": sorted(categories),
        "matched_files": matched_files,
        "lightweight_security_classification_required": True,
    }


def _read_source_controls(repo_root: Path) -> list[SourceControl]:
    text = (repo_root / SOURCE_LIST).read_text(encoding="utf-8")
    domain = ""
    rows: list[SourceControl] = []
    for line in text.splitlines():
        if line.startswith("DOMAIN "):
            domain = line.strip()
            continue
        match = re.match(r"^(\d+)\.\s+(.+)$", line.strip())
        if not match:
            continue
        number = int(match.group(1))
        rows.append(
            SourceControl(
                item_number=number,
                name=match.group(2),
                domain=domain,
                category_id=CATEGORY_BY_SOURCE_NUMBER[number],
            )
        )
    return rows


def _security_contract_root(repo_root: Path | None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[2]
    if (root / SOURCE_LIST).exists() and (root / CROSSWALK).exists() and (root / CATALOG).exists():
        return root
    return Path(__file__).resolve().parents[2]


def _read_crosswalk(repo_root: Path) -> dict[int, dict[str, str]]:
    rows: dict[int, dict[str, str]] = {}
    text = (repo_root / CROSSWALK).read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line.startswith("| ") or line.startswith("| ---") or "Original #" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 7 or not cells[0].isdigit():
            continue
        rows[int(cells[0])] = {
            "coverage_status": cells[3],
            "scan_ids": cells[4],
            "rationale": cells[5],
            "recommended_action": cells[6],
        }
    return rows


def _read_catalog(repo_root: Path) -> dict[str, Any]:
    raw = yaml.safe_load((repo_root / CATALOG).read_text(encoding="utf-8")) or {}
    scans = raw.get("scans")
    raw["scans"] = scans if isinstance(scans, list) else []
    return raw


def _applicability_rows(
    *,
    source_controls: list[SourceControl],
    crosswalk: dict[int, dict[str, str]],
    impact_categories: set[str],
    full_review_required: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for control in source_controls:
        mapping = crosswalk.get(control.item_number)
        if mapping is None:
            rows.append(
                {
                    **_control_base(control),
                    "status": "unknown",
                    "reason": "Control is missing from the 47-control crosswalk.",
                    "dashboard_attention_required": True,
                    "manual_review_required": True,
                }
            )
            continue

        coverage = mapping["coverage_status"]
        category_matches = control.category_id in impact_categories or (
            control.category_id == "source_code_analysis" and "security_change" in impact_categories
        )
        if coverage.startswith("deferred") and (full_review_required or category_matches):
            status = "manual_review_required"
            reason = f"{coverage} coverage requires approved target/validation scope."
        elif full_review_required or category_matches:
            status = "applicable"
            reason = "Control is applicable to the lifecycle event or changed-file impact."
        else:
            status = "not_applicable"
            reason = "No current lifecycle trigger or changed-file impact maps to this control."

        rows.append(
            {
                **_control_base(control),
                "status": status,
                "reason": reason,
                "coverage_status": coverage,
                "catalog_scan_ids": _split_scan_ids(mapping["scan_ids"]),
                "dashboard_attention_required": status in {"unknown", "manual_review_required"},
                "manual_review_required": status in {"unknown", "manual_review_required"},
            }
        )
    return rows


def _control_base(control: SourceControl) -> dict[str, Any]:
    return {
        "control_id": f"ESC-{control.item_number:02d}",
        "source_item_number": control.item_number,
        "name": control.name,
        "domain": control.domain,
        "category_id": control.category_id,
    }


def _split_scan_ids(raw: str) -> list[str]:
    return re.findall(r"`([^`]+)`", raw)


def _security_open_finding_count(conn: sqlite3.Connection, *, project_id: str) -> int:
    # Read from findings_current_status (spine read-model, WO-Y / AD-10).
    # Falls back to 0 if the table is absent (pre-migration installs).
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM findings_current_status"
            " WHERE project_id = ? AND current_status = 'open'",
            (project_id,),
        ).fetchone()
        return int(row[0] if row else 0)
    except sqlite3.Error:
        return 0
