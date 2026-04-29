#!/usr/bin/env python3
"""Hook: on-pulse — proactive cross-project health check.

Trigger: scheduled (daily/weekly) or on demand.
Reads `github_repo` from `~/.dream-studio/config.json`. When a PAT is set
(via `GITHUB_PERSONAL_ACCESS_TOKEN`) the hook queries GitHub for stale
branches, overdue milestones, open PRs, and CI status. It also inspects
the local user data dir for pending draft lessons, corrections, and
unresolved escalations, then writes `pulse-YYYY-MM-DD.md` and
`pulse-latest.json` under `~/.dream-studio/meta/`.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))

from lib import paths, state  # noqa: E402
from lib.time_utils import utcnow  # noqa: E402

GITHUB_TOKEN = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
STALE_BRANCH_DAYS = 7
COOLDOWN_MINUTES = 60


def _github_repo() -> str:
    return str(state.read_config().get("github_repo") or "").strip()


def gh_api(endpoint: str):
    if not GITHUB_TOKEN:
        return []
    try:
        req = urllib.request.Request(
            f"https://api.github.com/{endpoint}",
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "dream-studio-pulse-hook",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[on-pulse] GitHub API failed ({endpoint}): {e}", flush=True)
        return []


def check_stale_branches(repo: str) -> list[str]:
    branches = gh_api(f"repos/{repo}/branches?per_page=100")
    if not isinstance(branches, list):
        return []
    cutoff = utcnow() - timedelta(days=STALE_BRANCH_DAYS)
    stale = []
    for b in branches:
        name = b.get("name", "")
        if name in ("main", "master"):
            continue
        commit_date_str = (
            b.get("commit", {}).get("commit", {}).get("committer", {}).get("date", "")
        )
        if not commit_date_str:
            continue
        try:
            commit_date = datetime.fromisoformat(commit_date_str.replace("Z", "+00:00"))
            if commit_date < cutoff:
                days_ago = (utcnow() - commit_date).days
                stale.append(f"{name} ({days_ago}d stale)")
        except (ValueError, TypeError):
            continue
    return stale


def check_overdue_milestones(repo: str) -> list[str]:
    milestones = gh_api(f"repos/{repo}/milestones?state=open&per_page=100")
    if not isinstance(milestones, list):
        return []
    now = utcnow()
    overdue = []
    for ms in milestones:
        due = ms.get("due_on")
        if not due:
            continue
        try:
            due_dt = datetime.fromisoformat(due.replace("Z", "+00:00"))
            if due_dt < now:
                overdue.append(f"{ms['title']} ({(now - due_dt).days}d overdue)")
        except (ValueError, TypeError):
            continue
    return overdue


def check_open_prs(repo: str) -> list[str]:
    prs = gh_api(f"repos/{repo}/pulls?state=open&per_page=100")
    if not isinstance(prs, list):
        return []
    return [f"#{pr['number']}: {pr['title'][:50]}" for pr in prs]


def check_ci_status(repo: str) -> str:
    runs = gh_api(f"repos/{repo}/actions/runs?per_page=1")
    if not isinstance(runs, dict):
        return "unknown"
    workflow_runs = runs.get("workflow_runs", [])
    if not workflow_runs:
        return "no runs found"
    run = workflow_runs[0]
    conclusion = run.get("conclusion") or run.get("status", "unknown")
    return f"{run.get('name', 'unknown')}: {conclusion}"


MAX_PENDING_DRAFTS = 100
DRAFT_STALE_DAYS = 30


def check_pending_drafts() -> list[str]:
    drafts_dir = paths.meta_dir() / "draft-lessons"
    if not drafts_dir.exists():
        return []
    try:
        files = sorted(drafts_dir.glob("*.md"))
    except OSError:
        return []
    return [f.name for f in files]


def auto_archive_stale_drafts() -> int:
    """Move drafts older than DRAFT_STALE_DAYS to draft-lessons/archive/. Returns count moved."""
    drafts_dir = paths.meta_dir() / "draft-lessons"
    if not drafts_dir.exists():
        return 0
    import time as _time
    cutoff = _time.time() - (DRAFT_STALE_DAYS * 86400)
    archive_dir = drafts_dir / "archive"
    moved = 0
    try:
        for f in drafts_dir.glob("*.md"):
            if f.stat().st_mtime < cutoff:
                archive_dir.mkdir(exist_ok=True)
                f.rename(archive_dir / f.name)
                moved += 1
    except Exception:
        pass
    return moved


def check_corrections_growth() -> tuple[int, str]:
    log_path = paths.meta_dir() / "corrections.log"
    if not log_path.exists():
        return 0, ""
    lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return 0, ""
    last = lines[-1].split("\t")
    return len(lines), (last[0][:10] if last else "")


def check_open_escalations() -> list[str]:
    meta_dir = paths.meta_dir()
    if not meta_dir.exists():
        return []
    escalations = []
    for f in meta_dir.glob("*.md"):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
            if "ESC-" in text and "unresolved" in text.lower():
                escalations.append(f.name)
        except Exception:
            continue
    return escalations


def check_stale_agents(plugin_root: Path) -> list[str]:
    """Return repo_names of agent-type ingest-log entries whose refresh_due has passed."""
    ingest_log = plugin_root / "skills" / "domains" / "ingest-log.yml"
    if not ingest_log.exists():
        return []
    try:
        import yaml  # noqa: PLC0415
        data = yaml.safe_load(ingest_log.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return []
        entries = data.get("entries", [])
        if not isinstance(entries, list):
            return []
        today = utcnow().date()
        stale = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if not entry.get("persona_md_path"):
                continue  # repo-type entry, skip
            refresh_due_str = entry.get("refresh_due", "")
            if not refresh_due_str:
                continue
            try:
                refresh_due = datetime.fromisoformat(str(refresh_due_str)).date()
                if refresh_due < today:
                    days_over = (today - refresh_due).days
                    stale.append(f"{entry.get('repo_name', 'unknown')} ({days_over}d past refresh_due)")
            except (ValueError, TypeError):
                continue
        return stale
    except Exception:
        return []


def collect_memory_stats() -> dict:
    """Return memory health stats; returns empty dict on any failure."""
    try:
        mem_dir = paths.memory_dir()
    except Exception:
        return {}
    if not mem_dir.exists():
        return {}
    try:
        import time as _time
        active = [f for f in mem_dir.glob("*.md")]
        archive_dir = mem_dir / "archive"
        archived = list(archive_dir.glob("*.md")) if archive_dir.exists() else []
        db = mem_dir / "memory.db"
        index_age = int(_time.time() - db.stat().st_mtime) if db.exists() else -1

        state_path = paths.state_dir() / "memory-last-score.json"
        top_score = 0.0
        if state_path.exists():
            import json as _json
            data = _json.loads(state_path.read_text(encoding="utf-8"))
            top_score = float(data.get("top_score", 0.0))

        return {
            "memory_active": len(active),
            "memory_archived": len(archived),
            "memory_index_age_secs": index_age,
            "memory_top_score": top_score,
        }
    except Exception:
        return {}


def generate_pulse() -> tuple[str, dict]:
    date = utcnow().strftime("%Y-%m-%d %H:%M UTC")
    repo = _github_repo()

    if repo:
        stale_branches = check_stale_branches(repo)
        overdue_ms = check_overdue_milestones(repo)
        open_prs = check_open_prs(repo)
        ci_status = check_ci_status(repo)
    else:
        stale_branches, overdue_ms, open_prs, ci_status = [], [], [], "no github_repo configured"

    archived = auto_archive_stale_drafts()
    pending_drafts = check_pending_drafts()
    corrections_count, last_correction = check_corrections_growth()
    open_escalations = check_open_escalations()
    stale_agents = check_stale_agents(Path(__file__).resolve().parents[3])
    mem_stats = collect_memory_stats()
    drafts_overflow = len(pending_drafts) > MAX_PENDING_DRAFTS

    issues = len(stale_branches) + len(overdue_ms) + len(open_escalations) + len(stale_agents)
    if drafts_overflow:
        issues += 1
    if issues == 0:
        health = "HEALTHY"
    elif issues <= 3:
        health = "ATTENTION"
    else:
        health = "ACTION NEEDED"

    def bullets(items: list[str], empty: str = "None") -> str:
        if not items:
            return f"- {empty}\n"
        return "".join(f"- {item}\n" for item in items)

    repo_header = repo or "no github_repo configured"
    report = (
        f"# dream-studio Pulse — {date}\n\n"
        f"**Overall health:** {health}\n\n"
        f"## GitHub ({repo_header})\n\n"
        f"### Stale Branches (>{STALE_BRANCH_DAYS}d)\n\n"
        f"{bullets(stale_branches, 'All branches active')}\n"
        f"### Overdue Milestones\n\n"
        f"{bullets(overdue_ms, 'None overdue')}\n"
        f"### Open PRs\n\n"
        f"{bullets(open_prs, 'No open PRs')}\n"
        f"### CI Status\n\n"
        f"- {ci_status}\n\n"
        f"## Local\n\n"
        f"### Pending Draft Lessons ({len(pending_drafts)}){' ⚠ OVERFLOW — run /recap to clear' if drafts_overflow else ''}\n\n"
        f"{f'> {archived} stale drafts auto-archived (older than {DRAFT_STALE_DAYS}d).' + chr(10) if archived else ''}"
        f"{bullets(pending_drafts[:20], 'None pending')}"
        f"{f'... and {len(pending_drafts) - 20} more. Run /recap to review.' + chr(10) if len(pending_drafts) > 20 else chr(10)}"
        f"### Corrections Log\n\n"
        f"- Total corrections: {corrections_count}\n"
        f"- Last correction: {last_correction or 'none'}\n\n"
        f"### Open Escalations\n\n"
        f"{bullets(open_escalations, 'None open')}\n"
        f"### Stale Domain Knowledge\n\n"
        f"{bullets(stale_agents, 'All agents current')}\n"
        f"{('Run `workflow: domain-refresh` to re-synthesize stale agents.' + chr(10)) if stale_agents else ''}"
        + (
            f"### Memory Health\n\n"
            f"- memory_active: {mem_stats['memory_active']}\n"
            f"- memory_archived: {mem_stats['memory_archived']}\n"
            f"- memory_index_age_secs: {mem_stats['memory_index_age_secs']}\n"
            f"- memory_top_score: {mem_stats['memory_top_score']:.2f}\n\n"
            if mem_stats else ""
        )
        + "---\n\n"
        "*Generated by dream-studio on-pulse hook.*\n"
    )

    stats = {
        "health": health,
        "stale_branches": len(stale_branches),
        "overdue_milestones": len(overdue_ms),
        "open_prs": len(open_prs),
        "ci_status": ci_status,
        "pending_drafts": len(pending_drafts),
        "corrections": corrections_count,
        "escalations": len(open_escalations),
        "stale_agents": len(stale_agents),
        **mem_stats,
    }
    return report, stats


def _cooldown_active() -> bool:
    """Return True if the last pulse ran less than COOLDOWN_MINUTES ago."""
    last = state.read_pulse()
    ts = last.get("timestamp")
    if not ts:
        return False
    try:
        last_run = datetime.fromisoformat(ts)
        elapsed = (utcnow() - last_run).total_seconds()
        return elapsed < COOLDOWN_MINUTES * 60
    except (ValueError, TypeError):
        return False


def main() -> None:
    paths.warn_version_mismatch()
    # Quiet mode: suppress advisory hooks for N turns (user-configured)
    remaining = state.get_quiet_mode()
    if remaining > 0:
        state.set_quiet_mode(remaining - 1)
        return
    if _cooldown_active():
        return
    report, stats = generate_pulse()

    date_str = utcnow().strftime("%Y-%m-%d")
    report_path = paths.meta_dir() / f"pulse-{date_str}.md"
    report_path.write_text(report, encoding="utf-8")

    state.write_pulse(
        {"timestamp": utcnow().isoformat(), **stats}
    )

    print(
        f"\n[dream-studio] Pulse check complete — {stats['health']}\n"
        f"  -> Report: {report_path}\n"
        f"  -> Stale branches: {stats['stale_branches']}\n"
        f"  -> Overdue milestones: {stats['overdue_milestones']}\n"
        f"  -> Open PRs: {stats['open_prs']}\n"
        f"  -> Pending draft lessons: {stats['pending_drafts']}\n"
        f"  -> Stale domain agents: {stats['stale_agents']}\n",
        flush=True,
    )

    print(json.dumps({"status": "ok", "hook": "on-pulse", **stats, "output": str(report_path)}))


if __name__ == "__main__":
    main()
