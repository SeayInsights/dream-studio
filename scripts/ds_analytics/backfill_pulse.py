"""One-time migration: backfill raw_operational_snapshots from pulse-*.md files."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))
from lib import paths  # noqa: E402


def _count_section_items(text: str, header_pattern: str, *, exclude: str) -> int:
    header_match = re.search(header_pattern, text)
    if not header_match:
        return 0
    rest = text[header_match.end():]
    count = 0
    for line in rest.splitlines():
        stripped = line.strip()
        if stripped.startswith("##") or stripped.startswith("---"):
            break
        if stripped.startswith("- ") and exclude not in stripped:
            count += 1
    return count


def backfill(db_path: Path | None = None, project_slug: str = "dream-studio") -> int:
    from lib.studio_db import insert_operational_snapshot  # noqa: PLC0415

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
        stale_branches = _count_section_items(raw, r"### Stale Branches", exclude="All branches active")

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
            db_path=db_path,
        )
        if ok:
            count += 1

    return count


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill operational snapshots from pulse-*.md")
    ap.add_argument("--db", type=Path, default=None, help="override studio.db path")
    ap.add_argument("--project-slug", default="dream-studio", help="project slug for backfilled rows")
    args = ap.parse_args()

    count = backfill(args.db, args.project_slug)
    print(f"Backfilled {count} operational snapshot(s) from pulse files.")


if __name__ == "__main__":
    main()
