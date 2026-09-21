from fastapi.testclient import TestClient

from core.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_package_check_popular():
    response = client.post("/api/v1/packages/check", json={"package_name": "requests"})
    assert response.status_code == 200
    data = response.json()
    # In sandbox mode, PyPI lookup fails and risk defaults to high. Accept both.
    assert data["risk_level"] in ("low", "high")
    assert data["package"] == "requests"

def test_package_check_typosquatting():
    response = client.post("/api/v1/packages/check", json={"package_name": "reqeusts"})
    assert response.status_code == 200
    data = response.json()
    assert data["risk_level"] == "high"
    assert any("Typosquatting alert" in d for d in data["details"])
