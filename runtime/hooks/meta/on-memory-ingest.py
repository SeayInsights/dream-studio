#!/usr/bin/env python3
"""Hook: on-memory-ingest — batch-sync domain tables into memory_entries.

Runs at session end (Stop event) via on-stop-dispatch.py HANDLERS, position 10.
Non-blocking: all errors swallowed; hook exits clean regardless of outcome.

FIRST-RUN NOTE: existing memory_entries with source_type=NULL will cause all
reg_gotchas to appear pending on first run (~1-2s upsert cost, one-time only).
18.4.5-followup-1 deduplicates the orphaned NULL entries after first run.
Subsequent runs hit cooldown (< 5ms) or "nothing new" path (~100ms).

Cooldown: default 300s. Override: DREAM_STUDIO_MEMORY_INGEST_INTERVAL=<secs>.
State file: ~/.dream-studio/state/memory-ingest-last-run.json
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from datetime import UTC

_DEFAULT_INTERVAL_SECS = 300

_STATE_DIR = Path.home() / ".dream-studio" / "state"
_LAST_RUN_FILE = _STATE_DIR / "memory-ingest-last-run.json"


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


def _cooldown_secs() -> int:
    raw = os.environ.get("DREAM_STUDIO_MEMORY_INGEST_INTERVAL", "")
    try:
        return max(0, int(raw))
    except (ValueError, TypeError):
        return _DEFAULT_INTERVAL_SECS


def _within_cooldown() -> bool:
    if not _LAST_RUN_FILE.is_file():
        return False
    try:
        data = json.loads(_LAST_RUN_FILE.read_text(encoding="utf-8"))
        elapsed = time.time() - data.get("completed_at_ts", 0)
        return elapsed < _cooldown_secs()
    except Exception:
        return False


def _write_result(results: list, duration_ms: float) -> None:
    try:
        from datetime import datetime

        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        summary = {
            "ok": True,
            "completed_at": datetime.now(UTC).isoformat(),
            "completed_at_ts": time.time(),
            "duration_ms": round(duration_ms),
            "consumers": [
                {
                    "name": r.consumer_name,
                    "found": r.records_found,
                    "ingested": r.records_ingested,
                    "updated": r.records_updated,
                    "skipped": r.records_skipped,
                    "errors": len(r.errors),
                }
                for r in results
            ],
            "total_ingested": sum(r.records_ingested for r in results),
            "total_updated": sum(r.records_updated for r in results),
            "total_errors": sum(len(r.errors) for r in results),
        }
        _LAST_RUN_FILE.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    except Exception:
        pass


def _emit_canonical_event(results: list, duration_ms: float) -> None:
    """Emit memory.ingested to the spool. Best-effort, never raises."""
    try:
        plugin_root = _get_plugin_root()
        if str(plugin_root) not in sys.path:
            sys.path.insert(0, str(plugin_root))
        import spool.writer as _writer  # noqa: PLC0415
        from canonical.events.envelope import CanonicalEventEnvelope  # noqa: PLC0415

        _writer.write_event(
            CanonicalEventEnvelope(
                event_type="memory.ingested",
                payload={
                    "total_ingested": sum(r.records_ingested for r in results),
                    "total_updated": sum(r.records_updated for r in results),
                    "total_errors": sum(len(r.errors) for r in results),
                    "duration_ms": round(duration_ms),
                    "consumers": [r.consumer_name for r in results],
                },
                severity="info",
            ).to_dict()
        )
    except Exception:
        pass


def main() -> None:
    plugin_root = _get_plugin_root()
    if str(plugin_root) not in sys.path:
        sys.path.insert(0, str(plugin_root))

    if _within_cooldown():
        return

    t0 = time.monotonic()
    try:
        from core.memory.ingestion import run_all_ingestion  # noqa: PLC0415

        results = run_all_ingestion()
        duration_ms = (time.monotonic() - t0) * 1000
        _write_result(results, duration_ms)
        _emit_canonical_event(results, duration_ms)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
