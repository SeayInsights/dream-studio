"""
Context threshold handler.
At 75% normalized context usage: harvest session state, then spawn
a fresh Claude Code session that inherits invocation flags.
Never blocks execution.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

# --- resolve session_config via installed layout ---
# Installed path: ~/.claude/hooks/runtime/hooks/meta/on-context-threshold.py
# session_config:  ~/.claude/hooks/runtime/session_config.py  (2 levels up from meta/)
_meta_dir = Path(__file__).parent
_runtime_dir = _meta_dir.parent.parent  # ~/.claude/hooks/runtime/
if str(_runtime_dir) not in sys.path:
    sys.path.insert(0, str(_runtime_dir))

# Fallback: resolve via .plugin-root sidecar for repo imports
def _get_plugin_root() -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).resolve()
    sidecar = _runtime_dir.parent / ".plugin-root"  # ~/.claude/hooks/.plugin-root
    if sidecar.is_file():
        try:
            return Path(sidecar.read_text(encoding="utf-8").strip()).resolve()
        except Exception:
            pass
    return Path(__file__).resolve().parents[4]


try:
    from session_config import read_session_config
except ImportError:
    repo = _get_plugin_root()
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    try:
        from runtime.session_config import read_session_config
    except ImportError:
        def read_session_config(session_id: str) -> dict:  # type: ignore[misc]
            return {}

HARVEST_THRESHOLD = 75.0
COMPACT_THRESHOLD = 83.0
_SPAWN_LOCK_SECONDS = 300


def _bridge_pct(session_id: str) -> float | None:
    try:
        bp = Path(tempfile.gettempdir()) / f"claude-ctx-{session_id}.json"
        if bp.is_file():
            data = json.loads(bp.read_text(encoding="utf-8"))
            if time.time() - data.get("timestamp", 0) < 120:
                return float(data.get("used_pct", data.get("raw_pct", 0)))
    except Exception:
        pass
    return None


def _already_spawned(session_id: str) -> bool:
    lock = Path(tempfile.gettempdir()) / f"claude-spawn-lock-{session_id}.json"
    if lock.is_file():
        try:
            data = json.loads(lock.read_text(encoding="utf-8"))
            if time.time() - data.get("timestamp", 0) < _SPAWN_LOCK_SECONDS:
                return True
        except Exception:
            pass
    return False


def _write_spawn_lock(session_id: str) -> None:
    lock = Path(tempfile.gettempdir()) / f"claude-spawn-lock-{session_id}.json"
    lock.write_text(json.dumps({"timestamp": int(time.time())}), encoding="utf-8")


def _emit_harvest(session_id: str, normalized_pct: float, raw_pct: float) -> None:
    try:
        repo = _get_plugin_root()
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        from spool.emitter import emit
        emit("ds_session_harvest", {
            "session_id": session_id,
            "trigger": "context_threshold",
            "normalized_pct": round(normalized_pct, 1),
            "raw_pct": round(raw_pct, 1),
            "timestamp": int(time.time()),
        })
    except Exception:
        pass


def _write_pending_handoff(session_id: str, session_config: dict) -> None:
    state_dir = Path.home() / ".dream-studio" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    pending = state_dir / "pending-handoff.json"
    pending.write_text(json.dumps({
        "session_id": session_id,
        "triggered_at": int(time.time()),
        "cwd": session_config.get("cwd", ""),
        "invocation_flags": session_config.get("invocation_flags", []),
        "status": "pending",
    }), encoding="utf-8")


def main() -> None:
    raw = sys.stdin.read() or "{}"
    data = json.loads(raw)

    session_id = (
        data.get("session_id")
        or (data.get("session") or {}).get("id")
        or ""
    )
    used = (data.get("context_window") or {}).get("used_percentage")

    if not session_id:
        sys.exit(0)

    if used is None:
        normalized = _bridge_pct(session_id)
        if normalized is None:
            sys.exit(0)
        raw_pct = normalized * COMPACT_THRESHOLD / 100.0
    else:
        raw_pct = float(used)
        normalized = min(100.0, raw_pct * 100.0 / COMPACT_THRESHOLD)

    if normalized < HARVEST_THRESHOLD:
        sys.exit(0)

    if _already_spawned(session_id):
        sys.exit(0)

    # Emit harvest event
    _emit_harvest(session_id, normalized, raw_pct)

    # Write spawn lock to prevent double-triggering
    _write_spawn_lock(session_id)

    # Write pending-handoff.json; on-prompt-validate will inject the handoff
    # skill instruction into the next user message, and on-stop-dispatch will
    # spawn the continuation window after the handoff document is written.
    session_config = read_session_config(session_id)
    try:
        _write_pending_handoff(session_id, session_config)
    except Exception:
        pass

    print(
        "\n[Dream Studio] Context at 75% — "
        "preparing handoff for continuation session. "
        "Finish your current thought.",
        flush=True,
    )

    sys.exit(0)


if __name__ == "__main__":
    main()
