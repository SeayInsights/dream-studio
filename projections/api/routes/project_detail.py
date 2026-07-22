"""Project detail, health, history, analysis run, and activity endpoints — facade.

WO-GF-API-ROUTES: implementation moved to project_detail_{router,health,
details,history_runs,activity}.py; this module imports every group sibling
(in original top-to-bottom order) so their handlers decorate the shared
`router`, then re-exports the full prior public surface so existing
`from projections.api.routes.project_detail import X` callers (including
`from .routes.project_detail import router as project_detail_router` in
main.py) are unchanged.
"""

from __future__ import annotations

from .project_detail_router import router
from .project_detail_health import get_project_health
from .project_detail_details import get_project_details
from .project_detail_history_runs import get_project_history, get_analysis_run
from .project_detail_activity import get_project_activity

__all__ = [
    "router",
    "get_project_health",
    "get_project_details",
    "get_project_history",
    "get_analysis_run",
    "get_project_activity",
]
