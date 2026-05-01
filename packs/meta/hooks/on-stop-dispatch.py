#!/usr/bin/env python3
"""Dispatcher: Stop — single process for all stop-fired hooks.

Replaces 9 subprocess invocations with one process that imports and calls
each handler sequentially. Reads stdin once and re-injects it before each
handler's main() so existing code works unchanged.

Handlers (in order):
  1. on-session-end      (packs/meta)
  2. on-stop-handoff     (packs/core)
  3. on-quality-score    (packs/quality)
  4. on-skill-telemetry  (packs/meta)
  5. on-milestone-end    (packs/core)
  6. on-token-log        (packs/meta)
  7. on-meta-review      (packs/meta)
  8. on-workflow-progress (packs/core)
  9. on-changelog-nudge  (packs/core)
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
    ("on-session-end", PLUGIN_ROOT / "packs" / "meta" / "hooks" / "on-session-end.py"),
    ("on-stop-handoff", PLUGIN_ROOT / "packs" / "core" / "hooks" / "on-stop-handoff.py"),
    ("on-quality-score", PLUGIN_ROOT / "packs" / "quality" / "hooks" / "on-quality-score.py"),
    ("on-skill-telemetry", PLUGIN_ROOT / "packs" / "meta" / "hooks" / "on-skill-telemetry.py"),
    ("on-milestone-end", PLUGIN_ROOT / "packs" / "core" / "hooks" / "on-milestone-end.py"),
    ("on-token-log", PLUGIN_ROOT / "packs" / "meta" / "hooks" / "on-token-log.py"),
    ("on-meta-review", PLUGIN_ROOT / "packs" / "meta" / "hooks" / "on-meta-review.py"),
    ("on-workflow-progress", PLUGIN_ROOT / "packs" / "core" / "hooks" / "on-workflow-progress.py"),
    ("on-changelog-nudge", PLUGIN_ROOT / "packs" / "core" / "hooks" / "on-changelog-nudge.py"),
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
            _write_timing("Stop", name, elapsed)
        except Exception:
            pass
        finally:
            sys.stdin = sys.__stdin__


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
