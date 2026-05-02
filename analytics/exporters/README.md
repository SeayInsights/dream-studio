# Analytics Exporters

Professional export functionality for analytics reports in multiple formats.

## Available Exporters

### PDFExporter

Generate professional PDF reports with tables, charts, and branded headers/footers.

**Features:**
- Multi-page reports with automatic page breaks
- Professional styling with tables and formatting
- Branded headers and footers on each page
- Chart image embedding support
- Graceful fallback when reportlab unavailable

**Installation:**

```bash
# Full features (recommended)
pip install reportlab Pillow

# Text-only fallback (no additional dependencies)
# Works without reportlab, generates simple text-based output
```

**Usage:**

```python
from analytics.exporters import PDFExporter

# Initialize exporter
exporter = PDFExporter()

# Prepare report data
report_data = {
    "metadata": {
        "generated_at": "2026-05-01T22:00:00Z",
        "report_type": "security_summary",
        "date_range": {
            "start": "2026-04-01",
            "end": "2026-04-30"
        }
    },
    "sections": [
        {
            "title": "Executive Summary",
            "metrics": {
                "Total Vulnerabilities": 142,
                "Critical": 8,
                "High": 23
            },
            "charts": [
                {
                    "type": "bar",
                    "title": "Vulnerabilities by Severity",
                    "image_path": "/path/to/chart.png"  # Optional
                }
            ]
        }
    ]
}

# Export to PDF
success, result = exporter.export_to_pdf(report_data, "report.pdf")

if success:
    print(f"PDF saved to: {result}")
else:
    print(f"Error: {result}")
```

**Integration with ReportGenerator:**

```python
from analytics.core.report_generator import ReportGenerator
from analytics.exporters import PDFExporter

# Generate report data
generator = ReportGenerator(data_store)
report_data = generator.generate_report(
    report_type="summary",
    start_date="2026-04-01",
    end_date="2026-04-30"
)

# Export to PDF
exporter = PDFExporter()
success, path = exporter.export_to_pdf(report_data, "monthly_report.pdf")
```

## Report Data Structure

All exporters expect the following data structure:

```python
{
    "metadata": {
        "generated_at": str,      # ISO datetime
        "report_type": str,       # Report type identifier
        "date_range": {
            "start": str,         # YYYY-MM-DD
            "end": str           # YYYY-MM-DD
        }
    },
    "sections": [
        {
            "title": str,         # Section heading
            "metrics": {          # Key-value metrics
                "metric_name": value,
                ...
            },
            "charts": [           # Chart definitions
                {
                    "type": str,       # Chart type (bar, line, pie, etc.)
                    "title": str,      # Chart title
                    "data": list,      # Chart data
                    "image_path": str  # Optional: pre-rendered image path
                }
            ]
        }
    ]
}
```

## Testing

Run the test suite:

```bash
python -m analytics.exporters.test_pdf_exporter
```

## Output Examples

Generated PDFs include:
- Professional title page with metadata
- Styled section headings
- Formatted data tables with alternating row colors
- Chart placeholders (or embedded images when available)
- Page numbers and branded footers
- Automatic page breaks

See `test_output/test_report.pdf` for a complete example.
