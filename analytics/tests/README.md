# Analytics Test Suite

Comprehensive test coverage for the dream-studio analytics export and reporting system.

## Test Files

### ER020: Report Generation Tests
**File**: `test_reports.py`

Tests the ReportGenerator's ability to create various report types with proper metric compilation and template rendering.

**Coverage**:
- Summary, detailed, executive, and custom report generation
- Template rendering and validation
- Metric compilation from all collectors
- Date range handling (tuples, defaults, relative)
- Invalid input handling and error cases
- Report metadata structure validation

**Key Test Classes**:
- `TestReportGenerator`: Core report generation functionality
- `TestReportIntegration`: Integration tests with real database

**Run**:
```bash
pytest analytics/tests/test_reports.py -v
```

### ER021: Export Format Tests
**File**: `test_exporters.py`

Tests all export formats (PDF, Excel, PowerPoint, CSV, Power BI) with proper chart embedding, multi-page layouts, and error handling.

**Coverage**:
- **PDF Exporter**: Basic export, chart embedding, multi-page layouts
- **Excel Exporter**: Workbook creation, multi-sheet, charts, formatting
- **PowerPoint Exporter**: Presentation creation, slide generation, templates
- **CSV Exporter**: Single file, multiple files, ZIP archives, delimiters
- **Power BI Exporter**: Dataset export, schema generation, .pbids files
- **Integration**: Export same report to all formats

**Key Test Classes**:
- `TestPDFExporter`: PDF export functionality
- `TestExcelExporter`: Excel workbook export
- `TestPPTXExporter`: PowerPoint presentation export
- `TestCSVExporter`: CSV file export
- `TestPowerBIExporter`: Power BI dataset export
- `TestExporterIntegration`: Cross-format integration tests

**Run**:
```bash
pytest analytics/tests/test_exporters.py -v
```

### ER022: Email and Scheduler Tests
**Files**: `test_email.py`, `test_scheduler.py`

Tests email delivery system and automated report scheduling.

#### Email Tests (`test_email.py`)

**Coverage**:
- SMTP connection with mocked server
- Single and multiple recipients
- File attachments (single and multiple)
- HTML template rendering
- CC and BCC support
- Error handling (connection, authentication, invalid attachments)

**Key Test Classes**:
- `TestEmailSender`: Email sending functionality
- `TestTemplateRenderer`: HTML template rendering
- `TestEmailIntegration`: Full email workflow

**Run**:
```bash
pytest analytics/tests/test_email.py -v
```

#### Scheduler Tests (`test_scheduler.py`)

**Coverage**:
- Schedule creation and management
- Job execution and timing
- Pause/resume functionality
- Cron expression parsing
- Database persistence
- Schedule updates and deletion

**Key Test Classes**:
- `TestReportScheduler`: Job management and execution
- `TestScheduleStorage`: Database persistence
- `TestSchedulerIntegration`: Scheduler + storage integration

**Run**:
```bash
pytest analytics/tests/test_scheduler.py -v
```

## Running Tests

### Run All Tests
```bash
# From analytics directory
pytest tests/ -v

# Or using the test runner
python -m analytics.tests.run_tests
```

### Run Specific Test File
```bash
pytest tests/test_reports.py -v
pytest tests/test_exporters.py -v
pytest tests/test_email.py -v
pytest tests/test_scheduler.py -v
```

### Run Specific Test Class
```bash
pytest tests/test_reports.py::TestReportGenerator -v
pytest tests/test_exporters.py::TestPDFExporter -v
```

### Run Specific Test Method
```bash
pytest tests/test_reports.py::TestReportGenerator::test_generate_summary_report -v
```

### Run with Coverage
```bash
# Generate coverage report
pytest tests/ --cov=analytics --cov-report=html --cov-report=term-missing

# Or using test runner
python -m analytics.tests.run_tests --coverage

# View HTML report
# Open htmlcov/index.html in browser
```

### Run with Different Verbosity
```bash
# Standard verbose
pytest tests/ -v

# Extra verbose (show test docstrings)
pytest tests/ -vv

# Quiet (minimal output)
pytest tests/ -q
```

### Run Only Failed Tests
```bash
# Run tests that failed in last run
pytest tests/ --lf

# Run failed tests first, then others
pytest tests/ --ff
```

## Test Coverage Target

**Minimum**: 70% code coverage across all modules

**Current Coverage** (run tests with `--coverage` to see):
- `analytics/core/reports/`: Target >75%
- `analytics/exporters/`: Target >70%
- `analytics/core/email/`: Target >70%
- `analytics/core/scheduler/`: Target >70%

## Mocking Strategy

Tests use extensive mocking to avoid external dependencies:

### Database Mocking
- Temporary SQLite databases created with `tempfile`
- Mock collectors return sample data
- Integration tests skip if real database unavailable

### SMTP Mocking
- `unittest.mock.patch` for `smtplib.SMTP`
- Mock SMTP server for email tests
- No actual emails sent during tests

### File System Mocking
- Temporary directories via `tempfile.TemporaryDirectory`
- All test outputs written to temp locations
- Automatic cleanup after tests

## Fixtures

Common pytest fixtures available:

### `temp_db`
Temporary SQLite database file (auto-deleted after test)

### `temp_output_dir`
Temporary directory for export outputs (auto-deleted after test)

### `sample_report`
Sample report data structure for export tests

### `mock_collectors`
Mocked data collectors with sample return values

### `email_sender`
EmailSender instance with mocked SMTP connection

## Test Organization

Tests follow the AAA pattern:
- **Arrange**: Set up test data and mocks
- **Act**: Execute the function being tested
- **Assert**: Verify expected outcomes

Example:
```python
def test_generate_summary_report(self, mock_collectors):
    # Arrange
    generator = ReportGenerator()
    
    # Act
    report = generator.generate_report("summary")
    
    # Assert
    assert report["metadata"]["report_type"] == "summary"
    assert len(report["sections"]) > 0
```

## Continuous Integration

These tests are designed to run in CI/CD pipelines:

### GitHub Actions Example
```yaml
- name: Run Analytics Tests
  run: |
    cd analytics
    pytest tests/ -v --cov=analytics --cov-report=xml
    
- name: Upload Coverage
  uses: codecov/codecov-action@v3
  with:
    files: ./analytics/coverage.xml
```

## Writing New Tests

When adding new tests:

1. **Follow naming convention**: `test_<feature>.py`
2. **Use descriptive test names**: `test_export_with_charts_succeeds`
3. **Add docstrings**: Explain what the test validates
4. **Mock external dependencies**: Databases, SMTP, file I/O
5. **Clean up resources**: Use fixtures with cleanup or context managers
6. **Test both success and failure**: Happy path + error cases
7. **Use parametrize for variants**: Multiple inputs to same test logic

Example:
```python
@pytest.mark.parametrize("report_type", ["summary", "detailed", "executive"])
def test_all_report_types(self, report_type, mock_collectors):
    """Test that all report types generate successfully"""
    generator = ReportGenerator()
    report = generator.generate_report(report_type)
    
    assert report["metadata"]["report_type"] == report_type
    assert len(report["sections"]) > 0
```

## Troubleshooting

### Tests fail with import errors
Ensure analytics package is in Python path:
```bash
cd /path/to/dream-studio
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
pytest analytics/tests/ -v
```

### Mock SMTP not working
Verify patch path matches import:
```python
# If code does: from analytics.core.email.sender import EmailSender
# Then patch: 'analytics.core.email.sender.smtplib.SMTP'
```

### Temp files not cleaned up
Use context managers or pytest fixtures with cleanup:
```python
@pytest.fixture
def temp_file():
    f = tempfile.NamedTemporaryFile(delete=False)
    yield f.name
    os.unlink(f.name)  # Cleanup
```

### Coverage too low
Identify uncovered lines:
```bash
pytest tests/ --cov=analytics --cov-report=term-missing
# Shows line numbers not covered by tests
```

## Dependencies

Test dependencies (install with `pip install -r requirements-test.txt`):
- `pytest>=7.0.0`
- `pytest-cov>=4.0.0`
- `pytest-mock>=3.10.0`

Optional for better output:
- `pytest-html` - HTML test reports
- `pytest-xdist` - Parallel test execution

## Support

For test-related questions:
- Check existing test patterns in this directory
- Review pytest documentation: https://docs.pytest.org/
- Ask in dream-studio GitHub issues
