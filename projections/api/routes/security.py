"""Security findings API routes for vulnerability tracking dashboard — facade.

WO-GF-API-ROUTES: implementation moved to security_{router,shared,dismiss,
findings,stats,import}.py; this module imports every group sibling (in
original top-to-bottom order) so their handlers decorate the shared
`router`, then re-exports the full prior public+private surface so existing
`from projections.api.routes.security import X` callers are unchanged.

`_count_group` and `_count_since` are dead (no callers) but are still
re-exported here for parity with the prior module surface.
"""

from __future__ import annotations

from .security_router import router
from .security_dismiss import DismissRequest, dismiss_finding
from .security_shared import (
    _security_empty,
    _security_fallback_findings,
    _count_group,
    _security_finding_count_group,
    _count_since,
)
from .security_findings import (
    list_all_findings,
    list_sarif_findings,
    list_cve_matches,
    list_manual_reviews,
)
from .security_stats import get_security_stats
from .security_import import import_sarif_file

__all__ = [
    "router",
    "DismissRequest",
    "dismiss_finding",
    "_security_empty",
    "_security_fallback_findings",
    "_count_group",
    "_security_finding_count_group",
    "_count_since",
    "list_all_findings",
    "list_sarif_findings",
    "list_cve_matches",
    "list_manual_reviews",
    "get_security_stats",
    "import_sarif_file",
]
