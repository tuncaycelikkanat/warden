"""Unit tests for SarifReportService and OASIS SARIF v2.1.0 export."""

import json
from pathlib import Path

import pytest

from core.services.sarif_service import SARIF_SCHEMA, SARIF_VERSION, SarifReportService


@pytest.fixture
def sarif_service() -> SarifReportService:
    return SarifReportService()


@pytest.fixture
def sample_audit_data() -> dict:
    return {
        "repo_path": "/workspace/sample_app",
        "scorecard": {
            "total_score": 75,
            "grade": "C",
            "layer1_score": 70,
            "layer2_score": 80,
        },
        "layer1": {
            "entropy": {
                "findings": [
                    {
                        "file": "/workspace/sample_app/core/auth.py",
                        "line": 42,
                        "variable_name": "API_KEY",
                        "masked_value": "AIza********************",
                        "entropy_score": 4.85,
                    }
                ]
            },
            "security": {
                "findings": [
                    {
                        "path": "/workspace/sample_app/db.py",
                        "start": {"line": 15},
                        "check_id": "python.lang.security.audit.sqli",
                        "extra": {"message": "Possible SQL injection detected"},
                    }
                ]
            },
            "circular_dependencies": {
                "cycles": [
                    {"cycle_path": ["module_a", "module_b", "module_a"], "length": 2}
                ]
            },
            "tech_debt": {
                "hotspots": [
                    {
                        "file": "/workspace/sample_app/complex.py",
                        "function_name": "heavy_processor",
                        "line": 88,
                        "complexity": 18,
                    }
                ]
            },
            "dependency_health": {
                "typosquatting_warnings": [
                    {
                        "package": "reqeusts",
                        "target_package": "requests",
                        "similarity_score": 0.94,
                    }
                ]
            },
        },
        "layer1_5": {
            "slop_findings": [
                {
                    "file": "/workspace/sample_app/ai_helper.py",
                    "line": 10,
                    "pattern_description": "Excessive repetitive try/except boilerplate",
                }
            ]
        },
    }


class TestSarifReportService:
    def test_sarif_schema_and_version(self, sarif_service: SarifReportService, sample_audit_data: dict) -> None:
        doc = sarif_service.generate_sarif(sample_audit_data, repo_path="/workspace/sample_app")
        assert doc["$schema"] == SARIF_SCHEMA
        assert doc["version"] == SARIF_VERSION
        assert "runs" in doc
        assert len(doc["runs"]) == 1

    def test_sarif_tool_rules_catalog(self, sarif_service: SarifReportService, sample_audit_data: dict) -> None:
        doc = sarif_service.generate_sarif(sample_audit_data)
        driver = doc["runs"][0]["tool"]["driver"]
        assert driver["name"] == "WARDEN"
        assert driver["version"] == "0.1.0"

        rule_ids = {r["id"] for r in driver["rules"]}
        expected_rules = {
            "WARDEN-SEC-001",
            "WARDEN-SEC-002",
            "WARDEN-ARCH-001",
            "WARDEN-QUAL-001",
            "WARDEN-SUPPLY-001",
            "WARDEN-VIBE-001",
        }
        assert expected_rules.issubset(rule_ids)

    def test_sarif_results_extraction(self, sarif_service: SarifReportService, sample_audit_data: dict) -> None:
        doc = sarif_service.generate_sarif(sample_audit_data, repo_path="/workspace/sample_app")
        results = doc["runs"][0]["results"]
        assert len(results) == 6

        # Verify secret finding
        sec_findings = [r for r in results if r["ruleId"] == "WARDEN-SEC-001"]
        assert len(sec_findings) == 1
        assert sec_findings[0]["level"] == "error"
        loc = sec_findings[0]["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"]["uri"] == "core/auth.py"
        assert loc["region"]["startLine"] == 42

        # Verify SQLi finding
        sqli_findings = [r for r in results if r["ruleId"] == "WARDEN-SEC-002"]
        assert len(sqli_findings) == 1
        assert "SQL injection" in sqli_findings[0]["message"]["text"]

        # Verify circular import finding
        arch_findings = [r for r in results if r["ruleId"] == "WARDEN-ARCH-001"]
        assert len(arch_findings) == 1
        assert arch_findings[0]["level"] == "warning"

        # Verify complexity finding
        cc_findings = [r for r in results if r["ruleId"] == "WARDEN-QUAL-001"]
        assert len(cc_findings) == 1
        assert "heavy_processor" in cc_findings[0]["message"]["text"]

    def test_sarif_export_to_file(self, sarif_service: SarifReportService, sample_audit_data: dict, tmp_path: Path) -> None:
        out_file = tmp_path / "warden-results.sarif"
        saved = sarif_service.export_to_file(sample_audit_data, out_file, repo_path="/workspace/sample_app")
        assert saved.exists()

        content = json.loads(saved.read_text(encoding="utf-8"))
        assert content["version"] == "2.1.0"
        assert len(content["runs"][0]["results"]) == 6
