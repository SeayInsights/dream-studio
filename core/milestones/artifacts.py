"""Milestone gate artifact reads — docstore-first, disk-fallback (WO-FILESDB-P3 S3b-2).

Milestone gate artifacts (design-audit / security-audit / harden-results / cwv-results)
are moving off loose ``.planning/milestones/<id>/*.md`` disk files into the files.db
docstore (name ``milestones/<id>/<filename>``). Readers go through this helper so the
gate works whether an artifact was authored via ``ds files`` (docstore) or, during the
transition, still written to disk. The disk fallback is removed in S4 once every writer
authors via the docstore.
"""

from __future__ import annotations

from pathlib import Path


def read_milestone_artifact(ms_dir: Path, filename: str) -> str | None:
    """Return a milestone gate artifact's text content, or None if it does not exist.

    ``ms_dir.name`` is the milestone id, so the docstore name is
    ``milestones/<milestone_id>/<filename>``. Reads the docstore first, then falls back
    to the legacy disk path ``ms_dir / filename``.
    """
    from core.files.store import read_file_by_name

    try:
        row = read_file_by_name(f"milestones/{ms_dir.name}/{filename}")
    except KeyError:
        row = None
    if row is not None:
        content = row["content"]
        if isinstance(content, (bytes, bytearray)):
            return content.decode("utf-8")
        return str(content)

    disk = ms_dir / filename
    if disk.is_file():
        return disk.read_text(encoding="utf-8")
    return None
