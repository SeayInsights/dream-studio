"""Contract registry and documentation drift mapping — facade over the split modules.

The registry maps meaningful code/schema/dashboard/workflow/adapter changes to
the public contracts and docs that must stay fresh. It is intentionally
repo-backed and deterministic so release gates can run without live DB writes.

WO-GF-SHARED-INTEL-SPLIT: implementation moved to contract_registry_{constants,
domains_core,domains_ops,report}.py; this module re-exports the public and
private surface so existing `from core.shared_intelligence.contract_registry
import X` callers are unchanged.
"""

from __future__ import annotations

from .contract_registry_constants import (
    CONTRACT_ATLAS_DOC,
    CONTRACT_REGISTRY_SCHEMA,
    DOC_DRIFT_GATE_SCHEMA,
    PRD_DOC,
    PRIVATE_ARTIFACT_PATTERNS,
    PUBLICATION_BOUNDARY_DOC,
    PUBLICATION_RISK_PATTERNS,
    README_DOC,
)
from .contract_registry_domains_ops import CONTRACT_DOMAINS
from .contract_registry_report import (
    _matches,
    _matches_any,
    _normalize,
    _publication_required_actions,
    _required_actions,
    change_impact_report,
    contract_registry,
    validate_contract_registry,
)

__all__ = [
    "CONTRACT_ATLAS_DOC",
    "CONTRACT_DOMAINS",
    "CONTRACT_REGISTRY_SCHEMA",
    "DOC_DRIFT_GATE_SCHEMA",
    "PRD_DOC",
    "PRIVATE_ARTIFACT_PATTERNS",
    "PUBLICATION_BOUNDARY_DOC",
    "PUBLICATION_RISK_PATTERNS",
    "README_DOC",
    "_matches",
    "_matches_any",
    "_normalize",
    "_publication_required_actions",
    "_required_actions",
    "change_impact_report",
    "contract_registry",
    "validate_contract_registry",
]
