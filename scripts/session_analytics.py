"""session_analytics.py — Parse historical session data, detect patterns, produce trend reports.

Usage:
    py scripts/session_analytics.py [--days N] [--project PATH] [--json]

Defaults:
    --days 90
    --project  (all projects found under harvest.projects_root in config)
    --json     print JSON only (no table)

Output:
    ~/.dream-studio/state/session-analytics.json
    Formatted summary table on stdout (unless --json)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Import session_parser from hooks/lib
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
try:
    from lib.session_parser import scan_sessions, extract_blockers
except ImportError as exc:
    print(f"[session_analytics] ERROR: cannot import session_parser: {exc}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    config_path = Path.home() / ".dream-studio" / "config.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[session_analytics] WARNING: could not read config: {exc}", file=sys.stderr)
    return {}


def _find_project_roots(config: dict, explicit_project: str | None) -> list[Path]:
    """Return a list of project directories to scan."""
    if explicit_project:
        p = Path(explicit_project).expanduser().resolve()
        if not p.is_dir():
            print(f"[session_analytics] WARNING: --project path not found: {p}", file=sys.stderr)
            return []
        return [p]

    projects_root = config.get("harvest", {}).get("projects_root", "")
    if not projects_root:
        # Fall back to cwd as a single project
        return [Path.cwd()]

    root = Path(projects_root).expanduser().resolve()
    if not root.is_dir():
        print(f"[session_analytics] WARNING: projects_root not found: {root}", file=sys.stderr)
        return []

    # Each immediate subdirectory that contains a .sessions dir is a project
    candidates: list[Path] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / ".sessions").is_dir():
            candidates.append(child)

    # Also include root itself if it has .sessions
    if (root / ".sessions").is_dir():
        candidates.insert(0, root)

    if not candidates:
        # Broader fallback: return root itself so we still scan
        return [root]

    return candidates


# ---------------------------------------------------------------------------
# Analytics engine
# ---------------------------------------------------------------------------

def _iso_week(date_str: str) -> str:
    """Convert YYYY-MM-DD to ISO week string YYYY-Www, or '' on error."""
    try:
        d = date.fromisoformat(date_str[:10])
        return f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
    except ValueError:
        return ""


def _date_window(date_str: str, today: date, window_days: int) -> str | None:
    """Return '30d', '60d', '90d' or None if outside the window."""
    try:
        d = date.fromisoformat(date_str[:10])
    except ValueError:
        return None
    delta = (today - d).days
    if delta < 0:
        delta = 0
    if delta <= 30:
        return "30d"
    if delta <= 60:
        return "60d"
    if delta <= window_days:
        return "90d"
    return None


def compute_analytics(sessions: list[dict], window_days: int) -> dict:
    """Compute all analytics from a list of parsed session dicts."""
    today = date.today()

    # --- Skill usage frequency (across all windows) ---
    skill_usage: dict[str, int] = defaultdict(int)
    skill_usage_by_window: dict[str, dict[str, int]] = {
        "30d": defaultdict(int),
        "60d": defaultdict(int),
        "90d": defaultdict(int),
    }

    # --- Failure tracking per skill ---
    # failure = session that has broken_items or risk_flags
    skill_total: dict[str, int] = defaultdict(int)
    skill_failed: dict[str, int] = defaultdict(int)

    # --- Task tracking ---
    tasks_completed_sum = 0
    tasks_total_sum = 0
    sessions_with_tasks = 0

    # --- Correction count by skill ---
    correction_count_by_skill: dict[str, int] = defaultdict(int)

    # --- Session volume by week ---
    week_counts: dict[str, int] = defaultdict(int)

    # --- Blocker extraction handled separately via extract_blockers ---

    for s in sessions:
        s_date = s.get("date", "")
        window = _date_window(s_date, today, window_days)
        if window is None:
            continue

        week = _iso_week(s_date)
        if week:
            week_counts[week] += 1

        skills_used: list[str] = s.get("skills_used", []) or ["dream-studio:core"]

        # Flatten per-skill counts
        for sk in skills_used:
            skill_usage[sk] += 1
            skill_usage_by_window["90d"][sk] += 1
            if window in ("30d", "60d"):
                skill_usage_by_window["60d"][sk] += 1
            if window == "30d":
                skill_usage_by_window["30d"][sk] += 1

            skill_total[sk] += 1

            # Failure: handoff with broken_items, recap with risk_flags
            is_failed = False
            if s.get("type") == "handoff" and s.get("broken_items"):
                is_failed = True
            elif s.get("type") == "recap" and s.get("risk_flags"):
                is_failed = True
            if is_failed:
                skill_failed[sk] += 1

            # Corrections
            corrections = s.get("corrections", [])
            correction_count_by_skill[sk] += len(corrections)

        # Task averages — handoff only
        if s.get("type") == "handoff":
            tc = s.get("tasks_completed", 0) or 0
            tt = s.get("tasks_total", 0) or 0
            if tt > 0:
                tasks_completed_sum += tc
                tasks_total_sum += tt
                sessions_with_tasks += 1

    # --- Failure rates ---
    failure_rates: dict[str, float] = {}
    for sk, total in skill_total.items():
        failed = skill_failed.get(sk, 0)
        failure_rates[sk] = round(failed / total, 4) if total else 0.0

    # --- Average tasks per session ---
    avg_tasks = round(tasks_completed_sum / sessions_with_tasks, 2) if sessions_with_tasks else 0.0

    # --- Common blockers ---
    blockers = extract_blockers(sessions)
    common_blockers = [
        {"item": b["item"], "frequency": b["frequency"]}
        for b in blockers[:20]  # top 20
    ]

    # --- Sessions per week (sorted ascending) ---
    sessions_per_week = [
        {"week": w, "count": c}
        for w, c in sorted(week_counts.items())
    ]

    return {
        "generated": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": window_days,
        "total_sessions": len(sessions),
        "skill_usage": dict(sorted(skill_usage.items(), key=lambda x: -x[1])),
        "skill_usage_by_window": {
            k: dict(sorted(v.items(), key=lambda x: -x[1]))
            for k, v in skill_usage_by_window.items()
        },
        "failure_rates": dict(sorted(failure_rates.items(), key=lambda x: -x[1])),
        "avg_tasks_per_session": avg_tasks,
        "common_blockers": common_blockers,
        "correction_count_by_skill": dict(
            sorted(correction_count_by_skill.items(), key=lambda x: -x[1])
        ),
        "sessions_per_week": sessions_per_week,
    }


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _save_output(analytics: dict) -> Path:
    state_dir = Path.home() / ".dream-studio" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    out_path = state_dir / "session-analytics.json"
    out_path.write_text(json.dumps(analytics, indent=2), encoding="utf-8")
    return out_path


def _print_table(analytics: dict) -> None:
    w = analytics["window_days"]
    total = analytics["total_sessions"]
    generated = analytics["generated"]

    SEP = "-" * 56
    print(f"\n{'='*56}")
    print(f"  dream-studio Session Analytics")
    print(f"  Generated : {generated}")
    print(f"  Window    : {w} days   |   Total sessions: {total}")
    print(f"{'='*56}")

    # Skill usage
    print(f"\nSkill Usage (last {w} days)")
    print(SEP)
    su = analytics.get("skill_usage", {})
    if su:
        for skill, count in su.items():
            bar = "#" * min(count, 40)
            print(f"  {skill:<30} {count:>4}  {bar}")
    else:
        print("  (no skill data)")

    # Failure rates
    print(f"\nFailure Rate per Skill")
    print(SEP)
    fr = analytics.get("failure_rates", {})
    if fr:
        for skill, rate in fr.items():
            pct = f"{rate*100:.1f}%"
            print(f"  {skill:<30} {pct:>6}")
    else:
        print("  (no failure data)")

    # Avg tasks
    avg = analytics.get("avg_tasks_per_session", 0)
    print(f"\nAverage Tasks per Session (handoff): {avg}")

    # Common blockers
    print(f"\nTop Common Blockers")
    print(SEP)
    blockers = analytics.get("common_blockers", [])
    if blockers:
        for i, b in enumerate(blockers[:10], 1):
            freq = b["frequency"]
            item = b["item"][:50]
            print(f"  {i:>2}. [{freq:>3}x] {item}")
    else:
        print("  (none found)")

    # Corrections by skill
    print(f"\nCorrection Count by Skill")
    print(SEP)
    cc = analytics.get("correction_count_by_skill", {})
    if cc:
        for skill, count in cc.items():
            print(f"  {skill:<30} {count:>4}")
    else:
        print("  (no correction data)")

    # Sessions per week
    print(f"\nSession Volume per Week")
    print(SEP)
    spw = analytics.get("sessions_per_week", [])
    if spw:
        for entry in spw[-12:]:  # last 12 weeks
            bar = "#" * min(entry["count"], 30)
            print(f"  {entry['week']}  {entry['count']:>3}  {bar}")
    else:
        print("  (no weekly data)")

    # Window breakdown
    print(f"\nSkill Usage by Window")
    print(SEP)
    sub = analytics.get("skill_usage_by_window", {})
    for win in ("30d", "60d", "90d"):
        data = sub.get(win, {})
        top = list(data.items())[:3]
        top_str = ", ".join(f"{s}({c})" for s, c in top) if top else "—"
        print(f"  {win}: {top_str}")

    print(f"\n{'='*56}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse dream-studio session data and produce trend reports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        metavar="N",
        help="Analysis window in days (default: 90)",
    )
    parser.add_argument(
        "--project",
        default=None,
        metavar="PATH",
        help="Path to a specific project directory (default: all projects under projects_root)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON output only (no table)",
    )
    args = parser.parse_args()

    config = _load_config()
    project_roots = _find_project_roots(config, args.project)

    if not project_roots:
        print("[session_analytics] No project directories found. Exiting.", file=sys.stderr)
        sys.exit(0)

    # Scan all project .sessions directories
    all_sessions: list[dict] = []
    for proj in project_roots:
        sessions_dir = proj / ".sessions"
        if sessions_dir.is_dir():
            parsed = scan_sessions(sessions_dir, days=args.days)
            all_sessions.extend(parsed)
        else:
            # Also try project root directly as a .sessions dir
            parsed = scan_sessions(proj, days=args.days)
            all_sessions.extend(parsed)

    # De-duplicate by (type, date, topic) — same session may appear if dirs overlap
    seen: set[tuple] = set()
    deduped: list[dict] = []
    for s in all_sessions:
        key = (s.get("type"), s.get("date"), s.get("topic"))
        if key not in seen:
            seen.add(key)
            deduped.append(s)
    all_sessions = deduped

    analytics = compute_analytics(all_sessions, window_days=args.days)

    # Save
    out_path = _save_output(analytics)

    if args.json:
        print(json.dumps(analytics, indent=2))
    else:
        _print_table(analytics)
        print(f"[session_analytics] Report saved to: {out_path}")


if __name__ == "__main__":
    main()
