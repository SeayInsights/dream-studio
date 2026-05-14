#!/usr/bin/env python3
"""Hook: on-context-threshold — warn, auto-handoff, or block when context fills."""

import json
import os
import sys
from pathlib import Path

from control.context import monitor as context_monitor
from core.config import paths  # noqa: E402


def main() -> None:
    try:
        p = json.loads(sys.stdin.read())
        sid, cwd = p.get("session_id"), Path(p.get("cwd") or paths.project_root())
    except Exception:
        return
    is_compact, projects, boost = (
        os.environ.get("CLAUDE_USER_MESSAGE_TEXT", "").lower().startswith("/compact"),
        context_monitor.projects_dir_for_cwd(cwd),
        context_monitor.milestone_boost(),
    )
    pct = context_monitor.read_bridge_pct(sid)
    if pct is not None:
        band, _ = context_monitor.pct_to_band(max(0, pct - boost))
        label, using_pct, kb_val = f"~{pct:.0f}%", True, pct
    else:
        kb = context_monitor.session_kb(projects, sid)
        if kb <= 0:
            return
        band, _ = context_monitor.kb_to_band(max(0, kb - boost * context_monitor.HANDOFF_KB / 100))
        label, using_pct, kb_val = f"~{kb:.0f} KB", False, kb
    sentinel = context_monitor.sentinel(projects, sid, "compact")
    if band == "ok" or sentinel.exists():
        sentinel.unlink(missing_ok=True)
    elif band == "urgent":
        context_monitor.handle_urgent_block(projects, sid, label)
    elif not context_monitor.handle_compact_cooldown(projects, sid, is_compact):
        if band == "handoff":
            context_monitor.handle_handoff(projects, sid, cwd, label, kb_val, using_pct)
        elif band == "compact":
            context_monitor.handle_compact_warning(projects, sid, label)
        elif band == "warn":
            context_monitor.handle_warn(projects, sid, label, pct)


if __name__ == "__main__":
    main()
