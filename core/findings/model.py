"""One shape for a finding, whatever produced it.

Dream Studio currently records "a finding" in three incompatible formats:

  1. SQL rows      — security_events / scan_runs in the authority DB
  2. Markdown      — milestones/<id>/security-audit.md and harden-results.md in
                     the docstore, whose blocking status is recovered by running
                     a regex over English prose
  3. Raw JSONL     — ~/.dream-studio/diagnostics/guard-findings.jsonl, which
                     nothing reads back

So "what was found, and where?" cannot be answered from any single surface. The
dashboard renders only (1); the close gates consume only (2); nothing consumes
(3). An operator has to know which of the three to look in before they can even
start looking.

This module defines the common shape. It is deliberately a READ-layer
normalisation, not a schema migration: the right way to find out whether this
shape is correct is to render every existing source through it first. Migrating
storage before the shape is proven would just create a fourth format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Severity ordering, most severe first. Used for sorting and for the rank filter.
SEVERITY_ORDER: tuple[str, ...] = ("critical", "high", "medium", "low", "info", "pass")

_SEVERITY_ALIASES: dict[str, str] = {
    "blocker": "critical",
    "blocking": "critical",
    "blocked": "critical",
    "crit": "critical",
    "error": "high",
    "warn": "medium",
    "warning": "medium",
    "moderate": "medium",
    "minor": "low",
    "note": "info",
    "notice": "info",
    "informational": "info",
    "ok": "pass",
    "passed": "pass",
}


def normalize_severity(raw: Any) -> str:
    """Map a producer's severity vocabulary onto SEVERITY_ORDER.

    Unknown values become "info" rather than being dropped — a finding with an
    unrecognised severity is still a finding, and silently discarding it would
    repeat the failure this module exists to fix.
    """
    if raw is None:
        return "info"
    text = str(raw).strip().lower()
    if not text:
        return "info"
    if text in SEVERITY_ORDER:
        return text
    return _SEVERITY_ALIASES.get(text, "info")


def severity_rank(severity: str) -> int:
    """Sort key — lower is more severe."""
    try:
        return SEVERITY_ORDER.index(severity)
    except ValueError:
        return len(SEVERITY_ORDER)


@dataclass(frozen=True)
class Finding:
    """A single finding, normalised across producers."""

    source: str
    """Which producer this came from: security_event | audit_markdown | guard_log."""

    severity: str
    """One of SEVERITY_ORDER."""

    title: str

    ref: str
    """Where to go to see the original: an event id, a docstore name, a line number."""

    detail: str = ""
    file_path: str | None = None
    line: int | None = None
    project_id: str | None = None
    created_at: str | None = None
    blocking: bool = False
    """True when this finding would fail a close gate."""

    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def location(self) -> str:
        """`path:line`, or an empty string when the finding has no location."""
        if not self.file_path:
            return ""
        return f"{self.file_path}:{self.line}" if self.line else str(self.file_path)

    def sort_key(self) -> tuple[int, str, str]:
        return (severity_rank(self.severity), self.source, self.title)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "severity": self.severity,
            "title": self.title,
            "ref": self.ref,
            "detail": self.detail,
            "file_path": self.file_path,
            "line": self.line,
            "location": self.location,
            "project_id": self.project_id,
            "created_at": self.created_at,
            "blocking": self.blocking,
            "extra": dict(self.extra),
        }
