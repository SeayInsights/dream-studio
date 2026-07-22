"""Cross-cutting helpers used by 3+ shared-intelligence route groups.

WO-GF-API-ROUTES: split out of shared_intelligence.py.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import Any

from fastapi import HTTPException

from core.config.database import get_connection


def _with_connection(func: Any) -> dict[str, Any]:
    try:
        with closing(get_connection(read_only=True)) as conn:
            payload = func(conn)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _dashboard_response(payload)


def _dashboard_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "dashboard_consumable": True,
        "execution_authorized": False,
        "policy_mutation_authorized": False,
        "authority_note": (
            "Shared-intelligence API routes expose derived views over SQLite authority; "
            "they do not write adapter configs, mutate routing policy, or authorize execution."
        ),
    }


def _split_query_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    normalized = raw.replace(";", ",").replace("\n", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]
