"""Adaptive brownfield routing: detected stack/purpose -> relevant ds packs/modes.

WO-BROWNFIELD-ADAPTIVE (570e6c1f). The stack detector
(``control.analysis.stacks.detector``) already surfaces skill-dispatch-relevant
signals on every detected project (web_framework, frontend_framework,
database_type, test_framework, monorepo_type/architecture_framework, container/
k8s ops signals, PII/compliance hints, pre-launch service signals). This module
maps those persisted signals to concrete ``ds-quality`` modes so the brownfield
pipeline can recommend the audits/builders that actually fit each repo — instead
of a generic one-size prompt.

Pure mapping over the persisted ``stack_json`` dict; no I/O, no detection.
"""

from __future__ import annotations

from typing import Any

# Every mode this module recommends, mapped to its CURRENT owning pack. The
# pack-split campaign has moved several of these since this module was
# written (it originally hardcoded "ds-quality" for all of them); a mode
# missing here is a bug in this map, not a fallback case, so recommend_dispatches
# raises rather than guessing.
_MODE_PACK: dict[str, str] = {
    "backend": "ds-fullstack",
    "frontend": "ds-fullstack",
    "database": "ds-data",
    "comply": "ds-security",
    "testing": "ds-code-health",
    "architecture": "ds-code-health",
    "ops": "ds-release",
    "pre-launch": "ds-release",
}


def recommend_dispatches(stack_data: dict[str, Any] | None) -> list[dict[str, str]]:
    """Map a project's detected stack signals to relevant ds pack:mode dispatches.

    ``stack_data`` is the persisted ``business_projects.stack_json`` dict (see
    ``core.projects.intake.detect_and_persist_stack``). Returns an ordered,
    de-duplicated list of ``{"pack", "mode", "reason"}`` recommendations; empty
    when nothing relevant is detected.
    """
    if not stack_data:
        return []

    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(mode: str, reason: str) -> None:
        if mode in seen:
            return
        seen.add(mode)
        out.append({"pack": _MODE_PACK[mode], "mode": mode, "reason": reason})

    if stack_data.get("web_framework"):
        # backend-api was folded into fullstack:backend's `audit` sub-mode in the
        # pack-split campaign's fullstack merge -- "backend-api" is no longer an
        # invocable mode name on its own, so the reason names the real invocation
        # rather than pointing at a dead target.
        add(
            "backend",
            f"detected {stack_data['web_framework']} web/API framework -- invoke ds-fullstack:backend audit",
        )
    if stack_data.get("frontend_framework"):
        add(
            "frontend",
            f"detected {stack_data['frontend_framework']} frontend framework -- invoke ds-fullstack:frontend audit",
        )
    if stack_data.get("database_type"):
        add("database", f"detected {stack_data['database_type']} database")
    if stack_data.get("has_pii_schema") or stack_data.get("compliance_hints"):
        hints = stack_data.get("compliance_hints") or []
        detail = ", ".join(hints) if hints else "PII-suggestive schema"
        # database-compliance was folded into comply's `privacy` sub-mode in the
        # pack-split campaign's security merge -- "database-compliance" is no
        # longer an invocable mode name on its own, so the reason names the real
        # invocation (`ds-security:comply privacy`) rather than pointing at a
        # dead target the way `mode: "database-compliance"` would have.
        add(
            "comply",
            f"detected compliance signals: {detail} -- invoke ds-security:comply privacy",
        )
    if stack_data.get("test_framework"):
        add("testing", f"detected {stack_data['test_framework']} test framework")
    if stack_data.get("architecture_framework") or stack_data.get("monorepo_type"):
        arch = stack_data.get("architecture_framework") or stack_data.get("monorepo_type")
        add("architecture", f"detected {arch} architecture/monorepo tooling")
    if (
        stack_data.get("has_dockerfile")
        or stack_data.get("has_docker_compose")
        or stack_data.get("has_k8s_manifest")
        or stack_data.get("deployment_type") in {"container", "serverless"}
    ):
        add("ops", "detected containerization / deployment tooling")
    if stack_data.get("service_type") or stack_data.get("release_tooling"):
        svc = stack_data.get("service_type") or "service"
        add("pre-launch", f"detected {svc} release/launch signals")

    return out
