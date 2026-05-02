"""Report scheduler system for automated report generation and delivery

This module provides scheduled report generation with email delivery support.
Uses APScheduler for robust scheduling with fallback to simple loop-based scheduler.

Components:
    - ReportScheduler: Main scheduler class with job management
    - ScheduleStorage: SQLite-based persistence for schedule configurations

Features:
    - Cron-based scheduling (daily, weekly, monthly, custom)
    - Multiple export formats (PDF, Excel)
    - Email delivery to multiple recipients
    - Timezone support
    - Pause/resume/delete operations
    - Graceful error handling and logging

Example:
    >>> from analytics.core.scheduler import ReportScheduler, ScheduleStorage
    >>>
    >>> # Initialize scheduler
    >>> storage = ScheduleStorage("~/.dream-studio/schedules.db")
    >>> scheduler = ReportScheduler(storage)
    >>>
    >>> # Schedule weekly executive report
    >>> job_id = scheduler.schedule_report({
    ...     "name": "Weekly Executive Summary",
    ...     "report_type": "summary",
    ...     "schedule": "0 9 * * MON",  # Every Monday at 9 AM
    ...     "recipients": ["exec@company.com", "manager@company.com"],
    ...     "format": "pdf",
    ...     "timezone": "America/New_York",
    ...     "config": {
    ...         "date_range": ("2026-04-01", "2026-04-30")
    ...     }
    ... })
    >>>
    >>> # Start scheduler
    >>> scheduler.start()
    >>>
    >>> # List all jobs
    >>> jobs = scheduler.list_jobs()
    >>> for job in jobs:
    ...     print(f"{job['name']}: next run at {job['next_run']}")
    >>>
    >>> # Pause a job
    >>> scheduler.pause_job(job_id)
    >>>
    >>> # Resume a job
    >>> scheduler.resume_job(job_id)
    >>>
    >>> # Stop scheduler
    >>> scheduler.stop()

Cron Expression Format:
    Cron expressions use 5 fields: minute hour day month day_of_week

    Examples:
        "0 9 * * *"      - Daily at 9:00 AM
        "0 9 * * MON"    - Every Monday at 9:00 AM
        "0 9 1 * *"      - 1st of every month at 9:00 AM
        "*/30 * * * *"   - Every 30 minutes
        "0 18 * * FRI"   - Every Friday at 6:00 PM

Installation:
    For full features (recommended):
        pip install apscheduler

    For basic functionality (fallback):
        No additional dependencies required

Dependencies:
    - Required: sqlite3 (built-in)
    - Optional: apscheduler (for robust scheduling)
    - Integration: analytics.core.reports.ReportGenerator
    - Integration: analytics.exporters (PDFExporter, ExcelExporter)
    - Integration: analytics.core.email (EmailSender, when implemented)
"""

from .storage import ScheduleStorage
from .job_scheduler import ReportScheduler

__all__ = ["ReportScheduler", "ScheduleStorage"]
