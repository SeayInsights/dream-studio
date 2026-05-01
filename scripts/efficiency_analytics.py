#!/usr/bin/env python3
"""Efficiency analytics for dream-studio sessions.

Parses token-log.md (the SSOT for per-session token trajectories) and computes:
- Time to context limit per session (duration before handoff/compaction)
- Token usage per session (total consumption, burn rate)
- Model distribution (Opus vs Sonnet vs Haiku)
- Tokens per task (from handoff data)
- Session lifecycle stats (avg duration, peak tokens, context pressure)

Usage:
    py scripts/efficiency_analytics.py                   # full report
    py scripts/efficiency_analytics.py --json            # JSON output only
    py scripts/efficiency_analytics.py --days 14         # last 14 days
    py scripts/efficiency_analytics.py --export <path>   # save JSON to file
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
from lib import paths

CONTEXT_LIMIT_TOKENS = 400_000


def parse_token_log(log_path: Path | None = None) -> list[dict]:
    """Parse token-log.md into structured records.

    Each row has: timestamp, session_id, model, prompt_tokens (cumulative),
    completion_tokens (cumulative), total_tokens (cumulative).
    """
    if log_path is None:
        log_path = paths.meta_dir() / "token-log.md"
    if not log_path.is_file():
        return []

    records = []
    line_re = re.compile(
        r"\|\s*(\d{4}-\d{2}-\d{2}T[^\s|]+)\s*\|"
        r"\s*([0-9a-f-]{36})\s*\|"
        r"\s*([^\s|]+)\s*\|"
        r"\s*([0-9,]+)\s*\|"
        r"\s*([0-9,]+)\s*\|"
        r"\s*([0-9,]+)\s*\|"
    )

    for line in log_path.read_text(encoding="utf-8").splitlines():
        m = line_re.match(line)
        if not m:
            continue
        records.append({
            "timestamp": m.group(1),
            "session_id": m.group(2),
            "model": m.group(3),
            "prompt_tokens": int(m.group(4).replace(",", "")),
            "completion_tokens": int(m.group(5).replace(",", "")),
            "total_tokens": int(m.group(6).replace(",", "")),
        })
    return records


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def build_sessions(records: list[dict], cutoff: datetime | None = None) -> list[dict]:
    """Group token records by session_id and compute per-session metrics."""
    by_session: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_session[r["session_id"]].append(r)

    sessions = []
    for sid, recs in by_session.items():
        recs.sort(key=lambda x: x["timestamp"])
        first = recs[0]
        last = recs[-1]

        start = _parse_ts(first["timestamp"])
        end = _parse_ts(last["timestamp"])

        if cutoff and start < cutoff:
            continue

        duration_s = (end - start).total_seconds()
        duration_min = duration_s / 60

        peak_tokens = last["total_tokens"]
        burn_rate = peak_tokens / duration_min if duration_min > 0 else 0

        # Context pressure: how close did we get to the limit?
        context_pct = (peak_tokens / CONTEXT_LIMIT_TOKENS) * 100

        # Model usage within this session
        models = defaultdict(int)
        for r in recs:
            models[r["model"]] += 1
        primary_model = max(models, key=lambda m: models[m])

        sessions.append({
            "session_id": sid,
            "start": first["timestamp"],
            "end": last["timestamp"],
            "date": start.strftime("%Y-%m-%d"),
            "duration_min": round(duration_min, 1),
            "checkpoints": len(recs),
            "peak_tokens": peak_tokens,
            "prompt_tokens": last["prompt_tokens"],
            "completion_tokens": last["completion_tokens"],
            "context_pct": round(context_pct, 1),
            "burn_rate_per_min": round(burn_rate),
            "primary_model": primary_model,
            "model_breakdown": dict(models),
            "hit_context_limit": context_pct >= 75,
        })

    sessions.sort(key=lambda x: x["start"])
    return sessions


def get_handoff_tasks(db_path: Path | None = None) -> dict:
    """Get task completion data from handoffs for efficiency ratios."""
    if db_path is None:
        db_path = paths.state_dir() / "studio.db"
    if not db_path.is_file():
        return {}

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT topic, tasks_completed, tasks_total, created_at FROM raw_handoffs"
        ).fetchall()
        conn.close()
        return {r["topic"]: dict(r) for r in rows}
    except Exception:
        return {}


def compute_efficiency_report(sessions: list[dict], handoffs: dict) -> dict:
    """Compute aggregate efficiency metrics."""
    if not sessions:
        return {"error": "No session data found"}

    durations = [s["duration_min"] for s in sessions if s["duration_min"] > 1]
    peaks = [s["peak_tokens"] for s in sessions]
    burns = [s["burn_rate_per_min"] for s in sessions if s["burn_rate_per_min"] > 0]
    context_pcts = [s["context_pct"] for s in sessions]

    # Model distribution across all sessions
    model_tokens = defaultdict(int)
    model_sessions = defaultdict(int)
    for s in sessions:
        model_tokens[s["primary_model"]] += s["peak_tokens"]
        model_sessions[s["primary_model"]] += 1

    total_model_tokens = sum(model_tokens.values()) or 1
    model_dist = {
        m: {
            "sessions": model_sessions[m],
            "total_tokens": model_tokens[m],
            "pct_tokens": round(model_tokens[m] / total_model_tokens * 100, 1),
        }
        for m in sorted(model_tokens, key=lambda k: model_tokens[k], reverse=True)
    }

    # Sessions that hit context pressure (>75% of limit)
    high_pressure = [s for s in sessions if s["hit_context_limit"]]

    # Task efficiency
    total_tasks = sum(h.get("tasks_completed", 0) or 0 for h in handoffs.values())
    total_tokens_all = sum(peaks)
    tokens_per_task = round(total_tokens_all / total_tasks) if total_tasks > 0 else None

    # Daily aggregation for trends
    daily = defaultdict(lambda: {"sessions": 0, "total_tokens": 0, "total_duration_min": 0})
    for s in sessions:
        d = s["date"]
        daily[d]["sessions"] += 1
        daily[d]["total_tokens"] += s["peak_tokens"]
        daily[d]["total_duration_min"] += s["duration_min"]

    return {
        "summary": {
            "total_sessions": len(sessions),
            "date_range": f"{sessions[0]['date']} to {sessions[-1]['date']}",
            "total_tokens_consumed": total_tokens_all,
        },
        "time_to_context": {
            "avg_duration_min": round(sum(durations) / len(durations), 1) if durations else 0,
            "median_duration_min": round(sorted(durations)[len(durations) // 2], 1) if durations else 0,
            "max_duration_min": round(max(durations), 1) if durations else 0,
            "min_duration_min": round(min(durations), 1) if durations else 0,
            "sessions_hitting_75pct": len(high_pressure),
            "pct_hitting_75pct": round(len(high_pressure) / len(sessions) * 100, 1),
        },
        "token_usage": {
            "avg_peak_tokens": round(sum(peaks) / len(peaks)),
            "median_peak_tokens": sorted(peaks)[len(peaks) // 2],
            "max_peak_tokens": max(peaks),
            "avg_burn_rate_per_min": round(sum(burns) / len(burns)) if burns else 0,
            "tokens_per_task": tokens_per_task,
            "total_tasks_completed": total_tasks,
        },
        "model_distribution": model_dist,
        "context_pressure": {
            "avg_context_pct": round(sum(context_pcts) / len(context_pcts), 1),
            "sessions_over_50pct": len([p for p in context_pcts if p >= 50]),
            "sessions_over_75pct": len(high_pressure),
            "sessions_over_90pct": len([p for p in context_pcts if p >= 90]),
        },
        "daily_trends": {
            d: {
                "sessions": v["sessions"],
                "total_tokens": v["total_tokens"],
                "avg_tokens_per_session": round(v["total_tokens"] / v["sessions"]),
                "total_duration_min": round(v["total_duration_min"], 1),
            }
            for d, v in sorted(daily.items())
        },
        "sessions": sessions,
    }


def print_report(report: dict) -> None:
    """Print a formatted efficiency report to stdout."""
    s = report["summary"]
    t = report["time_to_context"]
    u = report["token_usage"]
    p = report["context_pressure"]

    print("=" * 70)
    print("  DREAM-STUDIO EFFICIENCY REPORT")
    print("=" * 70)
    print(f"  Sessions: {s['total_sessions']}  |  Period: {s['date_range']}")
    print(f"  Total tokens consumed: {s['total_tokens_consumed']:,}")
    print()

    print("--- TIME TO CONTEXT (independent) ---")
    print(f"  Avg session duration:     {t['avg_duration_min']} min")
    print(f"  Median session duration:  {t['median_duration_min']} min")
    print(f"  Range:                    {t['min_duration_min']} - {t['max_duration_min']} min")
    print(f"  Sessions hitting 75%:     {t['sessions_hitting_75pct']} ({t['pct_hitting_75pct']}%)")
    print()

    print("--- TOKEN USAGE (independent) ---")
    print(f"  Avg peak tokens:          {u['avg_peak_tokens']:,}")
    print(f"  Median peak tokens:       {u['median_peak_tokens']:,}")
    print(f"  Max peak tokens:          {u['max_peak_tokens']:,}")
    print(f"  Avg burn rate:            {u['avg_burn_rate_per_min']:,} tokens/min")
    if u["tokens_per_task"]:
        print(f"  Tokens per task:          {u['tokens_per_task']:,}")
        print(f"  Total tasks completed:    {u['total_tasks_completed']}")
    print()

    print("--- CONTEXT PRESSURE ---")
    print(f"  Avg context usage:        {p['avg_context_pct']}%")
    print(f"  Sessions >50% context:    {p['sessions_over_50pct']}")
    print(f"  Sessions >75% context:    {p['sessions_over_75pct']}")
    print(f"  Sessions >90% context:    {p['sessions_over_90pct']}")
    print()

    print("--- MODEL DISTRIBUTION ---")
    for model, info in report["model_distribution"].items():
        print(f"  {model:30s}  {info['sessions']:3d} sessions  {info['pct_tokens']:5.1f}% tokens")
    print()

    # Top 10 longest sessions
    by_duration = sorted(report["sessions"], key=lambda x: x["duration_min"], reverse=True)[:10]
    print("--- TOP 10 LONGEST SESSIONS ---")
    print(f"  {'Date':12s} {'Duration':>10s} {'Peak Tokens':>14s} {'Context%':>10s} {'Model':>25s}")
    for s in by_duration:
        if s["duration_min"] < 1:
            continue
        print(
            f"  {s['date']:12s} {s['duration_min']:>8.1f}m "
            f"{s['peak_tokens']:>13,} {s['context_pct']:>9.1f}% "
            f"{s['primary_model']:>25s}"
        )
    print()

    # Daily trend summary
    print("--- DAILY TRENDS ---")
    print(f"  {'Date':12s} {'Sessions':>10s} {'Tokens':>14s} {'Avg/Session':>14s} {'Duration':>10s}")
    for d, v in sorted(report["daily_trends"].items()):
        print(
            f"  {d:12s} {v['sessions']:>10d} {v['total_tokens']:>13,} "
            f"{v['avg_tokens_per_session']:>13,} {v['total_duration_min']:>8.1f}m"
        )
    print()
    print("=" * 70)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Dream-studio efficiency analytics")
    parser.add_argument("--days", type=int, default=90, help="Analyze last N days")
    parser.add_argument("--json", action="store_true", help="JSON output only")
    parser.add_argument("--export", metavar="PATH", help="Save JSON to file")
    args = parser.parse_args(argv)

    records = parse_token_log()
    if not records:
        print("No token-log.md data found.", file=sys.stderr)
        sys.exit(1)

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    sessions = build_sessions(records, cutoff)
    handoffs = get_handoff_tasks()
    report = compute_efficiency_report(sessions, handoffs)

    if args.json:
        # Remove full session list for cleaner JSON output
        compact = {k: v for k, v in report.items() if k != "sessions"}
        print(json.dumps(compact, indent=2))
    elif args.export:
        compact = {k: v for k, v in report.items() if k != "sessions"}
        out = Path(args.export)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(compact, indent=2), encoding="utf-8")
        print(f"Exported: {out}")
    else:
        print_report(report)

    # Also save to state dir for dashboard consumption
    state_out = paths.state_dir() / "efficiency-analytics.json"
    compact = {k: v for k, v in report.items() if k != "sessions"}
    state_out.write_text(json.dumps(compact, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
