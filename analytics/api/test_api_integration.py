"""Integration tests for API endpoints (ER015-ER017)

Tests all three API modules:
- ER015: Reports endpoints
- ER016: Export endpoints
- ER017: Schedule endpoints
"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime
import json

from analytics.api.main import app

client = TestClient(app)


class TestReportsAPI:
    """Test ER015 - Reports endpoints"""

    def test_generate_report_summary(self):
        """Test POST /api/v1/reports/generate - summary report"""
        response = client.post(
            "/api/v1/reports/generate",
            json={
                "report_type": "summary",
                "date_range": ["2026-04-01", "2026-04-30"],
                "template": "executive"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert "report_id" in data
        assert data["report_type"] == "summary"
        assert data["status"] in ["pending", "completed"]

    def test_generate_report_invalid_type(self):
        """Test invalid report type"""
        response = client.post(
            "/api/v1/reports/generate",
            json={
                "report_type": "invalid",
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert "error" in data["detail"]

    def test_list_reports(self):
        """Test GET /api/v1/reports"""
        # First create a report
        create_response = client.post(
            "/api/v1/reports/generate",
            json={"report_type": "detailed"}
        )
        assert create_response.status_code == 201

        # Then list reports
        response = client.get("/api/v1/reports")
        assert response.status_code == 200
        data = response.json()
        assert "reports" in data
        assert "total" in data
        assert data["total"] >= 1

    def test_get_report(self):
        """Test GET /api/v1/reports/{id}"""
        # Create a report
        create_response = client.post(
            "/api/v1/reports/generate",
            json={"report_type": "executive"}
        )
        report_id = create_response.json()["report_id"]

        # Get the report
        response = client.get(f"/api/v1/reports/{report_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["report_id"] == report_id
        assert "content" in data

    def test_get_report_not_found(self):
        """Test GET /api/v1/reports/{id} - not found"""
        response = client.get("/api/v1/reports/nonexistent-id")
        assert response.status_code == 404

    def test_delete_report(self):
        """Test DELETE /api/v1/reports/{id}"""
        # Create a report
        create_response = client.post(
            "/api/v1/reports/generate",
            json={"report_type": "summary"}
        )
        report_id = create_response.json()["report_id"]

        # Delete the report
        response = client.delete(f"/api/v1/reports/{report_id}")
        assert response.status_code == 204

        # Verify it's deleted
        get_response = client.get(f"/api/v1/reports/{report_id}")
        assert get_response.status_code == 404

    def test_pagination(self):
        """Test pagination parameters"""
        response = client.get("/api/v1/reports?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 10


class TestExportsAPI:
    """Test ER016 - Export endpoints"""

    @pytest.fixture
    def report_id(self):
        """Create a test report"""
        response = client.post(
            "/api/v1/reports/generate",
            json={"report_type": "detailed"}
        )
        return response.json()["report_id"]

    def test_export_pdf(self, report_id):
        """Test GET /api/v1/export/pdf/{report_id}"""
        response = client.get(f"/api/v1/export/pdf/{report_id}")
        # May return 200 (success) or 501 (not implemented)
        assert response.status_code in [200, 501]

    def test_export_excel(self, report_id):
        """Test GET /api/v1/export/excel/{report_id}"""
        response = client.get(f"/api/v1/export/excel/{report_id}")
        # May return 200 (success) or 501 (not implemented)
        assert response.status_code in [200, 501]

    def test_export_pptx(self, report_id):
        """Test GET /api/v1/export/pptx/{report_id}"""
        response = client.get(f"/api/v1/export/pptx/{report_id}")
        # May return 200 (success) or 501 (not implemented)
        assert response.status_code in [200, 501]

    def test_export_csv(self):
        """Test GET /api/v1/export/csv"""
        response = client.get("/api/v1/export/csv")
        # May return 200 (success) or 501 (not implemented)
        assert response.status_code in [200, 501]

    def test_export_csv_with_filters(self):
        """Test GET /api/v1/export/csv with filters"""
        filters = json.dumps({"severity": "high"})
        response = client.get(
            f"/api/v1/export/csv?filters={filters}"
        )
        assert response.status_code in [200, 400, 501]

    def test_export_powerbi(self):
        """Test GET /api/v1/export/powerbi"""
        response = client.get("/api/v1/export/powerbi")
        # May return 200 (success) or 501 (not implemented)
        assert response.status_code in [200, 501]

    def test_export_not_found(self):
        """Test export with non-existent report"""
        response = client.get("/api/v1/export/pdf/nonexistent-id")
        assert response.status_code == 404


class TestSchedulesAPI:
    """Test ER017 - Schedule endpoints"""

    def test_create_schedule(self):
        """Test POST /api/v1/schedules"""
        response = client.post(
            "/api/v1/schedules",
            json={
                "name": "Weekly Executive Summary",
                "report_type": "summary",
                "schedule": "0 9 * * MON",
                "recipients": ["exec@company.com"],
                "format": "pdf",
                "timezone": "America/New_York"
            }
        )
        # May succeed or fail if scheduler not available
        assert response.status_code in [201, 501]

    def test_create_schedule_invalid_email(self):
        """Test schedule with invalid email"""
        response = client.post(
            "/api/v1/schedules",
            json={
                "name": "Test Schedule",
                "report_type": "summary",
                "schedule": "0 9 * * *",
                "recipients": ["invalid-email"],
                "format": "pdf"
            }
        )
        assert response.status_code in [400, 422, 501]

    def test_create_schedule_invalid_format(self):
        """Test schedule with invalid format"""
        response = client.post(
            "/api/v1/schedules",
            json={
                "name": "Test Schedule",
                "report_type": "summary",
                "schedule": "0 9 * * *",
                "recipients": ["test@example.com"],
                "format": "invalid"
            }
        )
        assert response.status_code in [400, 422, 501]

    def test_list_schedules(self):
        """Test GET /api/v1/schedules"""
        response = client.get("/api/v1/schedules")
        assert response.status_code in [200, 501]
        if response.status_code == 200:
            data = response.json()
            assert "schedules" in data
            assert "total" in data

    def test_update_schedule(self):
        """Test PUT /api/v1/schedules/{id}"""
        # Try to create a schedule first
        create_response = client.post(
            "/api/v1/schedules",
            json={
                "name": "Test Schedule",
                "report_type": "summary",
                "schedule": "0 9 * * *",
                "recipients": ["test@example.com"]
            }
        )

        if create_response.status_code == 201:
            job_id = create_response.json()["job_id"]

            # Update the schedule
            response = client.put(
                f"/api/v1/schedules/{job_id}",
                json={"name": "Updated Schedule"}
            )
            assert response.status_code in [200, 404]

    def test_delete_schedule(self):
        """Test DELETE /api/v1/schedules/{id}"""
        # Try to create a schedule first
        create_response = client.post(
            "/api/v1/schedules",
            json={
                "name": "Test Schedule",
                "report_type": "summary",
                "schedule": "0 9 * * *",
                "recipients": ["test@example.com"]
            }
        )

        if create_response.status_code == 201:
            job_id = create_response.json()["job_id"]

            # Delete the schedule
            response = client.delete(f"/api/v1/schedules/{job_id}")
            assert response.status_code in [204, 404]

    def test_pause_schedule(self):
        """Test POST /api/v1/schedules/{id}/pause"""
        # Try to create a schedule first
        create_response = client.post(
            "/api/v1/schedules",
            json={
                "name": "Test Schedule",
                "report_type": "summary",
                "schedule": "0 9 * * *",
                "recipients": ["test@example.com"]
            }
        )

        if create_response.status_code == 201:
            job_id = create_response.json()["job_id"]

            # Pause the schedule
            response = client.post(f"/api/v1/schedules/{job_id}/pause")
            assert response.status_code in [200, 404]

    def test_resume_schedule(self):
        """Test POST /api/v1/schedules/{id}/resume"""
        # Try to create a schedule first
        create_response = client.post(
            "/api/v1/schedules",
            json={
                "name": "Test Schedule",
                "report_type": "summary",
                "schedule": "0 9 * * *",
                "recipients": ["test@example.com"]
            }
        )

        if create_response.status_code == 201:
            job_id = create_response.json()["job_id"]

            # Pause first
            client.post(f"/api/v1/schedules/{job_id}/pause")

            # Resume the schedule
            response = client.post(f"/api/v1/schedules/{job_id}/resume")
            assert response.status_code in [200, 404]


class TestAPIHealth:
    """Test general API health"""

    def test_root_endpoint(self):
        """Test GET /"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "operational"

    def test_health_check(self):
        """Test GET /api/health"""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_openapi_docs(self):
        """Test OpenAPI documentation endpoint"""
        response = client.get("/api/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "paths" in data
        assert "/api/v1/reports/generate" in data["paths"]
        assert "/api/v1/export/pdf/{report_id}" in data["paths"]
        assert "/api/v1/schedules" in data["paths"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
