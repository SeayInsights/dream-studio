"""One-time migration: backfill raw_operational_snapshots from pulse-*.md files."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from core.config import paths  # noqa: E402


def _count_section_items(text: str, header_pattern: str, *, exclude: str) -> int:
    header_match = re.search(header_pattern, text)
    if not header_match:
        return 0
    rest = text[header_match.end() :]
    count = 0
    for line in rest.splitlines():
        stripped = line.strip()
        if stripped.startswith("##") or stripped.startswith("---"):
            break
        if stripped.startswith("- ") and exclude not in stripped:
            count += 1
    return count


def backfill(db_path: Path | None = None, project_slug: str = "dream-studio") -> int:
    from core.event_store.studio_db import insert_operational_snapshot  # noqa: PLC0415

    meta = paths.meta_dir()
    pulse_files = sorted(meta.glob("pulse-*.md"))
    if not pulse_files:
        return 0

    count = 0
    for pf in pulse_files:
        m = re.search(r"pulse-(\d{4}-\d{2}-\d{2})\.md$", pf.name)
        if not m:
            continue
        snapshot_date = m.group(1)
        raw = pf.read_text(encoding="utf-8")

        ci_match = re.search(r"- CI:\s*(.+)", raw)
        ci_status = ci_match.group(1).strip() if ci_match else None

        open_prs = _count_section_items(raw, r"### Open PRs", exclude="No open PRs")
        stale_branches = _count_section_items(
            raw, r"### Stale Branches", exclude="All branches active"
        )

        pd_match = re.search(r"### Pending Draft Lessons\s*\((\d+)\)", raw)
        pending_drafts = int(pd_match.group(1)) if pd_match else 0

        open_escalations = _count_section_items(raw, r"### Open Escalations", exclude="None open")

        ok = insert_operational_snapshot(
            snapshot_date=snapshot_date,
            project_slug=project_slug,
            ci_status=ci_status,
            open_prs=open_prs,
            stale_branches=stale_branches,
            pending_drafts=pending_drafts,
            open_escalations=open_escalations,
            report_body=raw,  # WO-FILESDB-C4B: reconstructed snapshots carry the full body
            db_path=db_path,
        )
        if ok:
            count += 1

    return count


def backfill_report_bodies(db_path: Path | None = None, meta_dir: Path | None = None) -> int:
    """Backfill report_body onto EXISTING raw_operational_snapshots rows (WO 35cb2edb).

    The full pulse body moved into raw_operational_snapshots.report_body (migration 153,
    C4B-S4); rows written before that carry report_body=NULL and the body lives only in the
    historical meta/pulse-<date>.md files. For each such disk file, set report_body on that
    date's rows that still lack one — an UPDATE-only backfill (never inserts, never
    overwrites an existing body). Returns the number of rows updated.

    A no-op (returns 0) when the meta dir is absent or the report_body column does not yet
    exist (migration 153 unreleased on this DB). raw_operational_snapshots is a direct-write
    table, so the UPDATE is authoritative and not undone by any projection replay.
    """
    import sqlite3

    resolved_db = db_path or (paths.state_dir() / "studio.db")
    meta = meta_dir or paths.meta_dir()
    if not meta.is_dir():
        return 0

    conn = sqlite3.connect(str(resolved_db))
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(raw_operational_snapshots)")}
        if "report_body" not in columns:
            return 0  # migration 153 not applied on this DB — nothing to backfill into
        updated = 0
        for pf in sorted(meta.glob("pulse-*.md")):
            m = re.search(r"pulse-(\d{4}-\d{2}-\d{2})\.md$", pf.name)
            if not m:
                continue
            body = pf.read_text(encoding="utf-8", errors="replace")
            cur = conn.execute(
                "UPDATE raw_operational_snapshots SET report_body = ?"
                " WHERE snapshot_date = ? AND report_body IS NULL",
                (body, m.group(1)),
            )
            updated += cur.rowcount
        conn.commit()
        return updated
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill operational snapshots from pulse-*.md")
    ap.add_argument("--db", type=Path, default=None, help="override studio.db path")
    ap.add_argument(
        "--project-slug", default="dream-studio", help="project slug for backfilled rows"
    )
    ap.add_argument(
        "--bodies-only",
        action="store_true",
        help="Only backfill report_body onto EXISTING rows (UPDATE by date; no new rows).",
    )
    args = ap.parse_args()

    if args.bodies_only:
        count = backfill_report_bodies(args.db)
        print(f"Backfilled report_body onto {count} existing operational snapshot(s).")
    else:
        count = backfill(args.db, args.project_slug)
        print(f"Backfilled {count} operational snapshot(s) from pulse files.")


if __name__ == "__main__":
    main()
