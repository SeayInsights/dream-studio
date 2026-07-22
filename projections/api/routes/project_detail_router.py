"""Shared APIRouter instance for the project-detail route group.

WO-GF-API-ROUTES: project_detail.py split into project_detail_{router,health,
details,history_runs,activity}.py. This leaf owns the single `router`
instance; every group sibling imports it and decorates handlers onto it at
import time. `projections/api/main.py` still does
`app.include_router(project_detail_router, prefix="/api/v1/projects", ...)`
unchanged — prefix/tags stay there, not here.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
