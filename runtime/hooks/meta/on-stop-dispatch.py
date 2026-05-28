#!/usr/bin/env python3
"""Dispatcher: Stop — single process for all stop-fired hooks."""

import io
import json
import os
import sys
import time
from pathlib import Path


def _get_plugin_root() -> Path:
    sidecar = Path(__file__).resolve()
    for _ in range(6):
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
    return Path(__file__).resolve().parents[3]


PLUGIN_ROOT = _get_plugin_root()
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))
sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))

_sc_path = str(PLUGIN_ROOT / "runtime")
if _sc_path not in sys.path:
    sys.path.insert(0, _sc_path)

try:
    from session_config import spawn_new_session as _spawn_new_session
except ImportError:
    _spawn_new_session = None

from control.execution.dispatch_helpers import load_module, write_timing  # noqa: E402

HANDLERS: list[tuple[str, Path]] = [
    ("on-session-end", PLUGIN_ROOT / "runtime" / "hooks" / "meta" / "on-session-end.py"),
    ("on-stop-handoff", PLUGIN_ROOT / "runtime" / "hooks" / "core" / "on-stop-handoff.py"),
    ("on-quality-score", PLUGIN_ROOT / "runtime" / "hooks" / "quality" / "on-quality-score.py"),
    ("on-skill-telemetry", PLUGIN_ROOT / "runtime" / "hooks" / "meta" / "on-skill-telemetry.py"),
    ("on-milestone-end", PLUGIN_ROOT / "runtime" / "hooks" / "core" / "on-milestone-end.py"),
    ("on-token-log", PLUGIN_ROOT / "runtime" / "hooks" / "meta" / "on-token-log.py"),
    ("on-meta-review", PLUGIN_ROOT / "runtime" / "hooks" / "meta" / "on-meta-review.py"),
    (
        "on-workflow-progress",
        PLUGIN_ROOT / "runtime" / "hooks" / "core" / "on-workflow-progress.py",
    ),
    ("on-changelog-nudge", PLUGIN_ROOT / "runtime" / "hooks" / "core" / "on-changelog-nudge.py"),
    ("on-memory-ingest", PLUGIN_ROOT / "runtime" / "hooks" / "meta" / "on-memory-ingest.py"),
]

STATE_DIR = Path.home() / ".dream-studio" / "state"


def _dispatch_handoff_continuation() -> None:
    """
    If Claude produced a handoff document (handoff-latest.json) during this
    stop cycle, spawn a new session seeded with the handoff content, then
    clean up the state files.
    """
    if _spawn_new_session is None:
        return

    handoff_file = STATE_DIR / "handoff-latest.json"
    pending_file = STATE_DIR / "pending-handoff.json"

    if not handoff_file.is_file():
        return

    try:
        hd = json.loads(handoff_file.read_text(encoding="utf-8"))
        age = time.time() - hd.get("written_at", 0)

        if age >= 120:
            return

        content = hd.get("content", "")
        if not content:
            return

        pending: dict = {}
        if pending_file.is_file():
            try:
                pending = json.loads(pending_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        flags = pending.get("invocation_flags", [])
        cwd = pending.get("cwd") or os.getcwd()

        safe = content.replace('"', '\\"')
        prompt = f"Continue from handoff: {safe}"
        flags_str = " ".join(flags)
        claude_cmd = f'claude {flags_str} "{prompt}"'.strip()

        _spawn_new_session(claude_cmd, cwd)

        handoff_file.unlink(missing_ok=True)
        pending_file.unlink(missing_ok=True)

    except Exception:
        pass


def main() -> None:
    raw_payload = sys.stdin.read()
    for name, path in HANDLERS:
        if not path.is_file():
            continue
        try:
            mod = load_module(name.replace("-", "_"), path)
            if mod is None or not hasattr(mod, "main"):
                continue
            sys.stdin = io.StringIO(raw_payload)
            t0 = time.perf_counter()
            mod.main()
            write_timing(STATE_DIR, "Stop", name, (time.perf_counter() - t0) * 1000)
        except Exception:
            pass
        finally:
            sys.stdin = sys.__stdin__

    _dispatch_handoff_continuation()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
