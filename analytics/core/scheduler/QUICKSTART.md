# Report Scheduler - Quick Start Guide

## Installation

```bash
# Optional but recommended
pip install apscheduler
```

## 5-Minute Quickstart

### 1. Run the Demo

```bash
cd C:/Users/Dannis\ Seay/builds/dream-studio
PYTHONPATH=. python analytics/core/scheduler/demo.py
```

This creates 3 example schedules and demonstrates all features.

### 2. Use the CLI

```bash
# List all schedules
python -m analytics.core.scheduler list

# Create a schedule
python -m analytics.core.scheduler create \
    --name "Daily Summary" \
    --type summary \
    --schedule "0 9 * * *" \
    --recipients "team@company.com" \
    --format pdf

# Show statistics
python -m analytics.core.scheduler stats

# Start the scheduler service
python -m analytics.core.scheduler start
```

### 3. Use the Python API

```python
from analytics.core.scheduler import ReportScheduler, ScheduleStorage

# Initialize
storage = ScheduleStorage("~/.dream-studio/schedules.db")
scheduler = ReportScheduler(storage)

# Schedule a report
job_id = scheduler.schedule_report({
    "name": "Weekly Report",
    "report_type": "summary",
    "schedule": "0 9 * * MON",  # Monday 9 AM
    "recipients": ["user@example.com"],
    "format": "pdf",
    "timezone": "America/New_York"
})

# Start the scheduler
scheduler.start()

# Keep it running
import signal
signal.pause()  # Or integrate into your app's event loop
```

## Common Schedules

```python
# Daily at 9 AM
"0 9 * * *"

# Every Monday at 9 AM
"0 9 * * MON"

# 1st of every month at midnight
"0 0 1 * *"

# Every 30 minutes
"*/30 * * * *"

# Every weekday at 6 PM
"0 18 * * MON-FRI"
```

## File Locations

- **Schedules DB**: `~/.dream-studio/schedules.db`
- **Analytics DB**: `~/.dream-studio/state/studio.db`
- **Generated Reports**: `/tmp/dream-studio-reports/` (temp directory)

## Next Steps

1. Read the full [README.md](README.md)
2. Explore [example_usage.py](example_usage.py)
3. Run tests: `pytest test_scheduler.py -v`
4. Review [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)

## Troubleshooting

### "APScheduler not available"
This is just a warning. The scheduler works without it using a simple fallback.
To get full features: `pip install apscheduler`

### "Email not being sent"
Email delivery requires EmailSender implementation (pending). Reports are still generated.

### "Job not running"
Check:
1. Scheduler is started: `scheduler.running == True`
2. Job is enabled: Check with `scheduler.get_job_status(job_id)`
3. Next run time: Verify it's in the future

## Support

- **Documentation**: See [README.md](README.md)
- **Examples**: See [example_usage.py](example_usage.py)
- **Tests**: See [test_scheduler.py](test_scheduler.py)
