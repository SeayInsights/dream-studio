"""`ds pulse` -- the health report, on demand instead of in your face.

The pulse used to print an eight-line summary into the model's context on every
single prompt, cached or fresh. It is actionable on the rare turn something is
genuinely overdue and noise on every other one, which made it the highest
frequency / lowest value thing the platform did.

The hook now prints one line, and only when health is not HEALTHY. This command
is where the full report lives. Nothing about collection changed -- the data was
always written to the authority; only the narration moved.
"""

from __future__ import annotations

import argparse


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach the ``pulse`` subparser to *subcommands*."""
    pulse_cmd = subcommands.add_parser("pulse", help="Show the project health report")
    pulse_cmd.add_argument(
        "--refresh",
        action="store_true",
        default=False,
        help="Re-collect now instead of showing the last cached report",
    )


def handle(args: argparse.Namespace) -> int:
    from core.config import state
    from interfaces.cli import pulse_collector

    if args.refresh:
        report, stats = pulse_collector.generate_pulse()
        state.write_pulse({"timestamp": pulse_collector.utcnow().isoformat(), **stats})
    else:
        stats = state.read_pulse()
        if not stats:
            print("No pulse recorded yet. Run `ds pulse --refresh`.")
            return 0
        report = None

    health = stats.get("health", "UNKNOWN")
    print(f"\n[dream-studio] Pulse - {health}")
    for label, key in (
        ("Stale branches", "stale_branches"),
        ("Overdue milestones", "overdue_milestones"),
        ("Open PRs", "open_prs"),
        ("Pending draft lessons", "pending_drafts"),
        ("Stale domain agents", "stale_agents"),
        ("Degraded skills", "degraded_skills"),
        ("Open escalations", "escalations"),
    ):
        value = stats.get(key)
        if value:
            print(f"  {label:<24} {value}")
    if stats.get("timestamp"):
        print(f"  {'Collected':<24} {stats['timestamp']}")
    if report:
        print(f"\n{report}")
    else:
        print("\n  Full report: raw_operational_snapshots.report_body in the authority.")
    return 0
