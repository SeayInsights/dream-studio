"""
Comprehensive tests for report scheduling system (ER022 - Part 2)

Tests ReportScheduler and ScheduleStorage for automated report generation
with cron scheduling, job execution, and persistence.

Coverage target: >70%
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
import sys
import time
from datetime import datetime

# Ensure analytics package is in path
analytics_path = Path(__file__).parent.parent
if str(analytics_path) not in sys.path:
    sys.path.insert(0, str(analytics_path))


@pytest.fixture
def temp_db():
    """Create temporary test database"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    yield db_path

    try:
        os.unlink(db_path)
    except:
        pass


# ============================================================================
# ReportScheduler Tests
# ============================================================================

class TestReportScheduler:
    """Test ReportScheduler job management"""

    @pytest.fixture
    def scheduler(self, temp_db):
        """Create ReportScheduler with temporary storage"""
        from analytics.core.scheduler.job_scheduler import ReportScheduler
        from analytics.core.scheduler.storage import ScheduleStorage

        storage = ScheduleStorage(db_path=temp_db)
        scheduler = ReportScheduler(storage=storage)

        yield scheduler

        # Cleanup: stop scheduler if running
        if scheduler.is_running():
            scheduler.stop()

    def test_create_schedule(self, scheduler):
        """Test creating a new schedule"""
        schedule_config = {
            "name": "Daily Summary",
            "report_type": "summary",
            "schedule": "0 9 * * *",  # Daily at 9am
            "recipients": ["user@example.com"],
            "format": "pdf"
        }

        job_id = scheduler.schedule_report(schedule_config)

        assert job_id is not None
        assert isinstance(job_id, str)
        assert len(job_id) > 0

    def test_create_multiple_schedules(self, scheduler):
        """Test creating multiple independent schedules"""
        schedule1 = {
            "name": "Daily Report",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["daily@example.com"],
            "format": "pdf"
        }

        schedule2 = {
            "name": "Weekly Report",
            "report_type": "detailed",
            "schedule": "0 9 * * MON",  # Monday at 9am
            "recipients": ["weekly@example.com"],
            "format": "excel"
        }

        job_id1 = scheduler.schedule_report(schedule1)
        job_id2 = scheduler.schedule_report(schedule2)

        assert job_id1 != job_id2
        assert scheduler.get_schedule(job_id1) is not None
        assert scheduler.get_schedule(job_id2) is not None

    def test_job_execution(self, scheduler):
        """Test that scheduled jobs execute"""
        executed = []

        def mock_job_func():
            executed.append(True)

        # Schedule job to run every second for testing
        job_id = scheduler.add_job(
            func=mock_job_func,
            trigger='interval',
            seconds=1,
            id='test_job'
        )

        scheduler.start()
        time.sleep(2.5)  # Wait for at least 2 executions
        scheduler.stop()

        # Job should have executed at least once
        assert len(executed) >= 1

    def test_pause_resume(self, scheduler):
        """Test pausing and resuming jobs"""
        schedule_config = {
            "name": "Test Schedule",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["test@example.com"],
            "format": "pdf"
        }

        job_id = scheduler.schedule_report(schedule_config)

        # Pause job
        success = scheduler.pause_job(job_id)
        assert success is True

        # Resume job
        success = scheduler.resume_job(job_id)
        assert success is True

    def test_delete_schedule(self, scheduler):
        """Test deleting a schedule"""
        schedule_config = {
            "name": "Temporary Schedule",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["temp@example.com"],
            "format": "pdf"
        }

        job_id = scheduler.schedule_report(schedule_config)
        assert scheduler.get_schedule(job_id) is not None

        # Delete schedule
        success = scheduler.delete_schedule(job_id)
        assert success is True

        # Should no longer exist
        assert scheduler.get_schedule(job_id) is None

    def test_list_all_schedules(self, scheduler):
        """Test listing all active schedules"""
        # Create multiple schedules
        for i in range(3):
            scheduler.schedule_report({
                "name": f"Schedule {i}",
                "report_type": "summary",
                "schedule": "0 9 * * *",
                "recipients": [f"user{i}@example.com"],
                "format": "pdf"
            })

        schedules = scheduler.list_schedules()

        assert len(schedules) >= 3

    def test_cron_parsing(self, scheduler):
        """Test various cron expression formats"""
        cron_expressions = [
            "0 9 * * *",          # Daily at 9am
            "0 9 * * MON",        # Monday at 9am
            "0 */6 * * *",        # Every 6 hours
            "0 0 1 * *",          # First day of month
            "0 9 * * 1-5",        # Weekdays at 9am
        ]

        for i, cron_expr in enumerate(cron_expressions):
            config = {
                "name": f"Test {i}",
                "report_type": "summary",
                "schedule": cron_expr,
                "recipients": ["test@example.com"],
                "format": "pdf"
            }

            job_id = scheduler.schedule_report(config)
            assert job_id is not None

    def test_invalid_cron_expression(self, scheduler):
        """Test handling of invalid cron expressions"""
        invalid_config = {
            "name": "Invalid Schedule",
            "report_type": "summary",
            "schedule": "INVALID CRON",
            "recipients": ["test@example.com"],
            "format": "pdf"
        }

        with pytest.raises((ValueError, Exception)):
            scheduler.schedule_report(invalid_config)

    def test_scheduler_start_stop(self, scheduler):
        """Test starting and stopping the scheduler"""
        assert not scheduler.is_running()

        scheduler.start()
        assert scheduler.is_running()

        scheduler.stop()
        assert not scheduler.is_running()

    def test_update_schedule(self, scheduler):
        """Test updating an existing schedule"""
        schedule_config = {
            "name": "Original Name",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["original@example.com"],
            "format": "pdf"
        }

        job_id = scheduler.schedule_report(schedule_config)

        # Update schedule
        updated_config = {
            "name": "Updated Name",
            "recipients": ["updated@example.com"],
            "format": "excel"
        }

        success = scheduler.update_schedule(job_id, updated_config)
        assert success is True

        # Verify update
        schedule = scheduler.get_schedule(job_id)
        assert schedule["name"] == "Updated Name"
        assert schedule["recipients"] == ["updated@example.com"]

    def test_get_next_run_time(self, scheduler):
        """Test getting next scheduled run time"""
        schedule_config = {
            "name": "Test Schedule",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["test@example.com"],
            "format": "pdf"
        }

        job_id = scheduler.schedule_report(schedule_config)

        next_run = scheduler.get_next_run_time(job_id)

        assert next_run is not None
        assert isinstance(next_run, (datetime, str))


# ============================================================================
# ScheduleStorage Tests
# ============================================================================

class TestScheduleStorage:
    """Test ScheduleStorage database persistence"""

    @pytest.fixture
    def storage(self, temp_db):
        """Create ScheduleStorage with temporary database"""
        from analytics.core.scheduler.storage import ScheduleStorage
        return ScheduleStorage(db_path=temp_db)

    def test_save_schedule(self, storage):
        """Test saving schedule to database"""
        schedule_data = {
            "job_id": "job_123",
            "name": "Test Schedule",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["user@example.com"],
            "format": "pdf",
            "created_at": datetime.now().isoformat(),
            "enabled": True
        }

        success = storage.save_schedule(schedule_data)

        assert success is True

    def test_load_schedules(self, storage):
        """Test loading schedules from database"""
        # Save multiple schedules
        for i in range(3):
            storage.save_schedule({
                "job_id": f"job_{i}",
                "name": f"Schedule {i}",
                "report_type": "summary",
                "schedule": "0 9 * * *",
                "recipients": [f"user{i}@example.com"],
                "format": "pdf",
                "created_at": datetime.now().isoformat(),
                "enabled": True
            })

        # Load all schedules
        schedules = storage.load_schedules()

        assert len(schedules) >= 3

        # Verify structure
        for schedule in schedules:
            assert "job_id" in schedule
            assert "name" in schedule
            assert "schedule" in schedule

    def test_get_schedule_by_id(self, storage):
        """Test retrieving specific schedule by ID"""
        job_id = "unique_job_123"
        schedule_data = {
            "job_id": job_id,
            "name": "Unique Schedule",
            "report_type": "detailed",
            "schedule": "0 9 * * MON",
            "recipients": ["unique@example.com"],
            "format": "excel",
            "created_at": datetime.now().isoformat(),
            "enabled": True
        }

        storage.save_schedule(schedule_data)

        # Retrieve by ID
        loaded = storage.get_schedule(job_id)

        assert loaded is not None
        assert loaded["job_id"] == job_id
        assert loaded["name"] == "Unique Schedule"

    def test_update_schedule_in_storage(self, storage):
        """Test updating existing schedule in database"""
        job_id = "update_test_123"

        # Save initial schedule
        storage.save_schedule({
            "job_id": job_id,
            "name": "Original",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["original@example.com"],
            "format": "pdf",
            "created_at": datetime.now().isoformat(),
            "enabled": True
        })

        # Update schedule
        updated_data = {
            "job_id": job_id,
            "name": "Updated",
            "recipients": ["updated@example.com"]
        }

        success = storage.update_schedule(job_id, updated_data)
        assert success is True

        # Verify update
        loaded = storage.get_schedule(job_id)
        assert loaded["name"] == "Updated"
        assert loaded["recipients"] == ["updated@example.com"]

    def test_delete_schedule_from_storage(self, storage):
        """Test deleting schedule from database"""
        job_id = "delete_test_123"

        storage.save_schedule({
            "job_id": job_id,
            "name": "To Delete",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["delete@example.com"],
            "format": "pdf",
            "created_at": datetime.now().isoformat(),
            "enabled": True
        })

        # Delete
        success = storage.delete_schedule(job_id)
        assert success is True

        # Should no longer exist
        loaded = storage.get_schedule(job_id)
        assert loaded is None

    def test_persistence(self, temp_db):
        """Test that data persists across storage instances"""
        from analytics.core.scheduler.storage import ScheduleStorage

        job_id = "persist_test_123"

        # Create first instance and save
        storage1 = ScheduleStorage(db_path=temp_db)
        storage1.save_schedule({
            "job_id": job_id,
            "name": "Persistent Schedule",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["persist@example.com"],
            "format": "pdf",
            "created_at": datetime.now().isoformat(),
            "enabled": True
        })

        # Create second instance and load
        storage2 = ScheduleStorage(db_path=temp_db)
        loaded = storage2.get_schedule(job_id)

        assert loaded is not None
        assert loaded["job_id"] == job_id
        assert loaded["name"] == "Persistent Schedule"

    def test_list_enabled_schedules(self, storage):
        """Test filtering enabled vs disabled schedules"""
        # Save enabled schedule
        storage.save_schedule({
            "job_id": "enabled_1",
            "name": "Enabled",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["enabled@example.com"],
            "format": "pdf",
            "created_at": datetime.now().isoformat(),
            "enabled": True
        })

        # Save disabled schedule
        storage.save_schedule({
            "job_id": "disabled_1",
            "name": "Disabled",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["disabled@example.com"],
            "format": "pdf",
            "created_at": datetime.now().isoformat(),
            "enabled": False
        })

        # Load only enabled
        enabled = storage.load_schedules(enabled_only=True)

        # Should have at least the enabled one
        enabled_ids = [s["job_id"] for s in enabled]
        assert "enabled_1" in enabled_ids
        assert "disabled_1" not in enabled_ids


# ============================================================================
# Integration Tests
# ============================================================================

class TestSchedulerIntegration:
    """Integration tests for scheduler + storage"""

    def test_scheduler_loads_persisted_schedules(self, temp_db):
        """Test that scheduler loads schedules from database on init"""
        from analytics.core.scheduler.job_scheduler import ReportScheduler
        from analytics.core.scheduler.storage import ScheduleStorage

        # Save schedules directly to storage
        storage = ScheduleStorage(db_path=temp_db)
        storage.save_schedule({
            "job_id": "persisted_1",
            "name": "Persisted Schedule",
            "report_type": "summary",
            "schedule": "0 9 * * *",
            "recipients": ["persist@example.com"],
            "format": "pdf",
            "created_at": datetime.now().isoformat(),
            "enabled": True
        })

        # Create scheduler - should load persisted schedules
        scheduler = ReportScheduler(storage=storage)

        # Verify schedule was loaded
        schedule = scheduler.get_schedule("persisted_1")
        assert schedule is not None
        assert schedule["name"] == "Persisted Schedule"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
