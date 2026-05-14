"""Project registry and target-boundary helpers."""

from core.projects.paused_targets import (
    ProjectTargetPolicy,
    build_project_target_registry_policy,
    classify_project_target,
    validate_project_target_policy,
)
from core.projects.external_validation import (
    build_external_project_validation_pipeline,
    validate_external_project_validation_pipeline,
)
from core.projects.dashboard_views import build_external_project_dashboard_view

__all__ = [
    "ProjectTargetPolicy",
    "build_external_project_validation_pipeline",
    "build_external_project_dashboard_view",
    "build_project_target_registry_policy",
    "classify_project_target",
    "validate_external_project_validation_pipeline",
    "validate_project_target_policy",
]
