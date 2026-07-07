"""SQLite analytics backend for dream-studio — facade over the split modules.

WO-SPLIT-STUDIO-DB: implementation moved to connection / migration_runner /
event_writer / event_reader; this module re-exports the public API so every
`from core.event_store.studio_db import X` caller is unchanged.
"""

from __future__ import annotations

# Backward-compat re-exports: external callers (production + tests) historically
# imported/accessed these private helpers and connection primitives directly from
# studio_db. The facade preserves the ENTIRE original namespace so it is a drop-in
# replacement (WO-SPLIT-STUDIO-DB).
from .connection import (  # noqa: F401
    _NOW,
    _connect,
    _db_path,
    _db_transaction,
    _get_event_store,
    _reraise_if_busy,
    _try_emit_canonical,
    _with_retry,
    get_connection,
    transaction,
)
from .migration_runner import (  # noqa: F401
    _migrations_dir,
    _run_migrations,
    _split_statements,
)

from .event_writer import (
    cache_research,
    capture_approach,
    clear_expired_sentinels,
    clear_registry,
    draft_lesson,
    end_session,
    import_buffer,
    insert_approach,
    insert_handoff,
    insert_hook_execution,
    insert_lesson,
    insert_operational_snapshot,
    insert_session,
    log_skill_execution,
    mark_handoff_consumed,
    promote_lesson,
    reject_lesson,
    rolling_window_prune,
    set_sentinel,
    update_project_stats,
    upsert_gotcha,
    upsert_project,
)
from .event_reader import (
    get_approach_patterns,
    get_best_approaches,
    get_gotchas_for_skill,
    get_handoffs_for_project,
    get_latest_handoff,
    get_latest_session,
    get_latest_unconsumed_handoff,
    get_lessons,
    get_pending_lessons,
    get_project,
    get_research_by_prd,
    get_research_by_task,
    get_research_cache,
    get_session,
    get_skill_summaries,
    has_sentinel,
    last_run,
    list_projects,
    run_count,
    search_gotchas_db,
)
from .migration_runner import (
    main,
    schema_version,
)

__all__ = [
    "cache_research",
    "capture_approach",
    "clear_expired_sentinels",
    "clear_registry",
    "draft_lesson",
    "end_session",
    "get_approach_patterns",
    "get_best_approaches",
    "get_gotchas_for_skill",
    "get_handoffs_for_project",
    "get_latest_handoff",
    "get_latest_session",
    "get_latest_unconsumed_handoff",
    "get_lessons",
    "get_pending_lessons",
    "get_project",
    "get_research_by_prd",
    "get_research_by_task",
    "get_research_cache",
    "get_session",
    "get_skill_summaries",
    "has_sentinel",
    "import_buffer",
    "insert_approach",
    "insert_handoff",
    "insert_hook_execution",
    "insert_lesson",
    "insert_operational_snapshot",
    "insert_session",
    "last_run",
    "list_projects",
    "log_skill_execution",
    "main",
    "mark_handoff_consumed",
    "promote_lesson",
    "reject_lesson",
    "rolling_window_prune",
    "run_count",
    "schema_version",
    "search_gotchas_db",
    "set_sentinel",
    "update_project_stats",
    "upsert_gotcha",
    "upsert_project",
]

if __name__ == "__main__":
    main()
