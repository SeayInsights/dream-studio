"""Dismiss-finding endpoint (Phase 19.2).

WO-GF-API-ROUTES: split out of security.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from core.config.database import get_connection
from core.findings.current_status import FINDINGS_CURRENT_STATUS_SQL, security_spine_present

from .security_router import router


class DismissRequest(BaseModel):
    reason: str


@router.post("/findings/{finding_id}/dismiss")
async def dismiss_finding(finding_id: str, body: DismissRequest) -> dict[str, Any]:
    """Mark a finding as dismissed (false_positive) on the security_events spine.

    Calls set_finding_status() to record a finding.status_changed event.
    Idempotent: dismissing an already-dismissed finding records a new status event.
    """
    from core.findings.mutations import set_finding_status

    # findings_current_status dropped migration 140 (WO dff23cb0) — derive from
    # security_events at read time (core/findings/current_status.py).
    with get_connection() as conn:
        if not security_spine_present(conn):
            raise HTTPException(
                status_code=503,
                detail="security_events not present — migration 111 not yet applied",
            )
        row = conn.execute(
            f"SELECT finding_id FROM ({FINDINGS_CURRENT_STATUS_SQL}) WHERE finding_id = ?",
            (finding_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Finding {finding_id!r} not found")

    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    set_finding_status(
        finding_id,
        "false_positive",
        project_id=None,
        reason=body.reason,
        correlation_id=None,
        db_path=None,
    )

    return {
        "finding_id": finding_id,
        "dismissed_at": now,
        "dismissed_reason": body.reason,
        "status": "false_positive",
    }
