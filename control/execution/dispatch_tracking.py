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
        try:
            mod = load_module(name.replace("-", "_"), path)
            if mod is None or not hasattr(mod, "main"):
                continue
            sys.stdin = io.StringIO(raw_payload)
            t0 = time.perf_counter()
            mod.main()
            elapsed = (time.perf_counter() - t0) * 1000
            write_timing(state_dir, event_name, name, elapsed)
        except Exception:
            pass
        finally:
            sys.stdin = sys.__stdin__
