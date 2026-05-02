"""Report scheduler with APScheduler backend and fallback support

Manages scheduled report generation with email delivery, error handling, and logging.

Installation:
    Full features (recommended):
        pip install apscheduler

    Fallback (simple loop-based):
        No additional dependencies required

Example:
    >>> from analytics.core.scheduler import ReportScheduler, ScheduleStorage
    >>> storage = ScheduleStorage("~/.dream-studio/schedules.db")
    >>> scheduler = ReportScheduler(storage)
    >>>
    >>> # Schedule weekly report
    >>> job_id = scheduler.schedule_report({
    ...     "name": "Weekly Executive Summary",
    ...     "report_type": "summary",
    ...     "schedule": "0 9 * * MON",  # Every Monday 9am
    ...     "recipients": ["exec@company.com"],
    ...     "format": "pdf",
    ...     "timezone": "America/New_York"
    ... })
    >>>
    >>> # Start scheduler
    >>> scheduler.start()
    >>>
    >>> # List jobs
    >>> jobs = scheduler.list_jobs()
"""

import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import time
import threading

# Try importing APScheduler (preferred)
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False

from analytics.core.scheduler.storage import ScheduleStorage

# Configure logging
logger = logging.getLogger(__name__)


class ReportScheduler:
    """Scheduled report generation with APScheduler backend"""

    def __init__(self, storage: ScheduleStorage, db_path: Optional[str] = None):
        """
        Initialize report scheduler

        Args:
            storage: ScheduleStorage instance for persisting schedules
            db_path: Path to analytics database (default: ~/.dream-studio/state/studio.db)
        """
        self.storage = storage
        self.db_path = db_path or str(Path.home() / ".dream-studio" / "state" / "studio.db")
        self.running = False

        # Initialize scheduler
        if HAS_APSCHEDULER:
            self.scheduler = BackgroundScheduler(timezone='UTC')
            self.scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
            self.use_apscheduler = True
            logger.info("ReportScheduler initialized with APScheduler backend")
        else:
            self.scheduler = None
            self.use_apscheduler = False
            self._simple_scheduler_thread = None
            logger.warning("APScheduler not available - using simple fallback scheduler")
            logger.warning("   Install with: pip install apscheduler")

    def schedule_report(self, schedule_config: Dict[str, Any]) -> str:
        """
        Schedule a new report or update existing schedule

        Args:
            schedule_config: Configuration dict with keys:
                - name: str (required)
                - report_type: str (required, e.g., "summary", "detailed")
                - schedule: str (required, cron expression like "0 9 * * MON")
                - recipients: list[str] (required, email addresses)
                - format: str (optional, default "pdf", options: "pdf", "excel")
                - config: dict (optional, additional report configuration)
                - enabled: bool (optional, default True)
                - timezone: str (optional, default "UTC")
                - job_id: str (optional, for updating existing job)

        Returns:
            str: job_id of scheduled report

        Raises:
            ValueError: If required fields missing or cron expression invalid
        """
        # Validate schedule expression
        try:
            self._validate_cron_expression(schedule_config["schedule"])
        except Exception as e:
            raise ValueError(f"Invalid cron expression: {e}")

        # Save to storage
        job_id = self.storage.save_schedule(schedule_config)

        # Calculate next run time
        next_run = self._calculate_next_run(
            schedule_config["schedule"],
            schedule_config.get("timezone", "UTC")
        )

        # Update next_run in storage
        self.storage.save_schedule({
            **schedule_config,
            "job_id": job_id,
            "next_run": next_run.isoformat() if next_run else None
        })

        # Add to scheduler if running
        if self.running:
            self._add_job_to_scheduler(job_id, schedule_config)

        logger.info(f"Scheduled report '{schedule_config['name']}' (job_id: {job_id})")
        if next_run:
            logger.info(f"  Next run: {next_run.isoformat()}")

        return job_id

    def run_scheduled_job(self, job_id: str) -> Dict[str, Any]:
        """
        Execute a scheduled report job

        Args:
            job_id: Job identifier

        Returns:
            Dict with execution result:
                - success: bool
                - job_id: str
                - message: str
                - report_path: str (if success)
                - error: str (if failure)
        """
        try:
            # Load job config
            config = self.storage.get_schedule(job_id)
            if not config:
                raise ValueError(f"Job {job_id} not found")

            if not config.get("enabled", True):
                logger.warning(f"Job {job_id} is disabled, skipping execution")
                return {
                    "success": False,
                    "job_id": job_id,
                    "message": "Job is disabled"
                }

            logger.info(f"Running scheduled job: {config['name']} ({job_id})")

            # Generate report
            from analytics.core.reports import ReportGenerator

            generator = ReportGenerator(self.db_path)
            report_data = generator.generate_report(
                config["report_type"],
                config.get("config", {})
            )

            # Export to specified format
            output_path = self._export_report(report_data, config, job_id)

            # Send email
            email_result = self._send_report_email(output_path, config)

            # Update last run timestamp
            next_run = self._calculate_next_run(
                config["schedule"],
                config.get("timezone", "UTC")
            )
            self.storage.update_last_run(
                job_id,
                datetime.now(),
                next_run.isoformat() if next_run else None
            )

            logger.info(f"Job {job_id} completed successfully")

            return {
                "success": True,
                "job_id": job_id,
                "message": f"Report generated and sent to {len(config['recipients'])} recipient(s)",
                "report_path": str(output_path),
                "email_sent": email_result.get("success", False)
            }

        except Exception as e:
            logger.error(f"Job {job_id} failed: {str(e)}", exc_info=True)
            return {
                "success": False,
                "job_id": job_id,
                "error": str(e)
            }

    def pause_job(self, job_id: str) -> bool:
        """
        Pause a scheduled job without deleting it

        Args:
            job_id: Job identifier

        Returns:
            bool: True if paused successfully
        """
        success = self.storage.set_enabled(job_id, False)

        if success and self.running:
            # Remove from active scheduler
            if self.use_apscheduler and self.scheduler:
                try:
                    self.scheduler.remove_job(job_id)
                except Exception:
                    pass  # Job might not be in scheduler

        logger.info(f"Paused job {job_id}")
        return success

    def resume_job(self, job_id: str) -> bool:
        """
        Resume a paused job

        Args:
            job_id: Job identifier

        Returns:
            bool: True if resumed successfully
        """
        config = self.storage.get_schedule(job_id)
        if not config:
            return False

        success = self.storage.set_enabled(job_id, True)

        if success and self.running:
            # Add back to scheduler
            self._add_job_to_scheduler(job_id, config)

        logger.info(f"Resumed job {job_id}")
        return success

    def delete_job(self, job_id: str) -> bool:
        """
        Delete a scheduled job permanently

        Args:
            job_id: Job identifier

        Returns:
            bool: True if deleted successfully
        """
        # Remove from scheduler if running
        if self.running and self.use_apscheduler and self.scheduler:
            try:
                self.scheduler.remove_job(job_id)
            except Exception:
                pass  # Job might not be in scheduler

        # Delete from storage
        success = self.storage.delete_schedule(job_id)

        if success:
            logger.info(f"Deleted job {job_id}")

        return success

    def list_jobs(self) -> List[Dict[str, Any]]:
        """
        List all scheduled jobs with their status

        Returns:
            List of job dictionaries with status information
        """
        schedules = self.storage.load_schedules()

        # Add runtime status if scheduler is running
        if self.running and self.use_apscheduler and self.scheduler:
            active_jobs = {job.id: job for job in self.scheduler.get_jobs()}

            for schedule in schedules:
                job_id = schedule["job_id"]
                if job_id in active_jobs:
                    job = active_jobs[job_id]
                    schedule["scheduler_status"] = "active"
                    if hasattr(job, "next_run_time") and job.next_run_time:
                        schedule["next_run_scheduler"] = job.next_run_time.isoformat()
                else:
                    schedule["scheduler_status"] = "inactive"

        return schedules

    def start(self) -> None:
        """Start the scheduler background thread"""
        if self.running:
            logger.warning("Scheduler already running")
            return

        # Load all enabled schedules
        schedules = self.storage.load_schedules(enabled_only=True)

        if self.use_apscheduler and self.scheduler:
            # Add all enabled jobs to APScheduler
            for schedule in schedules:
                self._add_job_to_scheduler(schedule["job_id"], schedule)

            self.scheduler.start()
            logger.info(f"APScheduler started with {len(schedules)} active job(s)")

        else:
            # Start simple scheduler thread
            self._simple_scheduler_thread = threading.Thread(
                target=self._simple_scheduler_loop,
                daemon=True
            )
            self._simple_scheduler_thread.start()
            logger.info(f"Simple scheduler started with {len(schedules)} active job(s)")

        self.running = True

    def stop(self) -> None:
        """Gracefully shutdown the scheduler"""
        if not self.running:
            logger.warning("Scheduler not running")
            return

        if self.use_apscheduler and self.scheduler:
            self.scheduler.shutdown(wait=True)
            logger.info("APScheduler stopped")
        else:
            # Simple scheduler will exit on next loop iteration
            logger.info("Simple scheduler stopped")

        self.running = False

    def _add_job_to_scheduler(self, job_id: str, config: Dict[str, Any]) -> None:
        """Add a job to the active scheduler"""
        if not self.use_apscheduler or not self.scheduler:
            return  # Simple scheduler handles jobs differently

        try:
            # Remove existing job if present
            try:
                self.scheduler.remove_job(job_id)
            except Exception:
                pass

            # Parse cron expression
            cron_parts = config["schedule"].split()
            if len(cron_parts) != 5:
                raise ValueError(f"Invalid cron expression: {config['schedule']}")

            minute, hour, day, month, day_of_week = cron_parts

            # Create trigger
            trigger = CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
                timezone=config.get("timezone", "UTC")
            )

            # Add job
            self.scheduler.add_job(
                func=self.run_scheduled_job,
                trigger=trigger,
                args=[job_id],
                id=job_id,
                name=config["name"],
                replace_existing=True
            )

            logger.debug(f"Added job {job_id} to scheduler")

        except Exception as e:
            logger.error(f"Failed to add job {job_id} to scheduler: {e}")

    def _simple_scheduler_loop(self) -> None:
        """Simple cron-like loop for when APScheduler is not available"""
        logger.info("Starting simple scheduler loop")

        while self.running:
            try:
                # Check all enabled schedules
                schedules = self.storage.load_schedules(enabled_only=True)
                now = datetime.now()

                for schedule in schedules:
                    next_run_str = schedule.get("next_run")
                    if not next_run_str:
                        continue

                    next_run = datetime.fromisoformat(next_run_str)

                    # If it's time to run, execute job
                    if now >= next_run:
                        logger.info(f"Simple scheduler executing job: {schedule['name']}")
                        self.run_scheduled_job(schedule["job_id"])

                # Sleep for 60 seconds before next check
                time.sleep(60)

            except Exception as e:
                logger.error(f"Simple scheduler loop error: {e}", exc_info=True)
                time.sleep(60)

    def _job_listener(self, event) -> None:
        """APScheduler event listener for logging"""
        if event.exception:
            logger.error(f"Job {event.job_id} failed with exception: {event.exception}")
        else:
            logger.info(f"Job {event.job_id} executed successfully")

    def _validate_cron_expression(self, cron_expr: str) -> None:
        """Validate cron expression format"""
        parts = cron_expr.split()
        if len(parts) != 5:
            raise ValueError(f"Cron expression must have 5 parts (minute hour day month day_of_week), got {len(parts)}")

        # Basic validation of each part
        # Allow alphanumeric for day/month names (MON, TUE, JAN, FEB, etc.)
        valid_chars = set("0123456789,-*/ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
        for part in parts:
            if not all(c in valid_chars for c in part):
                raise ValueError(f"Invalid characters in cron part: {part}")

    def _calculate_next_run(self, cron_expr: str, timezone_str: str) -> Optional[datetime]:
        """Calculate next run time from cron expression"""
        try:
            if self.use_apscheduler:
                # Use APScheduler's CronTrigger for accurate calculation
                cron_parts = cron_expr.split()
                if len(cron_parts) != 5:
                    return None

                minute, hour, day, month, day_of_week = cron_parts

                trigger = CronTrigger(
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=day_of_week,
                    timezone=timezone_str
                )

                next_run = trigger.get_next_fire_time(None, datetime.now())
                return next_run

            else:
                # Simple fallback: just add 24 hours (not accurate for weekly/monthly)
                return datetime.now() + timedelta(hours=24)

        except Exception as e:
            logger.error(f"Failed to calculate next run time: {e}")
            return None

    def _export_report(self, report_data: Dict[str, Any], config: Dict[str, Any], job_id: str) -> Path:
        """Export report to specified format"""
        format_type = config.get("format", "pdf").lower()

        # Create temp file for report
        temp_dir = Path(tempfile.gettempdir()) / "dream-studio-reports"
        temp_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{job_id}_{timestamp}.{format_type}"
        output_path = temp_dir / filename

        if format_type == "pdf":
            from analytics.exporters.pdf_exporter import PDFExporter
            exporter = PDFExporter()
            success, result = exporter.export_to_pdf(report_data, str(output_path))

            if not success:
                raise RuntimeError(f"PDF export failed: {result}")

        elif format_type == "excel":
            from analytics.exporters.excel_exporter import ExcelExporter
            exporter = ExcelExporter()
            result = exporter.export_to_excel(report_data, str(output_path))

            if not result.get("success"):
                raise RuntimeError(f"Excel export failed: {result.get('error', 'Unknown error')}")

        else:
            raise ValueError(f"Unsupported export format: {format_type}")

        return output_path

    def _send_report_email(self, report_path: Path, config: Dict[str, Any]) -> Dict[str, Any]:
        """Send report via email to recipients"""
        try:
            # Try to import email sender
            from analytics.core.email import EmailSender

            # This is a placeholder - EmailSender needs to be implemented
            # For now, log that email would be sent
            recipients = config["recipients"]
            logger.info(f"Would send report {report_path} to {recipients}")
            logger.warning("EmailSender not yet implemented - skipping email delivery")

            return {
                "success": False,
                "message": "Email delivery not yet implemented"
            }

        except ImportError:
            logger.warning("Email module not available - report generated but not sent")
            return {
                "success": False,
                "message": "Email module not available"
            }

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed status of a specific job

        Args:
            job_id: Job identifier

        Returns:
            Dict with job status or None if not found
        """
        config = self.storage.get_schedule(job_id)
        if not config:
            return None

        status = {
            **config,
            "running": self.running,
            "backend": "apscheduler" if self.use_apscheduler else "simple"
        }

        # Add scheduler-specific info
        if self.running and self.use_apscheduler and self.scheduler:
            try:
                job = self.scheduler.get_job(job_id)
                if job:
                    status["scheduler_active"] = True
                    if hasattr(job, "next_run_time") and job.next_run_time:
                        status["next_run_scheduler"] = job.next_run_time.isoformat()
                else:
                    status["scheduler_active"] = False
            except Exception:
                status["scheduler_active"] = False

        return status
