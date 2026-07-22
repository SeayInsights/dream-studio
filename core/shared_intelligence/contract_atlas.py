"""Contract Atlas derived read model for Dream Studio — facade over the split modules.

The atlas explains Dream Studio's own layers, modules, interfaces, runtime
profiles, adapter projection boundaries, and dependency graph without creating
new authority. It is private/local by default; public exports are sanitized.

WO-GF-SHARED-INTEL-SPLIT: implementation moved to contract_atlas_{sections,
graph,scorecard,boundary,validate,main}.py; this module re-exports the public
and private surface so existing `from core.shared_intelligence.contract_atlas
import X` callers are unchanged.
"""

from __future__ import annotations

from .contract_atlas_boundary import (
    _active_adapter_execution_validation,
    _boundary_violation_report,
)
from .contract_atlas_graph import _confirmed_dependency_graph
from .contract_atlas_main import (
    CONTRACT_ATLAS_SCHEMA,
    DEFAULT_CONTRACT_ATLAS_PROJECT_ID,
    EXPORT_SCOPES,
    build_contract_atlas,
)
from .contract_atlas_scorecard import _github_cicd_profile, _maturity_scorecard
from .contract_atlas_sections import (
    _adapter_projection_contracts,
    _analytics_only_profile,
    _dashboard_private_export_boundaries,
    _docs_freshness_tracking,
    _interface_contracts,
    _layer_contracts,
    _runtime_profiles,
    _source_tables,
    _whole_system_contract,
)
from .contract_atlas_validate import (
    _PRIVATE_PATH_RULES,
    _SANITIZE_TOKEN_CHARS,
    _contains_absolute_path,
    _sanitize_absolute_paths,
    _sanitize_value,
    sanitize_contract_atlas_for_public_export,
    validate_contract_atlas,
)

__all__ = [
    "CONTRACT_ATLAS_SCHEMA",
    "DEFAULT_CONTRACT_ATLAS_PROJECT_ID",
    "EXPORT_SCOPES",
    "_PRIVATE_PATH_RULES",
    "_SANITIZE_TOKEN_CHARS",
    "_active_adapter_execution_validation",
    "_adapter_projection_contracts",
    "_analytics_only_profile",
    "_boundary_violation_report",
    "_confirmed_dependency_graph",
    "_contains_absolute_path",
    "_dashboard_private_export_boundaries",
    "_docs_freshness_tracking",
    "_github_cicd_profile",
    "_interface_contracts",
    "_layer_contracts",
    "_maturity_scorecard",
    "_runtime_profiles",
    "_sanitize_absolute_paths",
    "_sanitize_value",
    "_source_tables",
    "_whole_system_contract",
    "build_contract_atlas",
    "sanitize_contract_atlas_for_public_export",
    "validate_contract_atlas",
]
