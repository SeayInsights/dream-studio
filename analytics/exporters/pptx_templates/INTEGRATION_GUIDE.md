# PPTX Template Integration Guide

How to integrate PowerPoint templates with the dream-studio analytics PPTXExporter.

## Quick Start

```python
from analytics.exporters.pptx_exporter import PPTXExporter
from analytics.exporters.pptx_template_loader import PPTXTemplateLoader

# 1. Load template
loader = PPTXTemplateLoader()
template = loader.load_template("executive")  # or "technical"

# 2. Create exporter with template
exporter = PPTXExporter()
exporter.export_to_pptx(
    report_data,
    "output.pptx",
    template=template
)
```

## Integration Patterns

### Pattern 1: Template-First Export

Use when you want the template structure to drive the report layout.

```python
from analytics.exporters.pptx_template_loader import PPTXTemplateLoader
from pptx.util import Inches, Pt

# Load template
loader = PPTXTemplateLoader()
prs = loader.load_template("executive")

# Populate slide 2: Executive Summary
slide = prs.slides[1]
for shape in slide.shapes:
    if shape.has_text_frame:
        text_frame = shape.text_frame
        if "Key finding" in text_frame.text:
            # Replace placeholder with actual data
            for i, finding in enumerate(report_data['key_findings'], 1):
                if i <= len(text_frame.paragraphs):
                    text_frame.paragraphs[i-1].text = finding

# Populate slide 3: Key Metrics
slide = prs.slides[2]
metrics = report_data['summary_metrics']
# Update metric cards (implementation depends on shape IDs)

# Save
prs.save("executive_report.pptx")
```

### Pattern 2: Data-First Export with Template Styling

Use when you want to generate slides from data but apply template styling.

```python
from analytics.exporters.pptx_exporter import PPTXExporter
from analytics.exporters.pptx_template_loader import PPTXTemplateLoader

loader = PPTXTemplateLoader()
exporter = PPTXExporter()

# Generate presentation from data
prs = exporter.create_presentation_from_data(report_data)

# Apply template styling
styled_prs = loader.apply_template(prs, "executive")

# Save
styled_prs.save("styled_report.pptx")
```

### Pattern 3: Hybrid Approach

Use template for structure, insert custom data slides.

```python
loader = PPTXTemplateLoader()
prs = loader.load_template("technical")

# Insert custom data slide after TOC (slide 1)
from analytics.exporters.chart_builder import ChartBuilder

blank_layout = prs.slide_layouts[6]
new_slide = prs.slides.add_slide(blank_layout)
new_slide._element.addprevious(prs.slides[2]._element)  # Insert at position 2

# Add chart to new slide
chart_builder = ChartBuilder()
chart_img = chart_builder.create_skill_usage_chart(report_data['skills'])
new_slide.shapes.add_picture(
    chart_img,
    Inches(0.8), Inches(1.3),
    width=Inches(5.5)
)

prs.save("hybrid_report.pptx")
```

## Modifying PPTXExporter for Template Support

### Option 1: Add Template Parameter

Modify `pptx_exporter.py` to accept template as parameter:

```python
class PPTXExporter:
    def export_to_pptx(
        self,
        report_data: Dict,
        output_path: str,
        template: Optional[Presentation] = None
    ) -> str:
        """
        Export analytics report to PowerPoint.

        Args:
            report_data: Analytics data to export
            output_path: Path to save .pptx file
            template: Optional template presentation to use

        Returns:
            Path to saved file
        """
        if template:
            prs = template
            # Populate template slides with data
            self._populate_template(prs, report_data)
        else:
            # Create presentation from scratch
            prs = self._create_presentation(report_data)

        prs.save(output_path)
        return output_path

    def _populate_template(
        self,
        prs: Presentation,
        report_data: Dict
    ):
        """Populate template slides with actual data."""
        # Slide 2: Executive Summary
        if len(prs.slides) > 1:
            self._populate_executive_summary(prs.slides[1], report_data)

        # Slide 3: Key Metrics
        if len(prs.slides) > 2:
            self._populate_key_metrics(prs.slides[2], report_data)

        # Add more population logic...

    def _populate_executive_summary(self, slide, report_data):
        """Populate executive summary slide."""
        findings = report_data.get('key_findings', [])

        for shape in slide.shapes:
            if shape.has_text_frame:
                text_frame = shape.text_frame
                # Replace placeholder bullets with actual findings
                if len(findings) > 0 and len(text_frame.paragraphs) >= len(findings):
                    for i, finding in enumerate(findings):
                        text_frame.paragraphs[i].text = finding
```

### Option 2: Template-Specific Export Method

Add dedicated method for template-based exports:

```python
class PPTXExporter:
    def export_with_template(
        self,
        report_data: Dict,
        output_path: str,
        template_name: str = "executive"
    ) -> str:
        """
        Export using a specific template.

        Args:
            report_data: Analytics data
            output_path: Output file path
            template_name: Template to use ('executive' or 'technical')

        Returns:
            Path to saved file
        """
        from analytics.exporters.pptx_template_loader import PPTXTemplateLoader

        loader = PPTXTemplateLoader()
        prs = loader.load_template(template_name)

        # Populate based on template type
        if template_name == "executive":
            self._populate_executive_template(prs, report_data)
        elif template_name == "technical":
            self._populate_technical_template(prs, report_data)

        prs.save(output_path)
        return output_path

    def _populate_executive_template(self, prs, report_data):
        """Populate executive template with data."""
        # Slide 1: Title (update date range)
        # Slide 2: Executive Summary
        # Slide 3: Key Metrics
        # Slide 4: Trends
        # Slide 5: Recommendations
        # Slide 6: Q&A
        pass

    def _populate_technical_template(self, prs, report_data):
        """Populate technical template with data."""
        # Populate all 17 slides with detailed data
        pass
```

## Data Mapping Guide

### Executive Template Data Requirements

```python
report_data = {
    'metadata': {
        'title': 'Q1 2026 Analytics Report',
        'period': 'Jan 1 - Mar 31, 2026',
        'generated_at': '2026-05-01'
    },
    'key_findings': [
        'Finding 1: Total sessions increased 25% QoQ',
        'Finding 2: Average token usage decreased 15%',
        'Finding 3: Most used skill: dream-studio:core plan',
        'Finding 4: Cost per session reduced by $0.05',
        'Finding 5: Peak usage hours: 2-4 PM EST'
    ],
    'summary_metrics': {
        'total_sessions': 1234,
        'total_tokens': 5678901,
        'total_cost': '$123.45',
        'avg_session_duration': '15.3 min'
    },
    'trends': {
        'chart_data': {...},  # For chart generation
        'insights': [
            'Token usage trending down',
            'Session duration stable',
            'Cost efficiency improving'
        ]
    },
    'recommendations': [
        'Priority 1: Implement token caching for repeated queries',
        'Priority 2: Optimize prompt templates for common tasks',
        'Priority 3: Schedule batch processing for off-peak hours'
    ]
}
```

### Technical Template Data Requirements

```python
report_data = {
    'metadata': {...},
    'methodology': {
        'data_sources': ['SQLite analytics DB', 'Session logs', 'API metrics'],
        'analysis_period': '30 days',
        'frameworks': ['pandas', 'matplotlib']
    },
    'skill_usage': {
        'by_skill': {
            'dream-studio:core': {'calls': 150, 'tokens': 45000, 'cost': 12.50},
            'dream-studio:quality': {'calls': 75, 'tokens': 22500, 'cost': 6.25},
            # ...
        },
        'trends': [...],
        'insights': [...]
    },
    'token_usage': {
        'total_input': 1234567,
        'total_output': 890123,
        'cache_hits': 15000,
        'by_model': {...}
    },
    'cost_analysis': {
        'total': 123.45,
        'by_model': {...},
        'by_skill': {...},
        'trends': [...]
    },
    'session_analytics': {
        'total': 1234,
        'avg_duration': 915,  # seconds
        'duration_distribution': {...},
        'patterns': [...]
    },
    'model_performance': {
        'sonnet': {'usage': 80, 'avg_tokens': 5000, 'cost': 98.76},
        'haiku': {'usage': 15, 'avg_tokens': 2000, 'cost': 12.34},
        'opus': {'usage': 5, 'avg_tokens': 8000, 'cost': 12.35}
    },
    'lessons_learned': [...],
    'workflow_analysis': {...},
    'recommendations': [...]
}
```

## Shape Identification

To update specific shapes in templates, you need to identify them:

```python
# List all shapes in a slide
for slide in prs.slides:
    print(f"Slide {prs.slides.index(slide) + 1}:")
    for shape in slide.shapes:
        print(f"  - {shape.name}: {shape.shape_type}")
        if shape.has_text_frame:
            print(f"    Text: {shape.text_frame.text[:50]}...")

# Update specific shape by name
for shape in slide.shapes:
    if "metric" in shape.name.lower():
        # Update this metric shape
        pass
```

## Chart Integration

### Inserting Matplotlib Charts

```python
import io
import matplotlib.pyplot as plt

# Create chart
fig, ax = plt.subplots(figsize=(6, 4))
ax.bar(['Skill A', 'Skill B', 'Skill C'], [100, 150, 120])
ax.set_title('Skill Usage')

# Save to bytes
img_bytes = io.BytesIO()
fig.savefig(img_bytes, format='png', dpi=150, bbox_inches='tight')
img_bytes.seek(0)
plt.close(fig)

# Insert into slide
from pptx.util import Inches
slide.shapes.add_picture(
    img_bytes,
    Inches(0.8), Inches(1.3),
    width=Inches(5.5)
)
```

### Replacing Chart Placeholder

```python
# Find chart placeholder shape
chart_placeholder = None
for shape in slide.shapes:
    if shape.has_text_frame and "[CHART PLACEHOLDER]" in shape.text:
        chart_placeholder = shape
        break

if chart_placeholder:
    # Get placeholder position and size
    left = chart_placeholder.left
    top = chart_placeholder.top
    width = chart_placeholder.width
    height = chart_placeholder.height

    # Remove placeholder
    sp = chart_placeholder._element
    sp.getparent().remove(sp)

    # Insert chart at same position
    slide.shapes.add_picture(
        img_bytes,
        left, top,
        width=width
    )
```

## Best Practices

1. **Template Selection**:
   - Use `executive` for high-level reports (< 10 slides)
   - Use `technical` for detailed analysis (10+ slides)
   - Create custom templates for specialized reports

2. **Data Validation**:
   - Validate all required data fields before populating
   - Provide default values for missing data
   - Log warnings for incomplete data

3. **Chart Generation**:
   - Generate charts at 150 DPI for good quality
   - Use consistent color scheme matching template
   - Save charts as PNG (better than JPEG for charts)

4. **Text Formatting**:
   - Keep bullet points concise (< 80 chars)
   - Use consistent font sizes from template
   - Don't override template colors unless necessary

5. **Testing**:
   - Test on both Windows and Mac PowerPoint
   - Verify charts render correctly
   - Check slide aspect ratio (16:9)

6. **Performance**:
   - Cache template loading if generating multiple reports
   - Generate charts in parallel when possible
   - Compress images before inserting

## Troubleshooting

### Shapes Not Updating

```python
# Debug: Print all shape text
for shape in slide.shapes:
    if shape.has_text_frame:
        print(f"{shape.name}: {shape.text}")
```

### Charts Not Appearing

```python
# Verify image bytes are valid
img_bytes.seek(0)
from PIL import Image
img = Image.open(img_bytes)
print(f"Image size: {img.size}, format: {img.format}")
```

### Template Not Found

```python
# Check template path
loader = PPTXTemplateLoader()
print(f"Template dir: {loader.template_dir}")
print(f"Templates: {loader.list_available_templates()}")
```

## Example: Complete Executive Report

```python
from analytics.exporters.pptx_template_loader import PPTXTemplateLoader
from analytics.exporters.pptx_exporter import PPTXExporter
from analytics.analytics_db import AnalyticsDB
from datetime import datetime, timedelta

# 1. Load data from database
db = AnalyticsDB()
end_date = datetime.now()
start_date = end_date - timedelta(days=30)

report_data = db.generate_report_data(start_date, end_date)

# 2. Load template
loader = PPTXTemplateLoader()
prs = loader.load_template("executive")

# 3. Update title slide
title_slide = prs.slides[0]
for shape in title_slide.shapes:
    if shape.has_text_frame:
        if "[Report Period]" in shape.text:
            shape.text = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"

# 4. Populate remaining slides
exporter = PPTXExporter()
exporter._populate_executive_template(prs, report_data)

# 5. Save
output_path = f"Executive_Report_{datetime.now().strftime('%Y%m%d')}.pptx"
prs.save(output_path)
print(f"Report saved: {output_path}")
```

## Next Steps

1. **Update PPTXExporter**: Add template support to existing exporter
2. **Create Population Methods**: Implement `_populate_*` methods for each slide type
3. **Add Chart Builder**: Create helper to generate and insert charts
4. **Test Integration**: Generate sample reports from real analytics data
5. **Document Custom Templates**: Guide for creating project-specific templates
