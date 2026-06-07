"""Spec ingestion — seed preflight_events with spec_reference findings.

Reads .planning/specs/*.md and .planning/work-orders/<wo_id>/*.md (excluding
context.md) and creates preflight.created events for any file that has a
'work_order:' key in its YAML frontmatter.

A spec file is only ingested if a preflight finding for it doesn't already exist
(dedup via source column matching the file path relative to planning_root).
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML-style frontmatter delimited by '---'.

    Returns (frontmatter_dict, body_text).  Frontmatter is minimal key-value
    parsing (key: value per line, no nested YAML).  Returns ({}, text) if no
    frontmatter block is found.
    """
    if not text.startswith("---"):
        return {}, text

    end = text.find("\n---", 3)
    if end == -1:
        return {}, text

    fm_block = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")  # noqa: E203

    fm: dict = {}
    for line in fm_block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()

    return fm, body


def _extract_summary(body: str, fallback: str) -> str:
    """Return the first heading or non-empty line from body as a short summary."""
    for line in body.splitlines():
        stripped = line.strip("#").strip()
        if stripped:
            return stripped[:200]
    return fallback


def _already_ingested(rel_path: str, conn: sqlite3.Connection) -> bool:
    """Return True if a spec_reference finding with this source path already exists."""
    try:
        row = conn.execute(
            "SELECT 1 FROM preflight_events WHERE finding_type = 'spec_reference' AND source = ? LIMIT 1",
            (rel_path,),
        ).fetchone()
        return row is not None
    except sqlite3.OperationalError:
        return False


def ingest_specs(
    planning_root: Path,
    *,
    db_path: Optional[Path] = None,
    dry_run: bool = False,
) -> list[dict]:
    """Ingest all eligible spec files under planning_root as preflight findings.

    Looks in:
        <planning_root>/specs/*.md
        <planning_root>/work-orders/<wo_id>/*.md  (excluding context.md)

    A file is eligible if its frontmatter contains a 'work_order:' key.

    Returns a list of dicts describing what was (or would be) ingested.
    """
    from core.preflight.mutations import create_preflight

    candidates: list[Path] = []

    specs_dir = planning_root / "specs"
    if specs_dir.is_dir():
        candidates.extend(p for p in specs_dir.glob("*.md") if p.is_file())

    wo_root = planning_root / "work-orders"
    if wo_root.is_dir():
        for wo_dir in wo_root.iterdir():
            if wo_dir.is_dir():
                for md in wo_dir.glob("*.md"):
                    if md.name != "context.md" and md.is_file():
                        candidates.append(md)

    ingested = []
    conn: Optional[sqlite3.Connection] = None
    owned = False

    if not dry_run:
        if db_path is not None:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            owned = True
        else:
            try:
                from core.config.database import get_connection

                conn = get_connection()
            except Exception:
                from core.event_store.studio_db import _connect as _sc
                from core.config.paths import state_dir

                conn = _sc(state_dir() / "studio.db")
                owned = True

    try:
        for path in sorted(candidates):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            fm, body = _parse_frontmatter(text)
            work_order_id = fm.get("work_order") or fm.get("work_order_id")
            if not work_order_id:
                continue

            rel_path = str(path.relative_to(planning_root))
            summary = _extract_summary(body, path.stem)

            record = {
                "path": rel_path,
                "work_order_id": work_order_id,
                "summary": summary,
            }

            if dry_run:
                record["action"] = "would_ingest"
                ingested.append(record)
                continue

            if conn is not None and _already_ingested(rel_path, conn):
                record["action"] = "skipped_duplicate"
                ingested.append(record)
                continue

            try:
                event_id = create_preflight(
                    work_order_id=work_order_id,
                    finding_type="spec_reference",
                    source=rel_path,
                    severity="info",
                    summary=summary,
                    body=body[:4000] if body else None,
                    author_type="spec_ingestor",
                    db_path=db_path,
                )
                record["action"] = "ingested"
                record["event_id"] = event_id
            except Exception as exc:
                record["action"] = "error"
                record["error"] = str(exc)

            ingested.append(record)
    finally:
        if owned and conn is not None:
            conn.close()

    return ingested
