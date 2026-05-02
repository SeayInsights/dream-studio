"""Unit tests for report scheduler system

Run with: pytest analytics/core/scheduler/test_scheduler.py -v
"""

import pytest
import tempfile
import time
from pathlib import Path
from datetime import datetime
from analytics.core.scheduler import ReportScheduler, ScheduleStorage


@pytest.fixture
def temp_db():
    """Create temporary database for testing"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def storage(temp_db):
    """Create ScheduleStorage instance with temp database"""
    return ScheduleStorage(temp_db)


@pytest.fixture
def scheduler(storage):
    """Create ReportScheduler instance"""
    return ReportScheduler(storage)


class TestScheduleStorage:
    """Test ScheduleStorage class"""

    def test_init_creates_database(self, temp_db):
        """Test database initialization creates tables"""
        storage = ScheduleStorage(temp_db)
        assert Path(temp_db).exists()

        # Verify table exists
        import sqlite3
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='scheduled_reports'"
            )
            assert cursor.fetchone() is not None

    def test_save_schedule(self, storage):
        """Test saving a new schedule"""
        schedule = {
            "name": "Test Report",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["test@example.com"],
            "format": "pdf"
        }

        job_id = storage.save_schedule(schedule)
        assert job_id is not None
        assert len(job_id) > 0

    def test_save_schedule_missing_field(self, storage):
        """Test saving schedule with missing required field"""
        schedule = {
            "name": "Test Report",
            "report_type": "summary",
            # Missing 'schedule' and 'recipients'
        }

        with pytest.raises(ValueError, match="Missing required field"):
            storage.save_schedule(schedule)

    def test_load_schedules(self, storage):
        """Test loading all schedules"""
        # Save multiple schedules
        for i in range(3):
            storage.save_schedule({
                "name": f"Report {i}",
                "report_type": "summary",
                "schedule": "0 9 * * *",
                "recipients": [f"user{i}@example.com"]
            })

        schedules = storage.load_schedules()
        assert len(schedules) == 3

    def test_load_schedules_enabled_only(self, storage):
        """Test loading only enabled schedules"""
        # Save enabled schedule
        enabled_id = storage.save_schedule({
            "name": "Enabled Report",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["test@example.com"],
            "enabled": True
        })

        # Save disabled schedule
        disabled_id = storage.save_schedule({
            "name": "Disabled Report",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["test@example.com"],
            "enabled": False
        })

        schedules = storage.load_schedules(enabled_only=True)
        assert len(schedules) == 1
        assert schedules[0]["job_id"] == enabled_id

    def test_get_schedule(self, storage):
        """Test getting a single schedule by ID"""
        schedule = {
            "name": "Test Report",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["test@example.com"]
        }

        job_id = storage.save_schedule(schedule)
        retrieved = storage.get_schedule(job_id)

        assert retrieved is not None
        assert retrieved["job_id"] == job_id
        assert retrieved["name"] == "Test Report"
        assert retrieved["recipients"] == ["test@example.com"]

    def test_get_schedule_not_found(self, storage):
        """Test getting non-existent schedule"""
        result = storage.get_schedule("nonexistent-id")
        assert result is None

    def test_delete_schedule(self, storage):
        """Test deleting a schedule"""
        job_id = storage.save_schedule({
            "name": "Test Report",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["test@example.com"]
        })

        assert storage.delete_schedule(job_id) is True
        assert storage.get_schedule(job_id) is None

    def test_delete_schedule_not_found(self, storage):
        """Test deleting non-existent schedule"""
        result = storage.delete_schedule("nonexistent-id")
        assert result is False

    def test_update_last_run(self, storage):
        """Test updating last run timestamp"""
        job_id = storage.save_schedule({
            "name": "Test Report",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["test@example.com"]
        })

        now = datetime.now()
        storage.update_last_run(job_id, now, "2026-05-02T09:00:00")

        schedule = storage.get_schedule(job_id)
        assert schedule["last_run"] is not None
        assert schedule["next_run"] == "2026-05-02T09:00:00"

    def test_set_enabled(self, storage):
        """Test enabling/disabling a schedule"""
        job_id = storage.save_schedule({
            "name": "Test Report",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["test@example.com"],
            "enabled": True
        })

        # Disable
        assert storage.set_enabled(job_id, False) is True
        schedule = storage.get_schedule(job_id)
        assert schedule["enabled"] is False

        # Enable
        assert storage.set_enabled(job_id, True) is True
        schedule = storage.get_schedule(job_id)
        assert schedule["enabled"] is True

    def test_get_stats(self, storage):
        """Test getting storage statistics"""
        # Create schedules with different formats and types
        storage.save_schedule({
            "name": "PDF Report",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["test@example.com"],
            "format": "pdf"
        })

        storage.save_schedule({
            "name": "Excel Report",
            "report_type": "detailed",
            "schedule": "0 9 * * MON",
            "recipients": ["test@example.com"],
            "format": "excel",
            "enabled": False
        })

        stats = storage.get_stats()
        assert stats["total"] == 2
        assert stats["enabled"] == 1
        assert stats["disabled"] == 1
        assert stats["by_format"]["pdf"] == 1
        assert stats["by_format"]["excel"] == 1
        assert stats["by_report_type"]["summary"] == 1
        assert stats["by_report_type"]["detailed"] == 1


class TestReportScheduler:
    """Test ReportScheduler class"""

    def test_init(self, scheduler):
        """Test scheduler initialization"""
        assert scheduler is not None
        assert scheduler.storage is not None
        assert scheduler.running is False

    def test_schedule_report(self, scheduler):
        """Test scheduling a new report"""
        job_id = scheduler.schedule_report({
            "name": "Test Report",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["test@example.com"],
            "format": "pdf"
        })

        assert job_id is not None
        assert len(job_id) > 0

        # Verify it was saved
        schedule = scheduler.storage.get_schedule(job_id)
        assert schedule is not None
        assert schedule["name"] == "Test Report"

    def test_schedule_report_invalid_cron(self, scheduler):
        """Test scheduling with invalid cron expression"""
        with pytest.raises(ValueError, match="Invalid cron expression"):
            scheduler.schedule_report({
                "name": "Test Report",
                "report_type": "summary",
                "schedule": "invalid cron",
                "recipients": ["test@example.com"]
            })

    def test_pause_job(self, scheduler):
        """Test pausing a job"""
        job_id = scheduler.schedule_report({
            "name": "Test Report",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["test@example.com"]
        })

        assert scheduler.pause_job(job_id) is True

        schedule = scheduler.storage.get_schedule(job_id)
        assert schedule["enabled"] is False

    def test_resume_job(self, scheduler):
        """Test resuming a paused job"""
        job_id = scheduler.schedule_report({
            "name": "Test Report",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["test@example.com"]
        })

        scheduler.pause_job(job_id)
        assert scheduler.resume_job(job_id) is True

        schedule = scheduler.storage.get_schedule(job_id)
        assert schedule["enabled"] is True

    def test_delete_job(self, scheduler):
        """Test deleting a job"""
        job_id = scheduler.schedule_report({
            "name": "Test Report",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["test@example.com"]
        })

        assert scheduler.delete_job(job_id) is True
        assert scheduler.storage.get_schedule(job_id) is None

    def test_list_jobs(self, scheduler):
        """Test listing all jobs"""
        # Create multiple jobs
        for i in range(3):
            scheduler.schedule_report({
                "name": f"Test Report {i}",
                "report_type": "summary",
                "schedule": "0 9 * * *",
                "recipients": ["test@example.com"]
            })

        jobs = scheduler.list_jobs()
        assert len(jobs) == 3

    def test_get_job_status(self, scheduler):
        """Test getting job status"""
        job_id = scheduler.schedule_report({
            "name": "Test Report",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["test@example.com"]
        })

        status = scheduler.get_job_status(job_id)
        assert status is not None
        assert status["job_id"] == job_id
        assert status["name"] == "Test Report"
        assert "running" in status
        assert "backend" in status

    def test_validate_cron_expression(self, scheduler):
        """Test cron expression validation"""
        # Valid expressions should not raise
        scheduler._validate_cron_expression("0 9 * * *")
        scheduler._validate_cron_expression("*/30 * * * *")
        scheduler._validate_cron_expression("0 9 * * MON")

        # Invalid expressions should raise
        with pytest.raises(ValueError):
            scheduler._validate_cron_expression("invalid")

        with pytest.raises(ValueError):
            scheduler._validate_cron_expression("0 9 * *")  # Only 4 parts

    def test_start_stop(self, scheduler):
        """Test starting and stopping scheduler"""
        # Add a job first
        scheduler.schedule_report({
            "name": "Test Report",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["test@example.com"]
        })

        # Start
        scheduler.start()
        assert scheduler.running is True

        # Stop
        scheduler.stop()
        assert scheduler.running is False

    def test_calculate_next_run(self, scheduler):
        """Test calculating next run time from cron expression"""
        # Daily at 9 AM
        next_run = scheduler._calculate_next_run("0 9 * * *", "UTC")
        assert next_run is not None
        assert isinstance(next_run, datetime)

        # Weekly on Monday
        next_run = scheduler._calculate_next_run("0 9 * * MON", "UTC")
        assert next_run is not None


class TestIntegration:
    """Integration tests"""

    def test_full_workflow(self, scheduler):
        """Test complete workflow: schedule, start, pause, resume, delete"""
        # Schedule report
        job_id = scheduler.schedule_report({
            "name": "Integration Test Report",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["test@example.com"],
            "format": "pdf"
        })

        # Start scheduler
        scheduler.start()
        assert scheduler.running is True

        # List jobs
        jobs = scheduler.list_jobs()
        assert len(jobs) == 1

        # Pause job
        scheduler.pause_job(job_id)
        schedule = scheduler.storage.get_schedule(job_id)
        assert schedule["enabled"] is False

        # Resume job
        scheduler.resume_job(job_id)
        schedule = scheduler.storage.get_schedule(job_id)
        assert schedule["enabled"] is True

        # Stop scheduler
        scheduler.stop()
        assert scheduler.running is False

        # Delete job
        scheduler.delete_job(job_id)
        assert scheduler.storage.get_schedule(job_id) is None

    def test_multiple_schedules_different_formats(self, scheduler):
        """Test managing multiple schedules with different formats"""
        pdf_job = scheduler.schedule_report({
            "name": "PDF Report",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["test@example.com"],
            "format": "pdf"
        })

        excel_job = scheduler.schedule_report({
            "name": "Excel Report",
            "report_type": "detailed",
            "schedule": "0 9 * * MON",
            "recipients": ["test@example.com"],
            "format": "excel"
        })

        jobs = scheduler.list_jobs()
        assert len(jobs) == 2

        # Verify formats
        pdf_schedule = scheduler.storage.get_schedule(pdf_job)
        excel_schedule = scheduler.storage.get_schedule(excel_job)

        assert pdf_schedule["format"] == "pdf"
        assert excel_schedule["format"] == "excel"
