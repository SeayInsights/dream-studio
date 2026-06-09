"""Abstract installer base — plan(), install(mode), RefusalError, FileOpPlan."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


class RefusalError(ValueError):
    """Raised when install() is called without an explicit mode flag."""


@dataclass
class FileOp:
    """A single planned file operation."""

    target: Path
    op: str  # create | merge_json | prepend_block | copy | skip
    backup_required: bool
    source_hash: str
    reason: str
    safety_notes: str = ""
    source_content: str | None = None
    source_path: Path | None = (
        None  # fallback for binary files; atomic_copy used when source_content is None
    )
    backup_path: Path | None = None


@dataclass
class FileOpPlan:
    """Ordered list of file operations for one install target."""

    ops: list[FileOp] = field(default_factory=list)
    tool: str = ""
    scope: str = ""

    def summary(self) -> list[dict[str, Any]]:
        return [
            {
                "target": str(op.target),
                "op": op.op,
                "backup_required": op.backup_required,
                "source_hash": op.source_hash,
                "reason": op.reason,
                "safety_notes": op.safety_notes,
            }
            for op in self.ops
        ]


class InstallerBase:
    def plan(self) -> FileOpPlan:
        raise NotImplementedError

    def install(self, mode: Literal["dry_run", "execute"]) -> dict[str, Any]:
        if mode not in ("dry_run", "execute"):
            raise RefusalError(
                f"install() requires mode='dry_run' or mode='execute'; got {mode!r}. "
                "Use --dry-run to simulate or --execute to write files."
            )
        raise NotImplementedError
