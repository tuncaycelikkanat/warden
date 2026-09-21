from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from core.main import app

client = TestClient(app)


def test_scan_file_not_found():
    response = client.post("/api/v1/scan", json={"file_path": "non_existent_file.py"})
    assert response.status_code == 404
    assert response.json()["detail"] == "File not found"


def test_scan_file_success(tmp_path: Path):
    test_file = tmp_path / "sample.py"
    test_file.write_text("import os\nprint('hello')\n")

    response = client.post("/api/v1/scan", json={"file_path": str(test_file)})
    assert response.status_code == 200
    data = response.json()
    assert "risk_level" in data
    assert "findings" in data
    assert "scan_id" in data


def test_audit_repo_not_found():
    response = client.post("/api/v1/audit", json={"repo_path": "/non/existent/repo/path"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Repo not found"


def test_audit_repo_success(tmp_path: Path):
    mock_audit_res = {
        "scorecard": {
            "total_score": 95,
            "grade": "A+",
            "layer1_score": 58,
            "layer2_score": 37,
            "group_scores": {},
            "breakdown": {"member_scores": {}, "layer2_raw": []},
        }
    }

    with patch("core.services.orchestrator.AuditOrchestrator.run_full_audit", new_callable=AsyncMock) as mock_orch, \
         patch("core.services.report.AuditReportService.save_to_db", return_value=123), \
         patch("core.services.report.AuditReportService.generate_markdown", return_value="/path/to/report.md"):

        mock_orch.return_value = mock_audit_res

        response = client.post("/api/v1/audit", json={"repo_path": str(tmp_path)})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["db_id"] == 123
        assert data["md_path"] == "/path/to/report.md"
