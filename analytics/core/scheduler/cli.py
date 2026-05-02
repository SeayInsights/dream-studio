"""CLI tool for managing scheduled reports

Usage:
    python -m analytics.core.scheduler.cli list
    python -m analytics.core.scheduler.cli create --name "Daily Report" --type summary --schedule "0 9 * * *" --recipients "user@example.com"
    python -m analytics.core.scheduler.cli pause <job_id>
    python -m analytics.core.scheduler.cli resume <job_id>
    python -m analytics.core.scheduler.cli delete <job_id>
    python -m analytics.core.scheduler.cli run <job_id>
    python -m analytics.core.scheduler.cli status <job_id>
    python -m analytics.core.scheduler.cli stats
    python -m analytics.core.scheduler.cli start
"""

import sys
import argparse
import json
from pathlib import Path
from datetime import datetime

from analytics.core.scheduler import ReportScheduler, ScheduleStorage


def create_parser():
    """Create argument parser for CLI"""
    parser = argparse.ArgumentParser(
        description="Manage scheduled analytics reports",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # List command
    subparsers.add_parser("list", help="List all scheduled reports")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new scheduled report")
    create_parser.add_argument("--name", required=True, help="Report name")
    create_parser.add_argument("--type", required=True, choices=["summary", "detailed", "custom"],
                               help="Report type")
    create_parser.add_argument("--schedule", required=True, help="Cron expression (e.g., '0 9 * * *')")
    create_parser.add_argument("--recipients", required=True, help="Comma-separated email addresses")
    create_parser.add_argument("--format", default="pdf", choices=["pdf", "excel"], help="Export format")
    create_parser.add_argument("--timezone", default="UTC", help="Timezone for schedule")
    create_parser.add_argument("--config", help="JSON config for report (optional)")

    # Pause command
    pause_parser = subparsers.add_parser("pause", help="Pause a scheduled report")
    pause_parser.add_argument("job_id", help="Job ID to pause")

    # Resume command
    resume_parser = subparsers.add_parser("resume", help="Resume a paused report")
    resume_parser.add_argument("job_id", help="Job ID to resume")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a scheduled report")
    delete_parser.add_argument("job_id", help="Job ID to delete")
    delete_parser.add_argument("--confirm", action="store_true", help="Skip confirmation prompt")

    # Run command (manual execution)
    run_parser = subparsers.add_parser("run", help="Run a scheduled report manually")
    run_parser.add_argument("job_id", help="Job ID to run")

    # Status command
    status_parser = subparsers.add_parser("status", help="Get status of a scheduled report")
    status_parser.add_argument("job_id", help="Job ID to check")

    # Stats command
    subparsers.add_parser("stats", help="Show scheduler statistics")

    # Start command (run scheduler daemon)
    subparsers.add_parser("start", help="Start the scheduler service")

    return parser


def init_scheduler(db_path=None):
    """Initialize scheduler and storage"""
    if db_path is None:
        db_path = Path.home() / ".dream-studio" / "schedules.db"

    storage = ScheduleStorage(str(db_path))
    scheduler = ReportScheduler(storage)

    return scheduler, storage


def format_datetime(dt_str):
    """Format ISO datetime string for display"""
    if not dt_str:
        return "Never"
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    except:
        return dt_str


def cmd_list(scheduler, args):
    """List all scheduled reports"""
    jobs = scheduler.list_jobs()

    if not jobs:
        print("No scheduled reports found.")
        return

    print(f"\n{'=' * 80}")
    print(f"Scheduled Reports ({len(jobs)} total)")
    print(f"{'=' * 80}\n")

    for job in jobs:
        status = "[OK] enabled" if job["enabled"] else "[ERROR] disabled"
        print(f"ID: {job['job_id']}")
        print(f"Name: {job['name']}")
        print(f"Type: {job['report_type']}")
        print(f"Schedule: {job['schedule']} ({job['timezone']})")
        print(f"Format: {job['format']}")
        print(f"Recipients: {', '.join(job['recipients'])}")
        print(f"Status: {status}")
        print(f"Created: {format_datetime(job['created_at'])}")
        print(f"Last run: {format_datetime(job.get('last_run'))}")
        print(f"Next run: {format_datetime(job.get('next_run'))}")
        print("-" * 80)


def cmd_create(scheduler, args):
    """Create a new scheduled report"""
    # Parse recipients
    recipients = [r.strip() for r in args.recipients.split(",")]

    # Parse config if provided
    config = {}
    if args.config:
        try:
            config = json.loads(args.config)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON config: {e}")
            return 1

    # Create schedule
    try:
        job_id = scheduler.schedule_report({
            "name": args.name,
            "report_type": args.type,
            "schedule": args.schedule,
            "recipients": recipients,
            "format": args.format,
            "timezone": args.timezone,
            "config": config
        })

        print(f"\n[OK] Created scheduled report")
        print(f"Job ID: {job_id}")
        print(f"Name: {args.name}")
        print(f"Schedule: {args.schedule} ({args.timezone})")
        print(f"Next run: {format_datetime(scheduler.get_job_status(job_id).get('next_run'))}")

        return 0

    except Exception as e:
        print(f"\n[ERROR] Error creating schedule: {e}")
        return 1


def cmd_pause(scheduler, args):
    """Pause a scheduled report"""
    if scheduler.pause_job(args.job_id):
        print(f"[OK] Paused job {args.job_id}")
        return 0
    else:
        print(f"[ERROR] Job {args.job_id} not found")
        return 1


def cmd_resume(scheduler, args):
    """Resume a paused report"""
    if scheduler.resume_job(args.job_id):
        print(f"[OK] Resumed job {args.job_id}")
        return 0
    else:
        print(f"[ERROR] Job {args.job_id} not found")
        return 1


def cmd_delete(scheduler, args):
    """Delete a scheduled report"""
    # Get job details for confirmation
    status = scheduler.get_job_status(args.job_id)
    if not status:
        print(f"[ERROR] Job {args.job_id} not found")
        return 1

    # Confirm deletion
    if not args.confirm:
        print(f"\nAbout to delete:")
        print(f"  Name: {status['name']}")
        print(f"  Schedule: {status['schedule']}")
        response = input("\nAre you sure? (yes/no): ")
        if response.lower() not in ["yes", "y"]:
            print("Cancelled.")
            return 0

    # Delete
    if scheduler.delete_job(args.job_id):
        print(f"[OK] Deleted job {args.job_id}")
        return 0
    else:
        print(f"[ERROR] Failed to delete job {args.job_id}")
        return 1


def cmd_run(scheduler, args):
    """Run a scheduled report manually"""
    print(f"Running job {args.job_id}...")

    result = scheduler.run_scheduled_job(args.job_id)

    if result["success"]:
        print(f"\n[OK] Job completed successfully")
        print(f"Message: {result.get('message', 'N/A')}")
        if result.get("report_path"):
            print(f"Report: {result['report_path']}")
        return 0
    else:
        print(f"\n[ERROR] Job failed")
        print(f"Error: {result.get('error', 'Unknown error')}")
        return 1


def cmd_status(scheduler, args):
    """Get status of a scheduled report"""
    status = scheduler.get_job_status(args.job_id)

    if not status:
        print(f"[ERROR] Job {args.job_id} not found")
        return 1

    print(f"\n{'=' * 80}")
    print(f"Job Status: {status['name']}")
    print(f"{'=' * 80}\n")

    print(f"ID: {status['job_id']}")
    print(f"Name: {status['name']}")
    print(f"Type: {status['report_type']}")
    print(f"Schedule: {status['schedule']} ({status['timezone']})")
    print(f"Format: {status['format']}")
    print(f"Recipients: {', '.join(status['recipients'])}")
    print(f"Enabled: {'Yes' if status['enabled'] else 'No'}")
    print(f"\nScheduler:")
    print(f"  Running: {'Yes' if status['running'] else 'No'}")
    print(f"  Backend: {status['backend']}")

    print(f"\nTimestamps:")
    print(f"  Created: {format_datetime(status['created_at'])}")
    print(f"  Last run: {format_datetime(status.get('last_run'))}")
    print(f"  Next run: {format_datetime(status.get('next_run'))}")

    if status.get("config"):
        print(f"\nConfig:")
        print(f"  {json.dumps(status['config'], indent=2)}")

    return 0


def cmd_stats(scheduler, storage):
    """Show scheduler statistics"""
    stats = storage.get_stats()

    print(f"\n{'=' * 80}")
    print("Scheduler Statistics")
    print(f"{'=' * 80}\n")

    print(f"Total schedules: {stats['total']}")
    print(f"Enabled: {stats['enabled']}")
    print(f"Disabled: {stats['disabled']}")

    print(f"\nBy Format:")
    for format_type, count in stats["by_format"].items():
        print(f"  {format_type}: {count}")

    print(f"\nBy Report Type:")
    for report_type, count in stats["by_report_type"].items():
        print(f"  {report_type}: {count}")

    return 0


def cmd_start(scheduler, args):
    """Start the scheduler service"""
    import signal
    import time

    print("Starting scheduler service...")
    print(f"Backend: {'APScheduler' if scheduler.use_apscheduler else 'Simple fallback'}")

    # Load jobs
    jobs = scheduler.list_jobs()
    enabled_count = sum(1 for j in jobs if j["enabled"])
    print(f"Loaded {enabled_count} enabled job(s)")

    # Start scheduler
    scheduler.start()
    print("[OK] Scheduler started")
    print("\nPress Ctrl+C to stop\n")

    # Shutdown handler
    def shutdown_handler(signum, frame):
        print("\n\nShutting down scheduler...")
        scheduler.stop()
        print("[OK] Scheduler stopped")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Keep running
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        shutdown_handler(None, None)


def main():
    """Main CLI entry point"""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Initialize scheduler
    scheduler, storage = init_scheduler()

    # Dispatch command
    commands = {
        "list": lambda: cmd_list(scheduler, args),
        "create": lambda: cmd_create(scheduler, args),
        "pause": lambda: cmd_pause(scheduler, args),
        "resume": lambda: cmd_resume(scheduler, args),
        "delete": lambda: cmd_delete(scheduler, args),
        "run": lambda: cmd_run(scheduler, args),
        "status": lambda: cmd_status(scheduler, args),
        "stats": lambda: cmd_stats(scheduler, storage),
        "start": lambda: cmd_start(scheduler, args),
    }

    if args.command in commands:
        return commands[args.command]()
    else:
        print(f"Unknown command: {args.command}")
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
