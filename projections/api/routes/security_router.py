"""Shared APIRouter instance for the security route group.

WO-GF-API-ROUTES: security.py split into security_{router,shared,dismiss,
findings,stats,import}.py. This leaf owns the single `router` instance;
every group sibling imports it and decorates handlers onto it at import
time. `projections/api/main.py` still does
`app.include_router(security.router, prefix="/api/v1", tags=["security"])`
unchanged — prefix/tags stay there, not here.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
