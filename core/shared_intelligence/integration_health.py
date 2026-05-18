"""Integration health — replaces adapter_staleness.py.

Public API for querying integration health across all detected tools.
State machine lives in integrations/health.py; this module is the
shared_intelligence surface (used by dashboard, CLI, and alignment checks).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def integration_health_summary(
    *,
    working_dir: Path | None = None,
    ds_home: Path | None = None,
    canonical_root: Path | None = None,
) -> dict[str, Any]:
    """Compute current integration health for all detected tools.

    Returns a derived view dict — not authoritative; computed from disk state.
    """
    from integrations.detector import detect_all
    from integrations.health import doctor

    tools = detect_all(working_dir=working_dir)
    tool_states: list[dict[str, Any]] = []

    for tool in tools:
        state = doctor(
            tool.tool_id,
            tool.config_root,
            ds_home=ds_home,
            canonical_root=canonical_root,
        )
        tool_states.append({
            "tool_id": tool.tool_id,
            "scope": tool.scope,
            "config_root": str(tool.config_root),
            **state,
        })

    return {
        "model_name": "dream_studio_integration_health_summary",
        "derived_view": True,
        "primary_authority": False,
        "tools": tool_states,
        "live_db_mutation_authorized": False,
    }


def integration_health_for_tool(
    tool_id: str,
    config_root: Path,
    *,
    ds_home: Path | None = None,
    canonical_root: Path | None = None,
) -> dict[str, Any]:
    """Doctor report for a single tool."""
    from integrations.health import doctor

    return doctor(
        tool_id,
        config_root,
        ds_home=ds_home,
        canonical_root=canonical_root,
    )
