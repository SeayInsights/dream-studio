#!/usr/bin/env python3
"""
CLI for running the risk scoring engine.

Usage:
    py analytics/scoring/cli.py --run                # Run once
    py analytics/scoring/cli.py --daemon             # Run forever (5 min intervals)
    py analytics/scoring/cli.py --daemon --interval 60  # Custom interval
"""

import argparse
import sys
from pathlib import Path
from projections.scoring import RiskScoringEngine


def main():
    parser = argparse.ArgumentParser(description="Risk Scoring Engine CLI")
    parser.add_argument("--run", action="store_true", help="Run scoring once")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon (forever)")
    parser.add_argument(
        "--interval", type=int, default=300, help="Interval in seconds (default: 300)"
    )
    parser.add_argument("--db", type=str, help="Database path (default: ~/.dream-studio/studio.db)")

    args = parser.parse_args()

    # Default DB path
    db_path = args.db or str(Path.home() / ".dream-studio" / "studio.db")

    # Initialize engine
    engine = RiskScoringEngine(db_path)

    if args.daemon:
        print(f"Starting risk scoring daemon (interval: {args.interval}s)")
        print(f"Database: {db_path}")
        print("Press Ctrl+C to stop")
        try:
            engine.run_forever(interval_sec=args.interval)
        except KeyboardInterrupt:
            print("\nStopping risk scoring daemon")
            sys.exit(0)
    elif args.run:
        print(f"Running risk scoring once (database: {db_path})")
        events = engine.fetch_unscored_events()
        print(f"Found {len(events)} events to score")
        for event in events:
            score = engine.compute_risk_score(event)
            engine.emit_enriched_event(event, score)
        print("Done")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
