#!/usr/bin/env python3
"""Hook: on-skill-complete — advisory chain-suggest after skill invocation."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _get_plugin_root() -> Path:
    sidecar = Path(__file__).resolve()
    for _ in range(8):
        candidate = sidecar / ".plugin-root"
        if candidate.is_file():
            try:
                return Path(candidate.read_text(encoding="utf-8").strip()).resolve()
            except Exception:
                pass
        sidecar = sidecar.parent
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[4]


_PLUGIN_ROOT = _get_plugin_root()
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))
if str(_PLUGIN_ROOT / "hooks") not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))

from control.skills.calibration import record_outcome  # noqa: E402
from control.skills import completion as skill_completion  # noqa: E402
from core.event_store import studio_db  # noqa: E402
from core.sdlc.cwd_resolver import resolve_project_from_cwd  # noqa: E402


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
        ctx = resolve_project_from_cwd()
        project_id = ctx.project_id if ctx is not None else None
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
