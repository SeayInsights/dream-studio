# Power BI Integration Guide

## Overview

The `PowerBIExporter` exports Dream Studio analytics reports as Power BI-compatible datasets. It creates a directory structure with CSV files, schema metadata, and a connection file that can be opened directly in Power BI Desktop.

## Quick Start

```python
from analytics.core.reports import ReportGenerator
from analytics.exporters import PowerBIExporter

# Generate analytics report
generator = ReportGenerator()
report = generator.generate_report("detailed")

# Export to Power BI dataset
exporter = PowerBIExporter()
success, path = exporter.export_dataset(report, "powerbi_export/")

# Open dataset.pbids file in Power BI Desktop
```

## Output Structure

When you export a dataset, the following files are created:

```
powerbi_export/
├── data/
│   ├── skills.csv         # Skill performance data
│   ├── tokens.csv         # Token usage and costs
│   ├── sessions.csv       # Session activity
│   ├── models.csv         # Model usage statistics
│   ├── lessons.csv        # Captured lessons
│   ├── workflows.csv      # Workflow execution data
│   └── date.csv           # Date dimension for time intelligence
├── schema.json            # Table definitions, relationships, measures
├── dataset.pbids          # Power BI connection file
└── README.txt             # Usage instructions
```

## Data Model

### Tables

#### Skills
| Column | Type | Description |
|--------|------|-------------|
| skill_id | string (key) | Unique skill identifier |
| skill_name | string | Display name |
| invocations | integer | Number of times invoked |
| success_rate | decimal | Success rate (0.0 - 1.0) |

#### Tokens
| Column | Type | Description |
|--------|------|-------------|
| date | date | Usage date |
| token_count | integer | Number of tokens |
| cost_usd | decimal | Cost in USD |
| model | string | Model name |

#### Sessions
| Column | Type | Description |
|--------|------|-------------|
| session_id | string (key) | Unique session identifier |
| date | date | Session date |
| duration_minutes | integer | Session duration |
| project | string | Project name |

#### Models
| Column | Type | Description |
|--------|------|-------------|
| model_name | string (key) | Model identifier |
| usage_count | integer | Number of times used |
| total_tokens | integer | Total tokens consumed |

#### Lessons
| Column | Type | Description |
|--------|------|-------------|
| lesson_id | string (key) | Unique lesson identifier |
| category | string | Lesson category |
| description | string | Lesson content |
| created_at | datetime | Timestamp |

#### Workflows
| Column | Type | Description |
|--------|------|-------------|
| workflow_id | string (key) | Unique workflow identifier |
| workflow_name | string | Display name |
| executions | integer | Number of executions |
| avg_duration | decimal | Average duration |

#### Date (Dimension Table)
| Column | Type | Description |
|--------|------|-------------|
| date | date (key) | Calendar date |
| year | integer | Year (YYYY) |
| quarter | string | Quarter (Q1-Q4) |
| month | string | Month name |
| month_number | integer | Month (1-12) |
| day | integer | Day of month |
| day_of_week | string | Weekday name |
| day_of_year | integer | Day of year (1-366) |

### Relationships

```
Sessions.date → Date.date (many-to-one)
Tokens.date → Date.date (many-to-one)
```

### Suggested DAX Measures

The exporter includes these predefined measures in `schema.json`:

```dax
Total Tokens = SUM(Tokens[token_count])
Total Cost USD = SUM(Tokens[cost_usd])
Avg Success Rate = AVERAGE(Skills[success_rate])
Total Sessions = COUNTROWS(Sessions)
Avg Session Duration = AVERAGE(Sessions[duration_minutes])
Total Skill Invocations = SUM(Skills[invocations])
```

You can add these measures manually in Power BI Desktop or copy from `schema.json`.

### Time Hierarchy

The Date table supports a standard time hierarchy:
- Year
- Quarter
- Month
- Date

## Power BI Desktop Workflow

### Option 1: Open Connection File (Recommended)

1. Navigate to the export directory
2. Double-click `dataset.pbids`
3. Power BI Desktop opens and loads all CSV files
4. Create visuals using imported data

### Option 2: Manual Import

1. Open Power BI Desktop
2. Get Data → Text/CSV
3. Navigate to `data/` folder
4. Select all CSV files
5. Load all tables
6. Create relationships manually (see schema.json)

## Suggested Visuals

### Executive Dashboard

**Key Metrics (Cards)**
- Total Tokens
- Total Cost USD
- Avg Success Rate
- Total Sessions

**Charts**
- Token usage over time (Line Chart: Date → Total Tokens)
- Cost trend (Line Chart: Date → Total Cost USD)
- Top Skills (Bar Chart: skill_name → invocations)
- Model distribution (Pie Chart: model_name → usage_count)

### Performance Dashboard

**Charts**
- Success rate by skill (Bar Chart: skill_name → success_rate)
- Session duration trend (Line Chart: Date → Avg Session Duration)
- Workflow performance (Table: workflow_name, executions, avg_duration)
- Model token comparison (Stacked Bar: model_name → token_count by date)

### Cost Analysis Dashboard

**Charts**
- Daily cost trend (Line Chart: Date → Total Cost USD)
- Cost by model (Pie Chart: model → cost_usd)
- Cost per session (Calculated Column: cost / sessions)
- Budget burn rate (Running Total: Total Cost USD)

## Advanced Usage

### Custom Report Export

```python
from analytics.core.reports import ReportGenerator
from analytics.exporters import PowerBIExporter

# Generate custom report focused on costs
generator = ReportGenerator()

template = {
    'sections': [
        {
            'title': 'Cost Analysis',
            'metrics': [
                'tokens.total_cost_usd',
                'tokens.by_model',
                'tokens.daily_average'
            ]
        }
    ]
}

report = generator.generate_report(
    report_type="custom",
    config={
        "date_range": ("2026-04-01", "2026-04-30"),
        "template": template
    }
)

# Export to Power BI
exporter = PowerBIExporter()
success, path = exporter.export_dataset(report, "cost_analysis_powerbi/")
```

### Inspect Schema Before Export

```python
exporter = PowerBIExporter()
data_model = exporter.create_data_model(report)

# View tables
for table in data_model['tables']:
    print(f"{table['name']}: {len(table['rows'])} rows")

# View measures
for measure in data_model['measures']:
    print(f"{measure['name']}: {measure['expression']}")
```

### Programmatic Schema Access

```python
import json
from pathlib import Path

# Read exported schema
schema_path = Path("powerbi_export/schema.json")
with open(schema_path, 'r') as f:
    schema = json.load(f)

# Access table definitions
tables = schema['tables']
relationships = schema['relationships']
measures = schema['measures']
```

## Troubleshooting

### CSV Files Not Loading

**Issue**: Power BI can't find CSV files

**Solution**: Use the `.pbids` connection file instead of manually importing. The connection file uses absolute paths.

### Incorrect Data Types

**Issue**: Power BI interprets numbers as text

**Solution**: Check `schema.json` for correct column types. Power BI should auto-detect types, but you can manually set them in Power BI Desktop:
1. Open Power Query Editor
2. Select column
3. Transform → Data Type → Choose correct type

### Missing Relationships

**Issue**: Relationships not created automatically

**Solution**: Create relationships manually in Power BI Desktop:
1. Click Model view
2. Drag from source column to target column
3. Set cardinality (usually Many-to-One)

Refer to `schema.json` for the correct relationships.

### Empty Tables

**Issue**: Some tables have no data

**Solution**: This is expected if the report doesn't contain data for that section. Empty tables are created with fallback rows to maintain schema consistency.

### Date Format Issues

**Issue**: Dates not recognized as dates

**Solution**: Dates are exported in ISO format (YYYY-MM-DD). If Power BI doesn't auto-detect:
1. Open Power Query Editor
2. Select date column
3. Transform → Data Type → Date

## File Locations

Per Dream Studio conventions:
- Export datasets to `C:\Users\<username>\Downloads\` for non-code files
- Datasets are standalone and don't need to be in the project directory

## Integration with Other Exporters

The PowerBIExporter complements other exporters:

| Exporter | Use Case |
|----------|----------|
| PowerBIExporter | Interactive dashboards, executive reporting, time-series analysis |
| ExcelExporter | Detailed tables, offline analysis, sharing with non-Power BI users |
| PDFExporter | Static reports, printable summaries, archival |
| PPTXExporter | Presentations, stakeholder updates |

You can export the same report to multiple formats:

```python
report = generator.generate_report("detailed")

# Export to Power BI for dashboards
powerbi_exporter.export_dataset(report, "powerbi/")

# Export to Excel for detailed analysis
excel_exporter.export_to_excel(report, "analysis.xlsx")

# Export to PDF for archival
pdf_exporter.export_to_pdf(report, "report.pdf")
```

## Performance Considerations

### Large Datasets

For date ranges > 90 days, consider:
1. Export by month and combine in Power BI
2. Use DirectQuery mode instead of Import (requires SQL database)
3. Pre-aggregate data before export

### Refresh Strategy

Power BI datasets are static snapshots. To update:
1. Re-export from Dream Studio
2. Overwrite existing files
3. Refresh in Power BI Desktop (Home → Refresh)

For automated refresh, consider:
- Scheduled Python script to export daily
- Power BI Gateway for on-premises refresh
- Power BI Service scheduled refresh (requires cloud data source)

## Future Enhancements

Potential future improvements:
- Direct database export (SQL Server, PostgreSQL)
- Incremental refresh support
- Composite models (mix Import and DirectQuery)
- Row-level security (RLS) definitions
- Custom themes and report templates
- Automated Power BI Service publish

## References

- [Power BI Documentation](https://docs.microsoft.com/en-us/power-bi/)
- [DAX Function Reference](https://docs.microsoft.com/en-us/dax/)
- [Power BI Desktop Download](https://powerbi.microsoft.com/desktop/)
- [.pbids File Format](https://docs.microsoft.com/en-us/power-bi/connect-data/desktop-data-sources#power-bi-data-source-file-pbids)

## Support

For issues specific to PowerBIExporter:
- Check `schema.json` for data model details
- Review `README.txt` in the export directory
- Run tests: `pytest analytics/exporters/test_powerbi_exporter.py`
- See examples: `analytics/exporters/example_powerbi_usage.py`
