# Analytics API Documentation

Complete REST API for dream-studio analytics platform with report generation, export, and scheduling capabilities.

## Base URL

```
http://localhost:8000
```

## OpenAPI Documentation

Interactive API documentation available at:
- Swagger UI: `http://localhost:8000/api/docs`
- ReDoc: `http://localhost:8000/api/redoc`
- OpenAPI JSON: `http://localhost:8000/api/openapi.json`

## Quick Start

```bash
# Start the API server
cd analytics
python -m api.main

# Or with auto-reload for development
uvicorn analytics.api.main:app --reload --port 8000
```

## Authentication

Currently no authentication required. Production deployment should add:
- API key authentication
- Rate limiting
- CORS configuration

---

## ER015: Reports Endpoints

### POST /api/v1/reports/generate

Generate a new report.

**Request Body:**
```json
{
  "report_type": "summary",
  "date_range": ["2026-04-01", "2026-04-30"],
  "template": "executive",
  "filters": {},
  "sections": ["metrics", "insights", "recommendations"]
}
```

**Parameters:**
- `report_type` (required): `"summary"`, `"detailed"`, or `"executive"`
- `date_range` (optional): Tuple of ISO date strings `[start, end]`
- `template` (optional): Template name to use
- `filters` (optional): Dictionary of filters to apply
- `sections` (optional): Array of sections to include

**Response (201):**
```json
{
  "report_id": "550e8400-e29b-41d4-a716-446655440000",
  "report_type": "summary",
  "generated_at": "2026-05-01T12:00:00",
  "date_range": {
    "start": "2026-04-01",
    "end": "2026-04-30"
  },
  "status": "completed",
  "error": null
}
```

**Status Codes:**
- `201` - Report created successfully
- `400` - Invalid request (bad report_type, invalid date_range)
- `500` - Report generation failed

---

### GET /api/v1/reports

List all generated reports with pagination.

**Query Parameters:**
- `page` (optional, default: 1): Page number
- `page_size` (optional, default: 50, max: 100): Items per page

**Response (200):**
```json
{
  "reports": [
    {
      "report_id": "550e8400-e29b-41d4-a716-446655440000",
      "report_type": "summary",
      "generated_at": "2026-05-01T12:00:00",
      "status": "completed",
      "date_range": {
        "start": "2026-04-01",
        "end": "2026-04-30"
      }
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 50
}
```

---

### GET /api/v1/reports/{report_id}

Get a specific report with full content.

**Path Parameters:**
- `report_id`: Report UUID

**Response (200):**
```json
{
  "report_id": "550e8400-e29b-41d4-a716-446655440000",
  "report_type": "executive",
  "generated_at": "2026-05-01T12:00:00",
  "date_range": {
    "start": "2026-04-01",
    "end": "2026-04-30"
  },
  "status": "completed",
  "content": {
    "metrics": {},
    "insights": {},
    "recommendations": []
  },
  "metadata": {
    "config": {},
    "error": null
  }
}
```

**Status Codes:**
- `200` - Report found
- `404` - Report not found

---

### DELETE /api/v1/reports/{report_id}

Delete a report permanently.

**Path Parameters:**
- `report_id`: Report UUID

**Response:**
- `204` - No content (successful deletion)
- `404` - Report not found

---

## ER016: Export Endpoints

### GET /api/v1/export/pdf/{report_id}

Export a report as PDF.

**Path Parameters:**
- `report_id`: Report UUID

**Query Parameters:**
- `include_charts` (optional, default: true): Include charts in PDF

**Response:**
- `200` - PDF file download
- `404` - Report not found
- `400` - Report not ready (still processing)
- `501` - PDF export not available

**Headers:**
```
Content-Type: application/pdf
Content-Disposition: attachment; filename="report_<id>.pdf"
```

---

### GET /api/v1/export/excel/{report_id}

Export a report as Excel workbook.

**Path Parameters:**
- `report_id`: Report UUID

**Query Parameters:**
- `include_charts` (optional, default: true): Include charts
- `include_raw_data` (optional, default: false): Add raw data sheet

**Response:**
- `200` - Excel file download
- `404` - Report not found
- `400` - Report not ready
- `501` - Excel export not available

**Headers:**
```
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="report_<id>.xlsx"
```

---

### GET /api/v1/export/pptx/{report_id}

Export a report as PowerPoint presentation.

**Path Parameters:**
- `report_id`: Report UUID

**Query Parameters:**
- `template` (optional): PowerPoint template to use (`"executive"`, `"technical"`)

**Response:**
- `200` - PowerPoint file download
- `404` - Report not found
- `400` - Report not ready
- `501` - PowerPoint export not available

**Headers:**
```
Content-Type: application/vnd.openxmlformats-officedocument.presentationml.presentation
Content-Disposition: attachment; filename="report_<id>.pptx"
```

---

### GET /api/v1/export/csv

Export current analytics data as CSV (no pre-generated report required).

**Query Parameters:**
- `date_range` (optional): Comma-separated dates `"YYYY-MM-DD,YYYY-MM-DD"`
- `filters` (optional): JSON string of filters `{"severity": "high"}`

**Example:**
```
GET /api/v1/export/csv?date_range=2026-04-01,2026-04-30&filters={"type":"security"}
```

**Response:**
- `200` - CSV file download
- `400` - Invalid date_range or filters format
- `501` - CSV export not available

**Headers:**
```
Content-Type: text/csv
Content-Disposition: attachment; filename="analytics_data_20260501.csv"
```

---

### GET /api/v1/export/powerbi

Export Power BI dataset package (ZIP archive).

**Query Parameters:**
- `include_relationships` (optional, default: true): Include table relationships
- `include_measures` (optional, default: true): Include DAX measures

**Response:**
- `200` - ZIP file download
- `501` - Power BI export not available

**Headers:**
```
Content-Type: application/zip
Content-Disposition: attachment; filename="powerbi_dataset_20260501.zip"
```

**Package Contents:**
- `data/*.csv` - Data tables
- `schema.json` - Table schemas and relationships
- `measures.dax` - DAX measure definitions
- `README.md` - Import instructions

---

## ER017: Schedule Endpoints

### GET /api/v1/schedules

List all report schedules.

**Response (200):**
```json
{
  "schedules": [
    {
      "job_id": "abc123",
      "name": "Weekly Executive Summary",
      "report_type": "summary",
      "schedule": "0 9 * * MON",
      "recipients": ["exec@company.com"],
      "format": "pdf",
      "enabled": true,
      "timezone": "America/New_York",
      "next_run": "2026-05-05T09:00:00-04:00",
      "last_run": "2026-04-28T09:00:00-04:00",
      "created_at": "2026-04-01T10:00:00",
      "updated_at": "2026-04-01T10:00:00"
    }
  ],
  "total": 5,
  "active": 4,
  "paused": 1
}
```

---

### POST /api/v1/schedules

Create a new report schedule.

**Request Body:**
```json
{
  "name": "Weekly Executive Summary",
  "report_type": "summary",
  "schedule": "0 9 * * MON",
  "recipients": ["exec@company.com", "manager@company.com"],
  "format": "pdf",
  "enabled": true,
  "timezone": "America/New_York",
  "template": "executive",
  "config": {
    "date_range": ["2026-04-01", "2026-04-30"]
  }
}
```

**Parameters:**
- `name` (required): Schedule name (1-200 chars)
- `report_type` (required): `"summary"`, `"detailed"`, or `"executive"`
- `schedule` (required): Cron expression (see below)
- `recipients` (required): Array of email addresses (at least 1)
- `format` (optional, default: "pdf"): `"pdf"`, `"excel"`, or `"pptx"`
- `enabled` (optional, default: true): Whether schedule is active
- `timezone` (optional, default: "UTC"): Timezone for schedule
- `template` (optional): Template name
- `config` (optional): Additional report configuration

**Cron Expression Examples:**
```
"0 9 * * *"      - Daily at 9:00 AM
"0 9 * * MON"    - Every Monday at 9:00 AM
"0 9 1 * *"      - 1st of every month at 9:00 AM
"*/30 * * * *"   - Every 30 minutes
"0 18 * * FRI"   - Every Friday at 6:00 PM
```

**Response (201):**
```json
{
  "message": "Schedule created successfully",
  "job_id": "abc123"
}
```

**Status Codes:**
- `201` - Schedule created
- `400` - Invalid configuration (bad cron, invalid email, etc.)
- `422` - Validation error
- `501` - Scheduler not available

---

### PUT /api/v1/schedules/{job_id}

Update an existing schedule.

**Path Parameters:**
- `job_id`: Schedule ID

**Request Body:**
```json
{
  "name": "Updated Schedule Name",
  "schedule": "0 10 * * MON",
  "recipients": ["new@company.com"]
}
```

All fields are optional. Only provided fields will be updated.

**Response (200):**
```json
{
  "message": "Schedule updated successfully",
  "job_id": "abc123"
}
```

**Status Codes:**
- `200` - Schedule updated
- `404` - Schedule not found
- `400` - Invalid update parameters

---

### DELETE /api/v1/schedules/{job_id}

Delete a schedule permanently.

**Path Parameters:**
- `job_id`: Schedule ID

**Response:**
- `204` - No content (successful deletion)
- `404` - Schedule not found

---

### POST /api/v1/schedules/{job_id}/pause

Pause a schedule temporarily (disable without deleting).

**Path Parameters:**
- `job_id`: Schedule ID

**Response (200):**
```json
{
  "message": "Schedule paused successfully",
  "job_id": "abc123"
}
```

**Status Codes:**
- `200` - Schedule paused
- `404` - Schedule not found

---

### POST /api/v1/schedules/{job_id}/resume

Resume a paused schedule.

**Path Parameters:**
- `job_id`: Schedule ID

**Response (200):**
```json
{
  "message": "Schedule resumed successfully",
  "job_id": "abc123"
}
```

**Status Codes:**
- `200` - Schedule resumed
- `404` - Schedule not found

---

## Error Responses

All error responses follow this format:

```json
{
  "detail": {
    "error": "Error message",
    "status_code": 400,
    "details": {
      "additional": "context"
    }
  }
}
```

Common status codes:
- `400` - Bad Request (invalid parameters)
- `404` - Not Found (resource doesn't exist)
- `422` - Unprocessable Entity (validation error)
- `500` - Internal Server Error
- `501` - Not Implemented (feature not available)

---

## Rate Limiting

No rate limiting currently implemented. Production deployment should add:
- Per-IP rate limits (e.g., 100 requests/minute)
- Per-API-key rate limits
- Exponential backoff for retries

---

## Testing

Run integration tests:

```bash
# All tests
pytest analytics/api/test_api_integration.py -v

# Specific test class
pytest analytics/api/test_api_integration.py::TestReportsAPI -v

# Specific test
pytest analytics/api/test_api_integration.py::TestReportsAPI::test_generate_report_summary -v
```

---

## Examples

### Python Client

```python
import requests

BASE_URL = "http://localhost:8000"

# Generate a report
response = requests.post(
    f"{BASE_URL}/api/v1/reports/generate",
    json={
        "report_type": "executive",
        "date_range": ["2026-04-01", "2026-04-30"]
    }
)
report_id = response.json()["report_id"]

# Export as Excel
response = requests.get(
    f"{BASE_URL}/api/v1/export/excel/{report_id}"
)
with open("report.xlsx", "wb") as f:
    f.write(response.content)

# Create a schedule
response = requests.post(
    f"{BASE_URL}/api/v1/schedules",
    json={
        "name": "Weekly Report",
        "report_type": "summary",
        "schedule": "0 9 * * MON",
        "recipients": ["team@company.com"],
        "format": "pdf"
    }
)
job_id = response.json()["job_id"]
```

### cURL Examples

```bash
# Generate report
curl -X POST http://localhost:8000/api/v1/reports/generate \
  -H "Content-Type: application/json" \
  -d '{"report_type": "summary"}'

# List reports
curl http://localhost:8000/api/v1/reports

# Export CSV
curl -o analytics.csv http://localhost:8000/api/v1/export/csv

# Create schedule
curl -X POST http://localhost:8000/api/v1/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Daily Summary",
    "report_type": "summary",
    "schedule": "0 9 * * *",
    "recipients": ["team@company.com"]
  }'

# Pause schedule
curl -X POST http://localhost:8000/api/v1/schedules/abc123/pause
```

---

## Production Deployment

### Security Checklist

- [ ] Add API key authentication
- [ ] Configure CORS properly (remove wildcard)
- [ ] Add rate limiting
- [ ] Enable HTTPS/TLS
- [ ] Add request logging
- [ ] Set up monitoring/alerts
- [ ] Configure database backend (replace in-memory storage)
- [ ] Set up file storage (S3/Azure/GCS for exports)
- [ ] Add input sanitization
- [ ] Configure proper error messages (hide stack traces)

### Environment Variables

```bash
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4

# Database
DATABASE_URL=postgresql://user:pass@host/db

# Storage
STORAGE_BACKEND=s3
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=analytics-exports

# Email (for scheduled reports)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...

# Scheduler
SCHEDULER_DB_PATH=/var/lib/dream-studio/schedules.db
```

### Docker Deployment

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY analytics analytics/

EXPOSE 8000

CMD ["uvicorn", "analytics.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t dream-studio-api .
docker run -p 8000:8000 dream-studio-api
```

---

## Support

For issues or questions:
- GitHub: https://github.com/SeayInsights/dream-studio
- Documentation: /analytics/api/
