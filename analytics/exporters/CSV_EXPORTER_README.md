# CSV Exporter

Export analytics reports to CSV format with three flexible output options: single file, multiple files, or ZIP archive.

## Features

- **Single CSV File**: Flatten all report data into a simple table format
- **Multiple CSV Files**: One CSV per section with metric-specific structure
- **ZIP Archive**: Package multiple CSVs in a compressed archive
- **Excel Compatible**: UTF-8 with BOM encoding for proper Excel display
- **Proper Escaping**: Handles commas, quotes, and special characters correctly
- **Error Handling**: Validates inputs and provides clear error messages

## Installation

No external dependencies required - uses Python's built-in `csv` and `zipfile` modules.

## Usage

### Basic Example

```python
from analytics.core.reports import ReportGenerator
from analytics.exporters import CSVExporter

# Generate report
generator = ReportGenerator()
report = generator.generate_report("detailed")

# Export to CSV
exporter = CSVExporter()

# Option 1: Single file
success, path = exporter.export_to_csv(report, "report.csv")

# Option 2: Multiple files
success, paths = exporter.export_multiple(report, "export/")

# Option 3: ZIP archive
success, path = exporter.export_as_zip(report, "report.zip")
```

## Export Methods

### 1. Single CSV File (`export_to_csv`)

Flattens all report data into a simple 3-column table.

**Output Format:**
```csv
Section,Metric,Value
Skills,total_skill_invocations,1234
Skills,unique_skills,45
Tokens,total_tokens,5678901
```

**Usage:**
```python
exporter = CSVExporter()
success, result = exporter.export_to_csv(report, "report.csv")

if success:
    print(f"Exported to: {result}")
else:
    print(f"Error: {result}")
```

**Returns:**
- `(True, file_path)` on success
- `(False, error_message)` on failure

### 2. Multiple CSV Files (`export_multiple`)

Creates one CSV per section with metric-specific structure.

**Output Structure:**
```
export/
├── skills.csv          # Table format for list data
├── tokens.csv          # Key-value format for simple metrics
├── sessions.csv
└── metadata.txt        # Report metadata
```

**Example Output (skills.csv):**
```csv
skill,count,success_rate
core:build,567,92.50
quality:debug,234,88.30
domains:saas-build,123,95.10
```

**Example Output (tokens.csv):**
```csv
Metric,Value
total_tokens,5678901
daily_average,189296.70
by_model.claude-sonnet-4-5,3456789
```

**Usage:**
```python
exporter = CSVExporter()
success, result = exporter.export_multiple(report, "export/")

if success:
    print(f"Created {len(result)} files:")
    for path in result:
        print(f"  - {path}")
else:
    print(f"Error: {result}")
```

**Returns:**
- `(True, [file_paths])` on success
- `(False, error_message)` on failure

### 3. ZIP Archive (`export_as_zip`)

Packages multiple CSV files into a compressed ZIP archive.

**Archive Contents:**
```
report.zip
├── skills.csv
├── tokens.csv
├── sessions.csv
└── metadata.txt
```

**Usage:**
```python
exporter = CSVExporter()
success, result = exporter.export_as_zip(report, "report.zip")

if success:
    print(f"Created archive: {result}")
else:
    print(f"Error: {result}")
```

**Returns:**
- `(True, file_path)` on success
- `(False, error_message)` on failure

## CSV Formatting

### Encoding
- UTF-8 with BOM (Byte Order Mark) for Excel compatibility
- Ensures proper display of special characters in Excel

### Data Types

| Python Type | CSV Format | Example |
|------------|------------|---------|
| `int` | Plain number | `1234` |
| `float` | 2 decimal places | `92.50` |
| `bool` | `True`/`False` | `True` |
| `datetime` | ISO 8601 | `2026-05-01 23:15:00` |
| `list` | Comma-separated | `item1, item2, item3` |
| `None` | Empty string | `` |

### Special Characters
- Commas, quotes, and newlines are properly escaped
- Excel will automatically handle quoted fields
- Numbers formatted without thousands separators (no commas)

## Error Handling

The exporter validates inputs and provides clear error messages:

```python
# Invalid data structure
success, error = exporter.export_to_csv({}, "output.csv")
# Returns: (False, "Data must contain 'sections' key")

# Non-existent directory
success, error = exporter.export_to_csv(report, "nonexistent/output.csv")
# Returns: (False, "Directory does not exist: nonexistent")

# Permission denied
success, error = exporter.export_to_csv(report, "C:/protected/output.csv")
# Returns: (False, "Permission denied writing to: ...")
```

## Complete Example

```python
from pathlib import Path
from analytics.core.reports import ReportGenerator
from analytics.exporters import CSVExporter


def export_all_formats():
    """Export report in all CSV formats"""

    # Generate report
    generator = ReportGenerator()
    report = generator.generate_report("detailed")

    # Initialize exporter
    exporter = CSVExporter()

    # Create output directory
    output_dir = Path("exports")
    output_dir.mkdir(exist_ok=True)

    # Single file
    single_path = output_dir / "report_single.csv"
    success, result = exporter.export_to_csv(report, single_path)
    if success:
        print(f"✓ Single file: {result}")

    # Multiple files
    multi_dir = output_dir / "multiple"
    success, result = exporter.export_multiple(report, multi_dir)
    if success:
        print(f"✓ Multiple files: {len(result)} files created")

    # ZIP archive
    zip_path = output_dir / "report.zip"
    success, result = exporter.export_as_zip(report, zip_path)
    if success:
        print(f"✓ ZIP archive: {result}")


if __name__ == "__main__":
    export_all_formats()
```

## File Naming

Section titles are converted to safe filenames:
- Lowercase
- Spaces replaced with underscores
- Special characters removed
- Limited to 50 characters

Examples:
- `"Skills"` → `skills.csv`
- `"Token Usage"` → `token_usage.csv`
- `"Detailed Skill Metrics"` → `detailed_skill_metrics.csv`

## Testing

Run the test suite to verify functionality:

```bash
cd analytics/exporters
python test_csv_exporter.py
```

Tests include:
- Single file export
- Multiple files export
- ZIP archive export
- Error handling
- Excel compatibility (UTF-8 BOM)

## See Also

- [ExcelExporter](./EXCEL_TEMPLATES_GUIDE.md) - Export to Excel with charts and formatting
- [PDFExporter](./pdf_exporter.py) - Export to PDF with professional layout
- [ReportGenerator](../core/reports/generator.py) - Generate analytics reports
