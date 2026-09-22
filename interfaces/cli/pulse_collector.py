"""Pulse collection logic extracted from on-pulse hook.

Collects system health data from GitHub and local metrics.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path for canonical imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import paths
from core.config import state
from control.research.memory import MemorySearch
from core.utils.time import utcnow

GITHUB_TOKEN = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
STALE_BRANCH_DAYS = 7
#: Tokens already proven unusable this process, so one dead credential is not re-tried
#: against every endpoint the pulse reads. IN-PROCESS IS NOT ENOUGH ON ITS OWN --
#: the pulse runs in a fresh process on every prompt, so this set is empty each
#: time and a dead token still costs one failed request per prompt forever. The
#: rejection is therefore also written to disk, keyed by a fingerprint of the
#: token so a NEW credential re-arms automatically. See `_auth_is_broken`.
_REJECTED_TOKENS: set[str] = set()

# The pulse is an advisory health check, not a correctness gate. At 60s every
# interactive prompt landed on the cold path and paid up to five GitHub round
# trips; measured p95 4.7s, worst 27.7s, on the UserPromptSubmit critical path.
COOLDOWN_SEC = int(os.environ.get("PULSE_COOLDOWN_SEC", "3600"))

#: A health check may not hold the prompt open. 15s per call against five
#: endpoints is 75s of worst case in front of the operator.
GH_TIMEOUT_SEC = float(os.environ.get("PULSE_GH_TIMEOUT_SEC", "4"))
MAX_PENDING_DRAFTS = 100
DRAFT_STALE_DAYS = 30


def _github_repo() -> str:
    return str(state.read_config().get("github_repo") or "").strip()


def _gh_cli_token() -> str:
    """The token the `gh` CLI is authenticated with, or empty when it is not.

    Second credential source because the first one expires. ``GITHUB_PERSONAL_ACCESS_TOKEN``
    is a long-lived string in the operator's environment, and when it lapses the pulse does
    not degrade quietly -- it prints five `HTTP Error 401` lines on every prompt and reports
    ``open_prs: 0`` and ``ci_status: unknown`` while pull requests are open and main is red.
    Observed for a whole session: seven open pull requests read as zero. `gh` is already a
    hard dependency of this project's workflow and refreshes its own credential, so it is the
    natural fallback.
    """
    import shutil
    import subprocess

    if shutil.which("gh") is None:
        return ""
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (proc.stdout or "").strip() if proc.returncode == 0 else ""


def _token_fingerprint(token: str) -> str:
    """Short, non-reversible id for a token, so a NEW credential re-arms by itself."""
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _rejection_path(token: str) -> Path:
    return paths.state_dir() / f".gh-auth-failed-{_token_fingerprint(token)}"


def _auth_is_broken(token: str) -> bool:
    """True once this exact credential has been proven unusable, in any process.

    A 401 is not a transient blip -- the same string will fail forever. The
    in-process set alone cannot help here because the pulse runs in a fresh
    process on every prompt, so without this the operator pays one doomed
    request per prompt indefinitely. Keyed on a fingerprint rather than the
    token, so rotating the credential clears the breaker without a command.
    """
    try:
        return _rejection_path(token).is_file()
    except Exception:
        return False


def _persist_rejection(token: str) -> None:
    try:
        path = _rejection_path(token)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(utcnow().isoformat(), encoding="utf-8")
    except Exception:
        # Losing the breaker costs a wasted request, never a wrong answer.
        pass


def _github_tokens() -> list[str]:
    """Credentials to try, best first, minus any already proven dead.

    Rejections are checked in-process AND on disk: the first stops one dead token
    costing a request per endpoint within a run, the second stops it costing one
    per prompt across runs.
    """
    ordered = [GITHUB_TOKEN, _gh_cli_token()]
    seen: set[str] = set()
    usable = []
    for token in ordered:
        if not token or token in seen or token in _REJECTED_TOKENS:
            continue
        seen.add(token)
        if _auth_is_broken(token):
            continue
        usable.append(token)
    return usable


def gh_api(endpoint: str):
    tokens = _github_tokens()
    if not tokens:
        return []
    last_error: Exception | None = None
    for token in tokens:
        try:
            req = urllib.request.Request(
                f"https://api.github.com/{endpoint}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "dream-studio-pulse-hook",
                },
            )
            with urllib.request.urlopen(req, timeout=GH_TIMEOUT_SEC) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            last_error = e
            # 401/403 is the credential, not the endpoint: retire it and try the next one.
            # Any other status is about this request, so reporting it beats re-asking with a
            # different credential that would fail the same way.
            if e.code in (401, 403):
                _REJECTED_TOKENS.add(token)
                _persist_rejection(token)
                continue
            break
        except Exception as e:
            last_error = e
            break
    print(
        f"[on-pulse] GitHub API failed ({endpoint}): {last_error}",
        file=sys.stderr,
        flush=True,
    )
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
        commit_date_str = b.get("commit", {}).get("commit", {}).get("committer", {}).get("date", "")
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


def check_full_ci_on_main(repo: str) -> str | None:
    """Return the conclusion of the latest full-ci run on main, or None if unavailable."""
    runs = gh_api(f"repos/{repo}/actions/workflows/full-ci.yml/runs?branch=main&per_page=1")
    if not isinstance(runs, dict):
        return None
    workflow_runs = runs.get("workflow_runs", [])
    if not workflow_runs:
        return None
    return workflow_runs[0].get("conclusion") or None


def check_pending_drafts() -> list[str]:
    """Return lesson_ids of pending draft lessons from DB."""
    try:
        from core.event_store.studio_db import get_pending_lessons

        return [
            row["lesson_id"] for row in get_pending_lessons(db_path=paths.state_dir() / "studio.db")
        ]
    except Exception:
        return []


def auto_archive_stale_drafts() -> int:
    """No-op: stale-archiving is a file-system concept; DB rows don't expire this way.

    Kept for API compatibility — returns 0. Lesson triage is via lesson_queue or the DB directly.
    """
    return 0


def check_corrections_growth() -> tuple[int, str]:
    log_path = paths.meta_dir() / "corrections.log"
    if not log_path.exists():
        return 0, ""
    lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return 0, ""
    last = lines[-1].split("\t")
    return len(lines), (last[0][:10] if last else "")


#: When a number stops being housekeeping and becomes a problem. Set from the incident
#: that motivated the check rather than from taste: the runtime reached 10.6 GB on disk
#: with a 444 MB write-ahead log, and neither was noticed for months.
STORAGE_LIMITS = {
    "total_bytes": 1_000_000_000,  # 1 GB
    "wal_bytes": 100_000_000,  # 100 MB
    "spool_files": 500,
}


def check_storage() -> list[str]:
    """How much disk the runtime is using, and what is unusual about it.

    WHY THIS EXISTS. `ds pulse` ran nine checks -- branches, milestones, pull requests,
    CI, drafts, corrections, escalations, agents, skill health -- and **not one of them
    looked at storage**. So when the runtime reached 10.6 GB with a 444 MB write-ahead
    log, the pulse reported healthy for months. `--refresh` would not have helped: there
    was nothing to refresh, because nothing measured it.

    That is the difference between reading a snapshot and measuring. A snapshot can only
    be stale about something it records; this one was silent about something it never
    recorded at all, which looks identical to "fine" from the outside.

    THE SPOOL BACKLOG IS THE LEADING INDICATOR. Events are written to
    `events/spool/*.json` and removed by the ingestor. When ingestion stops, the files
    accumulate first, the database and its log grow second, and the disk fills third --
    so a spool that is not draining is the earliest of the three to say something is
    wrong. Measured while writing this: 1,025 unprocessed events were sitting there.

    Returns human-readable lines, empty when nothing is unusual -- the shape every other
    check here uses.
    """
    home = paths.user_data_dir()
    issues: list[str] = []

    total = 0
    try:
        for entry in home.rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError:
                    continue
    except OSError:
        return []  # an unreadable home is the doctor's finding, not the pulse's

    if total > STORAGE_LIMITS["total_bytes"]:
        issues.append(f"runtime is using {total / 1e9:.1f} GB on disk ({home})")

    wal = home / "state" / "studio.db-wal"
    try:
        wal_size = wal.stat().st_size if wal.exists() else 0
    except OSError:
        wal_size = 0
    if wal_size > STORAGE_LIMITS["wal_bytes"]:
        issues.append(
            f"write-ahead log is {wal_size / 1e6:.0f} MB -- a checkpoint is not happening"
        )

    spool = home / "events" / "spool"
    try:
        backlog = sum(1 for _ in spool.glob("*.json")) if spool.is_dir() else 0
    except OSError:
        backlog = 0
    if backlog > STORAGE_LIMITS["spool_files"]:
        issues.append(f"{backlog} events unprocessed in the spool -- ingestion is not keeping up")

    return issues


def check_open_escalations() -> list[str]:
    """Open operator escalations, read from the authority store (WO-FILESDB-C4B S3).

    The count moved off the disk glob onto business_work_order_artifacts
    (kind='escalation', status='unresolved'). Any legacy open disk ESC-*.md file is
    migrated into the store first (idempotent) so the count never drops on the switch.
    Falls back to the legacy disk scan only if the store is unreadable.
    """
    meta_dir = paths.meta_dir()
    db_path = paths.state_dir() / "studio.db"
    try:
        from core.work_orders.escalation import (
            backfill_open_escalations_from_disk,
            list_escalations,
        )

        backfill_open_escalations_from_disk(meta_dir, db_path=db_path)
        return [
            f"ESC-{(rec.get('type') or 'esc').upper()}-{str(rec.get('work_order_id', ''))[:8]}"
            for rec in list_escalations(db_path=db_path, include_resolved=False)
        ]
    except Exception:
        # Defensive: if the store is unreadable, fall back to the legacy disk scan so
        # the pulse never silently drops open escalations.
        from core.work_orders.escalation import scan_open_escalation_files

        return [f.name for f in scan_open_escalation_files(meta_dir)]


def _run_outcome_eval_safe() -> dict | None:
    """Run the WO-OUTCOME-EVAL safety net during the pulse (best-effort, never raises).

    Re-runs each closed defect WO's originating symptom; a persisting symptom reopens
    the WO and writes an unresolved escalation file (counted by check_open_escalations
    below). symptom_only=True keeps this to cheap SQL re-checks on the pulse hot path —
    the runner that ensures the outcome eval is never dormant (WO-OUTCOME-EVAL T3).
    """
    try:
        db_path = paths.state_dir() / "studio.db"
        if not db_path.exists():
            return None
        from core.eval.runner import run_outcome_eval

        return run_outcome_eval(
            db_path=db_path,
            dream_studio_home=paths.meta_dir().parent,
            auto_reopen=True,
            symptom_only=True,
            window_hours=168,  # only recently-closed (7d) — never reopen ancient WOs
        )
    except Exception:
        return None


def check_stale_agents(plugin_root: Path) -> list[str]:
    """Return repo_names of agent-type ingest-log entries whose refresh_due has passed."""
    ingest_log = plugin_root / "skills" / "domains" / "ingest-log.yml"
    if not ingest_log.exists():
        return []
    try:
        import yaml

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
                    stale.append(
                        f"{entry.get('repo_name', 'unknown')} ({days_over}d past refresh_due)"
                    )
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


def _run_memory_maintenance() -> None:
    """Archive stale memories, prune MEMORY.md, and enforce the active-count cap."""
    try:
        mem_dir = paths.memory_dir()
        if not mem_dir.exists():
            return
        ms = MemorySearch(mem_dir)
        archived_count = ms.archive_stale(days=90)
        if archived_count > 0:
            archive_dir = mem_dir / "archive"
            archived_paths = list(archive_dir.glob("*.md")) if archive_dir.exists() else []
            ms.prune_memory_md(archived_paths)
            print(
                f"[on-pulse] Archived {archived_count} stale memory file(s) → memory/archive/",
                file=sys.stderr,
                flush=True,
            )
        ms.enforce_limit(max_active=90)
        ms.close()
    except Exception:
        pass


def _import_and_rotate_buffer() -> int:
    """Batch-import telemetry buffer into DB, rotate file, rebuild summaries and prune."""
    try:
        from core.event_store.studio_db import (
            import_buffer,
            rolling_window_prune,
        )

        buf = paths.state_dir() / "telemetry-buffer.jsonl"
        if not buf.exists() or not buf.read_bytes().strip():
            return 0
        n = import_buffer(buf)
        buf.replace(buf.with_suffix(".jsonl.bak"))
        buf.write_bytes(b"")
        # get_skill_summaries computes live from raw_skill_telemetry — no rebuild step
        rolling_window_prune()
        return n
    except Exception:
        return 0


def _get_skill_health() -> tuple[list[dict], str]:
    """Return (summaries, formatted Skill Health section for pulse report)."""
    try:
        from core.event_store.studio_db import get_skill_summaries

        summaries = get_skill_summaries()
    except Exception:
        return [], "### Skill Health\n\n- Telemetry DB unavailable.\n\n"
    if not summaries:
        return [], "### Skill Health\n\n- No telemetry data yet.\n\n"
    degraded = [s for s in summaries if (s.get("success_rate") or 1.0) < 0.70]
    if not degraded:
        return (
            summaries,
            f"### Skill Health\n\n- All {len(summaries)} tracked skill(s) ≥70% success.\n\n",
        )
    lines = ["### Skill Health\n\n"]
    for s in degraded:
        rate = round((s.get("success_rate") or 0.0) * 100)
        ids_str = ", ".join(str(i) for i in (s.get("recent_failure_ids") or []))
        lines.append(
            f"- ⚠ {s['skill_name']} — {s['times_used']} uses, {rate}% success"
            + (f" (ids: {ids_str})" if ids_str else "")
            + "\n"
        )
    return summaries, "".join(lines) + "\n"


def _update_skill_metadata(plugin_root: Path, summaries: list[dict]) -> None:
    """Atomically update quality_metrics in each skill's metadata.yml; remove stale .tmp files."""
    import yaml

    for stale in (plugin_root / "skills").glob("*/metadata.yml.tmp"):
        try:
            stale.unlink()
        except Exception:
            pass
    for s in summaries:
        if (s.get("times_used") or 0) < 5:
            continue
        meta_path = plugin_root / "skills" / s["skill_name"] / "metadata.yml"
        if not meta_path.exists():
            continue
        try:
            data = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            data["quality_metrics"] = {
                "times_used": s.get("times_used") or 0,
                "success_rate": round(s.get("success_rate") or 0.0, 4),
                "avg_token_usage": int(
                    (s.get("avg_input_tokens") or 0) + (s.get("avg_output_tokens") or 0)
                ),
                "avg_execution_time_seconds": round(s.get("avg_exec_time_s") or 0.0, 2),
                "last_success": s.get("last_success"),
                "last_failure": s.get("last_failure"),
            }
            tmp = meta_path.with_suffix(".yml.tmp")
            tmp.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
            tmp.replace(meta_path)
        except Exception:
            pass


def generate_pulse() -> tuple[str, dict]:
    date = utcnow().strftime("%Y-%m-%d %H:%M UTC")
    repo = _github_repo()

    if repo:
        stale_branches = check_stale_branches(repo)
        overdue_ms = check_overdue_milestones(repo)
        open_prs = check_open_prs(repo)
        ci_status = check_ci_status(repo)
        full_ci_conclusion = check_full_ci_on_main(repo)
    else:
        stale_branches, overdue_ms, open_prs, ci_status = [], [], [], "no github_repo configured"
        full_ci_conclusion = None

    archived = auto_archive_stale_drafts()
    _run_memory_maintenance()
    pending_drafts = check_pending_drafts()
    corrections_count, last_correction = check_corrections_growth()
    _run_outcome_eval_safe()
    open_escalations = check_open_escalations()
    stale_agents = check_stale_agents(Path(__file__).resolve().parents[2])
    storage_issues = check_storage()
    mem_stats = collect_memory_stats()
    drafts_overflow = len(pending_drafts) > MAX_PENDING_DRAFTS
    skill_summaries, health_section = _get_skill_health()
    _update_skill_metadata(Path(__file__).resolve().parents[2], skill_summaries)
    telemetry_degraded = sum(1 for s in skill_summaries if (s.get("success_rate") or 1.0) < 0.70)
    from core.eval.friction import count_degraded_skills

    registry_degraded = count_degraded_skills()
    degraded_count = max(telemetry_degraded, registry_degraded)

    issues = (
        len(stale_branches)
        + len(overdue_ms)
        + len(open_escalations)
        + len(stale_agents)
        + len(storage_issues)
        + degraded_count
    )
    if drafts_overflow:
        issues += 1
    if issues == 0:
        health = "HEALTHY"
    elif issues <= 3:
        health = "ATTENTION"
    else:
        health = "ACTION NEEDED"

    # Full-CI red on main always degrades health to at least DEGRADED.
    if full_ci_conclusion == "failure" and health == "HEALTHY":
        health = "DEGRADED"

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
        f"- {ci_status}\n"
        + (
            f"- **full-ci (main): {full_ci_conclusion} ⚠ health degraded**\n"
            if full_ci_conclusion == "failure"
            else (
                f"- full-ci (main): {full_ci_conclusion}\n"
                if full_ci_conclusion is not None
                else ""
            )
        )
        + "\n"
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
        f"### Storage\n\n"
        f"{bullets(storage_issues, 'Within limits')}\n"
        f"### Stale Domain Knowledge\n\n"
        f"{bullets(stale_agents, 'All agents current')}\n"
        f"{('Run `workflow: domain-refresh` to re-synthesize stale agents.' + chr(10)) if stale_agents else ''}"
        + (
            f"### Memory Health\n\n"
            f"- memory_active: {mem_stats['memory_active']}\n"
            f"- memory_archived: {mem_stats['memory_archived']}\n"
            f"- memory_index_age_secs: {mem_stats['memory_index_age_secs']}\n"
            f"- memory_top_score: {mem_stats['memory_top_score']:.2f}\n\n"
            if mem_stats
            else ""
        )
        + health_section
        + "---\n\n"
        "*Generated by dream-studio on-pulse hook.*\n"
    )

    stats = {
        "health": health,
        "stale_branches": len(stale_branches),
        "overdue_milestones": len(overdue_ms),
        "open_prs": len(open_prs),
        "ci_status": ci_status,
        "full_ci_conclusion": full_ci_conclusion,
        "pending_drafts": len(pending_drafts),
        "corrections": corrections_count,
        "escalations": len(open_escalations),
        "stale_agents": len(stale_agents),
        "storage_issues": len(storage_issues),
        "degraded_skills": degraded_count,
        **mem_stats,
    }
    return report, stats


def _cooldown_active() -> bool:
    """Return True if the last pulse ran less than PULSE_COOLDOWN_SEC ago."""
    last = state.read_pulse()
    ts = last.get("timestamp")
    if not ts:
        return False
    try:
        last_run = datetime.fromisoformat(ts)
        elapsed = (utcnow() - last_run).total_seconds()
        return elapsed < COOLDOWN_SEC
    except (ValueError, TypeError):
        return False


def run_pulse_check() -> None:
    """Main pulse check implementation."""
    paths.warn_version_mismatch()
    paths.check_for_update()
    # Quiet mode: suppress advisory hooks for N turns (user-configured)
    remaining = state.get_quiet_mode()
    if remaining > 0:
        state.set_quiet_mode(remaining - 1)
        return
    if _cooldown_active():
        # Return cached pulse data instead of re-running checks
        cached = state.read_pulse()

        print(
            f"\n[dream-studio] Pulse check complete (cached) — {cached.get('health', 'UNKNOWN')}\n"
            f"  -> Stale branches: {cached.get('stale_branches', 0)}\n"
            f"  -> Overdue milestones: {cached.get('overdue_milestones', 0)}\n"
            f"  -> Open PRs: {cached.get('open_prs', 0)}\n"
            f"  -> Pending draft lessons: {cached.get('pending_drafts', 0)}\n"
            f"  -> Stale domain agents: {cached.get('stale_agents', 0)}\n"
            f"  -> Storage warnings: {cached.get('storage_issues', 0)}\n"
            + (
                f"  -> Degraded skills: {cached.get('degraded_skills', 0)}\n"
                if cached.get("degraded_skills")
                else ""
            ),
            file=sys.stderr,
            flush=True,
        )

        # stderr, not stdout. on-prompt-dispatch concatenates every handler's
        # stdout into ONE text stream of <xml> blocks; a JSON object printed into
        # that stream makes the whole thing look like JSON to the harness, which
        # then fails to parse it and reports every prompt as a hook error. This
        # payload is status, not a hook directive, and it is already persisted to
        # the authority, so it has no claim on the directive channel.
        print(
            json.dumps({"status": "ok", "hook": "on-pulse", **cached, "cached": True}),
            file=sys.stderr,
        )
        return
    imported = _import_and_rotate_buffer()
    report, stats = generate_pulse()

    state.write_pulse({"timestamp": utcnow().isoformat(), **stats})

    try:
        from core.event_store.studio_db import insert_operational_snapshot

        project_slug = Path.cwd().name
        insert_operational_snapshot(
            snapshot_date=utcnow().strftime("%Y-%m-%d"),
            project_slug=project_slug,
            ci_status=stats.get("ci_status"),
            open_prs=stats.get("open_prs"),
            stale_branches=stats.get("stale_branches"),
            pending_drafts=stats.get("pending_drafts"),
            open_escalations=stats.get("escalations"),
            # WO-FILESDB-C4B S4: the FULL pulse body is captured in the authority
            # (raw_operational_snapshots.report_body) — C4B-5 dropped the disk
            # pulse-<date>.md write, so this is now the sole copy.
            report_body=report,
        )
    except Exception:
        pass

    print(
        f"\n[dream-studio] Pulse check complete — {stats['health']}\n"
        f"  -> Report: stored in the authority (raw_operational_snapshots.report_body)\n"
        f"  -> Stale branches: {stats['stale_branches']}\n"
        f"  -> Overdue milestones: {stats['overdue_milestones']}\n"
        f"  -> Open PRs: {stats['open_prs']}\n"
        f"  -> Pending draft lessons: {stats['pending_drafts']}\n"
        f"  -> Stale domain agents: {stats['stale_agents']}\n"
        f"  -> Storage warnings: {stats['storage_issues']}\n"
        + (f"  -> Telemetry imported: {imported} row(s)\n" if imported else "")
        + (
            f"  -> Degraded skills: {stats['degraded_skills']}\n"
            if stats["degraded_skills"]
            else ""
        ),
        file=sys.stderr,
        flush=True,
    )

    # stderr for the same reason as the cached branch above: this is status,
    # not a hook directive, and stdout is a shared text stream.
    print(json.dumps({"status": "ok", "hook": "on-pulse", **stats}), file=sys.stderr)
