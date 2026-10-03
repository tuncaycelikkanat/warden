"""Unit tests for PdfReportService executive summary generation."""

from pathlib import Path
from typing import Any

import pytest

from core.services.pdf_report_service import PdfReportService


@pytest.fixture
def pdf_service() -> PdfReportService:
    return PdfReportService()


@pytest.fixture
def sample_audit_data() -> dict:
    return {
        "repo_path": "/workspace/enterprise_service",
        "profile_signature": "FastAPI Microservice",
        "scorecard": {
            "total_score": 88,
            "grade": "B",
            "layer1_score": 85,
            "layer2_score": 92,
            "group_scores": {
                "security_supply_chain": 90.0,
                "code_health_test": 85.0,
                "structural_health": 88.0,
                "resilience_performance": 82.0,
                "dev_hygiene_devops": 95.0,
            },
        },
        "layer1": {
            "tech_debt": {
                "remediation_estimate": {
                    "total_hours": 12.5,
                    "total_days": 1.6,
                }
            },
            "entropy": {"findings": []},
            "circular_dependencies": {"cycles": []},
        },
        "layer1_5": {"vibe_score": 94.0},
    }


class TestPdfReportService:
    def test_generate_pdf_bytes_magic_bytes(self, pdf_service: PdfReportService, sample_audit_data: dict) -> None:
        pdf_bytes = pdf_service.generate_pdf_bytes(sample_audit_data, repo_path="/workspace/enterprise_service")
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 2000
        # Standard PDF magic bytes
        assert pdf_bytes.startswith(b"%PDF-")

    def test_generate_pdf_file(self, pdf_service: PdfReportService, sample_audit_data: dict, tmp_path: Path) -> None:
        output_path = tmp_path / "executive_report.pdf"
        saved = pdf_service.generate_pdf(sample_audit_data, output_path, repo_path="/workspace/enterprise_service")
        assert saved.exists()
        assert saved.is_file()
        assert saved.stat().st_size > 2000

    def test_generate_pdf_different_grades(self, pdf_service: PdfReportService) -> None:
        # Test Grade A
        data_a = {
            "scorecard": {"total_score": 95, "grade": "A", "layer1_score": 95},
        }
        bytes_a = pdf_service.generate_pdf_bytes(data_a, "repo_a")
        assert bytes_a.startswith(b"%PDF-")

        # Test Grade F with regression and secrets
        data_f = {
            "scorecard": {"total_score": 42, "grade": "F", "layer1_score": 40},
            "regression_warning": "Score dropped by 30 points",
            "layer1": {
                "entropy": {
                    "findings": [{"file": "auth.py", "line": 10, "variable_name": "KEY", "entropy_score": 4.9}]
                },
                "circular_dependencies": {
                    "cycles": [{"cycle_path": ["a", "b", "a"]}]
                },
            },
        }
        bytes_f = pdf_service.generate_pdf_bytes(data_f, "repo_f")
        assert bytes_f.startswith(b"%PDF-")

    def test_generate_pdf_sparse_data(self, pdf_service: PdfReportService) -> None:
        # Handles minimal dictionary without crashing
        sparse: dict[str, Any] = {}
        pdf_bytes = pdf_service.generate_pdf_bytes(sparse, "unknown_repo")
        assert pdf_bytes.startswith(b"%PDF-")
