"""Example usage of report scheduler system

This script demonstrates how to use the ReportScheduler for automated report generation.

Run this script to:
1. Create example scheduled reports
2. Start the scheduler
3. Monitor job execution
4. Manage schedules (pause, resume, delete)
"""

from pathlib import Path
from datetime import datetime, timedelta
import time

from analytics.core.scheduler import ReportScheduler, ScheduleStorage


def main():
    """Run scheduler examples"""
    print("=" * 70)
    print("dream-studio Report Scheduler - Example Usage")
    print("=" * 70)

    # Initialize storage and scheduler
    db_path = Path.home() / ".dream-studio" / "schedules.db"
    print(f"\n1. Initializing scheduler with database: {db_path}")

    storage = ScheduleStorage(str(db_path))
    scheduler = ReportScheduler(storage)

    print(f"   Backend: {'APScheduler' if scheduler.use_apscheduler else 'Simple fallback'}")

    # Example 1: Daily summary report
    print("\n2. Scheduling daily summary report...")
    daily_job_id = scheduler.schedule_report({
        "name": "Daily Analytics Summary",
        "report_type": "summary",
        "schedule": "0 9 * * *",  # Every day at 9 AM
        "recipients": ["team@company.com"],
        "format": "pdf",
        "timezone": "America/New_York",
        "config": {
            "date_range": None  # Last 30 days (default)
        }
    })
    print(f"   Created job: {daily_job_id}")

    # Example 2: Weekly detailed report
    print("\n3. Scheduling weekly detailed report...")
    weekly_job_id = scheduler.schedule_report({
        "name": "Weekly Executive Report",
        "report_type": "detailed",
        "schedule": "0 9 * * MON",  # Every Monday at 9 AM
        "recipients": ["exec@company.com", "manager@company.com"],
        "format": "pdf",
        "timezone": "America/New_York"
    })
    print(f"   Created job: {weekly_job_id}")

    # Example 3: Monthly report in Excel
    print("\n4. Scheduling monthly Excel report...")
    monthly_job_id = scheduler.schedule_report({
        "name": "Monthly Metrics Export",
        "report_type": "detailed",
        "schedule": "0 9 1 * *",  # 1st of month at 9 AM
        "recipients": ["analytics@company.com"],
        "format": "excel",
        "timezone": "UTC"
    })
    print(f"   Created job: {monthly_job_id}")

    # List all jobs
    print("\n5. Listing all scheduled jobs:")
    jobs = scheduler.list_jobs()
    print(f"   Total jobs: {len(jobs)}")
    for job in jobs:
        enabled_status = "enabled" if job["enabled"] else "disabled"
        print(f"   - {job['name']}")
        print(f"     ID: {job['job_id']}")
        print(f"     Schedule: {job['schedule']} ({job['timezone']})")
        print(f"     Format: {job['format']}")
        print(f"     Recipients: {', '.join(job['recipients'])}")
        print(f"     Status: {enabled_status}")
        if job.get("next_run"):
            print(f"     Next run: {job['next_run']}")
        print()

    # Storage statistics
    print("\n6. Storage statistics:")
    stats = storage.get_stats()
    print(f"   Total schedules: {stats['total']}")
    print(f"   Enabled: {stats['enabled']}")
    print(f"   Disabled: {stats['disabled']}")
    print(f"   By format: {stats['by_format']}")
    print(f"   By type: {stats['by_report_type']}")

    # Start scheduler
    print("\n7. Starting scheduler...")
    scheduler.start()
    print(f"   Scheduler is running: {scheduler.running}")

    # Demonstrate job management
    print("\n8. Demonstrating job management...")

    # Pause a job
    print(f"   Pausing weekly job: {weekly_job_id}")
    scheduler.pause_job(weekly_job_id)

    # Check status
    status = scheduler.get_job_status(weekly_job_id)
    if status:
        print(f"   Job enabled: {status['enabled']}")

    # Resume the job
    print(f"   Resuming weekly job: {weekly_job_id}")
    scheduler.resume_job(weekly_job_id)

    # Get detailed status
    print("\n9. Detailed job status:")
    status = scheduler.get_job_status(daily_job_id)
    if status:
        print(f"   Job: {status['name']}")
        print(f"   Running: {status['running']}")
        print(f"   Backend: {status['backend']}")
        print(f"   Created: {status['created_at']}")
        print(f"   Last run: {status.get('last_run', 'Never')}")

    # Run a job manually (for testing)
    print("\n10. Manual job execution (testing)...")
    print(f"    Running job: {daily_job_id}")
    result = scheduler.run_scheduled_job(daily_job_id)
    print(f"    Success: {result['success']}")
    if result['success']:
        print(f"    Report path: {result.get('report_path', 'N/A')}")
        print(f"    Message: {result.get('message', 'N/A')}")
    else:
        print(f"    Error: {result.get('error', 'Unknown')}")

    # Let scheduler run for a bit
    print("\n11. Scheduler is running in background...")
    print("    Press Ctrl+C to stop")
    try:
        while True:
            time.sleep(5)
            # You could add monitoring logic here
            pass
    except KeyboardInterrupt:
        print("\n\n12. Stopping scheduler...")
        scheduler.stop()
        print("    Scheduler stopped.")

    # Cleanup (optional)
    print("\n13. Cleanup options:")
    print("    To delete a job: scheduler.delete_job(job_id)")
    print("    To clear all jobs: [scheduler.delete_job(j['job_id']) for j in scheduler.list_jobs()]")

    print("\n" + "=" * 70)
    print("Example completed!")
    print("=" * 70)


def example_custom_schedule():
    """Example: Create a custom schedule with specific configuration"""
    storage = ScheduleStorage("~/.dream-studio/schedules.db")
    scheduler = ReportScheduler(storage)

    # Custom report with date range and specific sections
    job_id = scheduler.schedule_report({
        "name": "Q1 Performance Report",
        "report_type": "custom",
        "schedule": "0 10 1 4 *",  # April 1st at 10 AM
        "recipients": ["board@company.com"],
        "format": "pdf",
        "timezone": "America/New_York",
        "config": {
            "date_range": ("2026-01-01", "2026-03-31"),
            "template": {
                "sections": [
                    {
                        "title": "Q1 Overview",
                        "metrics": [
                            "sessions.total_sessions",
                            "tokens.total_cost_usd",
                            "skills.success_rate_overall"
                        ]
                    },
                    {
                        "title": "Top Performing Skills",
                        "metrics": ["skills.top_skills"],
                        "charts": [
                            {
                                "type": "bar",
                                "title": "Skill Invocations"
                            }
                        ]
                    }
                ]
            }
        }
    })

    print(f"Created custom quarterly report: {job_id}")
    return job_id


def example_high_frequency():
    """Example: High-frequency scheduling (every 30 minutes)"""
    storage = ScheduleStorage("~/.dream-studio/schedules.db")
    scheduler = ReportScheduler(storage)

    job_id = scheduler.schedule_report({
        "name": "Real-time Metrics Snapshot",
        "report_type": "summary",
        "schedule": "*/30 * * * *",  # Every 30 minutes
        "recipients": ["monitoring@company.com"],
        "format": "excel",
        "timezone": "UTC"
    })

    print(f"Created high-frequency job: {job_id}")
    return job_id


if __name__ == "__main__":
    main()

    # Uncomment to run additional examples:
    # example_custom_schedule()
    # example_high_frequency()
