"""Pydantic models for reports endpoints"""
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional
from datetime import datetime
from enum import Enum


class ReportType(str, Enum):
    """Report types"""
    EXECUTIVE = "executive"
    DETAILED = "detailed"
    TECHNICAL = "technical"
    CUSTOM = "custom"


class ReportFormat(str, Enum):
    """Export formats"""
    PDF = "pdf"
    EXCEL = "excel"
    PPTX = "pptx"
    CSV = "csv"
    CSV_ZIP = "csv_zip"
    POWERBI = "powerbi"
    JSON = "json"
    HTML = "html"


class ReportCreate(BaseModel):
    """Create report request"""
    name: str = Field(min_length=1, max_length=200)
    type: ReportType
    description: Optional[str] = None
    days: int = Field(default=30, ge=1, le=365)
    filters: Optional[Dict[str, Any]] = None
    sections: Optional[List[str]] = None  # Which sections to include


class ReportUpdate(BaseModel):
    """Update report request"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    sections: Optional[List[str]] = None


class Report(BaseModel):
    """Report metadata"""
    id: str
    name: str
    type: ReportType
    description: Optional[str]
    days: int
    filters: Dict[str, Any]
    sections: List[str]
    created_at: datetime
    updated_at: datetime
    generated_count: int = 0


class ReportContent(BaseModel):
    """Full report content"""
    id: str
    name: str
    type: ReportType
    metadata: Dict[str, Any]
    metrics: Dict[str, Any]
    insights: Dict[str, Any]
    recommendations: List[Dict[str, Any]]
    charts: Optional[List[Dict[str, Any]]] = None
    generated_at: datetime


class ReportList(BaseModel):
    """List of reports"""
    reports: List[Report]
    total: int
    page: int = 1
    page_size: int = 50


class ExportRequest(BaseModel):
    """Export request"""
    report_id: Optional[str] = None
    format: ReportFormat
    include_charts: bool = True
    include_raw_data: bool = False


class ExportResponse(BaseModel):
    """Export response"""
    export_id: str
    format: ReportFormat
    status: str  # "processing", "complete", "failed"
    download_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    file_size_bytes: Optional[int] = None
