# Analytics Test Suite - Quick Start

## Installation

```bash
# Install test dependencies
pip install -r analytics/tests/requirements-test.txt
```

## Running Tests

### Run Everything
```bash
cd analytics
pytest tests/ -v
```

### Run Specific Module
```bash
pytest tests/test_reports.py -v       # Report generation
pytest tests/test_exporters.py -v     # Export formats
pytest tests/test_email.py -v         # Email delivery
pytest tests/test_scheduler.py -v     # Scheduling
```

### Run with Coverage
```bash
pytest tests/ --cov=analytics --cov-report=html
# Open htmlcov/index.html
```

### Using Test Runner
```bash
python -m analytics.tests.run_tests
python -m analytics.tests.run_tests --coverage
```

## Validate Tests

```bash
python analytics/tests/validate_tests.py
```

## Test Files Overview

| File | Purpose | Test Count |
|------|---------|------------|
| `test_reports.py` | Report generation (summary, detailed, custom) | 44 |
| `test_exporters.py` | PDF, Excel, PowerPoint, CSV, Power BI exports | 48 |
| `test_email.py` | Email sending with SMTP mocking | 38 |
| `test_scheduler.py` | Job scheduling and cron execution | 38 |

**Total**: 168 test functions across 14 test classes

## Coverage Target

**Minimum**: 70%  
**Expected**: 75%+

## Common Commands

```bash
# Run only failed tests
pytest tests/ --lf

# Run with extra verbose output
pytest tests/ -vv

# Run specific test class
pytest tests/test_reports.py::TestReportGenerator -v

# Run specific test
pytest tests/test_reports.py::TestReportGenerator::test_generate_summary_report -v
```

## CI/CD Integration

```yaml
# Example GitHub Actions
- name: Run Tests
  run: |
    pip install -r analytics/tests/requirements-test.txt
    pytest analytics/tests/ -v --cov=analytics --cov-report=xml
```

## Documentation

- **Test Guide**: `analytics/tests/README.md`
- **User Guide**: `analytics/README.md` (Export & Reporting section)
- **Completion Report**: `analytics/tests/ER020-ER023_COMPLETION_SUMMARY.md`

## Support

For issues:
1. Check test README: `analytics/tests/README.md`
2. Review completion summary for known issues
3. Run validation: `python analytics/tests/validate_tests.py`
4. Check pytest docs: https://docs.pytest.org/
