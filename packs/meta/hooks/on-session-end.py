#!/usr/bin/env python3
"""Hook: on-session-end — close out the session row on Stop event.

Trigger: Stop (fires before on-stop-handoff so session is ended first).

Reads session_id from the Stop payload. Calls end_session() to set
ended_at, duration_s, and token totals if present in the payload.
A sentinel prevents double-firing if Stop fires more than once.

Exits 0 always — tracking failure must never block session end.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))

from lib.studio_db import end_session, has_sentinel, set_sentinel, _connect  # noqa: E402


def validate_session_research(session_id: str) -> None:
    """Validate all research from this session based on session outcome.

    Args:
        session_id: The session identifier

    Session success heuristic:
        1. Check raw_sessions.outcome if available ('success' = successful)
        2. Fallback: check task completion ratio (completed >= 0)
        3. Default: assume successful (optimistic MVP approach)

    Trust score adjustments (via trigger):
        - Validated: trust_score += 0.1
        - Rejected: trust_score -= 0.2
    """
    try:
        with _connect() as conn:
            cursor = conn.cursor()

            # Determine session success
            is_successful = True  # Default optimistic

            # Check if raw_sessions has an outcome for this session
            outcome_row = cursor.execute(
                "SELECT outcome FROM raw_sessions WHERE session_id = ? LIMIT 1",
                (session_id,)
            ).fetchone()

            if outcome_row and outcome_row[0]:
                is_successful = outcome_row[0].lower() == 'success'
            else:
                # Fallback: check task completion ratio
                task_stats = cursor.execute(
                    "SELECT tasks_completed FROM raw_sessions WHERE session_id = ? LIMIT 1",
                    (session_id,)
                ).fetchone()

                if task_stats and task_stats[0] is not None:
                    # Simple heuristic: if we completed any tasks, consider successful
                    is_successful = task_stats[0] > 0

            # Get all pending research from this session
            pending_research = cursor.execute(
                """
                SELECT research_id, source_url, trust_score
                FROM raw_research
                WHERE session_id = ? AND validation_status = 'pending'
                """,
                (session_id,)
            ).fetchall()

            if not pending_research:
                return  # No research to validate

            # Update validation status based on session outcome
            new_status = 'validated' if is_successful else 'rejected'

            for row in pending_research:
                research_id = row[0]
                current_trust = row[2] or 0.5

                # Calculate new trust score (trigger will also adjust source trust)
                if is_successful:
                    new_trust = min(current_trust + 0.1, 1.0)
                else:
                    new_trust = max(current_trust - 0.2, 0.0)

                cursor.execute(
                    """
                    UPDATE raw_research
                    SET validation_status = ?,
                        trust_score = ?,
                        validated_by = ?,
                        validated_at = datetime('now')
                    WHERE research_id = ?
                    """,
                    (new_status, new_trust, session_id, research_id)
                )

            conn.commit()

    except Exception:
        # Don't break session cleanup on research validation errors
        pass


def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    session_id = payload.get("session_id", "")
    if not session_id:
        return

    sentinel_key = f"session-ended-{session_id}"
    if has_sentinel(sentinel_key):
        return

    input_tokens: int | None = None
    output_tokens: int | None = None
    if "prompt_tokens" in payload:
        input_tokens = payload.get("prompt_tokens")
        output_tokens = payload.get("completion_tokens")

    try:
        end_session(
            session_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    except Exception:
        pass

    # Validate research from this session
    try:
        validate_session_research(session_id)
    except Exception:
        pass

    try:
        set_sentinel(sentinel_key, "session")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
