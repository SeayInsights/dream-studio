"""Token consumption projection — ai_canonical_events → token_usage_records.

Reads token.consumed events from the ai canonical store and materializes them
into token_usage_records for the token analytics dashboard module.

Idempotency: INSERT OR IGNORE with token_usage_id = event_id ensures each
canonical event produces exactly one record regardless of how many times the
projection is replayed.
"""

from __future__ import annotations

import logging
from typing import Any

from core.projections.framework import Projection

logger = logging.getLogger(__name__)


class TokenConsumptionProjection(Projection):
    name = "token_consumption_projection"
    consumed_event_types = ["token.consumed"]
    source_canonical = "ai"
    target_tables = ["token_usage_records"]

    def setup_tables(self, conn: Any) -> None:
        pass  # DDL owned by migrations 037, 042, 081, 105

    def handle(self, event: dict[str, Any], conn: Any) -> int:
        event_id = event.get("event_id")
        if not event_id:
            return 0

        payload = event.get("payload") or {}
        trace = event.get("trace") or {}

        input_tokens = int(payload.get("input_tokens") or 0)
        output_tokens = int(payload.get("output_tokens") or 0)
        cache_creation = int(payload.get("cache_creation_input_tokens") or 0)
        cache_read = int(payload.get("cache_read_input_tokens") or 0)
        total_tokens = input_tokens + output_tokens + cache_creation + cache_read

        project_id = trace.get("project_id") or event.get("project_id")
        milestone_id = trace.get("milestone_id")
        task_id = trace.get("task_id")
        agent_id = trace.get("agent_id")
        skill_id = trace.get("skill_id")
        workflow_id = trace.get("workflow_id")
        hook_id = trace.get("hook_id")
        model_id = payload.get("model") or event.get("model_id")

        conn.execute(
            """
            INSERT OR IGNORE INTO token_usage_records (
                token_usage_id, project_id, milestone_id, task_id,
                agent_id, skill_id, workflow_id, hook_id, model_id,
                input_tokens, output_tokens, cached_tokens, cache_read_tokens,
                total_tokens, purpose, source_refs_json, evidence_refs_json
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, '[]', '[]'
            )
            """,
            (
                event_id,
                project_id,
                milestone_id,
                task_id,
                agent_id,
                skill_id,
                workflow_id,
                hook_id,
                model_id,
                input_tokens,
                output_tokens,
                cache_creation,
                cache_read,
                total_tokens,
                payload.get("granularity"),
            ),
        )
        return 1
