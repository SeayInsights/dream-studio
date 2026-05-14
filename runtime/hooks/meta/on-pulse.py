#!/usr/bin/env python3
"""Hook: on-pulse — proactive cross-project health check."""

import sys
import time
from pathlib import Path
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
