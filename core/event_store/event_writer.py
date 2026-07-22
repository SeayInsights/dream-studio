"""WO-SPLIT-STUDIO-DB: event_writer module (split from studio_db.py).

WO-GF-PROJECTION-ENGINE: implementation moved to event_writer_{buffer,approach,
registry,sessions,lessons,hooks}.py; this module re-exports the 22 public
functions plus the 9 `.connection` names it imports (tests patch `_db_path` /
`insert_hook_execution` against this module's path) so existing
`from core.event_store.event_writer import X` callers are unchanged.
"""

from __future__ import annotations

from .connection import (
    _CanonicalEventType,
    _NOW,
    _db_path,
    _db_transaction,
    _reraise_if_busy,
    _try_emit_canonical,
    _with_retry,
    get_connection,
    paths,
)
from .event_writer_approach import capture_approach, insert_approach
from .event_writer_buffer import import_buffer, insert_operational_snapshot, rolling_window_prune
from .event_writer_hooks import (
    clear_expired_sentinels,
    insert_hook_execution,
    log_skill_execution,
    set_sentinel,
)
from .event_writer_lessons import (
    cache_research,
    draft_lesson,
    insert_lesson,
    promote_lesson,
    reject_lesson,
)
from .event_writer_registry import (
    clear_registry,
    update_project_stats,
    upsert_gotcha,
    upsert_project,
)
from .event_writer_sessions import (
    end_session,
    insert_handoff,
    insert_session,
    mark_handoff_consumed,
)

__all__ = [
    "_CanonicalEventType",
    "_NOW",
    "_db_path",
    "_db_transaction",
    "_reraise_if_busy",
    "_try_emit_canonical",
    "_with_retry",
    "cache_research",
    "capture_approach",
    "clear_expired_sentinels",
    "clear_registry",
    "draft_lesson",
    "end_session",
    "get_connection",
    "import_buffer",
    "insert_approach",
    "insert_handoff",
    "insert_hook_execution",
    "insert_lesson",
    "insert_operational_snapshot",
    "insert_session",
    "log_skill_execution",
    "mark_handoff_consumed",
    "paths",
    "promote_lesson",
    "reject_lesson",
    "rolling_window_prune",
    "set_sentinel",
    "update_project_stats",
    "upsert_gotcha",
    "upsert_project",
]
