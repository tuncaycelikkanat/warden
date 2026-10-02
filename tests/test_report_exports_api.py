"""Integration tests for SARIF and PDF export API endpoints and CLI commands."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session

from core.infra.database import engine
from core.main import app
from core.models.audit import AuditReport


def test_api_report_sarif_export() -> None:
    # Seed an audit report in DB
    with Session(engine) as session:
        report = AuditReport(
            repo_path="/test/repo/sarif",
            total_score=82,
            grade="B",
            profile_signature="FastAPI Service",
            layer1_score=80,
            layer2_score=85,
            raw_data={
                "scorecard": {"total_score": 82, "grade": "B", "layer1_score": 80},
                "layer1": {
                    "entropy": {
                        "findings": [
                            {
                                "file": "app/config.py",
                                "line": 22,
                                "variable_name": "SECRET_KEY",
                                "masked_value": "secr***",
                                "entropy_score": 4.7,
                            }
                        ]
                    }
                },
            },
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        report_id = report.id

    client = TestClient(app)
    response = client.get(f"/api/v1/dashboard/report/{report_id}/sarif")
    assert response.status_code == 200
    assert "application/sarif+json" in response.headers.get("content-type", "")

    data = response.json()
    assert data["version"] == "2.1.0"
    results = data["runs"][0]["results"]
    assert len(results) >= 1
    assert results[0]["ruleId"] == "WARDEN-SEC-001"


def test_api_report_pdf_export() -> None:
    with Session(engine) as session:
        report = AuditReport(
            repo_path="/test/repo/pdf",
            total_score=91,
            grade="A",
            profile_signature="CLI Application",
            layer1_score=90,
            layer2_score=92,
            raw_data={
                "scorecard": {"total_score": 91, "grade": "A", "layer1_score": 90},
            },
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        report_id = report.id

    client = TestClient(app)
    response = client.get(f"/api/v1/dashboard/report/{report_id}/pdf")
    assert response.status_code == 200
    assert "application/pdf" in response.headers.get("content-type", "")
    assert response.content.startswith(b"%PDF-")


def test_cli_export_sarif_command(tmp_path: Path) -> None:
    from core.main import _run_export_sarif

    # Create dummy audit in DB
    with Session(engine) as session:
        report = AuditReport(
            repo_path=str(tmp_path),
            total_score=75,
            grade="C",
            profile_signature="Test",
            layer1_score=75,
            layer2_score=-1,
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        rep_id = report.id

    out_file = tmp_path / "cli_results.sarif"
    _run_export_sarif(target=str(tmp_path), output=str(out_file), audit_id=rep_id)

    assert out_file.exists()
    content = json.loads(out_file.read_text(encoding="utf-8"))
    assert content["version"] == "2.1.0"


def test_cli_export_pdf_command(tmp_path: Path) -> None:
    from core.main import _run_export_pdf

    with Session(engine) as session:
        report = AuditReport(
            repo_path=str(tmp_path),
            total_score=85,
            grade="B",
            profile_signature="Test",
            layer1_score=85,
            layer2_score=-1,
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        rep_id = report.id

    out_pdf = tmp_path / "cli_report.pdf"
    _run_export_pdf(target=str(tmp_path), output=str(out_pdf), audit_id=rep_id)

    assert out_pdf.exists()
    assert out_pdf.stat().st_size > 2000
    assert out_pdf.read_bytes().startswith(b"%PDF-")
