"""Render-packet and skill-identifier-safety evals for file-backed Work Orders.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/evals.py``. No logic
changes — extracted verbatim from the original module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .evals_shared import (
    REQUIRED_PACKET_TERMS,
    RENDER_COMPLETENESS,
    SKILL_IDENTIFIER_SAFETY,
    _base_artifact,
    _write_eval,
)
from .models import SKILL_ID_RE


def _legacy_skill_prefixes() -> tuple[str, str]:
    return ("dream" "-studio" + ":", "d" "s" + ":")


def create_render_completeness_eval(
    *,
    work_order: dict[str, Any],
    target: str,
    packet_path: Path,
    packet_text: str,
    storage_root: Path | str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Write a deterministic render completeness eval artifact."""
    # WO-FILESDB-C5: the packet is stored in the packet store (not a disk file), so
    # completeness is judged from packet_text content, not packet_path.is_file().
    missing = [term for term in REQUIRED_PACKET_TERMS if term not in packet_text]
    pass_fail = "pass" if not missing else "fail"
    observed = (
        f"{target} packet includes required render fields and prohibitions."
        if pass_fail == "pass"
        else f"{target} packet missing evidence: {', '.join(missing) or 'unknown'}."
    )
    artifact = _base_artifact(
        work_order=work_order,
        eval_type=RENDER_COMPLETENESS,
        expected_behavior="Rendered packet includes required fields, scope, validation, stop conditions, and render-only prohibitions.",
        observed_behavior=observed,
        pass_fail=pass_fail,
        evidence=[str(packet_path)],
        score=1 if pass_fail == "pass" else 0,
    )
    path = _write_eval(artifact, storage_root=storage_root)
    return artifact, path


def create_skill_identifier_safety_eval(
    *,
    work_order: dict[str, Any],
    storage_root: Path | str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Write a deterministic skill identifier safety eval artifact."""
    skills = work_order.get("allowed_skills")
    legacy_product, legacy_ds = _legacy_skill_prefixes()
    bad: list[str] = []
    if not isinstance(skills, list):
        bad.append("allowed_skills unavailable")
    else:
        for skill in skills:
            if not isinstance(skill, str):
                bad.append("<non-string>")
            elif skill.startswith(legacy_product) or skill.startswith(legacy_ds):
                bad.append(skill)
            elif not SKILL_ID_RE.fullmatch(skill):
                bad.append(skill)

    pass_fail = "pass" if not bad else "fail"
    observed = (
        "All allowed skills use ds-<slug> identifiers."
        if pass_fail == "pass"
        else f"Unsafe skill identifiers found: {', '.join(bad)}."
    )
    artifact = _base_artifact(
        work_order=work_order,
        eval_type=SKILL_IDENTIFIER_SAFETY,
        expected_behavior="allowed_skills use ds-<slug> and reject legacy product-name or colon-delimited forms.",
        observed_behavior=observed,
        pass_fail=pass_fail,
        evidence=["allowed_skills"],
        score=1 if pass_fail == "pass" else 0,
    )
    path = _write_eval(artifact, storage_root=storage_root)
    return artifact, path
