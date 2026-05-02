# Analytics API Quick Start Guide

Get the dream-studio analytics API up and running in 5 minutes.

## Prerequisites

- Python 3.12+ installed
- dream-studio project cloned
- Virtual environment activated (recommended)

## Installation

```bash
# Navigate to project root
cd dream-studio

# Activate virtual environment (if not already active)
.venv\Scripts\activate  # Windows
# or
source .venv/bin/activate  # Linux/Mac

# Install dependencies (should already be installed)
pip install fastapi uvicorn pydantic
```

## Start the API Server

```bash
# Method 1: Direct Python execution
cd analytics
python -m api.main

# Method 2: Uvicorn command
uvicorn analytics.api.main:app --reload --port 8000

# Method 3: From project root
python -m analytics.api.main
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

## Verify Installation

Open your browser and visit:

- **API Health Check:** http://localhost:8000/api/health
- **Swagger UI (Interactive Docs):** http://localhost:8000/api/docs
- **ReDoc (Alternative Docs):** http://localhost:8000/api/redoc

## Test the API

### Using Swagger UI (Easiest)

1. Open http://localhost:8000/api/docs
2. Click on any endpoint (e.g., `POST /api/v1/reports/generate`)
3. Click "Try it out"
4. Fill in the request body
5. Click "Execute"
6. See the response below

### Using cURL

```bash
# Generate a report
curl -X POST http://localhost:8000/api/v1/reports/generate \
  -H "Content-Type: application/json" \
  -d '{"report_type": "summary"}'

# Response:
# {
#   "report_id": "550e8400-e29b-41d4-a716-446655440000",
#   "report_type": "summary",
#   "generated_at": "2026-05-01T12:00:00",
#   "date_range": {...},
#   "status": "completed"
# }

# List all reports
curl http://localhost:8000/api/v1/reports

# Get specific report (use report_id from above)
curl http://localhost:8000/api/v1/reports/550e8400-e29b-41d4-a716-446655440000

# Export as Excel
curl -o report.xlsx http://localhost:8000/api/v1/export/excel/550e8400-e29b-41d4-a716-446655440000

# Create a schedule
curl -X POST http://localhost:8000/api/v1/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Daily Summary",
    "report_type": "summary",
    "schedule": "0 9 * * *",
    "recipients": ["team@company.com"]
  }'
```

### Using Python

```python
import requests

BASE_URL = "http://localhost:8000"

# Generate a report
response = requests.post(
    f"{BASE_URL}/api/v1/reports/generate",
    json={"report_type": "executive"}
)
print(f"Status: {response.status_code}")
print(f"Report ID: {response.json()['report_id']}")

report_id = response.json()["report_id"]

# Get the report
response = requests.get(f"{BASE_URL}/api/v1/reports/{report_id}")
print(f"Report: {response.json()}")

# Export as Excel
response = requests.get(f"{BASE_URL}/api/v1/export/excel/{report_id}")
if response.status_code == 200:
    with open("report.xlsx", "wb") as f:
        f.write(response.content)
    print("Excel file saved!")
```

## Common Use Cases

### 1. Generate and Export Report

```bash
# 1. Generate report
REPORT_ID=$(curl -s -X POST http://localhost:8000/api/v1/reports/generate \
  -H "Content-Type: application/json" \
  -d '{"report_type": "detailed"}' | jq -r '.report_id')

# 2. Export as PDF
curl -o report.pdf http://localhost:8000/api/v1/export/pdf/$REPORT_ID

# 3. Export as Excel
curl -o report.xlsx http://localhost:8000/api/v1/export/excel/$REPORT_ID

# 4. Export as PowerPoint
curl -o report.pptx http://localhost:8000/api/v1/export/pptx/$REPORT_ID
```

### 2. Schedule Weekly Report

```bash
curl -X POST http://localhost:8000/api/v1/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Weekly Executive Summary",
    "report_type": "summary",
    "schedule": "0 9 * * MON",
    "recipients": ["exec@company.com", "manager@company.com"],
    "format": "pdf",
    "timezone": "America/New_York"
  }'
```

### 3. Export Current Data (No Report Required)

```bash
# Export as CSV
curl -o analytics.csv http://localhost:8000/api/v1/export/csv

# Export with date range
curl -o analytics.csv "http://localhost:8000/api/v1/export/csv?date_range=2026-04-01,2026-04-30"

# Export Power BI dataset
curl -o powerbi.zip http://localhost:8000/api/v1/export/powerbi
```

### 4. Manage Schedules

```bash
# List all schedules
curl http://localhost:8000/api/v1/schedules

# Pause a schedule
curl -X POST http://localhost:8000/api/v1/schedules/abc123/pause

# Resume a schedule
curl -X POST http://localhost:8000/api/v1/schedules/abc123/resume

# Delete a schedule
curl -X DELETE http://localhost:8000/api/v1/schedules/abc123
```

## Endpoint Reference

### Reports (ER015)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/reports/generate` | POST | Create new report |
| `/api/v1/reports` | GET | List all reports |
| `/api/v1/reports/{id}` | GET | Get specific report |
| `/api/v1/reports/{id}` | DELETE | Delete report |

### Exports (ER016)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/export/pdf/{report_id}` | GET | Export as PDF |
| `/api/v1/export/excel/{report_id}` | GET | Export as Excel |
| `/api/v1/export/pptx/{report_id}` | GET | Export as PowerPoint |
| `/api/v1/export/csv` | GET | Export as CSV |
| `/api/v1/export/powerbi` | GET | Export Power BI dataset |

### Schedules (ER017)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/schedules` | GET | List all schedules |
| `/api/v1/schedules` | POST | Create schedule |
| `/api/v1/schedules/{id}` | PUT | Update schedule |
| `/api/v1/schedules/{id}` | DELETE | Delete schedule |
| `/api/v1/schedules/{id}/pause` | POST | Pause schedule |
| `/api/v1/schedules/{id}/resume` | POST | Resume schedule |

## Troubleshooting

### Port Already in Use

```bash
# Check what's using port 8000
netstat -ano | findstr :8000  # Windows
lsof -i :8000  # Linux/Mac

# Use different port
uvicorn analytics.api.main:app --port 8001
```

### Module Import Errors

```bash
# Make sure you're in the project root
cd dream-studio

# Set PYTHONPATH (if needed)
export PYTHONPATH="${PYTHONPATH}:$(pwd)"  # Linux/Mac
set PYTHONPATH=%PYTHONPATH%;%CD%  # Windows
```

### Scheduler Not Available (501 Error)

The scheduler endpoints return 501 if the scheduler module can't be imported. This is expected if APScheduler is not installed:

```bash
pip install apscheduler
```

### Exporter Not Available (501 Error)

Some exporters require additional dependencies:

```bash
# PDF export
pip install reportlab

# Excel export
pip install openpyxl

# PowerPoint export
pip install python-pptx
```

## Next Steps

1. **Read Full Documentation:** See [API_DOCUMENTATION.md](API_DOCUMENTATION.md)
2. **Run Tests:** `pytest analytics/api/test_api_integration.py -v`
3. **Explore Swagger UI:** http://localhost:8000/api/docs
4. **Build a Client:** Use the API in your application

## Support

- **Documentation:** [API_DOCUMENTATION.md](API_DOCUMENTATION.md)
- **Implementation:** [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
- **Tests:** [test_api_integration.py](test_api_integration.py)

## Production Deployment

For production deployment, see the "Production Deployment" section in [API_DOCUMENTATION.md](API_DOCUMENTATION.md).

Key points:
- Add authentication
- Configure CORS
- Set up database
- Enable HTTPS
- Add rate limiting
- Set up monitoring
