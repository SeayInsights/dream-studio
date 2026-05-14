#!/usr/bin/env python3
"""CLI tool to check validation health and display metrics.

Usage:
    python interfaces/cli/validation_health.py [--minutes 60] [--alert]

Options:
    --minutes N    Time window in minutes (default: 60)
    --alert        Exit with code 1 if alert threshold breached
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from core.monitoring.validation_monitor import ValidationMonitor


def format_metrics_report(monitor: ValidationMonitor, minutes: int) -> str:
    """Format validation metrics as readable report."""
    metrics = monitor.get_metrics(minutes)
    breakdown = monitor.get_failure_breakdown(minutes)
    patterns = monitor.get_error_patterns(minutes)

    lines = []
    lines.append("=" * 70)
    lines.append("VALIDATION HEALTH REPORT")
    lines.append("=" * 70)
    lines.append(f"Time Window: Past {minutes} minutes")
    lines.append(f"Total Failures: {metrics.total_failures}")
    lines.append(f"Unique Event Types: {metrics.unique_event_types}")
    lines.append(f"Failure Rate: {metrics.failure_rate:.2f} per minute")

    if metrics.most_common_failure:
        lines.append(f"Most Common: {metrics.most_common_failure}")

    # Alert status
    alert = monitor.check_thresholds(metrics)
    if alert:
        lines.append(f"\n[{alert.alert_level.upper()}] {alert.message}")
    else:
        lines.append("\n[OK] Failure rate within normal thresholds")

    # Breakdown by event type
    if breakdown:
        lines.append(f"\nTop Failing Event Types:")
        for event_type, count in breakdown[:10]:
            pct = (count / metrics.total_failures * 100) if metrics.total_failures > 0 else 0
            lines.append(f"  {count:4d} ({pct:5.1f}%)  {event_type}")

    # Error patterns
    if patterns:
        lines.append(f"\nError Patterns:")
        for pattern, count in sorted(patterns.items(), key=lambda x: x[1], reverse=True):
            pct = (count / metrics.total_failures * 100) if metrics.total_failures > 0 else 0
            lines.append(f"  {count:4d} ({pct:5.1f}%)  {pattern}")

    lines.append("=" * 70)

    return "\n".join(lines)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Check validation health and display metrics")
    parser.add_argument(
        "--minutes", type=int, default=60, help="Time window in minutes (default: 60)"
    )
    parser.add_argument(
        "--alert", action="store_true", help="Exit with code 1 if alert threshold breached"
    )

    args = parser.parse_args()

    # Create monitor and get report
    with ValidationMonitor() as monitor:
        report = format_metrics_report(monitor, args.minutes)
        print(report)

        # Check for alerts
        if args.alert:
            alert = monitor.check_thresholds(monitor.get_metrics(args.minutes))
            if alert:
                sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
