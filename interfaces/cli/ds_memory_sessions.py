"""ds memory ingest-sessions — Claude Code session-history harvest.

Split from interfaces/cli/ds_memory.py (WO-GF-CLI-split). Owns the
`ds memory ingest-sessions` command (consent-gated harvest of
~/.claude/projects/ session history via ``spool.session_harvester``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from interfaces.cli.ds_memory_ingest import REPO_ROOT

_CONSENT_TEXT = """\
Dream Studio will scan your Claude Code session history in:
  {claude_projects_dir}

It will extract derived metadata only:
  - Error->fix patterns (gotchas)
  - Skill invocation records
  - Architecture document paths (not content)
  - File type usage counts

Raw conversation content, prompts, assistant responses, and file contents
are NEVER stored.

Type 'yes' to proceed, or press Enter to cancel: """


def cmd_memory_ingest_sessions(args) -> int:
    """Entry point for `ds memory ingest-sessions`."""
    import os

    if args.claude_projects_dir:
        claude_projects_dir = Path(args.claude_projects_dir)
    else:
        if sys.platform == "win32":
            user_profile = os.environ.get("USERPROFILE", str(Path.home()))
            claude_projects_dir = Path(user_profile) / ".claude" / "projects"
        else:
            claude_projects_dir = Path.home() / ".claude" / "projects"

    dry_run: bool = getattr(args, "dry_run", False)
    no_consent_prompt: bool = getattr(args, "no_consent_prompt", False)

    if not no_consent_prompt:
        print(_CONSENT_TEXT.format(claude_projects_dir=claude_projects_dir), end="")
        try:
            answer = input()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 0
        if answer.strip().lower() != "yes":
            print("Cancelled.")
            return 0

    try:
        from core.installed_runtime import resolve_installed_runtime_paths

        paths = resolve_installed_runtime_paths(source_root=REPO_ROOT, dream_studio_home=None)
        db_path = paths.sqlite_path
    except Exception:
        db_path = Path.home() / ".dream-studio" / "state" / "studio.db"

    try:
        from spool.session_harvester import SessionHarvester

        harvester = SessionHarvester()
        result = harvester.harvest(
            claude_projects_dir=claude_projects_dir,
            db_path=db_path,
            dry_run=dry_run,
            consent=not dry_run,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    label = "[dry-run] " if dry_run else ""
    print(f"\n{label}Session harvest complete:")
    print(f"  Gotchas extracted:    {result.gotchas_new} new, {result.gotchas_skipped} skipped")
    print(
        f"  Skill approaches:     {result.approaches_new} new, {result.approaches_skipped} skipped"
    )
    print(f"  Architecture docs:    {result.arch_docs_found} found")
    print(f"  Sessions processed:   {result.sessions_processed}")
    print(f"  Sessions skipped:     {result.sessions_skipped}")
    return 0
