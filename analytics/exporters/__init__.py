"""Analytics Exporters Module

Provides export functionality for analytics reports in various formats.

Available Exporters:
    - PDFExporter: Generate professional PDF reports with charts and tables
    - ExcelExporter: Generate Excel workbooks with multiple sheets, charts, and formatting
    - PPTXExporter: Generate PowerPoint presentations with slides, charts, and tables
    - CSVExporter: Export to CSV format (single file, multiple files, or ZIP archive)
    - PowerBIExporter: Export Power BI-compatible datasets with CSV files, schema, and connection file
    - ExcelTemplateBuilder: Build predefined Excel templates for common report types
    - ChartRenderer: Convert Chart.js configs to static images for PDF embedding

Example:
    >>> from analytics.exporters import PDFExporter, ExcelExporter, PPTXExporter, CSVExporter, PowerBIExporter, ExcelTemplateBuilder, ChartRenderer
    >>> pdf_exporter = PDFExporter()
    >>> excel_exporter = ExcelExporter()
    >>> pptx_exporter = PPTXExporter()
    >>> csv_exporter = CSVExporter()
    >>> powerbi_exporter = PowerBIExporter()
    >>> template_builder = ExcelTemplateBuilder()
    >>> chart_renderer = ChartRenderer()
    >>>
    >>> # PDF export
    >>> success, result = pdf_exporter.export_to_pdf(report_data, "output.pdf")
    >>>
    >>> # Excel export
    >>> result = excel_exporter.export_to_excel(report_data, "output.xlsx")
    >>>
    >>> # PowerPoint export
    >>> success, result = pptx_exporter.export_to_pptx(report_data, "output.pptx")
    >>>
    >>> # CSV export (single file)
    >>> success, path = csv_exporter.export_to_csv(report_data, "report.csv")
    >>>
    >>> # CSV export (multiple files)
    >>> success, paths = csv_exporter.export_multiple(report_data, "export/")
    >>>
    >>> # CSV export (ZIP archive)
    >>> success, path = csv_exporter.export_as_zip(report_data, "report.zip")
    >>>
    >>> # Power BI dataset export
    >>> success, path = powerbi_exporter.export_dataset(report_data, "powerbi_export/")
    >>>
    >>> # Excel template export
    >>> wb = excel_exporter.create_workbook()
    >>> template_builder.build_summary_dashboard(report_data, wb)
    >>> excel_exporter.save_workbook(wb, "dashboard.xlsx")
    >>>
    >>> # Chart rendering
    >>> chart_path = chart_renderer.render_chart(chart_config, "output.png")
"""

from analytics.exporters.pdf_exporter import PDFExporter
from analytics.exporters.excel_exporter import ExcelExporter
from analytics.exporters.pptx_exporter import PPTXExporter
from analytics.exporters.csv_exporter import CSVExporter
from analytics.exporters.powerbi_exporter import PowerBIExporter
from analytics.exporters.excel_templates import ExcelTemplateBuilder
from analytics.exporters.chart_renderer import ChartRenderer, render_chart_fallback

__all__ = [
    "PDFExporter",
    "ExcelExporter",
    "PPTXExporter",
    "CSVExporter",
    "PowerBIExporter",
    "ExcelTemplateBuilder",
    "ChartRenderer",
    "render_chart_fallback"
]
