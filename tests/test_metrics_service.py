"""Tests for MetricsCollectorService and Prometheus exposition."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from core.infra.database import engine
from core.main import app
from core.models.audit import AuditReport
from core.services.metrics_service import MetricsCollectorService


@pytest.fixture
def metrics_service() -> MetricsCollectorService:
    return MetricsCollectorService(start_time=100.0)


class TestMetricsService:
    def test_uptime_seconds(self, metrics_service: MetricsCollectorService) -> None:
        uptime = metrics_service.get_uptime_seconds()
        assert uptime > 0.0

    def test_get_tool_status(self, metrics_service: MetricsCollectorService) -> None:
        tools = metrics_service.get_tool_status()
        assert isinstance(tools, dict)
        assert "gitleaks" in tools
        assert "semgrep" in tools
        assert "hypothesis" in tools
        assert all(val in (0, 1) for val in tools.values())

    def test_get_database_metrics_with_data(self, metrics_service: MetricsCollectorService) -> None:
        # Insert a sample report
        with Session(engine) as session:
            report = AuditReport(
                repo_path="/test/repo/metrics",
                total_score=85,
                grade="A",
                profile_signature="test_sig",
                layer1_score=80,
                layer2_score=90,
                raw_data={"scorecard": {"tech_debt": {"remediation_estimate": {"total_hours": 7.5}}}},
            )
            session.add(report)
            session.commit()

        metrics = metrics_service.get_database_metrics()
        assert metrics["total_audits"] >= 1
        assert metrics["average_score"] > 0
        assert metrics["last_score"] >= 0
        assert metrics["latest_tech_debt_hours"] >= 0
        assert "grades" in metrics
        assert metrics["grades"]["A"] >= 1

    def test_collect_metrics_data_structure(self, metrics_service: MetricsCollectorService) -> None:
        data = metrics_service.collect_metrics_data(uptime_override=42.0)
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"
        assert data["uptime_seconds"] == 42.0
        assert "database" in data
        assert "tools" in data
        assert "cache" in data

    def test_generate_prometheus_exposition_format(self, metrics_service: MetricsCollectorService) -> None:
        output = metrics_service.generate_prometheus_exposition(uptime_override=120.5)
        assert isinstance(output, str)
        assert output.endswith("\n") or output.endswith("1")

        # Standard HELP and TYPE comments
        assert "# HELP warden_uptime_seconds" in output
        assert "# TYPE warden_uptime_seconds gauge" in output
        assert "warden_uptime_seconds 120.5" in output

        assert "# HELP warden_total_audits_count" in output
        assert "# TYPE warden_total_audits_count counter" in output

        assert "# HELP warden_audits_by_grade_total" in output
        assert 'warden_audits_by_grade_total{grade="A"}' in output
        assert 'warden_audits_by_grade_total{grade="F"}' in output

        assert "# HELP warden_tool_availability" in output
        assert 'warden_tool_availability{tool="semgrep"}' in output

        assert "# HELP warden_cache_backend_info" in output
        assert "warden_cache_backend_info{backend=" in output

        assert "# HELP warden_build_info" in output
        assert 'warden_build_info{version="0.1.0"' in output


class TestMetricsEndpoints:
    def test_prometheus_endpoint_plain_text(self) -> None:
        client = TestClient(app)
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")
        assert "warden_uptime_seconds" in response.text
        assert "warden_total_audits_count" in response.text

    def test_prometheus_alias_endpoint(self) -> None:
        client = TestClient(app)
        response = client.get("/api/v1/metrics/prometheus")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")
        assert "warden_uptime_seconds" in response.text

    def test_json_metrics_endpoint_backwards_compatibility(self) -> None:
        client = TestClient(app)
        response = client.get("/api/v1/metrics")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "uptime_seconds" in data
        assert "database" in data
        assert "tools" in data


class TestMetricsCLI:
    def test_run_metrics_command_stdout(self, capsys: pytest.CaptureFixture) -> None:
        from core.main import _run_metrics_command

        _run_metrics_command(as_json=False)
        captured = capsys.readouterr()
        assert "warden_uptime_seconds" in captured.out
        assert "warden_total_audits_count" in captured.out

    def test_run_metrics_command_json(self, capsys: pytest.CaptureFixture) -> None:
        import json
        from core.main import _run_metrics_command

        _run_metrics_command(as_json=True)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "healthy"
        assert "uptime_seconds" in data
