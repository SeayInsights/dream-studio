"""Shared APIRouter instance for the shared-intelligence route group.

WO-GF-API-ROUTES: shared_intelligence.py split into shared_intelligence_{router,
shared,capability,platform,learning,routing,attribution}.py. This leaf owns
the single `router` instance; every group sibling imports it and decorates
handlers onto it at import time. `projections/api/main.py` still does
`app.include_router(shared_intelligence.router, prefix="/api/shared-intelligence", ...)`
unchanged — prefix/tags stay there, not here.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
