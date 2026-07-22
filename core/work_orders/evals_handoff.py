"""Handoff-prompt evals for file-backed Work Orders.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/evals.py``. No logic
changes — extracted verbatim from the original module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .evals_shared import _base_artifact, _write_eval
from .handoff import (
    HANDOFF_CONSTRAINT_PRESERVATION,
    HANDOFF_CURRENT_STATE_COMPLETENESS,
    HANDOFF_EVAL_TYPES,
    HANDOFF_EXECUTION_READINESS,
    HANDOFF_FRESH_SESSION_SUFFICIENCY,
    HANDOFF_HOOK_BEHAVIOR_AWARENESS,
    HANDOFF_INDEX_STATE_REQUIREMENTS,
    HANDOFF_OPERATOR_DECISION_GATE,
    HANDOFF_PATH_INTEGRITY,
    HANDOFF_PROMPT_COMPLETENESS,
    HANDOFF_PUSH_EVIDENCE_REQUIREMENTS,
    HANDOFF_PUSH_EXECUTION_COMPLETENESS,
    HANDOFF_PUSH_TARGET_CONSTRAINTS,
    HANDOFF_RECOVERY_MODE_COMPLETENESS,
    HANDOFF_RECOVERY_OPTION_CLARITY,
    evaluate_handoff_prompt,
)


def create_handoff_prompt_evals(
    *,
    work_order: dict[str, Any],
    prompt_text: str,
    readiness: str,
    can_continue: bool,
    report_path: Path,
    storage_root: Path | str | None = None,
) -> tuple[list[dict[str, Any]], list[Path]]:
    """Write deterministic Handoff Packet eval artifacts."""
    results = evaluate_handoff_prompt(
        prompt_text,
        readiness=readiness,
        can_continue=can_continue,
        target_repo_required=bool(str(work_order.get("target_path", "")).strip()),
    )
    expected = {
        HANDOFF_PROMPT_COMPLETENESS: "Handoff prompt includes required context and safety fields.",
        HANDOFF_CONSTRAINT_PRESERVATION: "Handoff prompt preserves Work Order authority constraints.",
        HANDOFF_EXECUTION_READINESS: "READY reports include execution prompts; HOLD/FAIL reports include decision-only recovery or hold prompts.",
        HANDOFF_FRESH_SESSION_SUFFICIENCY: "Handoff prompt is usable without prior chat context and requires a Handoff Understanding Report.",
        HANDOFF_RECOVERY_MODE_COMPLETENESS: "Recovery handoffs include recovery_decision fields and do not blend decision with execution.",
        HANDOFF_CURRENT_STATE_COMPLETENESS: "Recovery handoffs model current local commit, branch, staged/index, no-push, and forbidden-file state.",
        HANDOFF_RECOVERY_OPTION_CLARITY: "Recovery handoffs list options and recommend the safest option.",
        HANDOFF_OPERATOR_DECISION_GATE: "Recovery handoffs require an operator decision before mutation or index changes.",
        HANDOFF_PATH_INTEGRITY: "Handoff prompt preserves valid Dream Studio artifact path separators.",
        HANDOFF_INDEX_STATE_REQUIREMENTS: "Recovery handoffs with git staging require explicit index-state evidence.",
        HANDOFF_HOOK_BEHAVIOR_AWARENESS: "Recovery handoffs account for potentially mutating hook and lint-staged behavior.",
        HANDOFF_PUSH_EXECUTION_COMPLETENESS: "Push execution handoffs include push target, forbidden target, before/after evidence, command, readiness, verdict, and report sections.",
        HANDOFF_PUSH_TARGET_CONSTRAINTS: "Push execution handoffs constrain remote, branch, command, force-push, tags, other branches, other remotes, deletes, and extra refspecs.",
        HANDOFF_PUSH_EVIDENCE_REQUIREMENTS: "Push execution handoffs require approval, fetch, HEAD, ahead/behind, index, before-push, after-push, and no-forbidden-action evidence.",
    }
    artifacts: list[dict[str, Any]] = []
    paths: list[Path] = []
    for eval_type in sorted(HANDOFF_EVAL_TYPES):
        result = results[eval_type]
        artifact = _base_artifact(
            work_order=work_order,
            eval_type=eval_type,
            expected_behavior=expected.get(
                eval_type, "Handoff prompt eval passes deterministically."
            ),
            observed_behavior=str(result["observed_behavior"]),
            pass_fail=str(result["pass_fail"]),
            evidence=[str(report_path), *[str(item) for item in result.get("evidence", [])]],
            score=result["score"],
        )
        path = _write_eval(artifact, storage_root=storage_root)
        artifacts.append(artifact)
        paths.append(path)
    return artifacts, paths
