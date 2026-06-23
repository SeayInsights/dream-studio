"""Two-tier JSONL diagnostic stream for hook failures and module-level anomalies.

Centralizes structured diagnostic logging across token_capture, cwd_resolver,
and related TA3 modules. Best-effort: this module must never raise.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Literal

_DS_DIAGNOSTICS_DIR_ENV = "DS_DIAGNOSTICS_DIR"


def _diagnostics_dir() -> Path:
    override = os.environ.get(_DS_DIAGNOSTICS_DIR_ENV)
    if override:
        return Path(override)
    return Path.home() / ".dream-studio" / "state" / "diagnostics"


def _file_prefix_from_source(source: str) -> str:
    """'token_capture.handle_post_tool_use' → 'token-capture'"""
    segment = source.split(".")[0]
    return segment.replace("_", "-")


def log_diagnostic(
    category: Literal["failure", "anomaly", "performance"],
    source: str,
    context: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
    duration_ms: float | None = None,
    session_id: str | None = None,
    machine_id: str | None = None,
) -> None:
    """Append a structured diagnostic entry to a source-prefixed JSONL file.

    File path: <diagnostics_dir>/<source-prefix>.jsonl
    e.g. source='token_capture.handle' → 'token-capture.jsonl'

    Never raises.
    """
    try:
        diag_dir = _diagnostics_dir()
        diag_dir.mkdir(parents=True, exist_ok=True)
        prefix = _file_prefix_from_source(source)
        log_path = diag_dir / f"{prefix}.jsonl"

        entry: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "category": category,
            "source": source,
        }
        if machine_id is not None:
            entry["machine_id"] = machine_id
        if session_id is not None:
            entry["session_id"] = session_id
        if context:
            entry["context"] = context
        if details:
            entry["details"] = details
        if duration_ms is not None:
            entry["duration_ms"] = duration_ms

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # diagnostic logging must never raise
