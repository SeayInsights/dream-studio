# PowerPoint Templates for Dream-Studio Analytics

Professional PowerPoint templates for analytics exports, created with python-pptx.

## Available Templates

### 1. Executive Template (`executive.pptx`)
**Purpose**: High-level summary for executives and stakeholders  
**Slides**: 6 slides  
**Audience**: Non-technical leadership, clients, stakeholders

**Structure**:
1. **Title Slide** - Report title and period
2. **Executive Summary** - Key findings and highlights (5 bullet points)
3. **Key Metrics Dashboard** - 4 large metric cards with values
4. **Trends & Insights** - Chart area + insight bullets
5. **Recommendations** - Prioritized action items
6. **Q&A / Contact** - Questions and contact information

**Best for**:
- Board presentations
- Client reports
- Quarterly reviews
- Executive summaries

### 2. Technical Template (`technical.pptx`)
**Purpose**: Detailed analysis for technical teams  
**Slides**: 17 slides  
**Audience**: Developers, analysts, technical stakeholders

**Structure**:
1. **Title Slide** - Report title
2. **Table of Contents** - Navigation
3. **Methodology & Data Sources** - How data was collected
4. **Skill Usage Overview** - Chart + insights
5. **Skill Performance Deep-Dive** - Detailed analysis
6. **Token Usage Analysis** - Token metrics and trends
7. **Cost Analysis** - Cost breakdown and metrics
8. **Session Analytics** - Session-level analysis
9. **Session Duration Patterns** - Duration trends
10. **Model Performance Comparison** - Model metrics
11. **Model Selection Patterns** - Usage patterns by model
12. **Lessons Learned** - Key takeaways
13. **Workflow Analysis** - Workflow patterns
14. **Workflow Efficiency Metrics** - Efficiency data
15. **Detailed Recommendations** - Technical recommendations
16. **Appendix: Methodology Details** - Technical details
17. **Contact & Questions** - Q&A

**Best for**:
- Technical deep-dives
- Sprint retrospectives
- Performance analysis
- Detailed audit reports

## Color Scheme

All templates use a professional color palette:

| Color | Hex | RGB | Usage |
|-------|-----|-----|-------|
| Primary (Dark Blue) | `#2c3e50` | `44, 62, 80` | Titles, headers |
| Secondary (Bright Blue) | `#3498db` | `52, 152, 219` | Accents, links |
| Accent (Orange) | `#e67e22` | `230, 126, 34` | Highlights, CTAs |
| Success (Green) | `#27ae60` | `39, 174, 96` | Positive metrics |
| Warning (Yellow) | `#f1c40f` | `241, 196, 15` | Warnings, attention |
| Danger (Red) | `#e74c3c` | `231, 76, 60` | Errors, critical items |
| Light Gray | `#ecf0f1` | `236, 240, 241` | Backgrounds |
| Dark Gray | `#34495e` | `52, 73, 94` | Body text |

## Usage

### Basic Usage

```python
from analytics.exporters.pptx_template_loader import PPTXTemplateLoader

# Load a template
loader = PPTXTemplateLoader()
prs = loader.load_template("executive")

# Work with the presentation
# ... add your data to slides ...

# Save
prs.save("output.pptx")
```

### List Available Templates

```python
loader = PPTXTemplateLoader()
templates = loader.list_available_templates()
print(f"Available: {', '.join(templates)}")
# Output: Available: executive, technical
```

### Integration with PPTXExporter

```python
from analytics.exporters.pptx_exporter import PPTXExporter
from analytics.exporters.pptx_template_loader import PPTXTemplateLoader

# Load template
loader = PPTXTemplateLoader()
template = loader.load_template("executive")

# Export with template
exporter = PPTXExporter()
exporter.export_to_pptx(
    report_data,
    "dream_studio_report.pptx",
    template=template
)
```

## Customizing Templates

### Method 1: Edit Existing Templates (Recommended)

1. Open the template file in PowerPoint:
   - `executive.pptx` or `technical.pptx`

2. Make your changes:
   - Update colors (Design > Colors > Customize Colors)
   - Change fonts (Design > Fonts > Customize Fonts)
   - Modify slide layouts
   - Add company logo
   - Update footer text

3. Save the file with the same name to replace the template

### Method 2: Create New Template Programmatically

Add a new method to `PPTXTemplateLoader` class:

```python
def create_custom_template(self) -> Presentation:
    """Create custom template."""
    prs = Presentation()
    prs.slide_width = Inches(10)
    prs.slide_height = Inches(5.625)

    # Add slides using helper methods
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    self._add_title_slide(slide, "Custom Title", "Subtitle")

    # Add more slides...

    return prs
```

Then generate it:

```python
loader = PPTXTemplateLoader()
custom_prs = loader.create_custom_template()
custom_prs.save("analytics/exporters/pptx_templates/custom.pptx")
```

### Method 3: Modify Color Scheme

Edit the `colors` dictionary in `PPTXTemplateLoader.__init__()`:

```python
self.colors = {
    'primary': RGBColor(10, 50, 100),    # Your primary color
    'secondary': RGBColor(100, 150, 200), # Your secondary color
    # ... etc
}
```

Then regenerate templates:

```bash
py analytics/exporters/pptx_template_loader.py
```

## Template Components

### Helper Methods Available

The `PPTXTemplateLoader` class provides these helper methods for building slides:

- `_add_title_slide(slide, title, subtitle)` - Title slide with branding
- `_add_content_slide(slide, title, bullets)` - Content with bullet points
- `_add_chart_slide(slide, title)` - Chart placeholder + insights
- `_add_metrics_slide(slide, title)` - 2x2 grid of metric cards
- `_add_metric_card(slide, x, y, title, value, color)` - Single metric card
- `_add_toc_slide(slide)` - Table of contents
- `_add_qa_slide(slide)` - Q&A / contact slide
- `_add_footer(slide, slide_num, total_slides)` - Slide number footer

### Creating Custom Slides

```python
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

# Add a custom slide
slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank layout

# Add title
title_box = slide.shapes.add_textbox(
    Inches(0.5), Inches(0.3), Inches(9), Inches(0.6)
)
title_frame = title_box.text_frame
title_frame.text = "My Custom Slide"
p = title_frame.paragraphs[0]
p.font.size = Pt(32)
p.font.bold = True
p.font.color.rgb = RGBColor(44, 62, 80)  # Primary color

# Add content...
```

## Slide Dimensions

All templates use 16:9 aspect ratio:
- **Width**: 10 inches (Inches(10))
- **Height**: 5.625 inches (Inches(5.625))

Common measurements:
- Standard margin: `Inches(0.5)`
- Title height: `Inches(0.6)`
- Content area: `Inches(3.8)` to `Inches(4)`
- Metric card: `Inches(4)` wide × `Inches(1.5)` tall

## Fonts

Default fonts used:
- **Calibri** (primary)
- **Arial** (fallback)

Font sizes:
- Title slide: 44pt (title), 24pt (subtitle)
- Slide title: 32pt
- Body text: 18pt
- Metric value: 36pt
- Metric label: 16pt
- Footer: 10pt

## Regenerating Templates

To regenerate both templates from code:

```bash
cd C:\Users\Dannis Seay\builds\dream-studio
py analytics/exporters/pptx_template_loader.py
```

This will overwrite existing templates with freshly generated versions.

## Best Practices

1. **Keep it simple**: Don't overcrowd slides with too much data
2. **One idea per slide**: Each slide should have a clear focus
3. **Use visuals**: Charts and metrics are more impactful than text
4. **Consistent styling**: Use the template colors and fonts throughout
5. **Test on projector**: Colors that look good on screen may not project well
6. **Accessibility**: Ensure sufficient contrast for readability
7. **File size**: Optimize images before adding to presentations

## Troubleshooting

### Template not found
```python
# Check available templates
loader = PPTXTemplateLoader()
print(loader.list_available_templates())
```

### Colors not applying
Ensure you're using `RGBColor` objects:
```python
from pptx.dml.color import RGBColor
shape.fill.fore_color.rgb = RGBColor(44, 62, 80)
```

### Slide layout issues
Use blank layout (index 6) for full control:
```python
slide = prs.slides.add_slide(prs.slide_layouts[6])
```

## Examples

### Executive Report Example

```python
from analytics.exporters.pptx_template_loader import PPTXTemplateLoader

loader = PPTXTemplateLoader()
prs = loader.load_template("executive")

# Customize slide 2 (Executive Summary)
slide = prs.slides[1]
# Find text boxes and update content...

# Customize slide 3 (Key Metrics)
slide = prs.slides[2]
# Update metric values...

prs.save("Q1_2026_Executive_Report.pptx")
```

### Technical Report Example

```python
loader = PPTXTemplateLoader()
prs = loader.load_template("technical")

# Add charts, tables, detailed data to technical slides
# Slides 3-15 have chart and metric placeholders

prs.save("Dream_Studio_Technical_Analysis.pptx")
```

## Support

For questions or issues:
- Email: dannis.seay@twinrootsllc.com
- Check `pptx_template_loader.py` for implementation details
- See `pptx_exporter.py` for integration examples
