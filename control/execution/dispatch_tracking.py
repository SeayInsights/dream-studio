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
            # A REGISTERED HANDLER WITH NO FILE IS A BROKEN INSTALL, NOT A CHOICE.
            #
            # This was a bare `continue`, and I defended it as "absence is configuration"
            # when narrowing WO becfca00. That reading does not survive contact with
            # `_resolve_handlers`, which HARDCODES the list: nothing here is optional, so a
            # missing file cannot mean "not configured", only "the install is incomplete".
            # The independent review of WO 2fde7846 objected to that narrowing and was
            # right; task 5 of that work order asks for exactly this record.
            #
            # 07b9d3f7 shipped this and I reverted it in 54d95bfb because its stated cause
            # -- that this silence was how three skill handlers went dark -- was asserted
            # without evidence, and was in fact wrong (the cause was a partial installed
            # `control` package shadowing the repo's). The revert threw out a sound
            # mechanism along with an unsound reason for it. The reason now is evidenced
            # and different: the installer has NO delete op, so a renamed or dropped
            # handler leaves a stale tree behind and a missing file is a state this
            # codebase actually produces.
            _log_hook_execution(
                hook_name=name,
                hook_type=event_name,
                started_at=_utc_iso(),
                duration_ms=0.0,
                exit_code=1,
                status="not_found",
                error_message=f"handler file does not exist: {path}",
            )
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
                # A FILE THAT IS THERE AND WILL NOT LOAD IS A BROKEN HANDLER, NOT AN
                # ABSENT ONE. This was `continue`, which left `ran` False, so the
                # `finally` below logged nothing: no timing line, no execution row, no
                # error. Measured cost (WO becfca00): on-skill-complete, on-skill-metrics,
                # on-skill-load and on-skill-telemetry raised ModuleNotFoundError on every
                # dispatch and produced ZERO execution rows in their entire lifetime --
                # the skill telemetry was not degraded, it was severed, and nothing could
                # say so.
                status = "failed"
                exit_code = 1
                error_message = (
                    "handler could not be loaded" if mod is None else "handler defines no main()"
                )
            else:
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
            elapsed = (time.perf_counter() - t0) * 1000
            # TIMING STAYS EXECUTION-ONLY -- it measures how long a handler took to run,
            # and one that never ran has no runtime to report. The EXECUTION RECORD is
            # emitted either way, because "it failed" and "it was never reached" are
            # different facts and only one of them is actionable.
            if ran:
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
