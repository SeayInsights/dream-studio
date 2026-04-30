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
    ap.add_argument("--project", type=Path, default=None, help="project root for scoped analytics")
    args = ap.parse_args()

    db_path: Path | None = args.db
    project_path: Path | None = args.project

    if project_path:
        project_slug = project_path.name
        print(f"DSAE: project-scoped mode — {project_slug}")
    else:
        project_slug = None

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

    spec_count = harvest_specs(db_path)
    print(f"  planning specs:  {spec_count}")

    orphans = detect_orphans(db_path)
    print(f"  orphaned specs:  {len(orphans)}")

    velocity_df = harvest_skill_velocity(db_path)
    print(f"  skill telemetry: {len(velocity_df)} rows")

    op_rows = harvest_operational(db_path, project_slug)
    print(f"  operational:     {len(op_rows)} snapshots")

    git_metrics = None
    if project_path:
        from ds_analytics.git_harvester import harvest_git_metrics
        git_metrics = harvest_git_metrics(project_path)
        if git_metrics:
            print(f"  git metrics:     {git_metrics['total_commits_90d']} commits (90d), {git_metrics['branch_count']} branches")
        else:
            print("  git metrics:     not a git repo, skipped")

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
    if output is None and project_path:
        output = project_path / ".dream-studio" / "analytics" / "dashboard.html"

    data = {
        "pulse_trend": pulse_trend,
        "skill_velocity": skill_velocity,
        "conversion_rate": conversion_rate,
        "git_metrics": git_metrics,
        "project_name": project_slug,
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
