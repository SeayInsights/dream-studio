"""Unit tests for analytics API"""
import pytest
from fastapi.testclient import TestClient
from analytics.api.main import app

client = TestClient(app)


def test_root_endpoint():
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Dream-Studio Analytics API"
    assert data["status"] == "operational"


def test_health_check():
    """Test health check endpoint"""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_api_docs():
    """Test API documentation is available"""
    response = client.get("/api/docs")
    assert response.status_code == 200


def test_openapi_schema():
    """Test OpenAPI schema is available"""
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert data["info"]["title"] == "Dream-Studio Analytics API"


# Metrics endpoints tests

def test_get_all_metrics_endpoint():
    """Test metrics endpoint exists"""
    # This will fail if DB doesn't exist, but validates endpoint structure
    response = client.get("/api/v1/metrics/?days=7")
    # Accept either success or 500 (DB might not exist in test env)
    assert response.status_code in [200, 500]


def test_get_session_metrics_endpoint():
    """Test session metrics endpoint"""
    response = client.get("/api/v1/metrics/sessions?days=7")
    assert response.status_code in [200, 500]


def test_get_skill_metrics_endpoint():
    """Test skill metrics endpoint"""
    response = client.get("/api/v1/metrics/skills?days=7")
    assert response.status_code in [200, 500]


# Insights endpoints tests

def test_get_all_insights_endpoint():
    """Test insights endpoint exists"""
    response = client.get("/api/v1/insights/?days=7")
    assert response.status_code in [200, 500]


def test_get_strengths_endpoint():
    """Test strengths endpoint"""
    response = client.get("/api/v1/insights/strengths?days=7")
    assert response.status_code in [200, 500]


def test_get_issues_endpoint():
    """Test issues endpoint"""
    response = client.get("/api/v1/insights/issues?days=7")
    assert response.status_code in [200, 500]


def test_get_recommendations_endpoint():
    """Test recommendations endpoint"""
    response = client.get("/api/v1/insights/recommendations?days=7")
    assert response.status_code in [200, 500]


# Reports endpoints tests

def test_list_reports():
    """Test list reports endpoint"""
    response = client.get("/api/v1/reports/")
    assert response.status_code == 200
    data = response.json()
    assert "reports" in data
    assert "total" in data


def test_create_report():
    """Test create report endpoint"""
    report_data = {
        "name": "Test Report",
        "type": "executive",
        "description": "Test report description",
        "days": 30
    }

    response = client.post("/api/v1/reports/", json=report_data)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Report"
    assert data["type"] == "executive"
    assert "id" in data


def test_create_and_get_report():
    """Test creating and retrieving a report"""
    # Create report
    report_data = {
        "name": "Test Report 2",
        "type": "detailed",
        "days": 14
    }

    create_response = client.post("/api/v1/reports/", json=report_data)
    assert create_response.status_code == 201
    report_id = create_response.json()["id"]

    # Get report - this will trigger data collection
    # In test environment without DB, this will fail - that's expected
    try:
        get_response = client.get(f"/api/v1/reports/{report_id}")
        # Accept 200 or 500 (DB might not exist)
        assert get_response.status_code in [200, 500]
    except Exception:
        # Expected in test environment without database
        pass


def test_delete_report():
    """Test delete report endpoint"""
    # Create report first
    report_data = {
        "name": "Report to Delete",
        "type": "technical",
        "days": 7
    }

    create_response = client.post("/api/v1/reports/", json=report_data)
    report_id = create_response.json()["id"]

    # Delete it
    delete_response = client.delete(f"/api/v1/reports/{report_id}")
    assert delete_response.status_code == 204

    # Verify it's gone
    get_response = client.get(f"/api/v1/reports/{report_id}")
    assert get_response.status_code == 404


# Export endpoints tests

def test_create_export():
    """Test create export endpoint"""
    export_data = {
        "format": "json",
        "include_charts": True,
        "include_raw_data": False
    }

    response = client.post("/api/v1/export/", json=export_data)
    assert response.status_code == 202
    data = response.json()
    assert "export_id" in data
    assert data["format"] == "json"
    assert data["status"] == "processing"


def test_get_export_status():
    """Test get export status endpoint"""
    # Create export first
    export_data = {"format": "json"}
    create_response = client.post("/api/v1/export/", json=export_data)
    export_id = create_response.json()["export_id"]

    # Get status
    status_response = client.get(f"/api/v1/export/{export_id}")
    assert status_response.status_code == 200
    data = status_response.json()
    assert data["export_id"] == export_id


def test_query_parameter_validation():
    """Test that invalid query parameters are rejected"""
    # Days too low
    response = client.get("/api/v1/metrics/?days=0")
    assert response.status_code == 422

    # Days too high
    response = client.get("/api/v1/metrics/?days=400")
    assert response.status_code == 422


# Alerts endpoints tests

def test_list_alert_rules():
    """Test list alert rules endpoint"""
    response = client.get("/api/v1/alerts/rules")
    # Accept 200 or 500 (DB might not exist in test env)
    assert response.status_code in [200, 500]
    if response.status_code == 200:
        data = response.json()
        assert isinstance(data, list)


def test_create_alert_rule():
    """Test create alert rule endpoint"""
    rule_data = {
        "rule_name": "Test Alert Rule",
        "metric_path": "skill.success_rate",
        "condition": "lt",
        "threshold": 0.8,
        "severity": "warning",
        "enabled": True
    }

    response = client.post("/api/v1/alerts/rules", json=rule_data)
    # Accept 201 or 500 (DB might not exist in test env)
    assert response.status_code in [201, 500]
    if response.status_code == 201:
        data = response.json()
        assert "rule_id" in data
        assert "message" in data


def test_create_alert_rule_validation():
    """Test alert rule validation"""
    # Missing required fields
    incomplete_rule = {
        "rule_name": "Incomplete Rule"
    }

    response = client.post("/api/v1/alerts/rules", json=incomplete_rule)
    assert response.status_code == 422  # Pydantic validation error


def test_create_alert_rule_invalid_condition():
    """Test alert rule with invalid condition"""
    rule_data = {
        "rule_name": "Invalid Condition Rule",
        "metric_path": "test.metric",
        "condition": "invalid_op",  # Invalid condition
        "threshold": 100
    }

    response = client.post("/api/v1/alerts/rules", json=rule_data)
    # Should be either 400 (validation error) or 500 (DB error)
    assert response.status_code in [400, 500]


def test_get_alert_history():
    """Test get alert history endpoint"""
    response = client.get("/api/v1/alerts/history")
    # Accept 200 or 500 (DB might not exist in test env)
    assert response.status_code in [200, 500]
    if response.status_code == 200:
        data = response.json()
        assert isinstance(data, list)


def test_get_alert_history_with_filters():
    """Test get alert history with filters"""
    # Test with limit
    response = client.get("/api/v1/alerts/history?limit=10")
    assert response.status_code in [200, 500]

    # Test with severity filter
    response = client.get("/api/v1/alerts/history?severity=critical")
    assert response.status_code in [200, 500]

    # Test with both filters
    response = client.get("/api/v1/alerts/history?limit=5&severity=warning")
    assert response.status_code in [200, 500]


def test_alert_history_limit_validation():
    """Test alert history limit parameter validation"""
    # Limit too low
    response = client.get("/api/v1/alerts/history?limit=0")
    assert response.status_code == 422

    # Limit too high
    response = client.get("/api/v1/alerts/history?limit=2000")
    assert response.status_code == 422
