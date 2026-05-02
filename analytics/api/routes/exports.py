"""Export API routes - ER016 specification

Endpoints:
    GET /api/v1/export/pdf/{report_id}     - Export as PDF
    GET /api/v1/export/excel/{report_id}   - Export as Excel
    GET /api/v1/export/pptx/{report_id}    - Export as PowerPoint
    GET /api/v1/export/csv                 - Export current data as CSV
    GET /api/v1/export/powerbi             - Export Power BI dataset

Legacy endpoints (backward compatibility):
    POST /api/v1/export/                   - Create export job
    GET  /api/v1/export/{export_id}        - Get export status
    GET  /api/v1/export/{export_id}/download - Download export
    DELETE /api/v1/export/{export_id}      - Delete export
"""
from fastapi import APIRouter, HTTPException, Query, Path
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from datetime import datetime, timedelta
from typing import Optional
import uuid
import json
import tempfile
import io

from ..models.reports import (
    ExportRequest,
    ExportResponse,
    ReportFormat
)

router = APIRouter()

# In-memory storage for exports (would use database + file storage in production)
_exports_store: dict[str, dict] = {}


@router.post("/", response_model=ExportResponse, status_code=202)
async def create_export(request: ExportRequest):
    """Create an export job"""
    export_id = str(uuid.uuid4())

    # In a real implementation, this would:
    # 1. Queue an async job to generate the export
    # 2. Store the file in S3/storage
    # 3. Return a download URL

    # For MVP, we'll just create a placeholder
    export_data = {
        "export_id": export_id,
        "format": request.format,
        "status": "processing",
        "created_at": datetime.now(),
        "report_id": request.report_id,
        "include_charts": request.include_charts,
        "include_raw_data": request.include_raw_data
    }

    _exports_store[export_id] = export_data

    return ExportResponse(
        export_id=export_id,
        format=request.format,
        status="processing",
        download_url=None,
        expires_at=None,
        file_size_bytes=None
    )


@router.get("/{export_id}", response_model=ExportResponse)
async def get_export_status(export_id: str):
    """Get export status"""
    if export_id not in _exports_store:
        raise HTTPException(status_code=404, detail="Export not found")

    export_data = _exports_store[export_id]

    # Simulate completion (in real implementation, check actual job status)
    if (datetime.now() - export_data["created_at"]).seconds > 5:
        export_data["status"] = "complete"
        export_data["download_url"] = f"/api/v1/export/{export_id}/download"
        export_data["expires_at"] = datetime.now() + timedelta(hours=24)
        export_data["file_size_bytes"] = 1024 * 100  # Fake size

    return ExportResponse(
        export_id=export_id,
        format=export_data["format"],
        status=export_data["status"],
        download_url=export_data.get("download_url"),
        expires_at=export_data.get("expires_at"),
        file_size_bytes=export_data.get("file_size_bytes")
    )


@router.get("/{export_id}/download")
async def download_export(export_id: str):
    """Download the exported file"""
    if export_id not in _exports_store:
        raise HTTPException(status_code=404, detail="Export not found")

    export_data = _exports_store[export_id]

    if export_data["status"] != "complete":
        raise HTTPException(status_code=400, detail="Export not ready yet")

    format_type = export_data["format"]

    # In real implementation, would return actual file from storage
    # For MVP, return JSON representation
    if format_type == ReportFormat.JSON:
        # Get report data (simplified)
        from .insights import collect_metrics, analyze_metrics
        from analytics.core.insights import InsightEngine

        metrics = collect_metrics(days=30)
        analysis = analyze_metrics(metrics)

        insight_engine = InsightEngine()
        insights = insight_engine.generate_insights(metrics, analysis)

        export_content = {
            "export_id": export_id,
            "format": "json",
            "generated_at": datetime.now().isoformat(),
            "data": {
                "metrics": metrics,
                "analysis": analysis,
                "insights": insights
            }
        }

        return JSONResponse(content=export_content)

    elif format_type == ReportFormat.PDF:
        # Would generate PDF here
        raise HTTPException(status_code=501, detail="PDF export not yet implemented")

    elif format_type == ReportFormat.EXCEL:
        # Generate Excel file
        from analytics.exporters import ExcelExporter
        from .insights import collect_metrics, analyze_metrics
        from analytics.core.insights import InsightEngine, RecommendationEngine
        import tempfile

        # Collect report data
        metrics = collect_metrics(days=30)
        analysis = analyze_metrics(metrics)

        insight_engine = InsightEngine()
        insights = insight_engine.generate_insights(metrics, analysis)

        rec_engine = RecommendationEngine()
        recommendations = rec_engine.generate_recommendations(insights)

        # Prepare report data structure
        report_data = {
            "id": export_id,
            "name": "Analytics Report",
            "type": "executive",
            "metadata": {
                "days": 30,
                "filters": {},
                "sections": ["metrics", "insights", "recommendations"]
            },
            "metrics": metrics,
            "insights": insights,
            "recommendations": recommendations,
            "generated_at": datetime.now()
        }

        # Generate Excel file
        exporter = ExcelExporter()

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.xlsx', delete=False) as tmp:
            temp_path = tmp.name

        result = exporter.export_to_excel(report_data, temp_path)

        if not result["success"]:
            raise HTTPException(status_code=500, detail=f"Excel export failed: {result['error']}")

        # Return file
        return FileResponse(
            path=result["path"],
            filename=f"analytics_report_{export_id}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    elif format_type == ReportFormat.CSV:
        # Generate CSV file
        from analytics.exporters import CSVExporter
        from analytics.core.reports import ReportGenerator
        import tempfile

        # Generate report
        generator = ReportGenerator()
        report = generator.generate_report("detailed")

        # Export to CSV
        exporter = CSVExporter()

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp:
            temp_path = tmp.name

        success, result = exporter.export_to_csv(report, temp_path)

        if not success:
            raise HTTPException(status_code=500, detail=f"CSV export failed: {result}")

        # Return file
        return FileResponse(
            path=result,
            filename=f"analytics_report_{export_id}.csv",
            media_type="text/csv"
        )

    elif format_type == ReportFormat.CSV_ZIP:
        # Generate CSV ZIP archive
        from analytics.exporters import CSVExporter
        from analytics.core.reports import ReportGenerator
        import tempfile

        # Generate report
        generator = ReportGenerator()
        report = generator.generate_report("detailed")

        # Export to CSV ZIP
        exporter = CSVExporter()

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.zip', delete=False) as tmp:
            temp_path = tmp.name

        success, result = exporter.export_as_zip(report, temp_path)

        if not success:
            raise HTTPException(status_code=500, detail=f"CSV ZIP export failed: {result}")

        # Return file
        return FileResponse(
            path=result,
            filename=f"analytics_report_{export_id}.zip",
            media_type="application/zip"
        )

    elif format_type == ReportFormat.PPTX:
        # Generate PowerPoint file
        from analytics.exporters import PPTXExporter
        from .insights import collect_metrics, analyze_metrics
        from analytics.core.insights import InsightEngine, RecommendationEngine

        # Collect report data
        metrics = collect_metrics(days=30)
        analysis = analyze_metrics(metrics)

        insight_engine = InsightEngine()
        insights = insight_engine.generate_insights(metrics, analysis)

        rec_engine = RecommendationEngine()
        recommendations = rec_engine.generate_recommendations(insights)

        # Prepare report data structure
        report_data = {
            "id": export_id,
            "name": "Analytics Report",
            "type": "executive",
            "metadata": {
                "days": 30,
                "filters": {},
                "sections": ["metrics", "insights", "recommendations"]
            },
            "metrics": metrics,
            "insights": insights,
            "recommendations": recommendations,
            "generated_at": datetime.now()
        }

        # Generate PowerPoint file
        exporter = PPTXExporter()

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pptx', delete=False) as tmp:
            temp_path = tmp.name

        result = exporter.export_to_pptx(report_data, temp_path)

        if not result["success"]:
            raise HTTPException(status_code=500, detail=f"PowerPoint export failed: {result['error']}")

        # Return file
        return FileResponse(
            path=result["path"],
            filename=f"analytics_report_{export_id}.pptx",
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )

    elif format_type == ReportFormat.POWERBI:
        # Generate Power BI dataset
        from analytics.exporters import PowerBIExporter
        from .insights import collect_metrics, analyze_metrics
        from analytics.core.insights import InsightEngine

        # Collect report data
        metrics = collect_metrics(days=30)
        analysis = analyze_metrics(metrics)

        insight_engine = InsightEngine()
        insights = insight_engine.generate_insights(metrics, analysis)

        # Prepare report data structure
        report_data = {
            "id": export_id,
            "name": "Analytics Report",
            "type": "executive",
            "metadata": {
                "days": 30,
                "filters": {},
                "sections": ["metrics", "insights", "recommendations"]
            },
            "metrics": metrics,
            "insights": insights,
            "generated_at": datetime.now()
        }

        # Generate Power BI dataset
        exporter = PowerBIExporter()

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.xlsx', delete=False) as tmp:
            temp_path = tmp.name

        result = exporter.export_for_powerbi(report_data, temp_path)

        if not result["success"]:
            raise HTTPException(status_code=500, detail=f"Power BI export failed: {result['error']}")

        # Return file
        return FileResponse(
            path=result["path"],
            filename=f"powerbi_dataset_{export_id}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    elif format_type == ReportFormat.HTML:
        # Would generate HTML here
        raise HTTPException(status_code=501, detail="HTML export not yet implemented")

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format_type}")


@router.delete("/{export_id}", status_code=204)
async def delete_export(export_id: str):
    """Delete an export"""
    if export_id not in _exports_store:
        raise HTTPException(status_code=404, detail="Export not found")

    del _exports_store[export_id]
    return None


# ER016 - Direct Export Endpoints

@router.get("/pdf/{report_id}")
async def export_pdf(
    report_id: str = Path(..., description="Report ID to export"),
    include_charts: bool = Query(True, description="Include charts in PDF")
):
    """Export a report as PDF

    Generates a PDF version of the specified report.

    Args:
        report_id: Report ID to export
        include_charts: Whether to include charts (default: True)

    Returns:
        FileResponse with PDF file

    Raises:
        HTTPException: 404 if report not found
        HTTPException: 500 if PDF generation fails
    """
    # Import reports store from reports.py
    from . import reports as reports_module

    if report_id not in reports_module._reports_store:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Report not found",
                "status_code": 404,
                "details": {"report_id": report_id}
            }
        )

    report = reports_module._reports_store[report_id]

    if report["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Report not ready",
                "status_code": 400,
                "details": {"status": report["status"]}
            }
        )

    try:
        from analytics.exporters import PDFExporter

        exporter = PDFExporter()

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pdf', delete=False) as tmp:
            temp_path = tmp.name

        # Export to PDF
        result = exporter.export_to_pdf(report["content"], temp_path)

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "PDF export failed",
                    "status_code": 500,
                    "details": {"message": result.get("error")}
                }
            )

        return FileResponse(
            path=result["path"],
            media_type="application/pdf",
            filename=f"report_{report_id}.pdf"
        )

    except ImportError:
        raise HTTPException(
            status_code=501,
            detail={
                "error": "PDF export not available",
                "status_code": 501,
                "details": "PDFExporter not installed"
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "PDF export failed",
                "status_code": 500,
                "details": {"message": str(e)}
            }
        )


@router.get("/excel/{report_id}")
async def export_excel(
    report_id: str = Path(..., description="Report ID to export"),
    include_charts: bool = Query(True, description="Include charts in Excel"),
    include_raw_data: bool = Query(False, description="Include raw data sheet")
):
    """Export a report as Excel

    Generates an Excel workbook with formatted report data.

    Args:
        report_id: Report ID to export
        include_charts: Whether to include charts (default: True)
        include_raw_data: Whether to include raw data sheet (default: False)

    Returns:
        FileResponse with Excel file

    Raises:
        HTTPException: 404 if report not found
        HTTPException: 500 if Excel generation fails
    """
    from . import reports as reports_module

    if report_id not in reports_module._reports_store:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Report not found",
                "status_code": 404,
                "details": {"report_id": report_id}
            }
        )

    report = reports_module._reports_store[report_id]

    if report["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Report not ready",
                "status_code": 400,
                "details": {"status": report["status"]}
            }
        )

    try:
        from analytics.exporters import ExcelExporter

        exporter = ExcelExporter()

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.xlsx', delete=False) as tmp:
            temp_path = tmp.name

        # Prepare report data
        report_data = {
            "id": report_id,
            "name": f"{report['report_type'].title()} Report",
            "type": report["report_type"],
            "metadata": report.get("config", {}),
            **report["content"]
        }

        # Export to Excel
        result = exporter.export_to_excel(report_data, temp_path)

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Excel export failed",
                    "status_code": 500,
                    "details": {"message": result.get("error")}
                }
            )

        return FileResponse(
            path=result["path"],
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=f"report_{report_id}.xlsx"
        )

    except ImportError:
        raise HTTPException(
            status_code=501,
            detail={
                "error": "Excel export not available",
                "status_code": 501,
                "details": "ExcelExporter not installed"
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Excel export failed",
                "status_code": 500,
                "details": {"message": str(e)}
            }
        )


@router.get("/pptx/{report_id}")
async def export_pptx(
    report_id: str = Path(..., description="Report ID to export"),
    template: Optional[str] = Query(None, description="PowerPoint template to use")
):
    """Export a report as PowerPoint

    Generates a PowerPoint presentation with report visualizations.

    Args:
        report_id: Report ID to export
        template: Optional template name (e.g., 'executive', 'technical')

    Returns:
        FileResponse with PowerPoint file

    Raises:
        HTTPException: 404 if report not found
        HTTPException: 500 if PowerPoint generation fails
    """
    from . import reports as reports_module

    if report_id not in reports_module._reports_store:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Report not found",
                "status_code": 404,
                "details": {"report_id": report_id}
            }
        )

    report = reports_module._reports_store[report_id]

    if report["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Report not ready",
                "status_code": 400,
                "details": {"status": report["status"]}
            }
        )

    try:
        from analytics.exporters import PPTXExporter

        exporter = PPTXExporter()

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pptx', delete=False) as tmp:
            temp_path = tmp.name

        # Export to PowerPoint
        result = exporter.export_to_pptx(
            report["content"],
            temp_path,
            template=template
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "PowerPoint export failed",
                    "status_code": 500,
                    "details": {"message": result.get("error")}
                }
            )

        return FileResponse(
            path=result["path"],
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename=f"report_{report_id}.pptx"
        )

    except ImportError:
        raise HTTPException(
            status_code=501,
            detail={
                "error": "PowerPoint export not available",
                "status_code": 501,
                "details": "PPTXExporter not installed"
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "PowerPoint export failed",
                "status_code": 500,
                "details": {"message": str(e)}
            }
        )


@router.get("/csv")
async def export_csv(
    date_range: Optional[str] = Query(
        None,
        description="Date range in format 'YYYY-MM-DD,YYYY-MM-DD'"
    ),
    filters: Optional[str] = Query(
        None,
        description="JSON string of filters to apply"
    )
):
    """Export current analytics data as CSV

    Exports the latest analytics data in CSV format. Does not require
    a pre-generated report.

    Args:
        date_range: Optional date range (comma-separated start,end)
        filters: Optional JSON string of filters

    Returns:
        FileResponse with CSV file

    Raises:
        HTTPException: 400 if invalid parameters
        HTTPException: 500 if CSV generation fails
    """
    try:
        from analytics.exporters import CSVExporter
        from analytics.core.reports import ReportGenerator

        # Parse date range
        if date_range:
            try:
                start_date, end_date = date_range.split(",")
                date_range_tuple = (start_date.strip(), end_date.strip())
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Invalid date_range format",
                        "status_code": 400,
                        "details": "Expected 'YYYY-MM-DD,YYYY-MM-DD'"
                    }
                )
        else:
            date_range_tuple = None

        # Parse filters
        if filters:
            try:
                filters_dict = json.loads(filters)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Invalid filters format",
                        "status_code": 400,
                        "details": "Expected valid JSON string"
                    }
                )
        else:
            filters_dict = {}

        # Generate report data
        generator = ReportGenerator()
        report = generator.generate_report(
            "detailed",
            config={
                "date_range": date_range_tuple,
                "filters": filters_dict
            }
        )

        # Export to CSV
        exporter = CSVExporter()

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp:
            temp_path = tmp.name

        success, result = exporter.export_to_csv(report, temp_path)

        if not success:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "CSV export failed",
                    "status_code": 500,
                    "details": {"message": result}
                }
            )

        return FileResponse(
            path=result,
            media_type="text/csv",
            filename=f"analytics_data_{datetime.now().strftime('%Y%m%d')}.csv"
        )

    except ImportError:
        raise HTTPException(
            status_code=501,
            detail={
                "error": "CSV export not available",
                "status_code": 501,
                "details": "CSVExporter not installed"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "CSV export failed",
                "status_code": 500,
                "details": {"message": str(e)}
            }
        )


@router.get("/powerbi")
async def export_powerbi(
    include_relationships: bool = Query(True, description="Include table relationships"),
    include_measures: bool = Query(True, description="Include DAX measures")
):
    """Export Power BI dataset package

    Generates a ZIP archive containing Power BI-compatible data files,
    schema definitions, and DAX measures.

    Args:
        include_relationships: Include relationship definitions (default: True)
        include_measures: Include DAX measure definitions (default: True)

    Returns:
        FileResponse with ZIP file containing Power BI dataset

    Raises:
        HTTPException: 500 if export fails
    """
    try:
        from analytics.exporters import PowerBIExporter
        from analytics.core.reports import ReportGenerator

        # Generate comprehensive report
        generator = ReportGenerator()
        report = generator.generate_report("detailed")

        # Export to Power BI format
        exporter = PowerBIExporter()

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.zip', delete=False) as tmp:
            temp_path = tmp.name

        result = exporter.export_for_powerbi(
            report,
            temp_path,
            include_relationships=include_relationships,
            include_measures=include_measures
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Power BI export failed",
                    "status_code": 500,
                    "details": {"message": result.get("error")}
                }
            )

        return FileResponse(
            path=result["path"],
            media_type="application/zip",
            filename=f"powerbi_dataset_{datetime.now().strftime('%Y%m%d')}.zip"
        )

    except ImportError:
        raise HTTPException(
            status_code=501,
            detail={
                "error": "Power BI export not available",
                "status_code": 501,
                "details": "PowerBIExporter not installed"
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Power BI export failed",
                "status_code": 500,
                "details": {"message": str(e)}
            }
        )
