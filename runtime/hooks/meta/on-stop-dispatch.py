#!/usr/bin/env python3
"""Dispatcher: Stop — single process for all stop-fired hooks."""

import sys
import io, sys, time
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))

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
]

STATE_DIR = Path.home() / ".dream-studio" / "state"


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


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
