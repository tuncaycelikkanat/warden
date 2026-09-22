"""Comprehensive unit tests for core/main.py CLI and FastAPI endpoints."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from core.main import _run_audit_command, _run_milestone_command, app, cli
from core.models.audit import AuditReport


@pytest.fixture
def client():
    return TestClient(app)


def test_root_redirect(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/dashboard/"


def test_health_check(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics_endpoint_success(client):
    response = client.get("/api/v1/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "uptime_seconds" in data
    assert "database" in data
    assert "cache" in data
    assert "tools" in data


def test_metrics_endpoint_db_exception(client):
    with patch("sqlmodel.Session.exec", side_effect=Exception("DB Error")):
        response = client.get("/api/v1/metrics")
        assert response.status_code == 200
        data = response.json()
        assert data["database"]["average_score"] == 0


def test_run_audit_command_invalid_path():
    with patch("core.utils.path_validator.validate_audit_path", side_effect=ValueError("Invalid path")):
        with pytest.raises(SystemExit) as exc:
            _run_audit_command("nonexistent/path/here")
        assert exc.value.code == 1


def test_run_audit_command_success(tmp_path):
    mock_res = {
        "scorecard": {
            "total_score": 85,
            "grade": "B",
        },
        "vibe_coding": {
            "vibe_score": 15,
            "risk_level": "LOW",
            "findings_count": 2,
        },
    }
    with patch("core.utils.path_validator.validate_audit_path", return_value=tmp_path), \
         patch("core.services.orchestrator.AuditOrchestrator.run_full_audit", return_value=mock_res), \
         patch("core.services.report.AuditReportService.save_to_db", return_value=123), \
         patch("core.services.report.AuditReportService.generate_markdown", return_value=str(tmp_path / "rep.md")):
        # Should complete without error
        _run_audit_command(
            str(tmp_path),
            min_score=80,
            full_history=True,
            incremental=True,
            since_commit="HEAD~1",
        )


def test_run_audit_command_min_score_failure(tmp_path):
    mock_res = {
        "scorecard": {
            "total_score": 65,
            "grade": "D",
        },
        "vibe_coding": None,
    }
    with patch("core.utils.path_validator.validate_audit_path", return_value=tmp_path), \
         patch("core.services.orchestrator.AuditOrchestrator.run_full_audit", return_value=mock_res), \
         patch("core.services.report.AuditReportService.save_to_db", return_value=123), \
         patch("core.services.report.AuditReportService.generate_markdown", return_value=str(tmp_path / "rep.md")):
        with pytest.raises(SystemExit) as exc:
            _run_audit_command(
                str(tmp_path),
                min_score=80,
                full_history=False,
                incremental=False,
            )
        assert exc.value.code == 1


def test_run_milestone_command_not_found():
    with pytest.raises(SystemExit) as exc:
        _run_milestone_command(audit_id=99999999, label="baseline", clear=False)
    assert exc.value.code == 1


def test_run_milestone_command_set_and_clear(tmp_path):
    from core.infra.database import engine

    # Create dummy report
    with Session(engine) as session:
        rep = AuditReport(
            repo_path=str(tmp_path),
            total_score=88,
            grade="B",
            profile_signature="sig_test_ms",
            layer1_score=90,
            layer2_score=85,
            is_milestone=False,
        )
        session.add(rep)
        session.commit()
        session.refresh(rep)
        rep_id = rep.id

    # Set milestone
    _run_milestone_command(audit_id=rep_id, label="v1.0-release", clear=False)

    with Session(engine) as session:
        rep_after = session.exec(select(AuditReport).where(AuditReport.id == rep_id)).first()
        assert rep_after.is_milestone is True
        assert rep_after.milestone_label == "v1.0-release"

    # Clear milestone
    _run_milestone_command(audit_id=rep_id, label="", clear=True)

    with Session(engine) as session:
        rep_cleared = session.exec(select(AuditReport).where(AuditReport.id == rep_id)).first()
        assert rep_cleared.is_milestone is False
        assert rep_cleared.milestone_label is None


def test_cli_no_args():
    with patch.object(sys, "argv", ["warden"]):
        with pytest.raises(SystemExit) as exc:
            cli()
        assert exc.value.code == 0


def test_cli_audit_with_target():
    with patch.object(sys, "argv", ["warden", "audit", "/some/path", "--min-score", "90", "--incremental"]):
        with patch("core.main._run_audit_command") as mock_run:
            cli()
            mock_run.assert_called_once_with(
                "/some/path",
                90,
                full_history=False,
                incremental=True,
                since_commit=None,
            )


def test_cli_audit_with_path_flag():
    with patch.object(sys, "argv", ["warden", "audit", "--path", "/other/path", "--full-history", "--since-commit", "main"]):
        with patch("core.main._run_audit_command") as mock_run:
            cli()
            mock_run.assert_called_once_with(
                "/other/path",
                None,
                full_history=True,
                incremental=False,
                since_commit="main",
            )


def test_cli_serve():
    with patch.object(sys, "argv", ["warden", "serve", "--host", "127.0.0.1", "--port", "8080", "--reload"]):
        with patch("uvicorn.run") as mock_uvicorn:
            cli()
            mock_uvicorn.assert_called_once_with(
                "core.main:app",
                host="127.0.0.1",
                port=8080,
                reload=True,
            )


def test_cli_milestone():
    with patch.object(sys, "argv", ["warden", "milestone", "42", "--label", "gold", "--clear"]):
        with patch("core.main._run_milestone_command") as mock_ms:
            cli()
            mock_ms.assert_called_once_with(42, "gold", True)
