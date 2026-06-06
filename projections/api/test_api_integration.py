"""Integration tests for API endpoints

Reports (ER015), Export (ER016), and Schedule (ER017) endpoints were removed as
ghost surfaces (Wave 4+5 cleanup). The remaining tests cover general API health.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("DREAM_STUDIO_RUN_LEGACY_API_INTEGRATION") != "1",
    reason=(
        "Legacy package-local API integration tests are opt-in until they are "
        "isolated from the native runtime DB."
    ),
)

from fastapi.testclient import TestClient

from projections.api.main import app

client = TestClient(app)


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
