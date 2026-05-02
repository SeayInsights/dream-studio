"""Reports API routes"""
from fastapi import APIRouter, HTTPException, Path
from typing import List
from datetime import datetime
import uuid

from ..models.reports import (
    Report,
    ReportCreate,
    ReportUpdate,
    ReportList,
    ReportContent,
    ReportType
)

router = APIRouter()

# In-memory storage for MVP (would use database in production)
_reports_store: dict[str, Report] = {}


@router.get("/", response_model=ReportList)
async def list_reports(page: int = 1, page_size: int = 50):
    """List all saved reports"""
    reports = list(_reports_store.values())
    total = len(reports)

    # Simple pagination
    start = (page - 1) * page_size
    end = start + page_size
    paginated = reports[start:end]

    return ReportList(
        reports=paginated,
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("/", response_model=Report, status_code=201)
async def create_report(report: ReportCreate):
    """Create a new report configuration"""
    report_id = str(uuid.uuid4())
    now = datetime.now()

    new_report = Report(
        id=report_id,
        name=report.name,
        type=report.type,
        description=report.description,
        days=report.days,
        filters=report.filters or {},
        sections=report.sections or ["metrics", "insights", "recommendations"],
        created_at=now,
        updated_at=now,
        generated_count=0
    )

    _reports_store[report_id] = new_report
    return new_report


@router.get("/{report_id}", response_model=ReportContent)
async def get_report(report_id: str = Path(description="Report ID")):
    """Get report with full content"""
    if report_id not in _reports_store:
        raise HTTPException(status_code=404, detail="Report not found")

    report = _reports_store[report_id]

    # Import here to avoid circular dependency
    from .insights import collect_metrics, analyze_metrics
    from analytics.core.insights import InsightEngine, RecommendationEngine

    # Collect data based on report configuration
    metrics = collect_metrics(days=report.days)
    analysis = analyze_metrics(metrics)

    # Generate insights
    insight_engine = InsightEngine()
    insights = insight_engine.generate_insights(metrics, analysis)

    # Generate recommendations
    rec_engine = RecommendationEngine()
    recommendations = rec_engine.generate_recommendations(insights)

    # Build report content
    content = ReportContent(
        id=report.id,
        name=report.name,
        type=report.type,
        metadata={
            "days": report.days,
            "filters": report.filters,
            "sections": report.sections,
            "generated_count": report.generated_count + 1
        },
        metrics=metrics if "metrics" in report.sections else {},
        insights=insights if "insights" in report.sections else {},
        recommendations=recommendations if "recommendations" in report.sections else [],
        charts=None,  # Charts generation would go here
        generated_at=datetime.now()
    )

    # Update generated count
    report.generated_count += 1
    report.updated_at = datetime.now()

    return content


@router.put("/{report_id}", response_model=Report)
async def update_report(
    report_id: str = Path(description="Report ID"),
    updates: ReportUpdate = None
):
    """Update report configuration"""
    if report_id not in _reports_store:
        raise HTTPException(status_code=404, detail="Report not found")

    report = _reports_store[report_id]

    # Apply updates
    if updates.name:
        report.name = updates.name
    if updates.description is not None:
        report.description = updates.description
    if updates.filters is not None:
        report.filters = updates.filters
    if updates.sections is not None:
        report.sections = updates.sections

    report.updated_at = datetime.now()

    return report


@router.delete("/{report_id}", status_code=204)
async def delete_report(report_id: str = Path(description="Report ID")):
    """Delete a report"""
    if report_id not in _reports_store:
        raise HTTPException(status_code=404, detail="Report not found")

    del _reports_store[report_id]
    return None
