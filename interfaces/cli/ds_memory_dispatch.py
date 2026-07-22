"""ds memory — subcommand parser registration.

Split from interfaces/cli/ds_memory.py (WO-GF-CLI-split). Routing for `ds
memory` is via ``set_defaults(func=cmd_X)`` (no dispatch() function) — this
module just wires the `memory` subparser tree onto the parent parser and
points each leaf subcommand at its implementation in ds_memory_ingest,
ds_memory_sessions, or ds_memory_entries.
"""

from __future__ import annotations

from interfaces.cli.ds_memory_entries import (
    cmd_memory_dedup_orphans,
    cmd_memory_ingest_entries,
    cmd_memory_ingest_status,
)
from interfaces.cli.ds_memory_ingest import cmd_memory_ingest
from interfaces.cli.ds_memory_sessions import cmd_memory_ingest_sessions


def add_memory_subcommand(subparsers) -> None:
    """Register the 'memory' subcommand group onto the parent parser."""
    memory_parser = subparsers.add_parser("memory", help="Memory intelligence commands")
    memory_sub = memory_parser.add_subparsers(dest="memory_cmd", required=True)

    ingest = memory_sub.add_parser(
        "ingest", help="Ingest session history and planning files into SQLite"
    )
    ingest.add_argument("--project", default=None, help="Scope to a single project name")
    ingest.add_argument(
        "--sessions-dir",
        default=None,
        dest="sessions_dir",
        help="Override default ~/.sessions/ location",
    )
    ingest.add_argument(
        "--planning-dir",
        default=None,
        dest="planning_dir",
        help="Override default ~/.planning/ location",
    )
    ingest.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report what would be ingested without writing",
    )
    ingest.set_defaults(func=cmd_memory_ingest)

    ingest_sessions = memory_sub.add_parser(
        "ingest-sessions",
        help="Harvest intelligence from Claude Code session history in ~/.claude/projects/",
    )
    ingest_sessions.add_argument(
        "--claude-projects-dir",
        default=None,
        dest="claude_projects_dir",
        help="Override default ~/.claude/projects/ location",
    )
    ingest_sessions.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report counts without writing to DB",
    )
    ingest_sessions.add_argument(
        "--no-consent-prompt",
        action="store_true",
        default=False,
        dest="no_consent_prompt",
        help="Skip consent prompt (for automated testing only)",
    )
    ingest_sessions.set_defaults(func=cmd_memory_ingest_sessions)

    ingest_entries = memory_sub.add_parser(
        "ingest-entries",
        help="Sync reg_gotchas, raw_lessons, corrections, and decisions into memory_entries (Chain 7)",
    )
    ingest_entries.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report counts without writing to DB",
    )
    ingest_entries.set_defaults(func=cmd_memory_ingest_entries)

    ingest_status = memory_sub.add_parser(
        "ingest-status",
        help="Show last automated memory ingestion run (from ~/.dream-studio/state/memory-ingest-last-run.json)",
    )
    ingest_status.set_defaults(func=cmd_memory_ingest_status)

    dedup_parser = memory_sub.add_parser(
        "dedup-orphans",
        help="Remove NULL-source_type memory_entries that have a content-matched keyed counterpart",
    )
    dedup_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete (default: dry-run, count only)",
    )
    dedup_parser.set_defaults(func=cmd_memory_dedup_orphans)
