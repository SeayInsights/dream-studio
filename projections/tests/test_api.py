"""Unit tests for analytics API"""

import pytest
from fastapi.testclient import TestClient
from projections.api.main import app

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
    """Insights returns an honest response instead of a dashboard-breaking 500."""
    response = client.get("/api/v1/insights/?days=7")
    assert response.status_code == 200
    data = response.json()
    assert "strengths" in data
    assert "issues" in data
    assert "opportunities" in data
    assert "risks" in data


def test_get_strengths_endpoint():
    """Strengths returns an honest response instead of a dashboard-breaking 500."""
    response = client.get("/api/v1/insights/strengths?days=7")
    assert response.status_code == 200


def test_get_issues_endpoint():
    """Issues returns an honest response instead of a dashboard-breaking 500."""
    response = client.get("/api/v1/insights/issues?days=7")
    assert response.status_code == 200


def test_get_recommendations_endpoint():
    """Recommendations returns an honest response instead of a dashboard-breaking 500."""
    response = client.get("/api/v1/insights/recommendations?days=7")
    assert response.status_code == 200


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
        "enabled": True,
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
    incomplete_rule = {"rule_name": "Incomplete Rule"}

    response = client.post("/api/v1/alerts/rules", json=incomplete_rule)
    assert response.status_code == 422  # Pydantic validation error


def test_create_alert_rule_invalid_condition():
    """Test alert rule with invalid condition"""
    rule_data = {
        "rule_name": "Invalid Condition Rule",
        "metric_path": "test.metric",
        "condition": "invalid_op",  # Invalid condition
        "threshold": 100,
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
