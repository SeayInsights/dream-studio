"""Helper functions for hook dispatchers (on-*-dispatch.py hooks)."""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path


def load_module(name: str, path: Path):
    """Dynamically load a Python module from file path."""
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write_timing(state_dir: Path, event: str, handler: str, duration_ms: float) -> None:
    """Write hook timing record to hook-timing.jsonl."""
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
