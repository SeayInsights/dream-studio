#!/usr/bin/env python3
"""Hook: on-skill-complete — advisory chain-suggest after skill invocation."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from control.skills.calibration import record_outcome  # noqa: E402
from control.skills import completion as skill_completion  # noqa: E402
from core.event_store import studio_db  # noqa: E402


def _model_label() -> str:
    """Return adapter/tool metadata without making one provider canonical."""
    return os.environ.get("DREAM_STUDIO_MODEL") or os.environ.get("CLAUDE_MODEL") or "unspecified"


def main() -> None:
    # Parse skill invocation payload
    raw_input = sys.stdin.read()
    skill_name, skill_args = skill_completion.parse_skill_payload(raw_input)
    if not skill_name:
        return

    # Try to extract session_id from payload for activity_log linkage
    session_id = None
    project_id = None
    try:
        payload = json.loads(raw_input)
        session_id = payload.get("session_id")
        project_id = Path.cwd().name
    except Exception:
        pass

    # TC-007: Log skill execution to activity_log via EventNormalizer
    try:
        studio_db.log_skill_execution(
            skill_name=skill_name,
            skill_args=skill_args,
            status="success",  # Assume success if hook fired (future: parse outcome)
            model=_model_label(),
            session_id=session_id,
            project_id=project_id,
        )
    except Exception:
        pass  # Fire-and-forget - don't fail the hook

    # Original calibration logic (unchanged)
    try:
        record_outcome(skill_name, "unknown", "success", 0.0, 0)
    except Exception:
        pass

    # Original chain suggestion logic (unchanged)
    plugin_root = Path(__file__).resolve().parents[3]
    skill_dir = skill_completion.locate_skill_dir(skill_name, skill_args, plugin_root)
    if skill_dir:
        skill_completion.process_chain_suggests(skill_name, skill_dir)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
