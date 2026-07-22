"""Top-level detect_stack orchestration for stack detection.

WO-GF-CONTROL-INSTALL-split: see detector.py facade docstring.
"""

from __future__ import annotations

from pathlib import Path

from .detector_dispatch import (
    _detect_architecture_framework,
    _detect_database_type,
    _detect_frontend_framework,
    _detect_monorepo_structure,
    _detect_test_framework,
    _detect_web_framework,
)
from .detector_release import (
    _detect_compliance_context,
    _detect_ops_context,
    _detect_release_context,
)
from .detector_shared import DetectedStack, StackSignal
from .detector_signals import _combine_signals, _detect_by_files


def detect_stack(path: Path) -> DetectedStack:
    """
    Detect project stack using multiple signals.

    Args:
        path: Project root directory

    Returns:
        DetectedStack with adapter name and confidence
    """
    signals = []

    # Signal 1: Try repo_context detection
    try:
        from control.context.repo import _detect_stack

        detected = _detect_stack(path)
        if detected and isinstance(detected, dict):
            stack_name = detected.get("stack") or detected.get("framework")
            if stack_name and isinstance(stack_name, str):
                signals.append(
                    StackSignal(
                        name=stack_name.lower(),
                        confidence=0.7,
                        source="repo_context",
                        evidence=[f"Detected via repo_context: {stack_name}"],
                    )
                )
    except Exception:
        pass  # repo_context not available or failed

    # Signal 2: File-based detection
    signals.extend(_detect_by_files(path))

    # Combine signals into stack result
    result = _combine_signals(signals)

    # Augment with test framework for coverage parser dispatch
    result.test_framework = _detect_test_framework(path)

    # Augment with database type for database skill dispatch
    result.database_type = _detect_database_type(path)

    # Augment with web framework for backend-api skill dispatch
    result.web_framework = _detect_web_framework(path)

    # Augment with frontend framework for frontend-ux skill dispatch
    result.frontend_framework = _detect_frontend_framework(path)

    # Augment with monorepo type and architecture framework for architecture skill dispatch
    result.monorepo_type = _detect_monorepo_structure(path)
    result.architecture_framework = _detect_architecture_framework(path)

    # Augment with ops deployment context for ops skill dispatch
    ops_context = _detect_ops_context(path)
    result.has_dockerfile = ops_context["has_dockerfile"]
    result.has_docker_compose = ops_context["has_docker_compose"]
    result.has_k8s_manifest = ops_context["has_k8s_manifest"]
    result.is_service = ops_context["is_service"]
    result.deployment_type = ops_context["deployment_type"]

    # Augment with compliance context for database-compliance skill dispatch
    compliance_context = _detect_compliance_context(path)
    result.has_pii_schema = compliance_context["has_pii_schema"]
    result.has_privacy_policy = compliance_context["has_privacy_policy"]
    result.compliance_hints = compliance_context["compliance_hints"]

    # Augment with release context for pre-launch skill dispatch
    release_context = _detect_release_context(path)
    result.service_type = release_context["service_type"]
    result.has_changelog = release_context["has_changelog"]
    result.has_runbook = release_context["has_runbook"]
    result.changelog_convention = release_context["changelog_convention"]
    result.release_tooling = release_context["release_tooling"]

    return result
