"""Quick demo of scheduler functionality

Run: python analytics/core/scheduler/demo.py
"""

from analytics.core.scheduler import ReportScheduler, ScheduleStorage
from pathlib import Path

def main():
    print("=" * 70)
    print("Report Scheduler Demo")
    print("=" * 70)

    # Initialize
    db_path = Path.home() / ".dream-studio" / "schedules_demo.db"
    print(f"\n1. Initializing scheduler")
    print(f"   Database: {db_path}")

    storage = ScheduleStorage(str(db_path))
    scheduler = ReportScheduler(storage)

    backend = "APScheduler" if scheduler.use_apscheduler else "Simple fallback"
    print(f"   Backend: {backend}")

    # Create example schedules
    print("\n2. Creating example schedules...")

    schedules = [
        {
            "name": "Daily Summary",
            "report_type": "summary",
            "schedule": "0 9 * * *",  # 9 AM daily
            "recipients": ["team@company.com"],
            "format": "pdf",
            "timezone": "America/New_York"
        },
        {
            "name": "Weekly Executive Report",
            "report_type": "detailed",
            "schedule": "0 9 * * MON",  # Monday 9 AM
            "recipients": ["exec@company.com", "manager@company.com"],
            "format": "pdf",
            "timezone": "America/New_York"
        },
        {
            "name": "Monthly Metrics",
            "report_type": "detailed",
            "schedule": "0 0 1 * *",  # 1st of month
            "recipients": ["analytics@company.com"],
            "format": "excel",
            "timezone": "UTC"
        }
    ]

    job_ids = []
    for config in schedules:
        job_id = scheduler.schedule_report(config)
        job_ids.append(job_id)
        print(f"   - Created: {config['name']} ({job_id[:8]}...)")

    # List all jobs
    print("\n3. Listing scheduled jobs:")
    jobs = scheduler.list_jobs()
    for job in jobs:
        status = "enabled" if job["enabled"] else "disabled"
        print(f"\n   {job['name']}")
        print(f"   ID: {job['job_id']}")
        print(f"   Schedule: {job['schedule']} ({job['timezone']})")
        print(f"   Format: {job['format']}")
        print(f"   Recipients: {', '.join(job['recipients'])}")
        print(f"   Status: {status}")
        if job.get('next_run'):
            print(f"   Next run: {job['next_run']}")

    # Show statistics
    print("\n4. Storage statistics:")
    stats = storage.get_stats()
    print(f"   Total: {stats['total']}")
    print(f"   Enabled: {stats['enabled']}")
    print(f"   Disabled: {stats['disabled']}")
    print(f"   By format: {stats['by_format']}")
    print(f"   By type: {stats['by_report_type']}")

    # Demonstrate job management
    print("\n5. Demonstrating job management...")
    test_job = job_ids[0]
    print(f"   Testing with job: {test_job[:8]}...")

    # Pause
    scheduler.pause_job(test_job)
    job = scheduler.get_job_status(test_job)
    print(f"   - Paused: enabled={job['enabled']}")

    # Resume
    scheduler.resume_job(test_job)
    job = scheduler.get_job_status(test_job)
    print(f"   - Resumed: enabled={job['enabled']}")

    # Get detailed status
    print(f"\n6. Detailed job status for: {job['name']}")
    print(f"   Type: {job['report_type']}")
    print(f"   Schedule: {job['schedule']}")
    print(f"   Created: {job['created_at']}")
    print(f"   Running: {job['running']}")
    print(f"   Backend: {job['backend']}")

    print("\n" + "=" * 70)
    print("Demo complete!")
    print(f"\nSchedules saved to: {db_path}")
    print("\nNext steps:")
    print("  - Run 'python -m analytics.core.scheduler list' to list jobs")
    print("  - Run 'python -m analytics.core.scheduler start' to start scheduler")
    print("  - Run 'python -m analytics.core.scheduler --help' for more commands")
    print("=" * 70)

if __name__ == "__main__":
    main()
