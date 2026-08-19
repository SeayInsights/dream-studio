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


def read_milestone_artifact(
    ms_dir: Path, filename: str, *, db_path: Path | None = None
) -> str | None:
    """Return a milestone gate artifact's text content, or None if it does not exist.

    ``ms_dir.name`` is the milestone id, so the docstore name is
    ``milestones/<milestone_id>/<filename>``. Reads the docstore first, then falls back
    to the legacy disk path ``ms_dir / filename``. ``db_path`` selects a non-default
    docstore (used by the PRD rescore engine and isolated tests); None = default docstore.
    Provenance envelopes (WO-VERIFY-PROVENANCE) are unwrapped transparently.
    """
    content, _ = read_milestone_artifact_with_envelope(ms_dir, filename, db_path=db_path)
    return content


def read_milestone_artifact_with_envelope(
    ms_dir: Path, filename: str, *, db_path: Path | None = None
) -> tuple[str | None, dict | None]:
    """Like ``read_milestone_artifact`` but also returns the provenance envelope.

    ``envelope`` is None for legacy bare-text artifacts (both stores) and for
    absent artifacts. Milestone gates use it to reject enveloped audits that
    predate later commits (WO-VERIFY-PROVENANCE).
    """
    from core.files.store import read_file_by_name
    from core.work_orders.artifact_envelope import unwrap

    try:
        row = read_file_by_name(f"milestones/{ms_dir.name}/{filename}", db_path=db_path)
    except KeyError:
        row = None
    if row is not None:
        content = row["content"]
        if isinstance(content, (bytes, bytearray)):
            content = content.decode("utf-8")
        return unwrap(str(content))

    disk = ms_dir / filename
    if disk.is_file():
        return unwrap(disk.read_text(encoding="utf-8"))
    return None, None
