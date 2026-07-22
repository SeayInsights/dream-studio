"""Expert workflow catalog and overlap decisions — facade over the split modules.

The catalog formalizes Dream Studio's expert workflow system without creating
duplicate skills. It is a deterministic read model over repo-owned skills,
workflows, and authority tables. Runtime execution can persist results through
existing SQLite authority tables, but this module does not write to SQLite.

WO-GF-SHARED-INTEL-SPLIT: implementation moved to expert_workflows_{constants,
bases,catalog,validate}.py; this module re-exports the public and private
surface so existing `from core.shared_intelligence.expert_workflows import X`
callers are unchanged.
"""

from __future__ import annotations

from .expert_workflows_bases import _WORKFLOW_BASES
from .expert_workflows_catalog import (
    _overlap_matrix,
    _score_rubric,
    _workflow_definition,
    expert_workflow_catalog,
    workflow_by_id,
)
from .expert_workflows_constants import (
    APPLICATION_AUTOMATION_BOUNDARIES,
    AUTHORITY_WRITE_TARGETS,
    DECISION_VALUES,
    DESIGN_SPECIALIZED_SKILLS,
    EXPERT_WORKFLOW_CATALOG_SCHEMA,
    REQUIRED_WORKFLOW_IDS,
)
from .expert_workflows_validate import validate_expert_workflow_catalog

__all__ = [
    "APPLICATION_AUTOMATION_BOUNDARIES",
    "AUTHORITY_WRITE_TARGETS",
    "DECISION_VALUES",
    "DESIGN_SPECIALIZED_SKILLS",
    "EXPERT_WORKFLOW_CATALOG_SCHEMA",
    "REQUIRED_WORKFLOW_IDS",
    "_WORKFLOW_BASES",
    "_overlap_matrix",
    "_score_rubric",
    "_workflow_definition",
    "expert_workflow_catalog",
    "validate_expert_workflow_catalog",
    "workflow_by_id",
]
