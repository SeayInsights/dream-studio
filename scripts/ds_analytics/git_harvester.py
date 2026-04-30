"""Harvest git metrics from a project's git history."""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from pathlib import Path


def _git(args: list[str], cwd: Path, timeout: int = 15) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd),
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""


def harvest_git_metrics(project_path: Path) -> dict | None:
    """Compute git metrics from the last 90 days of project history.

    Returns dict with keys: commits_per_week, total_commits_90d,
    avg_commits_per_week, branch_count, weeks_labels.
    Returns None if project_path is not a git repo.
    """
    if not (project_path / ".git").exists():
        return None

    now = datetime.now()
    since = (now - timedelta(days=84)).strftime("%Y-%m-%d")  # 12 weeks

    log_output = _git(
        ["log", f"--since={since}", "--format=%aI", "--no-merges"],
        cwd=project_path,
    )

    weeks: dict[str, int] = {}
    for i in range(12):
        week_start = now - timedelta(weeks=11 - i)
        label = week_start.strftime("%m/%d")
        weeks[label] = 0

    if log_output:
        week_labels = list(weeks.keys())
        for line in log_output.splitlines():
            try:
                commit_date = datetime.fromisoformat(line)
                days_ago = (now - commit_date.replace(tzinfo=None)).days
                week_index = 11 - (days_ago // 7)
                if 0 <= week_index < 12:
                    weeks[week_labels[week_index]] += 1
            except (ValueError, IndexError):
                continue

    commits_list = list(weeks.values())
    total = sum(commits_list)
    active_weeks = sum(1 for c in commits_list if c > 0)

    branch_output = _git(["branch", "--list"], cwd=project_path)
    branch_count = len([b for b in branch_output.splitlines() if b.strip()]) if branch_output else 0

    return {
        "weeks_labels": list(weeks.keys()),
        "commits_per_week": commits_list,
        "total_commits_90d": total,
        "avg_commits_per_week": round(total / max(active_weeks, 1), 1),
        "branch_count": branch_count,
    }
