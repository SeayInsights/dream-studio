"""Shared APIRouter instance for the intelligence route group.

WO-GF-API-ROUTES: intelligence.py split into intelligence_{router,overview,
domains,workflow_patterns,friction}.py. This leaf owns the single `router`
instance; every group sibling imports it and decorates handlers onto it at
import time. `projections/api/main.py` still does
`app.include_router(intelligence.router, prefix="/api/v1/intelligence", ...)`
unchanged — prefix/tags stay there, not here.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
