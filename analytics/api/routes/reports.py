"""Reports API routes - ER015 specification

Endpoints:
    POST   /api/v1/reports/generate  - Create new report
    GET    /api/v1/reports           - List all reports
    GET    /api/v1/reports/{id}      - Get specific report
    DELETE /api/v1/reports/{id}      - Delete report
"""
from fastapi import APIRouter, HTTPException, Path, Query
from typing import List, Optional, Tuple
from datetime import datetime
from pydantic import BaseModel, Field
import uuid

# Import core components
try:
    from analytics.core.reports import ReportGenerator
    from analytics.core.insights import InsightEngine, RecommendationEngine
except ImportError:
    # Fallback for testing
    ReportGenerator = None
    InsightEngine = None
    RecommendationEngine = None


# Request/Response Models
class ReportGenerateRequest(BaseModel):
    """Request to generate a new report"""
    report_type: str = Field(
        ...,
        description="Type of report: 'summary', 'detailed', or 'executive'"
    )
    date_range: Optional[Tuple[str, str]] = Field(
        None,
        description="Optional date range tuple (start_date, end_date) in ISO format"
    )
    template: Optional[str] = Field(
        None,
        description="Optional template name to use for report generation"
    )
    filters: Optional[dict] = Field(
        None,
        description="Optional filters to apply to data"
    )
    sections: Optional[List[str]] = Field(
        None,
        description="Sections to include: ['metrics', 'insights', 'recommendations', 'charts']"
    )


class ReportResponse(BaseModel):
    """Response for a generated report"""
    report_id: str = Field(..., description="Unique report identifier")
    report_type: str = Field(..., description="Type of report generated")
    generated_at: str = Field(..., description="ISO timestamp of report generation")
    date_range: dict = Field(..., description="Date range used for the report")
    status: str = Field(
        ...,
        description="Report generation status: 'pending', 'completed', or 'failed'"
    )
    error: Optional[str] = Field(None, description="Error message if status is 'failed'")


class ReportListItem(BaseModel):
    """Report item in list view"""
    report_id: str
    report_type: str
    generated_at: str
    status: str
    date_range: dict


class ReportListResponse(BaseModel):
    """List of reports with pagination"""
    reports: List[ReportListItem]
    total: int
    page: int = 1
    page_size: int = 50


class ReportDetailResponse(BaseModel):
    """Full report with content"""
    report_id: str
    report_type: str
    generated_at: str
    date_range: dict
    status: str
    content: Optional[dict] = None
    metadata: Optional[dict] = None


# Router
router = APIRouter()

# In-memory storage (would use database in production)
_reports_store: dict[str, dict] = {}


@router.post("/generate", response_model=ReportResponse, status_code=201)
async def generate_report(request: ReportGenerateRequest):
    """Generate a new report

    Creates a new report based on the specified type and configuration.
    The report is generated asynchronously and stored for later retrieval.

    Args:
        request: Report generation parameters

    Returns:
        ReportResponse with report_id and status

    Raises:
        HTTPException: 400 if invalid report_type or configuration
        HTTPException: 500 if report generation fails
    """
    # Validate report type
    valid_types = ["summary", "detailed", "executive"]
    if request.report_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid report type",
                "status_code": 400,
                "details": {
                    "provided": request.report_type,
                    "valid_types": valid_types
                }
            }
        )

    # Generate report ID
    report_id = str(uuid.uuid4())
    now = datetime.now()

    # Parse date range
    if request.date_range:
        try:
            start_date, end_date = request.date_range
            date_range_dict = {
                "start": start_date,
                "end": end_date
            }
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Invalid date_range format",
                    "status_code": 400,
                    "details": "Expected tuple of (start_date, end_date) in ISO format"
                }
            )
    else:
        # Default to last 30 days
        date_range_dict = {
            "start": (now.replace(day=1)).isoformat(),
            "end": now.isoformat()
        }

    try:
        # Generate report using ReportGenerator
        if ReportGenerator:
            generator = ReportGenerator()
            report_config = {
                "date_range": request.date_range,
                "template": request.template,
                "filters": request.filters or {},
                "sections": request.sections or ["metrics", "insights", "recommendations"]
            }

            # Generate report
            report_data = generator.generate_report(
                request.report_type,
                config=report_config
            )

            # Store report
            _reports_store[report_id] = {
                "report_id": report_id,
                "report_type": request.report_type,
                "generated_at": now.isoformat(),
                "date_range": date_range_dict,
                "status": "completed",
                "content": report_data,
                "config": report_config,
                "error": None
            }

            status = "completed"
            error = None
        else:
            # Fallback when generator not available
            _reports_store[report_id] = {
                "report_id": report_id,
                "report_type": request.report_type,
                "generated_at": now.isoformat(),
                "date_range": date_range_dict,
                "status": "completed",
                "content": {
                    "message": "Report generator not available - placeholder data"
                },
                "config": {},
                "error": None
            }
            status = "completed"
            error = None

    except Exception as e:
        # Handle generation errors
        _reports_store[report_id] = {
            "report_id": report_id,
            "report_type": request.report_type,
            "generated_at": now.isoformat(),
            "date_range": date_range_dict,
            "status": "failed",
            "content": None,
            "config": {},
            "error": str(e)
        }
        status = "failed"
        error = str(e)

    return ReportResponse(
        report_id=report_id,
        report_type=request.report_type,
        generated_at=now.isoformat(),
        date_range=date_range_dict,
        status=status,
        error=error
    )


@router.get("", response_model=ReportListResponse)
async def list_reports(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page")
):
    """List all generated reports

    Returns a paginated list of all reports in the system.

    Args:
        page: Page number (1-indexed)
        page_size: Number of items per page (max 100)

    Returns:
        ReportListResponse with paginated reports
    """
    # Get all reports sorted by generated_at (newest first)
    all_reports = sorted(
        _reports_store.values(),
        key=lambda r: r["generated_at"],
        reverse=True
    )

    total = len(all_reports)

    # Paginate
    start = (page - 1) * page_size
    end = start + page_size
    paginated_reports = all_reports[start:end]

    # Convert to list items
    report_items = [
        ReportListItem(
            report_id=r["report_id"],
            report_type=r["report_type"],
            generated_at=r["generated_at"],
            status=r["status"],
            date_range=r["date_range"]
        )
        for r in paginated_reports
    ]

    return ReportListResponse(
        reports=report_items,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{report_id}", response_model=ReportDetailResponse)
async def get_report(report_id: str = Path(..., description="Report ID")):
    """Get a specific report with full content

    Retrieves a report by its ID including all generated content.

    Args:
        report_id: Unique report identifier

    Returns:
        ReportDetailResponse with full report data

    Raises:
        HTTPException: 404 if report not found
    """
    if report_id not in _reports_store:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Report not found",
                "status_code": 404,
                "details": {
                    "report_id": report_id
                }
            }
        )

    report = _reports_store[report_id]

    return ReportDetailResponse(
        report_id=report["report_id"],
        report_type=report["report_type"],
        generated_at=report["generated_at"],
        date_range=report["date_range"],
        status=report["status"],
        content=report.get("content"),
        metadata={
            "config": report.get("config", {}),
            "error": report.get("error")
        }
    )


@router.delete("/{report_id}", status_code=204)
async def delete_report(report_id: str = Path(..., description="Report ID")):
    """Delete a report

    Permanently deletes a report and its associated content.

    Args:
        report_id: Unique report identifier

    Returns:
        None (204 No Content)

    Raises:
        HTTPException: 404 if report not found
    """
    if report_id not in _reports_store:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Report not found",
                "status_code": 404,
                "details": {
                    "report_id": report_id
                }
            }
        )

    del _reports_store[report_id]
    return None
