# Report Scheduler System

Automated report generation and delivery system with cron-based scheduling, email notifications, and multiple export formats.

## Features

- **Flexible Scheduling**: Cron expressions for daily, weekly, monthly, or custom schedules
- **Multiple Formats**: PDF and Excel export support
- **Email Delivery**: Automatic email delivery to multiple recipients
- **Timezone Support**: Schedule reports in any timezone
- **Job Management**: Pause, resume, and delete scheduled jobs
- **Persistent Storage**: SQLite-based schedule persistence
- **Graceful Fallback**: Works with or without APScheduler
- **Error Handling**: Robust error handling and logging

## Installation

### Recommended (Full Features)

```bash
pip install apscheduler reportlab openpyxl
```

### Minimal (Fallback)

The scheduler will work without additional dependencies using a simple loop-based scheduler, though APScheduler is strongly recommended for production use.

## Quick Start

```python
from analytics.core.scheduler import ReportScheduler, ScheduleStorage

# Initialize
storage = ScheduleStorage("~/.dream-studio/schedules.db")
scheduler = ReportScheduler(storage)

# Schedule a weekly report
job_id = scheduler.schedule_report({
    "name": "Weekly Executive Summary",
    "report_type": "summary",
    "schedule": "0 9 * * MON",  # Every Monday at 9 AM
    "recipients": ["exec@company.com"],
    "format": "pdf",
    "timezone": "America/New_York"
})

# Start the scheduler
scheduler.start()

# Let it run in the background
# (or integrate into your application's lifecycle)
```

## Cron Expression Format

Cron expressions use 5 fields: `minute hour day month day_of_week`

| Expression | Description |
|------------|-------------|
| `0 9 * * *` | Daily at 9:00 AM |
| `0 9 * * MON` | Every Monday at 9:00 AM |
| `0 9 1 * *` | 1st of every month at 9:00 AM |
| `*/30 * * * *` | Every 30 minutes |
| `0 18 * * FRI` | Every Friday at 6:00 PM |
| `0 0 * * SUN` | Every Sunday at midnight |

### Cron Field Values

- **Minute**: 0-59
- **Hour**: 0-23
- **Day**: 1-31
- **Month**: 1-12 or JAN-DEC
- **Day of Week**: 0-6 (0=Sunday) or SUN-SAT

### Special Characters

- `*`: Any value
- `*/n`: Every nth value
- `n-m`: Range from n to m
- `n,m`: List of values

## API Reference

### ScheduleStorage

Manages SQLite storage of schedule configurations.

```python
storage = ScheduleStorage("path/to/schedules.db")

# Save a schedule
job_id = storage.save_schedule({
    "name": "My Report",
    "report_type": "summary",
    "schedule": "0 9 * * *",
    "recipients": ["user@example.com"],
    "format": "pdf"
})

# Load all schedules
schedules = storage.load_schedules()

# Load only enabled schedules
enabled = storage.load_schedules(enabled_only=True)

# Get single schedule
schedule = storage.get_schedule(job_id)

# Delete schedule
storage.delete_schedule(job_id)

# Enable/disable schedule
storage.set_enabled(job_id, False)  # Disable
storage.set_enabled(job_id, True)   # Enable

# Get statistics
stats = storage.get_stats()
# Returns: {"total": 5, "enabled": 4, "disabled": 1, ...}
```

### ReportScheduler

Main scheduler class for managing scheduled report jobs.

```python
scheduler = ReportScheduler(storage, db_path="path/to/studio.db")

# Schedule a report
job_id = scheduler.schedule_report({
    "name": "Report Name",
    "report_type": "summary",  # or "detailed", "custom"
    "schedule": "0 9 * * *",
    "recipients": ["user@example.com"],
    "format": "pdf",  # or "excel"
    "timezone": "UTC",
    "config": {}  # Optional report configuration
})

# Start the scheduler
scheduler.start()

# List all jobs
jobs = scheduler.list_jobs()

# Get job status
status = scheduler.get_job_status(job_id)

# Pause a job
scheduler.pause_job(job_id)

# Resume a job
scheduler.resume_job(job_id)

# Delete a job
scheduler.delete_job(job_id)

# Run a job manually (for testing)
result = scheduler.run_scheduled_job(job_id)

# Stop the scheduler
scheduler.stop()
```

## Schedule Configuration

### Required Fields

- `name` (str): Human-readable job name
- `report_type` (str): Report type - "summary", "detailed", or "custom"
- `schedule` (str): Cron expression
- `recipients` (list[str]): Email addresses for report delivery

### Optional Fields

- `format` (str): Export format - "pdf" (default) or "excel"
- `timezone` (str): Timezone for schedule - default "UTC"
- `enabled` (bool): Whether job is enabled - default True
- `config` (dict): Additional report configuration (date ranges, templates, etc.)
- `job_id` (str): For updating existing jobs

### Example: Custom Report with Date Range

```python
job_id = scheduler.schedule_report({
    "name": "Q1 Performance Report",
    "report_type": "custom",
    "schedule": "0 10 1 4 *",  # April 1st at 10 AM
    "recipients": ["board@company.com"],
    "format": "pdf",
    "config": {
        "date_range": ("2026-01-01", "2026-03-31"),
        "template": {
            "sections": [
                {
                    "title": "Q1 Overview",
                    "metrics": [
                        "sessions.total_sessions",
                        "tokens.total_cost_usd"
                    ]
                }
            ]
        }
    }
})
```

## Common Patterns

### Daily Summary Report

```python
scheduler.schedule_report({
    "name": "Daily Summary",
    "report_type": "summary",
    "schedule": "0 8 * * *",  # 8 AM every day
    "recipients": ["team@company.com"],
    "format": "pdf",
    "timezone": "America/Los_Angeles"
})
```

### Weekly Executive Report

```python
scheduler.schedule_report({
    "name": "Weekly Executive Report",
    "report_type": "detailed",
    "schedule": "0 9 * * MON",  # Monday 9 AM
    "recipients": ["exec@company.com", "manager@company.com"],
    "format": "pdf",
    "timezone": "America/New_York"
})
```

### Monthly Data Export

```python
scheduler.schedule_report({
    "name": "Monthly Data Export",
    "report_type": "detailed",
    "schedule": "0 0 1 * *",  # 1st of month at midnight
    "recipients": ["data@company.com"],
    "format": "excel",
    "timezone": "UTC"
})
```

### High-Frequency Monitoring

```python
scheduler.schedule_report({
    "name": "Hourly Metrics",
    "report_type": "summary",
    "schedule": "0 * * * *",  # Top of every hour
    "recipients": ["monitoring@company.com"],
    "format": "excel",
    "timezone": "UTC"
})
```

## Error Handling

The scheduler includes robust error handling:

- **Invalid cron expressions**: Validated before saving
- **Job execution failures**: Logged without crashing scheduler
- **Email send failures**: Logged (report still generated)
- **Missing dependencies**: Graceful fallback to simple scheduler

### Checking Job Results

```python
result = scheduler.run_scheduled_job(job_id)

if result["success"]:
    print(f"Report generated: {result['report_path']}")
    print(f"Email sent: {result.get('email_sent', False)}")
else:
    print(f"Error: {result['error']}")
```

## Logging

The scheduler uses Python's logging module. Configure logging in your application:

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# To see scheduler debug messages
logging.getLogger('analytics.core.scheduler').setLevel(logging.DEBUG)
```

## Database Schema

The scheduler uses a single SQLite table:

```sql
CREATE TABLE scheduled_reports (
    job_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    report_type TEXT NOT NULL,
    schedule TEXT NOT NULL,
    recipients TEXT NOT NULL,  -- JSON array
    format TEXT DEFAULT 'pdf',
    config TEXT,  -- JSON object
    enabled BOOLEAN DEFAULT 1,
    timezone TEXT DEFAULT 'UTC',
    created_at TEXT NOT NULL,
    last_run TEXT,
    next_run TEXT
);
```

## Integration with Other Modules

### ReportGenerator

The scheduler integrates with `analytics.core.reports.ReportGenerator` for report generation:

```python
from analytics.core.reports import ReportGenerator

generator = ReportGenerator()
report_data = generator.generate_report("summary")
```

### Exporters

Reports are exported using:
- `analytics.exporters.PDFExporter` for PDF format
- `analytics.exporters.ExcelExporter` for Excel format

### Email (Future)

Email delivery will integrate with `analytics.core.email.EmailSender` (to be implemented).

## Testing

Run the test suite:

```bash
pytest analytics/core/scheduler/test_scheduler.py -v
```

Run example script:

```bash
python analytics/core/scheduler/example_usage.py
```

## Troubleshooting

### Scheduler Not Running Jobs

1. Check that scheduler is started: `scheduler.running == True`
2. Verify job is enabled: `scheduler.get_job_status(job_id)['enabled']`
3. Check next run time: `status['next_run']`
4. Review logs for errors

### Jobs Running But Reports Not Generated

1. Check report generator is working: Run `ReportGenerator` manually
2. Verify database path is correct
3. Check exporters have required dependencies (reportlab, openpyxl)

### Email Not Being Sent

Email delivery requires `EmailSender` implementation. Currently, reports are generated but email sending is logged as "not yet implemented".

## Production Deployment

### Running as a Service

```python
# scheduler_service.py
from analytics.core.scheduler import ReportScheduler, ScheduleStorage
import signal
import sys

storage = ScheduleStorage("~/.dream-studio/schedules.db")
scheduler = ReportScheduler(storage)

def shutdown_handler(signum, frame):
    print("Shutting down scheduler...")
    scheduler.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

scheduler.start()
print("Scheduler service started")

# Keep running
signal.pause()
```

### Docker Container

```dockerfile
FROM python:3.11-slim

RUN pip install apscheduler reportlab openpyxl

COPY analytics /app/analytics
WORKDIR /app

CMD ["python", "scheduler_service.py"]
```

## License

Part of the dream-studio analytics platform.
