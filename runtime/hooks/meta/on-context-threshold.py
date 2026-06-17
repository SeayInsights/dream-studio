"""
Context threshold handler.

Monitors session JSONL size and context_window.used_percentage.
Prints an urgent /compact reminder at the urgent threshold (never blocks the prompt) and
a growing warning in the warn band. The KB fallback subtracts a post-compact baseline so a
large append-only JSONL does not read as urgent after a /compact.
Uses control.context.monitor for all threshold logic.
Never calls sys.exit() inside main() — all early exits are returns.
"""

import json
import os
import sys
from pathlib import Path

# --- resolve installed layout ---
# Installed path: ~/.claude/hooks/runtime/hooks/meta/on-context-threshold.py
_meta_dir = Path(__file__).parent
_runtime_dir = _meta_dir.parent.parent  # ~/.claude/hooks/runtime/
if str(_runtime_dir) not in sys.path:
    sys.path.insert(0, str(_runtime_dir))


def _emit_harvest(session_id: str, context_kb: float = 0.0) -> None:
    """Emit a session harvest event to the spool (best-effort, never raises)."""
    try:
        repo = _get_plugin_root()
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        import spool.writer as _writer  # noqa: PLC0415
        from canonical.events.envelope import CanonicalEventEnvelope  # noqa: PLC0415

        _writer.write_event(
            CanonicalEventEnvelope(
                event_type="session.harvested",
                session_id=session_id,
                payload={"context_kb": context_kb},
                severity="info",
            ).to_dict()
        )
    except Exception:
        pass


def _get_plugin_root() -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).resolve()
    sidecar = _runtime_dir.parent / ".plugin-root"
    if sidecar.is_file():
        try:
            return Path(sidecar.read_text(encoding="utf-8").strip()).resolve()
        except Exception:
            pass
    return Path(__file__).resolve().parents[4]


try:
    from session_config import read_session_config  # type: ignore[import]
except ImportError:
    _repo = _get_plugin_root()
    if str(_repo) not in sys.path:
        sys.path.insert(0, str(_repo))
    try:
        from runtime.session_config import read_session_config  # type: ignore[import]
    except ImportError:

        def read_session_config(session_id: str) -> dict:  # type: ignore[misc]
            return {}


def _load_monitor():
    repo = _get_plugin_root()
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from control.context import monitor  # noqa: PLC0415

    return monitor


def main() -> None:
    raw = sys.stdin.read().lstrip("﻿") or "{}"
    try:
        data = json.loads(raw)
    except Exception:
        data = {}

    session_id = data.get("session_id") or (data.get("session") or {}).get("id") or ""
    if not session_id:
        return

    cwd = Path(data.get("cwd") or os.getcwd())

    try:
        monitor = _load_monitor()
    except Exception:
        return

    projects = monitor.projects_dir_for_cwd(cwd)

    # Determine context level: bridge pct (accurate) with JSONL size as fallback.
    # The KB fallback subtracts a post-compact baseline (see monitor.session_kb) so a
    # large append-only JSONL no longer reads as "urgent" after a /compact.
    bridge_pct = monitor.read_bridge_pct(session_id)
    using_pct = bridge_pct is not None

    if using_pct:
        band, label = monitor.pct_to_band(bridge_pct)
    else:
        kb = monitor.session_kb(projects, session_id)
        if kb == 0.0:
            return
        # KB-fallback band. kb_to_band scales its thresholds to the active context
        # window (WO-CONTEXT-THRESHOLD-SCALE); db_path defaults to the live authority,
        # where the context.window_tokens override (if any) is read — so on the 1M model
        # this no longer trips 'handoff'/'compact' at ~50%.
        band, label = monitor.kb_to_band(kb, db_path=None)

    if band == "ok":
        return

    if band == "urgent":
        monitor.handle_urgent_reminder(projects, session_id, label)
    elif band == "handoff":
        kb_val = bridge_pct if using_pct else kb
        monitor.handle_handoff(projects, session_id, cwd, label, kb_val, using_pct)
    elif band == "compact":
        monitor.handle_compact_warning(projects, session_id, label)
    elif band == "warn":
        monitor.handle_warn(projects, session_id, label, bridge_pct if using_pct else None)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
