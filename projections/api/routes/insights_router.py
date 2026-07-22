"""Shared APIRouter instance for the insights route group.

WO-GF-API-ROUTES: insights.py split into insights_{router,shared,core,rhythm,
diagnostics}.py. This leaf owns the single `router` instance; every group
sibling imports it and decorates handlers onto it at import time.
`projections/api/main.py` still does
`app.include_router(insights.router, prefix="/api/v1/insights", ...)`
unchanged — prefix/tags stay there, not here.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
