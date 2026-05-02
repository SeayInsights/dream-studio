# 📊 Analytics Dashboard Generator

> **⚠️ DEPRECATION NOTICE**  
> This static dashboard generator is deprecated and will be removed in 30 days.  
> Please use the new **real-time dashboard** instead:
> 
> ```bash
> cd analytics
> python -m api.main
> # Navigate to http://localhost:8000/dashboard
> ```
> 
> The new dashboard includes WebSocket streaming, real-time alerts, ML insights, and responsive mobile design.

---

Production-ready dashboard generator for dream-studio analytics platform.

## Features

- **Beautiful UI**: Modern, responsive design with gradient backgrounds
- **Interactive Charts**: Chart.js powered visualizations
  - Session timeline (line chart)
  - Top skills by usage (bar chart)
  - Model distribution (doughnut chart)
  - Token cost over time (line chart)
- **Key Metrics**: Total sessions, success rate, token usage, costs
- **AI-Powered Insights**: Automatic detection of strengths, issues, opportunities
- **Strategic Recommendations**: Prioritized actionable recommendations
- **One-Command Generation**: Single command creates complete standalone HTML

## Quick Start

```bash
# Generate dashboard for last 30 days
python scripts/generate-dashboard.py

# Last 90 days
python scripts/generate-dashboard.py 90

# Custom output path
python scripts/generate-dashboard.py 30 my-dashboard.html
```

## Programmatic Usage

```python
from analytics.generators import ProductionDashboard

# Create dashboard
dashboard = ProductionDashboard()
path = dashboard.generate(days=30, output_path="dashboard.html")

print(f"Dashboard saved to: {path}")
```

## Output

Generates a single, self-contained HTML file with:
- All CSS embedded (no external stylesheets)
- All JavaScript embedded (only Chart.js CDN dependency)
- All data embedded (no API calls needed)
- Fully portable (works offline after first load)

## Requirements

- Python 3.8+
- dream-studio analytics data in `~/.dream-studio/studio.db`
- Internet connection (for Chart.js CDN on first load)

## Architecture

```
ProductionDashboard
├── _collect_metrics()      # Pull data from collectors
├── _analyze_metrics()       # Run analyzers
├── _generate_insights()     # Generate insights + recommendations
├── _generate_charts()       # Prepare chart data
└── _build_html()           # Assemble final HTML
```

## Charts Included

1. **Session Timeline**: Activity over time with trend line
2. **Top Skills**: Bar chart of most-used skills
3. **Model Distribution**: Pie chart of model usage
4. **Token Cost**: Cost tracking over time

## Insights Engine

Automatically detects:
- ✅ **Strengths**: High-performing skills, cost efficiency, positive trends
- ⚠️ **Issues**: Underperforming skills, anomalies, declining metrics
- 💡 **Opportunities**: Optimization potential, underutilized features
- 🎯 **Recommendations**: Prioritized actions with ROI estimates

## Customization

To add custom charts, edit `_generate_charts()`:

```python
def _generate_charts(self, metrics, analysis):
    charts = {}

    charts["my_custom_chart"] = {
        "type": "bar",  # line, bar, doughnut, etc.
        "title": "My Custom Metric",
        "data": {
            "labels": ["A", "B", "C"],
            "datasets": [{
                "label": "Values",
                "data": [10, 20, 30]
            }]
        }
    }

    return charts
```

## Performance

- Generation time: ~2-5 seconds (depends on data volume)
- Output size: ~100-500 KB (embedded data + charts)
- Browser load time: < 1 second

## Troubleshooting

**Error: "no such table: raw_sessions"**
- No analytics data exists yet. Run dream-studio to generate telemetry.

**Charts not rendering**
- Check internet connection (Chart.js CDN required)
- Open browser console for errors

**Missing metrics**
- Ensure all collectors have data for the time period
- Try increasing the `days` parameter

## Future Enhancements

- [ ] Export to PDF
- [ ] Email delivery
- [ ] Real-time updates (WebSocket)
- [ ] Custom date ranges
- [ ] Multiple dashboard templates
- [ ] Dark mode
- [ ] Drill-down interactivity
