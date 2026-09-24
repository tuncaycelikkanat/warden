from unittest.mock import patch

from fastapi.testclient import TestClient

from core.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_package_check_popular():
    mock_ret = {"package": "requests", "risk_level": "low", "risk_score": 0, "details": []}
    with patch("core.services.package.PackageCheckerService.calculate_risk_score", return_value=mock_ret):
        response = client.post("/api/v1/packages/check", json={"package_name": "requests"})
        assert response.status_code == 200
        data = response.json()
        assert data["risk_level"] == "low"
        assert data["package"] == "requests"

def test_package_check_typosquatting():
    mock_ret = {
        "package": "reqeusts",
        "risk_level": "high",
        "risk_score": 50,
        "details": ["Typosquatting alert: similar to requests"],
    }
    with patch("core.services.package.PackageCheckerService.calculate_risk_score", return_value=mock_ret):
        response = client.post("/api/v1/packages/check", json={"package_name": "reqeusts"})
        assert response.status_code == 200
        data = response.json()
        assert data["risk_level"] == "high"
        assert any("Typosquatting alert" in d for d in data["details"])


def test_dashboard_ui_served():
    """Verifies that the standalone HTML dashboard is served at /dashboard/."""
    response = client.get("/dashboard/")
    assert response.status_code == 200
    assert "WARDEN" in response.text
    assert "chart.js" in response.text.lower()


def test_dashboard_summary_api():
    """Verifies that GET /api/v1/dashboard/summary returns valid summary stats."""
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    assert "total_repos" in data
    assert "total_audits" in data
    assert "average_score" in data
    assert "grade_distribution" in data


def test_dashboard_repos_api():
    """Verifies that GET /api/v1/dashboard/repos returns repository list."""
    response = client.get("/api/v1/dashboard/repos")
    assert response.status_code == 200
    data = response.json()
    assert "repos" in data
    assert "total" in data


def test_metrics_api():
    """Verifies that GET /api/v1/metrics returns system health and tools status."""
    response = client.get("/api/v1/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "uptime_seconds" in data
    assert "database" in data
    assert "tools" in data
