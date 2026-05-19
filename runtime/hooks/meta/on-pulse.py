#!/usr/bin/env python3
"""Hook: on-pulse — proactive cross-project health check."""

import os
import sys
import time
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

from interfaces.cli.pulse_collector import run_pulse_check  # noqa: E402
from core.event_store.studio_db import insert_hook_execution  # noqa: E402
from core.utils.time import utcnow  # noqa: E402


def main() -> None:
    """Wrapper that tracks execution of the pulse check."""
    started_at = utcnow().isoformat()
    start_time = time.time()
    hook_status = "success"
    error_msg = None
    try:
        run_pulse_check()
    except Exception as e:
        hook_status = "failed"
        error_msg = str(e)
        raise
    finally:
        duration_ms = int((time.time() - start_time) * 1000)
        completed_at = utcnow().isoformat()
        try:
            insert_hook_execution(
                hook_name="on_pulse",
                hook_type="periodic",
                trigger_context={},
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                exit_code=0 if hook_status == "success" else 1,
                status=hook_status,
                error_message=error_msg,
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
