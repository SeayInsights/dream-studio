"""Harvesters: collect raw data from pulse files, specs, and skill telemetry."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))
from lib import paths, studio_db

# ---------------------------------------------------------------------------
# Health mapping
# ---------------------------------------------------------------------------
_HEALTH_MAP = {"HEALTHY": 100, "DEGRADED": 50, "CRITICAL": 0}


def harvest_pulse(db_path: Path | None = None) -> list[dict]:
    """Parse all pulse-*.md files and insert into raw_pulse_snapshots.

    Returns list of dicts with keys ``snapshot_date`` and ``health_score``.
    """
    meta = paths.meta_dir()
    pulse_files = sorted(meta.glob("pulse-*.md"))
    if not pulse_files:
        return []

    conn = sqlite3.connect(str(db_path or paths.state_dir() / "studio.db"))
    results: list[dict] = []

    for pf in pulse_files:
        # Extract date from filename  pulse-YYYY-MM-DD.md
        m = re.search(r"pulse-(\d{4}-\d{2}-\d{2})\.md$", pf.name)
        if not m:
            continue
        snapshot_date = m.group(1)

        raw_content = pf.read_text(encoding="utf-8")

        # Health status
        hm = re.search(r"\*\*Overall health:\*\*\s*(\w+)", raw_content)
        health_status = hm.group(1) if hm else "HEALTHY"
        health_score = _HEALTH_MAP.get(health_status, 0)

        # CI status
        ci_match = re.search(r"- CI:\s*(.+)", raw_content)
        ci_status = ci_match.group(1).strip() if ci_match else None

        # Open PRs — count bullet lines under ### Open PRs until next section
        open_prs = _count_section_items(raw_content, r"### Open PRs", exclude="No open PRs")

        # Stale branches — count bullet lines under ### Stale Branches
        stale_branches = _count_section_items(
            raw_content, r"### Stale Branches", exclude="All branches active"
        )

        # Pending drafts — extract N from header ### Pending Draft Lessons (N)
        pd_match = re.search(r"### Pending Draft Lessons\s*\((\d+)\)", raw_content)
        pending_drafts = int(pd_match.group(1)) if pd_match else 0

        # Open escalations
        open_escalations = _count_section_items(
            raw_content, r"### Open Escalations", exclude="None open"
        )

        conn.execute(
            """INSERT OR REPLACE INTO raw_pulse_snapshots
               (snapshot_date, health_score, health_status, ci_status,
                open_prs, stale_branches, pending_drafts, open_escalations, raw_content)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot_date,
                health_score,
                health_status,
                ci_status,
                open_prs,
                stale_branches,
                pending_drafts,
                open_escalations,
                raw_content,
            ),
        )
        results.append({"snapshot_date": snapshot_date, "health_score": health_score})

    conn.commit()
    conn.close()
    return results


def _count_section_items(text: str, header_pattern: str, *, exclude: str) -> int:
    """Count bullet list items under a markdown ### section.

    Stops at the next ``###`` header, ``##`` header, or ``---`` rule.
    Lines matching *exclude* are not counted.
    """
    header_match = re.search(header_pattern, text)
    if not header_match:
        return 0

    rest = text[header_match.end():]
    count = 0
    for line in rest.splitlines():
        stripped = line.strip()
        # Stop at next section header or horizontal rule
        if stripped.startswith("##") or stripped.startswith("---"):
            break
        if stripped.startswith("- ") and exclude not in stripped:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Operational harvester (reads from raw_operational_snapshots)
# ---------------------------------------------------------------------------


def harvest_operational(
    db_path: Path | None = None, project_slug: str | None = None
) -> list[dict]:
    """Read operational snapshots from SQLite.

    When project_slug is provided, filters to that project.
    Returns list of dicts with snapshot_date and metric columns.
    """
    db = db_path or paths.state_dir() / "studio.db"
    if not db.exists():
        return []

    conn = sqlite3.connect(str(db))
    try:
        if project_slug:
            rows = conn.execute(
                "SELECT snapshot_date, ci_status, open_prs, stale_branches, "
                "pending_drafts, open_escalations FROM raw_operational_snapshots "
                "WHERE project_slug = ? ORDER BY snapshot_date",
                (project_slug,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT snapshot_date, ci_status, open_prs, stale_branches, "
                "pending_drafts, open_escalations FROM raw_operational_snapshots "
                "ORDER BY snapshot_date"
            ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return []
    conn.close()

    cols = ["snapshot_date", "ci_status", "open_prs", "stale_branches",
            "pending_drafts", "open_escalations"]
    return [dict(zip(cols, r)) for r in rows]


# ---------------------------------------------------------------------------
# Planning spec harvester
# ---------------------------------------------------------------------------

def _parse_front_matter(text: str) -> dict[str, str]:
    """Extract YAML-style front matter (between --- delimiters) using regex.

    Returns a dict of key: value strings. Empty dict if no front matter found.
    """
    fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return {}
    result: dict[str, str] = {}
    for line in fm_match.group(1).splitlines():
        m = re.match(r"^(\w[\w-]*):\s*(.+)$", line)
        if m:
            result[m.group(1).strip()] = m.group(2).strip()
    return result


def _count_tasks(tasks_path: Path) -> int:
    """Count task entries in a tasks.md file.

    Matches both ``### T\\d+`` section headers and ``- [ ] T\\d+`` checklist items.
    """
    if not tasks_path.is_file():
        return 0
    content = tasks_path.read_text(encoding="utf-8")
    pattern = re.compile(r"(?:^### T\d+|^- \[[ x]\] T\d+)", re.MULTILINE)
    return len(pattern.findall(content))


def harvest_specs(db_path: Path | None = None, extra_roots: list[Path] | None = None) -> int:
    """Walk .planning/specs/**/spec.md and insert into raw_planning_specs.

    Scans dream-studio's own specs plus any extra_roots (project directories
    that may contain .planning/specs/).
    """
    roots: list[tuple[Path, Path]] = []  # (specs_dir, project_root)
    plugin = paths.plugin_root().resolve()
    seen: set[str] = set()
    for project_root in (extra_roots or []):
        sr = project_root.resolve() / ".planning" / "specs"
        if sr.is_dir():
            key = str(sr)
            if key not in seen:
                seen.add(key)
                roots.append((sr, project_root.resolve()))
    if not extra_roots:
        ds_specs = plugin / ".planning" / "specs"
        if ds_specs.is_dir():
            roots.append((ds_specs, plugin))

    if not roots:
        return 0

    conn = sqlite3.connect(str(db_path or paths.state_dir() / "studio.db"))
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for specs_root, project_root in roots:
        project_name = project_root.name
        for sf in sorted(specs_root.glob("**/spec.md")):
            content = sf.read_text(encoding="utf-8")
            fm = _parse_front_matter(content)

            title = fm.get("title")
            created_date = fm.get("created")

            tasks_path = sf.parent / "tasks.md"
            task_count = _count_tasks(tasks_path)

            try:
                rel = str(sf.relative_to(project_root))
            except ValueError:
                rel = str(sf)
            spec_path = f"{project_name}/{rel}"

            conn.execute(
                """INSERT OR REPLACE INTO raw_planning_specs
                   (spec_path, title, created_date, task_count, last_checked)
                   VALUES (?, ?, ?, ?, ?)""",
                (spec_path, title, created_date, task_count, now),
            )
            count += 1

    conn.commit()
    conn.close()
    return count


# ---------------------------------------------------------------------------
# T005 — Orphan detection
# ---------------------------------------------------------------------------

def detect_orphans(db_path: Path | None = None, git_roots: list[Path] | None = None) -> list[str]:
    """Identify specs with no matching build commit.

    Searches git history for ``feat`` commits within 14 days of each spec's
    created_date across all provided git_roots (defaults to plugin_root).
    """
    import subprocess
    from datetime import timedelta

    if git_roots is None:
        git_roots = [paths.plugin_root()]

    # Use studio_db._connect() to ensure migrations run and table exists
    conn = studio_db._connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, title, created_date FROM raw_planning_specs")
    rows = cur.fetchall()

    orphaned: list[str] = []

    for row_id, title, created_date in rows:
        if not created_date:
            conn.execute(
                "UPDATE raw_planning_specs SET has_build_commit = 0 WHERE id = ?",
                (row_id,),
            )
            if title:
                orphaned.append(title)
            continue

        try:
            since_date = created_date
            until_dt = datetime.strptime(created_date, "%Y-%m-%d") + timedelta(days=14)
            until_date = until_dt.strftime("%Y-%m-%d")
        except ValueError:
            conn.execute(
                "UPDATE raw_planning_specs SET has_build_commit = 0 WHERE id = ?",
                (row_id,),
            )
            if title:
                orphaned.append(title)
            continue

        has_build = 0
        for root in git_roots:
            if not (root / ".git").exists():
                continue
            try:
                result = subprocess.run(
                    [
                        "git", "log", "--oneline",
                        f"--since={since_date}",
                        f"--until={until_date}",
                        "--grep=feat",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=str(root),
                )
                if result.returncode == 0 and result.stdout.strip():
                    has_build = 1
                    break
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue

        conn.execute(
            "UPDATE raw_planning_specs SET has_build_commit = ? WHERE id = ?",
            (has_build, row_id),
        )
        if has_build == 0 and title:
            orphaned.append(title)

    conn.commit()
    conn.close()
    return orphaned


# ---------------------------------------------------------------------------
# T006 — Skill telemetry harvester
# ---------------------------------------------------------------------------

_EMPTY_VELOCITY_COLS = ["skill_name", "week", "invocation_count", "success_rate"]


def harvest_skill_velocity(db_path: Path | None = None) -> pd.DataFrame:
    """Query effective_skill_runs and compute weekly skill velocity.

    Returns a DataFrame with columns: ``skill_name``, ``week``,
    ``invocation_count``, ``success_rate``.  Returns an empty DataFrame
    with the correct columns if no telemetry data exists.
    """
    conn = sqlite3.connect(str(db_path or paths.state_dir() / "studio.db"))

    # Check if the view has any rows
    try:
        row_count = conn.execute("SELECT COUNT(*) FROM effective_skill_runs").fetchone()[0]
    except sqlite3.OperationalError:
        conn.close()
        return pd.DataFrame(columns=_EMPTY_VELOCITY_COLS)

    if row_count == 0:
        conn.close()
        return pd.DataFrame(columns=_EMPTY_VELOCITY_COLS)

    query = """
        SELECT skill_name,
               strftime('%Y-W%W', invoked_at) AS week,
               COUNT(*)                        AS invocation_count,
               AVG(success)                    AS success_rate
        FROM effective_skill_runs
        GROUP BY skill_name, week
        ORDER BY skill_name, week
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


# ---------------------------------------------------------------------------
# Hook timing harvester
# ---------------------------------------------------------------------------

def harvest_hook_timing() -> dict:
    """Read hook-timing.jsonl and compute per-handler averages.

    Returns dict with keys: handlers (list of {handler, event, avg_ms, count}),
    total_overhead_ms, slowest_handler.
    """
    import json

    timing_file = paths.state_dir() / "hook-timing.jsonl"
    if not timing_file.exists():
        return {"handlers": [], "total_overhead_ms": 0, "slowest_handler": None}

    stats: dict[str, dict] = {}
    try:
        for line in timing_file.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            record = json.loads(line)
            key = record["handler"]
            if key not in stats:
                stats[key] = {
                    "handler": key,
                    "event": record.get("event", ""),
                    "total_ms": 0.0,
                    "count": 0,
                }
            stats[key]["total_ms"] += record.get("duration_ms", 0)
            stats[key]["count"] += 1
    except Exception:
        return {"handlers": [], "total_overhead_ms": 0, "slowest_handler": None}

    handlers = []
    for s in stats.values():
        avg = s["total_ms"] / s["count"] if s["count"] > 0 else 0
        handlers.append({
            "handler": s["handler"],
            "event": s["event"],
            "avg_ms": round(avg, 2),
            "count": s["count"],
        })

    handlers.sort(key=lambda h: h["avg_ms"], reverse=True)
    total = sum(h["avg_ms"] for h in handlers)
    slowest = handlers[0]["handler"] if handlers else None

    return {
        "handlers": handlers,
        "total_overhead_ms": round(total, 2),
        "slowest_handler": slowest,
    }
