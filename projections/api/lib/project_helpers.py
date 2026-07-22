"""Shared project helpers used by multiple project intelligence route files — facade.

WO-GF-API-ROUTES: implementation moved to project_helpers_{utils,prd,health,
classification,module_fit,surfaces,decorate}.py; this module re-exports the
public+private API so existing
`from projections.api.lib.project_helpers import X` callers are unchanged.

`logger` and `SENSITIVE_PATH_PARTS` are dead (no callers) — they were
relocated verbatim into project_helpers_utils.py but are intentionally not
re-exported here.
"""

from __future__ import annotations

from .project_helpers_utils import (
    _as_int,
    _json_list,
    _optional_column_expr,
    _optional_count_expr,
    _project_path_exists,
    _parse_stack_json,
    get_db_path,
    get_db_connection,
    _active_project_where,
)
from .project_helpers_prd import (
    _resolve_prd_file,
    _safe_prd_summary,
    _build_prd_authority_status,
)
from .project_helpers_health import _build_health_model
from .project_helpers_classification import (
    _default_operator_exclusion_terms,
    _classify_project_authority,
)
from .project_helpers_module_fit import _module_runtime_fit
from .project_helpers_surfaces import (
    _recent_validation_state,
    _attention_detail_items,
    _component_index,
    _missing_tables,
    _empty_project_source_status,
    _project_surface_availability,
    _project_row_for_authority,
    _unavailable_project_surfaces,
)
from .project_helpers_decorate import (
    _decorate_project_for_dashboard,
    _finding_summary,
    _collect_evidence_refs,
    _project_detail_known_gaps,
    _project_detail_next_action,
)

__all__ = [
    "_as_int",
    "_json_list",
    "_optional_column_expr",
    "_optional_count_expr",
    "_project_path_exists",
    "_parse_stack_json",
    "get_db_path",
    "get_db_connection",
    "_active_project_where",
    "_resolve_prd_file",
    "_safe_prd_summary",
    "_build_prd_authority_status",
    "_build_health_model",
    "_default_operator_exclusion_terms",
    "_classify_project_authority",
    "_module_runtime_fit",
    "_recent_validation_state",
    "_attention_detail_items",
    "_component_index",
    "_missing_tables",
    "_empty_project_source_status",
    "_project_surface_availability",
    "_project_row_for_authority",
    "_unavailable_project_surfaces",
    "_decorate_project_for_dashboard",
    "_finding_summary",
    "_collect_evidence_refs",
    "_project_detail_known_gaps",
    "_project_detail_next_action",
]
