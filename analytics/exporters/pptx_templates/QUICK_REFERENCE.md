# PowerPoint Templates - Quick Reference

One-page reference for developers using the PPTX template system.

## Load Template

```python
from analytics.exporters.pptx_template_loader import PPTXTemplateLoader

loader = PPTXTemplateLoader()
prs = loader.load_template("executive")  # or "technical"
```

## List Templates

```python
templates = loader.list_available_templates()
# Returns: ['executive', 'technical']
```

## Templates Overview

| Template | Slides | Use Case |
|----------|--------|----------|
| `executive` | 6 | High-level summaries, board meetings |
| `technical` | 17 | Detailed analysis, technical reviews |

## Executive Template Structure

```
1. Title Slide          → Update title/period
2. Executive Summary    → 5 key findings
3. Key Metrics          → 4 metric cards
4. Trends & Insights    → Chart + bullets
5. Recommendations      → Prioritized actions
6. Q&A / Contact        → Questions
```

## Technical Template Structure

```
1. Title               9. Session Duration
2. Table of Contents  10. Model Performance
3. Methodology        11. Model Selection
4. Skill Usage        12. Lessons Learned
5. Skill Deep-Dive    13. Workflow Analysis
6. Token Usage        14. Workflow Metrics
7. Cost Analysis      15. Recommendations
8. Session Analytics  16. Appendix
                      17. Contact
```

## Access Slides

```python
# By index (0-based)
title_slide = prs.slides[0]
summary_slide = prs.slides[1]

# Loop through
for i, slide in enumerate(prs.slides):
    print(f"Slide {i+1}: {slide.shapes[0].text if slide.shapes else 'Empty'}")
```

## Update Text

```python
# Find shape with text
for shape in slide.shapes:
    if shape.has_text_frame:
        if "placeholder text" in shape.text:
            shape.text = "Updated text"

# Update paragraph
text_frame = shape.text_frame
text_frame.paragraphs[0].text = "New text"
```

## Add Content

```python
from pptx.util import Inches, Pt

# Add text box
box = slide.shapes.add_textbox(
    Inches(1), Inches(2),      # left, top
    Inches(8), Inches(1)       # width, height
)
box.text_frame.text = "Content"

# Style text
p = box.text_frame.paragraphs[0]
p.font.size = Pt(18)
p.font.bold = True
```

## Insert Chart

```python
import io
import matplotlib.pyplot as plt

# Create chart
fig, ax = plt.subplots(figsize=(6, 4))
ax.bar(['A', 'B', 'C'], [10, 20, 15])

# Save to bytes
img_bytes = io.BytesIO()
fig.savefig(img_bytes, format='png', dpi=150)
img_bytes.seek(0)
plt.close(fig)

# Insert into slide
slide.shapes.add_picture(
    img_bytes,
    Inches(0.8), Inches(1.3),  # position
    width=Inches(5.5)
)
```

## Color Scheme

```python
from pptx.dml.color import RGBColor

loader = PPTXTemplateLoader()

# Available colors
loader.colors['primary']    # Dark blue #2c3e50
loader.colors['secondary']  # Bright blue #3498db
loader.colors['accent']     # Orange #e67e22
loader.colors['success']    # Green #27ae60
loader.colors['warning']    # Yellow #f1c40f
loader.colors['danger']     # Red #e74c3c

# Apply color
shape.fill.fore_color.rgb = loader.colors['primary']
```

## Helper Methods (Internal)

```python
# Available in PPTXTemplateLoader class
loader._add_title_slide(slide, "Title", "Subtitle")
loader._add_content_slide(slide, "Title", ["Bullet 1", "Bullet 2"])
loader._add_chart_slide(slide, "Chart Title")
loader._add_metrics_slide(slide, "Metrics")
loader._add_metric_card(slide, 1, 2, "Label", "123", color)
```

## Save Presentation

```python
prs.save("output.pptx")
prs.save(r"C:\Users\Dannis Seay\Downloads\report.pptx")
```

## Common Patterns

### Pattern 1: Load & Populate
```python
prs = loader.load_template("executive")
# Update slides with data
prs.save("output.pptx")
```

### Pattern 2: Create Custom
```python
prs = loader.create_executive_template()
# Customize before saving
prs.save("custom.pptx")
```

### Pattern 3: With PPTXExporter
```python
from analytics.exporters.pptx_exporter import PPTXExporter

exporter = PPTXExporter()
template = loader.load_template("executive")
exporter.export_to_pptx(data, "output.pptx", template=template)
```

## Regenerate Templates

```bash
cd C:\Users\Dannis Seay\builds\dream-studio
py analytics/exporters/pptx_template_loader.py
```

## Run Examples

```bash
py analytics/exporters/pptx_templates/example_usage.py
```

## Slide Dimensions

- Width: 10 inches
- Height: 5.625 inches
- Aspect ratio: 16:9

## Common Sizes

```python
# Standard margin
margin = Inches(0.5)

# Title area
title_height = Inches(0.6)

# Content area
content_height = Inches(3.8)

# Metric card
card_width = Inches(4)
card_height = Inches(1.5)
```

## Font Sizes

```python
# Title slide
title = Pt(44)
subtitle = Pt(24)

# Content slides
slide_title = Pt(32)
body_text = Pt(18)
small_text = Pt(14)

# Metrics
metric_value = Pt(36)
metric_label = Pt(16)

# Footer
footer = Pt(10)
```

## Find Shapes

```python
# Debug: List all shapes
for i, slide in enumerate(prs.slides, 1):
    print(f"\nSlide {i}:")
    for shape in slide.shapes:
        print(f"  {shape.name}")
        if shape.has_text_frame:
            print(f"    Text: {shape.text[:30]}...")
```

## Replace Placeholder

```python
# Find and replace
for shape in slide.shapes:
    if shape.has_text_frame:
        text = shape.text
        if "[PLACEHOLDER]" in text:
            shape.text = text.replace("[PLACEHOLDER]", "Actual Value")
```

## Add New Slide

```python
# Use blank layout
blank = prs.slide_layouts[6]
new_slide = prs.slides.add_slide(blank)

# Add content using helper methods
loader._add_title_slide(new_slide, "Title", "Subtitle")
```

## Error Handling

```python
try:
    prs = loader.load_template("nonexistent")
except FileNotFoundError as e:
    print(f"Template not found: {e}")
    # Fallback to creating new
    prs = loader.create_executive_template()
```

## Tips

1. **Always use blank layout** (index 6) for full control
2. **Use Inches()** for positioning, not pixels
3. **Save charts at 150 DPI** for good quality
4. **Test on PowerPoint** after generation
5. **Keep bullets under 80 chars** for readability
6. **Use consistent colors** from loader.colors
7. **Add slide numbers** in footer for navigation

## Documentation

- `README.md` - Full documentation
- `INTEGRATION_GUIDE.md` - PPTXExporter integration
- `TEMPLATE_SUMMARY.md` - Build summary
- `example_usage.py` - Working examples

## Support

Email: dannis.seay@twinrootsllc.com
