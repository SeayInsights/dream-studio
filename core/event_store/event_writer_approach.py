"""event_writer approach group: raw_approaches insert + capture_approach convenience wrapper.

WO-GF-PROJECTION-ENGINE: split from ``core/event_store/event_writer.py``.
LANDMINE #1: tests/integration/test_approach_capture.py patches
``core.event_store.event_writer_approach._db_path`` (moved here — capture_approach
calls it by bare name).
"""

from __future__ import annotations
from datetime import datetime
from pathlib import Path

from .connection import (
    _CanonicalEventType,
    _NOW,
    _db_path,
    _db_transaction,
    _reraise_if_busy,
    _try_emit_canonical,
    _with_retry,
    paths,
)


@_with_retry
def insert_approach(
    skill_id: str,
    approach: str,
    outcome: str,
    *,
    context: str = "",
    why: str = "",
    tokens_used: int | None = None,
    duration_s: float | None = None,
    model: str | None = None,
    session_date: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        if db_path is not None and not Path(db_path).parent.exists():
            return False
        with _db_transaction(db_path) as c:
            c.execute(
                """INSERT INTO raw_approaches
                   (skill_id, session_date, approach, outcome, context,
                    why_worked, tokens_used, duration_s, model, captured_at,
                    project_id, session_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    skill_id,
                    session_date or _NOW()[:10],
                    approach,
                    outcome,
                    context or None,
                    why or None,
                    tokens_used,
                    duration_s,
                    model,
                    _NOW(),
                    project_id,
                    session_id,
                ),
            )

            # Event emission (additive side-effect) — TA0c: activity_log retired
            _try_emit_canonical(
                _CanonicalEventType.APPROACH_CAPTURED,
                {
                    "skill_id": skill_id,
                    "approach": approach,
                    "outcome": outcome,
                    "model": model,
                    "duration_s": duration_s,
                    "tokens_used": tokens_used,
                },
                session_id=session_id,
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def capture_approach(
    skill: str,
    approach: str,
    outcome: str,
    context: str = "",
    why: str = "",
) -> bool:
    """High-level convenience: write approach to DB, fall back to text file."""
    ok = insert_approach(skill, approach, outcome, context=context, why=why, db_path=_db_path())
    if not ok:
        try:
            fallback = paths.meta_dir() / "approaches.log"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%H:%M")
            with open(fallback, "a", encoding="utf-8") as f:
                f.write(f"{ts} | approach:{skill} | {outcome} | {approach}\n")
            return True
        except Exception:
            return False
    return True
