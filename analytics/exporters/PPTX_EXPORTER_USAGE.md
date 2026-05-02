# PowerPoint Exporter Usage Guide

Complete guide for using the `PPTXExporter` class to generate professional PowerPoint presentations from analytics data.

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [API Reference](#api-reference)
4. [Report Data Structure](#report-data-structure)
5. [Examples](#examples)
6. [Chart Integration](#chart-integration)
7. [Customization](#customization)
8. [Troubleshooting](#troubleshooting)

## Installation

### Preferred (Full Features)

```bash
pip install python-pptx Pillow
```

### Fallback

If `python-pptx` is not available, the exporter will automatically fall back to PDF export using `PDFExporter`:

```bash
pip install reportlab Pillow
```

## Quick Start

```python
from analytics.exporters import PPTXExporter
from datetime import datetime

# Create exporter
exporter = PPTXExporter()

# Prepare report data
report_data = {
    "metadata": {
        "generated_at": datetime.now().isoformat(),
        "report_type": "executive",
        "date_range": {
            "start": "2026-04-01",
            "end": "2026-04-30"
        }
    },
    "sections": [
        {
            "title": "Key Metrics",
            "metrics": {
                "Total Users": 15234,
                "Revenue": 125430.50
            },
            "charts": []
        }
    ]
}

# Export to PowerPoint
success, result = exporter.export_to_pptx(
    report_data,
    "C:/Users/Dannis Seay/Downloads/report.pptx"
)

if success:
    print(f"Presentation saved to: {result}")
else:
    print(f"Export failed: {result}")
```

## API Reference

### PPTXExporter Class

#### Constructor

```python
exporter = PPTXExporter()
```

Creates a new PowerPoint exporter instance.

#### Methods

##### `export_to_pptx(report_data, output_path)`

Main entry point for exporting data to PowerPoint.

**Parameters:**
- `report_data` (dict): Report data structure (see below)
- `output_path` (str): Full path where .pptx file should be saved

**Returns:**
- `(bool, str)`: Tuple of (success, result)
  - If `success=True`, `result` is the output file path
  - If `success=False`, `result` is the error message

**Example:**
```python
success, path = exporter.export_to_pptx(data, "report.pptx")
```

##### `create_presentation()`

Initialize a new presentation with 16:9 layout.

**Returns:**
- `Presentation`: python-pptx Presentation object

**Example:**
```python
prs = exporter.create_presentation()
```

##### `add_title_slide(prs, title, subtitle)`

Add a title slide to the presentation.

**Parameters:**
- `prs`: Presentation object
- `title` (str): Main title text (44pt, bold)
- `subtitle` (str): Subtitle text (20pt)

**Example:**
```python
exporter.add_title_slide(prs, "Q1 Analytics Report", "January - March 2026")
```

##### `add_chart_slide(prs, chart_data)`

Add a slide with a chart image.

**Parameters:**
- `prs`: Presentation object
- `chart_data` (dict): Chart configuration with keys:
  - `title` (str): Chart title
  - `type` (str): Chart type (line, bar, pie, scatter)
  - `image_path` (str): Path to chart image file

**Example:**
```python
chart_data = {
    "title": "Monthly Revenue",
    "type": "bar",
    "image_path": "/path/to/chart.png"
}
exporter.add_chart_slide(prs, chart_data)
```

##### `add_table_slide(prs, table_data)`

Add a slide with a data table.

**Parameters:**
- `prs`: Presentation object
- `table_data` (dict): Table configuration with keys:
  - `title` (str): Slide title
  - `data` (dict): Dictionary of metric_name: value pairs

**Example:**
```python
table_data = {
    "title": "Performance Metrics",
    "data": {
        "Total Users": 15234,
        "Revenue": 125430.50,
        "Conversion Rate": 0.0823
    }
}
exporter.add_table_slide(prs, table_data)
```

##### `add_text_slide(prs, title, content)`

Add a text/bullet point slide.

**Parameters:**
- `prs`: Presentation object
- `title` (str): Slide title
- `content` (list): List of text items (bullet points)

**Example:**
```python
exporter.add_text_slide(
    prs,
    "Key Findings",
    [
        "User growth increased 15% over quarter",
        "Revenue exceeded targets by 5%",
        "Customer retention at 94%"
    ]
)
```

##### `get_installation_instructions()`

Get installation instructions for required libraries.

**Returns:**
- `str`: Installation instructions

**Example:**
```python
print(exporter.get_installation_instructions())
```

## Report Data Structure

The `report_data` dictionary should follow this structure:

```python
{
    "metadata": {
        "generated_at": "2026-05-01T12:00:00Z",  # ISO datetime
        "report_type": "executive",               # Report type name
        "date_range": {
            "start": "2026-04-01",
            "end": "2026-04-30"
        }
    },
    "sections": [
        {
            "title": "Section Name",
            "metrics": {
                "Metric Name 1": 12345,
                "Metric Name 2": 98.7,
                "Metric Name 3": 0.0823
            },
            "charts": [
                {
                    "title": "Chart Title",
                    "type": "bar",
                    "image_path": "/path/to/chart.png"
                }
            ]
        }
    ]
}
```

### Required Fields

- `metadata` (dict): Report metadata
  - `generated_at` (str): ISO datetime string
  - Other fields are optional

- `sections` (list): List of report sections
  - `title` (str): Section title
  - `metrics` (dict): Optional metrics dictionary
  - `charts` (list): Optional charts list

## Examples

### Example 1: Simple Report

```python
from analytics.exporters import PPTXExporter
from datetime import datetime

exporter = PPTXExporter()

report_data = {
    "metadata": {
        "generated_at": datetime.now().isoformat(),
        "report_type": "summary"
    },
    "sections": [
        {
            "title": "Key Metrics",
            "metrics": {
                "Users": 10000,
                "Revenue": 50000.00
            },
            "charts": []
        }
    ]
}

exporter.export_to_pptx(report_data, "simple_report.pptx")
```

### Example 2: Multi-Section Report

```python
from analytics.exporters import PPTXExporter
from datetime import datetime

exporter = PPTXExporter()

report_data = {
    "metadata": {
        "generated_at": datetime.now().isoformat(),
        "report_type": "executive",
        "date_range": {"start": "2026-04-01", "end": "2026-04-30"}
    },
    "sections": [
        {
            "title": "Performance Overview",
            "metrics": {
                "Total Users": 15234,
                "Active Users": 12458,
                "Conversion Rate": 0.0823
            },
            "charts": []
        },
        {
            "title": "Revenue Metrics",
            "metrics": {
                "Total Revenue": 125430.50,
                "Growth Rate": 0.15
            },
            "charts": []
        },
        {
            "title": "Regional Performance",
            "metrics": {
                "North America": 45000,
                "Europe": 38000,
                "Asia Pacific": 28000
            },
            "charts": []
        }
    ]
}

success, path = exporter.export_to_pptx(
    report_data,
    "C:/Users/Dannis Seay/Downloads/multi_section_report.pptx"
)

print(f"Report saved to: {path}")
```

### Example 3: Report with Charts

```python
from analytics.exporters import PPTXExporter, ChartRenderer
from datetime import datetime
import tempfile

# Create chart renderer
chart_renderer = ChartRenderer()

# Render a chart
chart_config = {
    "type": "bar",
    "title": "Monthly Revenue",
    "data": {
        "labels": ["Jan", "Feb", "Mar", "Apr"],
        "datasets": [{
            "label": "Revenue",
            "data": [25000, 30000, 28000, 35000]
        }]
    }
}

chart_path = chart_renderer.render_chart(chart_config, "revenue_chart.png")

# Create report with chart
exporter = PPTXExporter()

report_data = {
    "metadata": {
        "generated_at": datetime.now().isoformat(),
        "report_type": "analytics"
    },
    "sections": [
        {
            "title": "Revenue Analysis",
            "metrics": {},
            "charts": [{
                "title": "Monthly Revenue Trend",
                "type": "bar",
                "image_path": chart_path
            }]
        }
    ]
}

exporter.export_to_pptx(report_data, "report_with_charts.pptx")
```

### Example 4: Custom Presentation

```python
from analytics.exporters import PPTXExporter

exporter = PPTXExporter()

# Create presentation manually
prs = exporter.create_presentation()

# Add title slide
exporter.add_title_slide(
    prs,
    "Custom Analytics Report",
    "Q1 2026 Performance Review"
)

# Add table of contents
exporter.add_text_slide(
    prs,
    "Table of Contents",
    [
        "Executive Summary",
        "Financial Metrics",
        "User Analytics",
        "Recommendations"
    ]
)

# Add metrics slide
exporter.add_table_slide(
    prs,
    {
        "title": "Executive Summary",
        "data": {
            "Total Revenue": 125430.50,
            "User Growth": 0.15,
            "Customer Retention": 0.94
        }
    }
)

# Add closing slide
exporter.add_text_slide(
    prs,
    "Questions?",
    ["Thank you for your attention"]
)

# Save presentation
prs.save("custom_report.pptx")
```

## Chart Integration

The PPTXExporter integrates with `ChartRenderer` to embed chart images in presentations.

### Basic Chart Integration

```python
from analytics.exporters import PPTXExporter, ChartRenderer

# Create renderer and exporter
chart_renderer = ChartRenderer()
exporter = PPTXExporter()

# Define chart configuration
chart_config = {
    "type": "line",
    "title": "User Growth",
    "data": {
        "labels": ["Q1", "Q2", "Q3", "Q4"],
        "datasets": [{
            "label": "Users",
            "data": [1000, 1500, 2000, 2500]
        }]
    }
}

# Render chart
chart_image = chart_renderer.render_chart(chart_config, "user_growth.png")

# Add to report
report_data = {
    "metadata": {"generated_at": "2026-05-01T12:00:00Z"},
    "sections": [{
        "title": "User Trends",
        "metrics": {},
        "charts": [{
            "title": "Quarterly User Growth",
            "type": "line",
            "image_path": chart_image
        }]
    }]
}

exporter.export_to_pptx(report_data, "report.pptx")
```

### Supported Chart Types

- **Line charts**: Trends over time
- **Bar charts**: Comparisons between categories
- **Pie charts**: Proportional distributions
- **Scatter plots**: Correlation analysis

## Customization

### Presentation Format

The default format is 16:9 (widescreen):
- Width: 10 inches
- Height: 5.625 inches

### Color Scheme

The exporter uses a professional color palette:

- **Primary**: Dark blue-gray (#2c3e50)
- **Secondary**: Blue (#3498db)
- **Accent Red**: #e74c3c
- **Accent Green**: #2ecc71
- **Light Gray**: #ecf0f1
- **Dark Gray**: #7f8c8d

### Typography

- **Slide Titles**: 32pt, bold, primary color
- **Title Slide**: 44pt, bold, primary color
- **Subtitle**: 20pt, dark gray
- **Body Text**: 18pt, primary color
- **Table Headers**: 14pt, bold, white on primary background
- **Table Data**: 12pt, primary color

### Custom Colors

To customize colors, modify the `COLORS` dictionary in `pptx_exporter.py`:

```python
COLORS = {
    'primary': RGBColor(44, 62, 80),      # Your custom color
    'secondary': RGBColor(52, 152, 219),
    # ... etc
}
```

## Troubleshooting

### python-pptx Not Installed

**Problem:** `WARNING: python-pptx not available - PowerPoint exports will use PDF fallback`

**Solution:**
```bash
pip install python-pptx Pillow
```

### Permission Denied Error

**Problem:** `PermissionError: Permission denied writing to output.pptx`

**Solution:** Close the PowerPoint file if it's open, or save to a different location.

### Chart Images Not Appearing

**Problem:** Charts show placeholder text instead of images

**Solutions:**
1. Ensure `image_path` in chart data points to an existing file
2. Install matplotlib for chart rendering: `pip install matplotlib`
3. Verify chart was successfully rendered before adding to presentation

### File Size Too Large

**Problem:** Generated .pptx files are very large

**Solutions:**
1. Compress chart images before embedding
2. Use PNG format instead of high-resolution formats
3. Optimize chart renderer DPI settings

### UTF-8 Encoding Issues (Windows)

**Problem:** Unicode characters not displaying correctly in console output

**Solution:**
```python
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
```

### Fallback to PDF Instead of PowerPoint

**Problem:** Exporter creates .pdf files instead of .pptx

**Cause:** python-pptx is not installed

**Solution:**
```bash
pip install python-pptx
```

### Empty Slides

**Problem:** Slides are created but appear empty

**Cause:** Section data missing `metrics` or `charts` keys

**Solution:** Ensure each section has either metrics or charts:
```python
{
    "title": "Section",
    "metrics": {"Metric": 123},  # Add metrics
    "charts": []                  # Or charts
}
```

## Additional Resources

- [python-pptx Documentation](https://python-pptx.readthedocs.io/)
- [PDFExporter Usage](./PDF_EXPORTER_USAGE.md)
- [ChartRenderer Documentation](./CHART_RENDERER_USAGE.md)
- [Analytics Platform Overview](../README.md)

## Support

For issues or questions:
1. Check this documentation
2. Review test cases in `test_pptx_exporter.py`
3. Check the codebase documentation
