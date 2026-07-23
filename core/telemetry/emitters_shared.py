"""WO-GF-TELEMETRY-SPLIT: emitters shared primitives.

Extracted verbatim from core/telemetry/emitters.py (see emitters.py facade).
Leaf module in the emitters_* DAG — no sibling imports. Holds env-var
constants, mode constants, TelemetryContext/TelemetryEmitResult, and the
generic connect/emit/text/refs helpers every emitters_* sibling depends on.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config.database import get_db_path

TELEMETRY_DB_ENV = "DREAM_STUDIO_TELEMETRY_DB"
TELEMETRY_DISABLED_ENV = "DREAM_STUDIO_TELEMETRY_DISABLED"
MODE_BEST_EFFORT = "best_effort"
MODE_STRICT = "strict"


@dataclass(frozen=True)
class TelemetryContext:
    project_id: str | None = None
    milestone_id: str | None = None
    task_id: str | None = None
    process_run_id: str | None = None
    source_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    current_stage_gate: str | None = None
    current_milestone: str | None = None
    next_stage_gate: str | None = None
    next_milestone: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> TelemetryContext:
        if not isinstance(value, Mapping):
            return cls()
        return cls(
            project_id=_text(
                value.get("project_id"), value.get("project"), value.get("project_name")
            ),
            milestone_id=_text(
                value.get("milestone_id"),
                value.get("milestone"),
                value.get("current_milestone"),
                value.get("next_milestone"),
            ),
            task_id=_text(
                value.get("task_id"), value.get("work_order_id"), value.get("linked_work_order_id")
            ),
            process_run_id=_text(
                value.get("process_run_id"), value.get("run_id"), value.get("session_name")
            ),
            source_refs=_tuple(value.get("source_refs")),
            evidence_refs=_tuple(value.get("evidence_refs")),
            current_stage_gate=_text(value.get("current_stage_gate")),
            current_milestone=_text(value.get("current_milestone")),
            next_stage_gate=_text(value.get("next_stage_gate")),
            next_milestone=_text(value.get("next_milestone")),
        )

    def scope(self) -> dict[str, str | None]:
        return {
            "project_id": _clean(self.project_id),
            "milestone_id": _clean(self.milestone_id or self.current_milestone),
            "task_id": _clean(self.task_id),
            "process_run_id": _clean(self.process_run_id),
        }


@dataclass(frozen=True)
class TelemetryEmitResult:
    emitted: bool
    event_id: str | None = None
    record_id: str | None = None
    error: str | None = None


def _status(value: Any) -> str:
    text = (_text(value) or "unknown").lower()
    if text in {"pass", "passed", "success", "succeeded", "ok"}:
        return "passed"
    if text in {"fail", "failed", "failure"}:
        return "failed"
    if text in {"warn", "warning"}:
        return "warning"
    if text in {"err", "error", "errored"}:
        return "error"
    if text in {"open", "unresolved", "resolved", "recorded", "unknown"}:
        return text
    return text


def _stable_id(prefix: str, *parts: Any) -> str:
    stable = "|".join(str(part) for part in parts if part is not None)
    return f"{prefix}-{uuid.uuid5(uuid.NAMESPACE_URL, stable).hex}"


def _emit(
    writer: Any,
    *,
    db_path: Path | str | None,
    mode: str,
    required_tables: Sequence[str],
) -> TelemetryEmitResult:
    if os.environ.get(TELEMETRY_DISABLED_ENV):
        return TelemetryEmitResult(False, error="telemetry disabled")
    try:
        with _connect(db_path) as conn:
            _require_tables(conn, required_tables)
            result = writer(conn)
            conn.commit()
            return result
    except Exception as exc:
        if mode == MODE_STRICT:
            raise
        return TelemetryEmitResult(False, error=str(exc))


def _connect(db_path: Path | str | None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else _default_db_path()
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _default_db_path() -> Path:
    override = os.environ.get(TELEMETRY_DB_ENV)
    return Path(override) if override else get_db_path()


def _require_tables(conn: sqlite3.Connection, tables: Sequence[str]) -> None:
    missing = [
        table
        for table in tables
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        is None
    ]
    if missing:
        raise RuntimeError(f"telemetry spine tables missing: {', '.join(missing)}")


def _context(value: TelemetryContext | Mapping[str, Any] | None) -> TelemetryContext:
    if isinstance(value, TelemetryContext):
        return value
    return TelemetryContext.from_mapping(value)


def _text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _clean(value: Any) -> str | None:
    return _text(value)


def _tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value if str(item).strip())
    return (str(value),)


def _refs(*values: Any) -> list[str]:
    refs: list[str] = []
    for value in values:
        refs.extend(_tuple(value))
    return refs


def _truthy(*values: Any) -> bool:
    for value in values:
        if isinstance(value, str):
            if value.strip().lower() in {"true", "1", "yes"}:
                return True
            continue
        if bool(value):
            return True
    return False


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"
