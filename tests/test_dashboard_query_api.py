"""Integration tests for Natural Language Dashboard Query API and CLI command."""

import json

import pytest
from fastapi.testclient import TestClient

from core.main import _run_query_command, app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_api_dashboard_query_valid(client: TestClient) -> None:
    payload = {"query": "En son yapılan denetimleri göster"}
    response = client.post("/api/v1/dashboard/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "sql" in data
    assert "columns" in data
    assert "data" in data
    assert "chart_type" in data
    assert "execution_time_ms" in data


def test_api_dashboard_query_security_violation_returns_400(client: TestClient) -> None:
    # Malicious injection attempting to drop tables
    payload = {"query": "DROP TABLE auditreport"}
    # The service will sanitize and reject non-SELECT
    response = client.post("/api/v1/dashboard/query", json=payload)
    # Natural language fallback may generate a safe query, but if raw SQL injection is tested:
    # Let's test by mocking or asking a direct malicious SQL
    from unittest.mock import patch
    with patch("core.services.nl_query_service.NaturalLanguageQueryService.generate_sql", return_value=("DROP TABLE auditreport", "", "")):
        bad_response = client.post("/api/v1/dashboard/query", json=payload)
        assert bad_response.status_code == 400
        assert "Güvenlik İhlali" in bad_response.json()["detail"]


def test_cli_query_command_stdout(capsys: pytest.CaptureFixture) -> None:
    _run_query_command("En düşük kaliteli projeler", as_json=False)
    captured = capsys.readouterr()
    assert "Soru:" in captured.out
    assert "SQL:" in captured.out
    assert "Önerilen Grafik:" in captured.out


def test_cli_query_command_json(capsys: pytest.CaptureFixture) -> None:
    _run_query_command("Not dağılımı", as_json=True)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "sql" in data
    assert "chart_type" in data
    assert "data" in data
