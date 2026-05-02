"""Schedules API routes - ER017 specification

Endpoints:
    GET    /api/v1/schedules          - List all schedules
    POST   /api/v1/schedules          - Create new schedule
    PUT    /api/v1/schedules/{id}     - Update schedule
    DELETE /api/v1/schedules/{id}     - Delete schedule
    POST   /api/v1/schedules/{id}/pause   - Pause schedule
    POST   /api/v1/schedules/{id}/resume  - Resume schedule
"""
from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime
import uuid

# Import scheduler components
try:
    from analytics.core.scheduler import ReportScheduler, ScheduleStorage
    SCHEDULER_AVAILABLE = True
except ImportError:
    ReportScheduler = None
    ScheduleStorage = None
    SCHEDULER_AVAILABLE = False


# Request/Response Models

class ScheduleCreateRequest(BaseModel):
    """Request to create a new schedule"""
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Schedule name"
    )
    report_type: str = Field(
        ...,
        description="Type of report to generate: 'summary', 'detailed', or 'executive'"
    )
    schedule: str = Field(
        ...,
        description="Cron expression (e.g., '0 9 * * MON' for every Monday at 9am)"
    )
    recipients: List[str] = Field(
        ...,
        min_items=1,
        description="Email addresses to send report to"
    )
    format: str = Field(
        default="pdf",
        description="Export format: 'pdf', 'excel', 'pptx'"
    )
    enabled: bool = Field(
        default=True,
        description="Whether schedule is active"
    )
    timezone: str = Field(
        default="UTC",
        description="Timezone for schedule execution"
    )
    template: Optional[str] = Field(
        None,
        description="Optional template to use for report generation"
    )
    config: Optional[dict] = Field(
        None,
        description="Additional configuration for report generation"
    )

    @validator("format")
    def validate_format(cls, v):
        """Validate export format"""
        valid_formats = ["pdf", "excel", "pptx"]
        if v not in valid_formats:
            raise ValueError(f"format must be one of {valid_formats}")
        return v

    @validator("report_type")
    def validate_report_type(cls, v):
        """Validate report type"""
        valid_types = ["summary", "detailed", "executive"]
        if v not in valid_types:
            raise ValueError(f"report_type must be one of {valid_types}")
        return v

    @validator("recipients")
    def validate_recipients(cls, v):
        """Validate email addresses"""
        import re
        email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        for email in v:
            if not email_pattern.match(email):
                raise ValueError(f"Invalid email address: {email}")
        return v


class ScheduleUpdateRequest(BaseModel):
    """Request to update an existing schedule"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    schedule: Optional[str] = None
    recipients: Optional[List[str]] = None
    format: Optional[str] = None
    enabled: Optional[bool] = None
    timezone: Optional[str] = None
    template: Optional[str] = None
    config: Optional[dict] = None


class ScheduleResponse(BaseModel):
    """Response for a schedule"""
    job_id: str = Field(..., description="Unique schedule identifier")
    name: str
    report_type: str
    schedule: str
    recipients: List[str]
    format: str
    enabled: bool
    timezone: str
    next_run: Optional[str] = Field(
        None,
        description="ISO timestamp of next scheduled run"
    )
    last_run: Optional[str] = Field(
        None,
        description="ISO timestamp of last run"
    )
    created_at: str
    updated_at: str


class ScheduleListResponse(BaseModel):
    """List of schedules"""
    schedules: List[ScheduleResponse]
    total: int
    active: int
    paused: int


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str
    job_id: Optional[str] = None


# Router
router = APIRouter()

# Global scheduler instance (singleton pattern)
_scheduler_instance = None
_storage_instance = None


def get_scheduler() -> tuple:
    """Get or create scheduler instance"""
    global _scheduler_instance, _storage_instance

    if not SCHEDULER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail={
                "error": "Scheduler not available",
                "status_code": 501,
                "details": "ReportScheduler module not installed"
            }
        )

    if _scheduler_instance is None:
        # Initialize storage and scheduler
        import os
        storage_path = os.path.expanduser("~/.dream-studio/schedules.db")
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)

        _storage_instance = ScheduleStorage(storage_path)
        _scheduler_instance = ReportScheduler(_storage_instance)

        # Start scheduler
        _scheduler_instance.start()

    return _scheduler_instance, _storage_instance


@router.get("", response_model=ScheduleListResponse)
async def list_schedules():
    """List all report schedules

    Returns all configured schedules with their current status.

    Returns:
        ScheduleListResponse with all schedules
    """
    scheduler, storage = get_scheduler()

    try:
        # Get schedules from storage
        schedules_data = storage.load_schedules()

        # Get job info from scheduler
        jobs_info = scheduler.list_jobs()
        jobs_by_id = {job["job_id"]: job for job in jobs_info}

        # Build response
        schedules = []
        active_count = 0
        paused_count = 0

        for schedule_data in schedules_data:
            job_id = schedule_data["job_id"]
            job_info = jobs_by_id.get(job_id, {})

            enabled = schedule_data.get("enabled", True)
            if enabled:
                active_count += 1
            else:
                paused_count += 1

            schedules.append(ScheduleResponse(
                job_id=job_id,
                name=schedule_data["name"],
                report_type=schedule_data["report_type"],
                schedule=schedule_data["schedule"],
                recipients=schedule_data["recipients"],
                format=schedule_data.get("format", "pdf"),
                enabled=enabled,
                timezone=schedule_data.get("timezone", "UTC"),
                next_run=job_info.get("next_run"),
                last_run=schedule_data.get("last_run"),
                created_at=schedule_data.get("created_at", datetime.now().isoformat()),
                updated_at=schedule_data.get("updated_at", datetime.now().isoformat())
            ))

        return ScheduleListResponse(
            schedules=schedules,
            total=len(schedules),
            active=active_count,
            paused=paused_count
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to list schedules",
                "status_code": 500,
                "details": {"message": str(e)}
            }
        )


@router.post("", response_model=MessageResponse, status_code=201)
async def create_schedule(request: ScheduleCreateRequest):
    """Create a new report schedule

    Schedules a report to be generated and delivered automatically
    according to the specified cron schedule.

    Args:
        request: Schedule configuration

    Returns:
        MessageResponse with created job_id

    Raises:
        HTTPException: 400 if invalid schedule configuration
        HTTPException: 500 if schedule creation fails
    """
    scheduler, storage = get_scheduler()

    try:
        # Prepare schedule config
        schedule_config = {
            "name": request.name,
            "report_type": request.report_type,
            "schedule": request.schedule,
            "recipients": request.recipients,
            "format": request.format,
            "enabled": request.enabled,
            "timezone": request.timezone,
            "template": request.template,
            "config": request.config or {}
        }

        # Create schedule
        job_id = scheduler.schedule_report(schedule_config)

        return MessageResponse(
            message="Schedule created successfully",
            job_id=job_id
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid schedule configuration",
                "status_code": 400,
                "details": {"message": str(e)}
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to create schedule",
                "status_code": 500,
                "details": {"message": str(e)}
            }
        )


@router.put("/{job_id}", response_model=MessageResponse)
async def update_schedule(
    job_id: str = Path(..., description="Schedule ID"),
    request: ScheduleUpdateRequest = None
):
    """Update an existing schedule

    Updates the configuration of a scheduled report. The schedule
    will be recreated with the new settings.

    Args:
        job_id: Schedule ID to update
        request: Updated schedule parameters

    Returns:
        MessageResponse confirming update

    Raises:
        HTTPException: 404 if schedule not found
        HTTPException: 400 if invalid update parameters
        HTTPException: 500 if update fails
    """
    scheduler, storage = get_scheduler()

    try:
        # Get existing schedule
        schedules = storage.load_schedules()
        schedule = None
        for s in schedules:
            if s["job_id"] == job_id:
                schedule = s
                break

        if not schedule:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "Schedule not found",
                    "status_code": 404,
                    "details": {"job_id": job_id}
                }
            )

        # Apply updates
        update_data = request.dict(exclude_unset=True)
        schedule.update(update_data)
        schedule["updated_at"] = datetime.now().isoformat()

        # Delete old job
        scheduler.delete_job(job_id)

        # Create new job with updated config
        new_job_id = scheduler.schedule_report(schedule)

        # Update storage with new job_id if it changed
        if new_job_id != job_id:
            storage.delete_schedule(job_id)
            schedule["job_id"] = new_job_id
            storage.save_schedule(schedule)

        return MessageResponse(
            message="Schedule updated successfully",
            job_id=new_job_id
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid update parameters",
                "status_code": 400,
                "details": {"message": str(e)}
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to update schedule",
                "status_code": 500,
                "details": {"message": str(e)}
            }
        )


@router.delete("/{job_id}", status_code=204)
async def delete_schedule(job_id: str = Path(..., description="Schedule ID")):
    """Delete a schedule

    Permanently deletes a scheduled report. The report will no longer
    be generated or delivered.

    Args:
        job_id: Schedule ID to delete

    Returns:
        None (204 No Content)

    Raises:
        HTTPException: 404 if schedule not found
        HTTPException: 500 if deletion fails
    """
    scheduler, storage = get_scheduler()

    try:
        # Check if schedule exists
        schedules = storage.load_schedules()
        exists = any(s["job_id"] == job_id for s in schedules)

        if not exists:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "Schedule not found",
                    "status_code": 404,
                    "details": {"job_id": job_id}
                }
            )

        # Delete from scheduler
        scheduler.delete_job(job_id)

        # Delete from storage
        storage.delete_schedule(job_id)

        return None

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to delete schedule",
                "status_code": 500,
                "details": {"message": str(e)}
            }
        )


@router.post("/{job_id}/pause", response_model=MessageResponse)
async def pause_schedule(job_id: str = Path(..., description="Schedule ID")):
    """Pause a schedule

    Temporarily disables a schedule without deleting it. The schedule
    can be resumed later.

    Args:
        job_id: Schedule ID to pause

    Returns:
        MessageResponse confirming pause

    Raises:
        HTTPException: 404 if schedule not found
        HTTPException: 500 if pause fails
    """
    scheduler, storage = get_scheduler()

    try:
        # Check if schedule exists
        schedules = storage.load_schedules()
        schedule = None
        for s in schedules:
            if s["job_id"] == job_id:
                schedule = s
                break

        if not schedule:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "Schedule not found",
                    "status_code": 404,
                    "details": {"job_id": job_id}
                }
            )

        # Pause job
        scheduler.pause_job(job_id)

        # Update storage
        schedule["enabled"] = False
        schedule["updated_at"] = datetime.now().isoformat()
        storage.update_schedule(job_id, schedule)

        return MessageResponse(
            message="Schedule paused successfully",
            job_id=job_id
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to pause schedule",
                "status_code": 500,
                "details": {"message": str(e)}
            }
        )


@router.post("/{job_id}/resume", response_model=MessageResponse)
async def resume_schedule(job_id: str = Path(..., description="Schedule ID")):
    """Resume a paused schedule

    Re-enables a previously paused schedule. The schedule will resume
    generating reports according to its cron expression.

    Args:
        job_id: Schedule ID to resume

    Returns:
        MessageResponse confirming resume

    Raises:
        HTTPException: 404 if schedule not found
        HTTPException: 500 if resume fails
    """
    scheduler, storage = get_scheduler()

    try:
        # Check if schedule exists
        schedules = storage.load_schedules()
        schedule = None
        for s in schedules:
            if s["job_id"] == job_id:
                schedule = s
                break

        if not schedule:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "Schedule not found",
                    "status_code": 404,
                    "details": {"job_id": job_id}
                }
            )

        # Resume job
        scheduler.resume_job(job_id)

        # Update storage
        schedule["enabled"] = True
        schedule["updated_at"] = datetime.now().isoformat()
        storage.update_schedule(job_id, schedule)

        return MessageResponse(
            message="Schedule resumed successfully",
            job_id=job_id
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to resume schedule",
                "status_code": 500,
                "details": {"message": str(e)}
            }
        )
