"""Dispatcher utilities for sequential hook execution."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import time
from pathlib import Path


def load_module(name: str, path: Path):
    """Load a Python module from file path."""
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _log_hook_execution(
    *,
    hook_name: str,
    hook_type: str,
    started_at: str,
    duration_ms: float,
    exit_code: int,
    status: str,
    error_message: str | None,
) -> None:
    """Emit a system.hook.execution.logged canonical event for one dispatched hook.

    WO-HOOK-EXEC-STATS: before this, only on-pulse logged its execution, so the
    per-hook stats surface showed a single hook. Logging here — the one place every
    dispatched hook flows through — covers all hooks uniformly.

    Hot-path safe: fire-and-forget to the spool (insert_hook_execution is
    best-effort with a lock fallback), never raises, and never writes stdout —
    blocking hooks own their stdout (lesson edb8525f), so telemetry must not.
    """
    try:
        from core.event_store.event_writer import insert_hook_execution

        insert_hook_execution(
            hook_name=hook_name.replace("-", "_"),
            hook_type=hook_type,
            trigger_context={},
            started_at=started_at,
            completed_at=_utc_iso(),
            duration_ms=int(duration_ms),
            exit_code=exit_code,
            status=status,
            error_message=error_message,
        )
    except BaseException:
        pass


def write_timing(state_dir: Path, event: str, handler: str, duration_ms: float) -> None:
    """Write hook timing data to JSONL log."""
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "event": event,
            "handler": handler,
            "duration_ms": round(duration_ms, 2),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with (state_dir / "hook-timing.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def execute_handlers(handlers: list[tuple[str, Path]], raw_payload: str, state_dir: Path) -> None:
    """Execute a list of handlers sequentially with shared payload.

    Args:
        handlers: List of (name, path) tuples
        raw_payload: Raw stdin payload to inject before each handler
        state_dir: Directory for timing logs
    """
    run_handlers(handlers, raw_payload, "UserPromptSubmit", state_dir)


def run_handlers(
    handlers: list[tuple[str, Path]], raw_payload: str, event_name: str, state_dir: Path
) -> None:
    """Execute a list of handlers sequentially with shared payload and custom event name.

    Args:
        handlers: List of (name, path) tuples
        raw_payload: Raw stdin payload to inject before each handler
        event_name: Event name for timing logs (e.g., "UserPromptSubmit", "PostToolUse_Edit_Write")
        state_dir: Directory for timing logs
    """
    for name, path in handlers:
        if not path.is_file():
            continue
        ran = False
        started_at = _utc_iso()
        t0 = time.perf_counter()
        status = "success"
        exit_code = 0
        error_message: str | None = None
        try:
            mod = load_module(name.replace("-", "_"), path)
            if mod is None or not hasattr(mod, "main"):
                continue
            ran = True
            sys.stdin = io.StringIO(raw_payload)
            mod.main()
        except SystemExit as exc:
            # A handler that sys.exit()s is not a dispatch failure — record its code.
            code = exc.code
            exit_code = code if isinstance(code, int) else (0 if code is None else 1)
            status = "success" if exit_code == 0 else "failed"
        except BaseException as exc:  # noqa: BLE001 — a hook must never crash dispatch
            status = "failed"
            exit_code = 1
            error_message = str(exc)
        finally:
            sys.stdin = sys.__stdin__
            if ran:
                elapsed = (time.perf_counter() - t0) * 1000
                write_timing(state_dir, event_name, name, elapsed)
                _log_hook_execution(
                    hook_name=name,
                    hook_type=event_name,
                    started_at=started_at,
                    duration_ms=elapsed,
                    exit_code=exit_code,
                    status=status,
                    error_message=error_message,
                )
