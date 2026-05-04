#!/usr/bin/env python3
"""Dispatcher: UserPromptSubmit — single process for all prompt-fired hooks.

Replaces 6 subprocess invocations with one process that imports and calls
each handler sequentially. Reads stdin once and re-injects it before each
handler's main() so existing code works unchanged.

Handlers (in order):
  1. on-session-start  (packs/meta)
  2. on-first-run      (packs/meta)
  3. on-memory-retrieve (packs/meta)
  4. on-milestone-start (packs/core)
  5. on-context-threshold (packs/meta)
  6. on-pulse           (packs/meta)
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import time
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))

HANDLERS: list[tuple[str, Path]] = [
    ("on-prompt-validate", PLUGIN_ROOT / "packs" / "meta" / "hooks" / "on-prompt-validate.py"),  # Wave 4: Security validation
    ("on-session-start", PLUGIN_ROOT / "packs" / "meta" / "hooks" / "on-session-start.py"),
    ("on-first-run", PLUGIN_ROOT / "packs" / "meta" / "hooks" / "on-first-run.py"),
    ("on-memory-retrieve", PLUGIN_ROOT / "packs" / "meta" / "hooks" / "on-memory-retrieve.py"),
    ("on-milestone-start", PLUGIN_ROOT / "packs" / "core" / "hooks" / "on-milestone-start.py"),
    ("on-context-threshold", PLUGIN_ROOT / "packs" / "meta" / "hooks" / "on-context-threshold.py"),
    ("on-pulse", PLUGIN_ROOT / "packs" / "meta" / "hooks" / "on-pulse.py"),
]

STATE_DIR = Path.home() / ".dream-studio" / "state"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_timing(event: str, handler: str, duration_ms: float) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "event": event,
            "handler": handler,
            "duration_ms": round(duration_ms, 2),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with (STATE_DIR / "hook-timing.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def main() -> None:
    raw_payload = sys.stdin.read()

    for name, path in HANDLERS:
        if not path.is_file():
            continue
        try:
            mod = _load_module(name.replace("-", "_"), path)
            if mod is None or not hasattr(mod, "main"):
                continue
            sys.stdin = io.StringIO(raw_payload)
            t0 = time.perf_counter()
            mod.main()
            elapsed = (time.perf_counter() - t0) * 1000
            _write_timing("UserPromptSubmit", name, elapsed)
        except Exception:
            pass
        finally:
            sys.stdin = sys.__stdin__


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
