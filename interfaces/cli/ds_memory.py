"""ds memory subcommands (Slice 5d) — session history and planning ingest.

WO-GF-CLI-split: this module is now a thin facade. The command set is
partitioned into three content siblings — ``ds_memory_ingest`` (the `ingest`
extraction passes), ``ds_memory_sessions`` (`ingest-sessions` Claude Code
session harvest), and ``ds_memory_entries`` (`ingest-entries`/`ingest-status`/
`dedup-orphans` memory_entries maintenance) — wired together by
``ds_memory_dispatch.add_memory_subcommand`` (there is no ``dispatch()``;
routing is via ``set_defaults(func=cmd_X)``). Every public and private name
that used to live here is re-exported below so existing imports
(``interfaces.cli.ds_memory.<name>``) keep working unchanged.
"""

from __future__ import annotations

from interfaces.cli.ds_memory_dispatch import add_memory_subcommand
from interfaces.cli.ds_memory_entries import (
    cmd_memory_dedup_orphans,
    cmd_memory_ingest_entries,
    cmd_memory_ingest_status,
)
from interfaces.cli.ds_memory_ingest import (
    REPO_ROOT,
    _ARCH_PATTERNS,
    _DATE_ANYWHERE_RE,
    _DATE_IN_PATH_RE,
    _SEVERITY_CRITICAL_RE,
    _SEVERITY_HIGH_RE,
    _SKILL_KEYWORDS,
    _TRIGGER_RE,
    _collect_architecture_files,
    _collect_handoff_recap_files,
    _connect_docs,
    _discover_date_from_path,
    _extract_fix,
    _find_gotcha_blocks,
    _find_latest_handoff,
    _find_project_id,
    _infer_severity,
    _infer_skill_id,
    _now_iso,
    _pass1_gotchas,
    _pass2_architecture,
    _pass3_session_handoffs,
    _slugify,
    cmd_memory_ingest,
    run_memory_ingest,
)
from interfaces.cli.ds_memory_sessions import _CONSENT_TEXT, cmd_memory_ingest_sessions

__all__ = [
    # Registration
    "add_memory_subcommand",
    # ds_memory_ingest
    "REPO_ROOT",
    "_TRIGGER_RE",
    "_DATE_IN_PATH_RE",
    "_DATE_ANYWHERE_RE",
    "_SKILL_KEYWORDS",
    "_SEVERITY_CRITICAL_RE",
    "_SEVERITY_HIGH_RE",
    "_ARCH_PATTERNS",
    "_connect_docs",
    "_slugify",
    "_infer_skill_id",
    "_infer_severity",
    "_discover_date_from_path",
    "_extract_fix",
    "_find_gotcha_blocks",
    "_collect_handoff_recap_files",
    "_collect_architecture_files",
    "_find_latest_handoff",
    "_find_project_id",
    "_now_iso",
    "_pass1_gotchas",
    "_pass2_architecture",
    "_pass3_session_handoffs",
    "run_memory_ingest",
    "cmd_memory_ingest",
    # ds_memory_sessions
    "_CONSENT_TEXT",
    "cmd_memory_ingest_sessions",
    # ds_memory_entries
    "cmd_memory_ingest_entries",
    "cmd_memory_ingest_status",
    "cmd_memory_dedup_orphans",
]
