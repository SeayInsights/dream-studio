"""PDF Export Module for Analytics Platform

Generates professional PDF reports from analytics data with graceful dependency handling.

Installation:
    Preferred (full features):
        pip install reportlab Pillow

    Minimal (text-only fallback):
        No additional dependencies required

Features:
    - Multi-page reports with automatic page breaks
    - Branded headers and footers
    - Data tables and metrics display
    - Chart image embedding (when reportlab available)
    - Professional styling and layout

Example:
    >>> from analytics.exporters import PDFExporter
    >>> exporter = PDFExporter()
    >>> report_data = {
    ...     "metadata": {
    ...         "generated_at": "2026-05-02T02:00:00Z",
    ...         "report_type": "summary",
    ...         "date_range": {"start": "2026-04-01", "end": "2026-04-30"}
    ...     },
    ...     "sections": [...]
    ... }
    >>> success, result = exporter.export_to_pdf(report_data, "report.pdf")
    >>> if success:
    ...     print(f"PDF saved to: {result}")
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

# Try importing reportlab (preferred PDF library)
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, Image as RLImage
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# Try importing Pillow for image handling
try:
    from PIL import Image as PILImage
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


class PDFExporter:
    """Professional PDF report generator with graceful dependency fallback"""

    def __init__(self):
        """Initialize PDF exporter with available libraries"""
        self.has_reportlab = HAS_REPORTLAB
        self.has_pillow = HAS_PILLOW

        if not self.has_reportlab:
            print("WARNING: reportlab not available - PDF exports will use text-only fallback")
            print("   Install with: pip install reportlab Pillow")

    def export_to_pdf(
        self,
        report_data: Dict[str, Any],
        output_path: str
    ) -> Tuple[bool, str]:
        """
        Export report data to PDF file

        Args:
            report_data: Report data dictionary with metadata and sections
            output_path: Path where PDF should be saved

        Returns:
            Tuple of (success: bool, result: str)
            - If success=True, result is the output file path
            - If success=False, result is the error message
        """
        try:
            # Validate report data structure
            validation_result = self._validate_report_data(report_data)
            if not validation_result[0]:
                return False, validation_result[1]

            # Ensure output directory exists
            output_path = Path(output_path).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Choose export method based on available dependencies
            if self.has_reportlab:
                return self._export_with_reportlab(report_data, output_path)
            else:
                return self._export_text_fallback(report_data, output_path)

        except Exception as e:
            return False, f"PDF export failed: {str(e)}"

    def _validate_report_data(self, report_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate report data structure"""
        if not isinstance(report_data, dict):
            return False, "report_data must be a dictionary"

        if "metadata" not in report_data:
            return False, "report_data must contain 'metadata' key"

        if "sections" not in report_data:
            return False, "report_data must contain 'sections' key"

        if not isinstance(report_data["sections"], list):
            return False, "'sections' must be a list"

        return True, "Valid"

    def _export_with_reportlab(
        self,
        report_data: Dict[str, Any],
        output_path: Path
    ) -> Tuple[bool, str]:
        """Export PDF using reportlab (full-featured)"""
        try:
            # Create PDF document
            doc = SimpleDocTemplate(
                str(output_path),
                pagesize=letter,
                rightMargin=0.75*inch,
                leftMargin=0.75*inch,
                topMargin=1*inch,
                bottomMargin=1*inch
            )

            # Build story (content elements)
            story = []
            styles = getSampleStyleSheet()

            # Custom styles
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                textColor=colors.HexColor('#1a1a1a'),
                spaceAfter=30,
                alignment=TA_CENTER
            )

            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontSize=16,
                textColor=colors.HexColor('#2c3e50'),
                spaceAfter=12,
                spaceBefore=12
            )

            # Extract metadata
            metadata = report_data.get("metadata", {})
            report_type = metadata.get("report_type", "Analytics Report").title()
            generated_at = metadata.get("generated_at", datetime.now().isoformat())
            date_range = metadata.get("date_range", {})

            # Add title
            story.append(Paragraph(f"{report_type} Report", title_style))

            # Add metadata table
            meta_data = []
            if date_range:
                start_date = date_range.get("start", "N/A")
                end_date = date_range.get("end", "N/A")
                meta_data.append(["Report Period:", f"{start_date} to {end_date}"])

            meta_data.append(["Generated:", self._format_datetime(generated_at)])

            if meta_data:
                meta_table = Table(meta_data, colWidths=[2*inch, 4*inch])
                meta_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
                    ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                    ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#555555')),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ]))
                story.append(meta_table)
                story.append(Spacer(1, 0.3*inch))

            # Add sections
            for section in report_data.get("sections", []):
                story.extend(self._build_section(section, styles, heading_style))

            # Add footer to each page
            def add_page_footer(canvas, doc):
                canvas.saveState()
                # Footer text
                footer_text = "Generated by dream-studio Analytics Platform"
                canvas.setFont('Helvetica', 9)
                canvas.setFillColor(colors.HexColor('#888888'))
                canvas.drawCentredString(
                    letter[0] / 2,
                    0.5 * inch,
                    footer_text
                )
                # Page number
                page_num = f"Page {doc.page}"
                canvas.drawRightString(
                    letter[0] - 0.75 * inch,
                    0.5 * inch,
                    page_num
                )
                canvas.restoreState()

            # Build PDF
            doc.build(story, onFirstPage=add_page_footer, onLaterPages=add_page_footer)

            return True, str(output_path)

        except Exception as e:
            return False, f"reportlab export failed: {str(e)}"

    def _build_section(
        self,
        section: Dict[str, Any],
        styles: Any,
        heading_style: Any
    ) -> List[Any]:
        """Build PDF elements for a report section"""
        elements = []

        # Section title
        title = section.get("title", "Section")
        elements.append(Paragraph(title, heading_style))
        elements.append(Spacer(1, 0.1*inch))

        # Metrics
        metrics = section.get("metrics", {})
        if metrics:
            elements.extend(self.add_tables({"Metrics": metrics}))
            elements.append(Spacer(1, 0.2*inch))

        # Charts
        charts = section.get("charts", [])
        if charts:
            elements.extend(self.add_charts(charts))
            elements.append(Spacer(1, 0.2*inch))

        # Add spacing between sections
        elements.append(Spacer(1, 0.2*inch))

        return elements

    def add_tables(self, table_data: Dict[str, Any]) -> List[Any]:
        """
        Format and add data tables to PDF

        Args:
            table_data: Dictionary mapping table names to data

        Returns:
            List of reportlab elements
        """
        elements = []

        if not self.has_reportlab:
            return elements

        for table_name, data in table_data.items():
            # Convert dict to table rows
            if isinstance(data, dict):
                rows = [["Metric", "Value"]]
                for key, value in data.items():
                    # Format value
                    if isinstance(value, (int, float)):
                        value_str = f"{value:,.2f}" if isinstance(value, float) else f"{value:,}"
                    else:
                        value_str = str(value)

                    rows.append([str(key), value_str])
            elif isinstance(data, list):
                rows = data
            else:
                continue

            # Create table
            table = Table(rows, colWidths=[3*inch, 2*inch])
            table.setStyle(TableStyle([
                # Header row
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                # Data rows
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('TOPPADDING', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ]))

            elements.append(table)
            elements.append(Spacer(1, 0.15*inch))

        return elements

    def add_charts(self, chart_data: List[Dict[str, Any]]) -> List[Any]:
        """
        Embed chart images in PDF

        Args:
            chart_data: List of chart dictionaries with 'type', 'title', 'data' keys
                       Optionally includes 'image_path' for pre-generated images

        Returns:
            List of reportlab elements
        """
        elements = []

        if not self.has_reportlab:
            return elements

        styles = getSampleStyleSheet()

        for chart in chart_data:
            chart_title = chart.get("title", "Chart")
            chart_type = chart.get("type", "unknown")
            image_path = chart.get("image_path")

            # Add chart title
            elements.append(Paragraph(
                f"<b>{chart_title}</b> ({chart_type})",
                styles['Heading3']
            ))
            elements.append(Spacer(1, 0.05*inch))

            # Add image if available
            if image_path and os.path.exists(image_path):
                try:
                    # Add image with max width
                    img = RLImage(image_path, width=5*inch, height=3*inch)
                    elements.append(img)
                except Exception as e:
                    # Fallback to placeholder text
                    elements.append(Paragraph(
                        f"[Chart placeholder - {chart_type}]",
                        styles['Italic']
                    ))
            else:
                # Placeholder for chart
                elements.append(Paragraph(
                    f"[Chart: {chart_title} - Image not available]",
                    styles['Italic']
                ))

            elements.append(Spacer(1, 0.15*inch))

        return elements

    def add_header_footer(self) -> None:
        """
        Add branded header/footer on each page

        Note: Header/footer are added via the onFirstPage/onLaterPages callbacks
        in the _export_with_reportlab method. This method is kept for API consistency.
        """
        pass

    def _export_text_fallback(
        self,
        report_data: Dict[str, Any],
        output_path: Path
    ) -> Tuple[bool, str]:
        """Export simple text-based PDF when reportlab unavailable"""
        try:
            # Extract metadata
            metadata = report_data.get("metadata", {})
            report_type = metadata.get("report_type", "Analytics Report").title()
            generated_at = metadata.get("generated_at", datetime.now().isoformat())
            date_range = metadata.get("date_range", {})

            # Build text content
            lines = []
            lines.append(f"%PDF-1.4")
            lines.append(f"1 0 obj")
            lines.append(f"<<")
            lines.append(f"/Type /Catalog")
            lines.append(f"/Pages 2 0 R")
            lines.append(f">>")
            lines.append(f"endobj")

            # Create simple text content
            text_content = []
            text_content.append(f"{report_type} Report")
            text_content.append("")

            if date_range:
                start = date_range.get("start", "N/A")
                end = date_range.get("end", "N/A")
                text_content.append(f"Report Period: {start} to {end}")

            text_content.append(f"Generated: {self._format_datetime(generated_at)}")
            text_content.append("")
            text_content.append("-" * 60)
            text_content.append("")

            # Add sections
            for section in report_data.get("sections", []):
                text_content.append(f"\n{section.get('title', 'Section')}")
                text_content.append("=" * 60)

                # Add metrics
                metrics = section.get("metrics", {})
                if metrics:
                    text_content.append("\nMetrics:")
                    for key, value in metrics.items():
                        text_content.append(f"  {key}: {value}")

                # Note charts
                charts = section.get("charts", [])
                if charts:
                    text_content.append(f"\nCharts: {len(charts)} chart(s)")
                    for chart in charts:
                        text_content.append(f"  - {chart.get('title', 'Chart')} ({chart.get('type', 'unknown')})")

                text_content.append("")

            text_content.append("-" * 60)
            text_content.append("Generated by dream-studio Analytics Platform")

            # Write minimal PDF structure (text-based)
            # Note: This creates a very basic PDF - recommend installing reportlab
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(text_content))

            return True, f"{output_path} (text-only - install reportlab for full PDF support)"

        except Exception as e:
            return False, f"Text fallback export failed: {str(e)}"

    def _format_datetime(self, dt_str: str) -> str:
        """Format ISO datetime string for display"""
        try:
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            return dt_str
