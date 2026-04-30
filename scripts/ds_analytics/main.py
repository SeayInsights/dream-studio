"""ds-analytics: dream-studio analytics pipeline."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "hooks"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
from lib import paths  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="ds-analytics — harvest, analyze, render")
    ap.add_argument("--db", type=Path, default=None, help="override studio.db path")
    ap.add_argument("--output", type=Path, default=None, help="override dashboard output path")
    ap.add_argument("--project", type=Path, default=None, help="single project root")
    ap.add_argument("--projects-dir", type=Path, default=None,
                     help="scan all git repos in this directory (default: ~/builds)")
    args = ap.parse_args()

    db_path: Path | None = args.db

    from ds_analytics.git_harvester import discover_projects, harvest_git_metrics

    # Determine project list
    if args.project:
        project_roots = [args.project.resolve()]
        print(f"DSAE: single project — {args.project.name}")
    elif args.projects_dir:
        project_roots = discover_projects(args.projects_dir.resolve())
        print(f"DSAE: scanning {args.projects_dir} — {len(project_roots)} projects")
    else:
        default_builds = Path.home() / "builds"
        if default_builds.is_dir():
            project_roots = discover_projects(default_builds)
            print(f"DSAE: auto-scanning ~/builds — {len(project_roots)} projects")
        else:
            project_roots = []

    print("DSAE: harvesting...")

    from ds_analytics.harvester import (
        harvest_pulse,
        harvest_specs,
        detect_orphans,
        harvest_skill_velocity,
        harvest_operational,
    )

    pulse_rows = harvest_pulse(db_path)
    print(f"  pulse snapshots: {len(pulse_rows)}")

    spec_count = harvest_specs(db_path, extra_roots=project_roots)
    print(f"  planning specs:  {spec_count}")

    orphans = detect_orphans(db_path, git_roots=project_roots or None)
    print(f"  orphaned specs:  {len(orphans)}")

    velocity_df = harvest_skill_velocity(db_path)
    print(f"  skill telemetry: {len(velocity_df)} rows")

    op_rows = harvest_operational(db_path)
    print(f"  operational:     {len(op_rows)} snapshots")

    all_git_metrics: list[dict] = []
    if project_roots:
        for pr in project_roots:
            gm = harvest_git_metrics(pr)
            if gm:
                all_git_metrics.append(gm)
        total_commits = sum(g["total_commits_90d"] for g in all_git_metrics)
        print(f"  git metrics:     {len(all_git_metrics)} repos, {total_commits} commits (90d)")

    print("DSAE: analyzing...")

    from ds_analytics.analyzer import (
        compute_pulse_trend,
        compute_skill_velocity,
        compute_conversion_rate,
    )

    pulse_trend = compute_pulse_trend(db_path)
    print(f"  pulse trend:     {pulse_trend['trend_direction']} (slope={pulse_trend['trend_slope']:.2f})")

    skill_velocity = compute_skill_velocity(db_path)
    print(f"  skill velocity:  {len(skill_velocity)} skills")

    conversion_rate = compute_conversion_rate(db_path)
    print(f"  conversion rate: {conversion_rate['rate']:.0%} ({conversion_rate['total'] - conversion_rate['orphaned']}/{conversion_rate['total']})")

    print("DSAE: rendering...")

    from ds_analytics.renderer import render_dashboard

    output = args.output
    if output is None and len(project_roots) == 1:
        output = project_roots[0] / ".dream-studio" / "analytics" / "dashboard.html"

    project_name = project_roots[0].name if len(project_roots) == 1 else None

    data = {
        "pulse_trend": pulse_trend,
        "skill_velocity": skill_velocity,
        "conversion_rate": conversion_rate,
        "git_metrics": all_git_metrics[0] if len(all_git_metrics) == 1 else None,
        "all_git_metrics": all_git_metrics if len(all_git_metrics) > 1 else None,
        "project_name": project_name,
    }

    output_path = render_dashboard(data, output)
    print(f"  dashboard: {output_path}")

    import sqlite3

    conn = sqlite3.connect(str(db_path or paths.state_dir() / "studio.db"))
    conn.execute(
        "INSERT INTO sum_analytics_run (run_at, pulse_rows, spec_rows, skill_rows, output_path) VALUES (?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), len(pulse_rows), spec_count, len(velocity_df), str(output_path)),
    )
    conn.commit()
    conn.close()

    print(f"\nDSAE complete. Open: {output_path}")


if __name__ == "__main__":
    main()
