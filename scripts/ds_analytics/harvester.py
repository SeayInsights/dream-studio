"""Harvesters: collect raw data from pulse files, specs, and skill telemetry."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))
from lib import paths

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
# T004 — Planning spec harvester
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


def harvest_specs(db_path: Path | None = None) -> int:
    """Walk .planning/specs/**/spec.md and insert into raw_planning_specs.

    Returns count of specs inserted.
    """
    specs_root = paths.plugin_root() / ".planning" / "specs"
    if not specs_root.is_dir():
        return 0

    spec_files = sorted(specs_root.glob("**/spec.md"))
    if not spec_files:
        return 0

    conn = sqlite3.connect(str(db_path or paths.state_dir() / "studio.db"))
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for sf in spec_files:
        content = sf.read_text(encoding="utf-8")
        fm = _parse_front_matter(content)

        title = fm.get("title")
        created_date = fm.get("created")

        # Count tasks from sibling tasks.md
        tasks_path = sf.parent / "tasks.md"
        task_count = _count_tasks(tasks_path)

        # Use path relative to plugin root for the unique key
        try:
            spec_path = str(sf.relative_to(paths.plugin_root()))
        except ValueError:
            spec_path = str(sf)

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

def detect_orphans(db_path: Path | None = None) -> list[str]:
    """Identify specs with no matching ``dream-studio:build`` commit.

    For each spec that has a ``created_date``, searches git history for a
    build commit within 14 days. Updates ``has_build_commit`` in the DB
    and returns titles of orphaned specs (those with no build commit).
    """
    import subprocess
    from datetime import timedelta

    conn = sqlite3.connect(str(db_path or paths.state_dir() / "studio.db"))
    cur = conn.cursor()
    cur.execute("SELECT id, title, created_date FROM raw_planning_specs")
    rows = cur.fetchall()

    orphaned: list[str] = []

    for row_id, title, created_date in rows:
        if not created_date:
            # No created_date — can't determine orphan status, mark as orphan
            conn.execute(
                "UPDATE raw_planning_specs SET has_build_commit = 0 WHERE id = ?",
                (row_id,),
            )
            if title:
                orphaned.append(title)
            continue

        # Calculate the 14-day window
        try:
            since_date = created_date  # YYYY-MM-DD
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

        # Search git history for build commits in the window
        has_build = 0
        try:
            result = subprocess.run(
                [
                    "git", "log", "--oneline",
                    f"--since={since_date}",
                    f"--until={until_date}",
                    "--grep=dream-studio:build",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(paths.plugin_root()),
            )
            if result.returncode == 0 and result.stdout.strip():
                has_build = 1
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            # git not available or timed out — default to orphan
            pass

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
