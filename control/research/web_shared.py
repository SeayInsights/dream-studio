"""Shared telemetry helper and dataclasses for web research.

WO-GF-CONTROL-INSTALL-split: implementation moved to web_{shared,scoring,
search,cache}.py; control/research/web.py re-exports the public+private
surface so existing `from control.research.web import X` callers are
unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
import json

from core.config.database import transaction


def _emit_metric(event: str, data: dict) -> None:
    """Emit telemetry metric to raw_metrics table if it exists.

    Args:
        event: Event name (e.g., "web_research.search")
        data: Event data dict
    """
    try:
        metric = {"event": event, "data": data, "timestamp": datetime.now(UTC).isoformat()}
        metric_json = json.dumps(metric)

        with transaction() as c:
            # Check if raw_metrics table exists
            table_exists = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='raw_metrics'"
            ).fetchone()

            if table_exists:
                # EXEMPTION CANDIDATE: raw_metrics writes are infrastructure telemetry, not business state
                c.execute("INSERT INTO raw_metrics (metric_json) VALUES (?)", (metric_json,))
    except Exception:
        # Silently fail - metrics are best-effort
        pass


@dataclass
class Source:
    """Represents a single research source with quality tier.

    Tier 1: Official docs, GitHub repos, readthedocs
    Tier 2: Technical blogs, Medium, dev.to
    Tier 3: Forums, Stack Overflow, Reddit
    """

    url: str
    title: str
    snippet: str
    tier: int
    source_type: str = "unknown"
    accessed_at: str = "unknown"
    extraction_notes: str = "unavailable"
    verification_status: str = "unverified"


@dataclass
class ResearchReport:
    """Complete research report with confidence metrics."""

    topic: str
    sources: list[Source]
    findings: str
    confidence: float
    triangulation: float
    verification_status: str = "unverified"
    cache_status: str = "not_cached"
    privacy_export_classification: str = "local_only"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
