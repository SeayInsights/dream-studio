"""TraceContext for event correlation — migrated from interfaces/adapters/models.py (Slice 3)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass
class TraceContext:
    """Execution trace metadata for event correlation.

    Links events to their originating context (project, task, session).
    """
    project_id: str | None = None
    task_id: str | None = None
    prd_id: str | None = None
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "task_id": self.task_id,
            "prd_id": self.prd_id,
            "session_id": self.session_id,
        }
