"""Unit and integration tests for Section D4 BDD/Gherkin Scenario Documentation Generator."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from core.main import _run_bdd_command, app
from core.services.bdd_scenario_generator import (
    ASTScenarioExtractor,
    BDDFeature,
    BDDScenario,
    BDDScenarioGeneratorService,
    BDDStep,
    BDDSuiteReport,
)


class TestASTScenarioExtractor:
    """Verifies parsing of Python test ASTs into Given-When-Then specifications."""

    def test_extract_fixtures_and_setup_as_given(self):
        extractor = ASTScenarioExtractor()
        code = '''
def test_user_authentication(client, tmp_path):
    """Verifies that an authorized user can log in."""
    credentials = {"username": "admin", "password": "secret"}
    res = client.post("/login", json=credentials)
    assert res.status_code == 200
'''
        features = extractor.extract_from_source(code, "test_auth.py")
        assert len(features) == 1
        feature = features[0]
        assert len(feature.scenarios) == 1

        sc = feature.scenarios[0]
        assert sc.name == "User authentication"
        assert "Verifies that an authorized user can log in." in sc.description

        step_types = [s.step_type for s in sc.steps]
        # Should have Given, And (fixtures + setup), When (client.post), Then (assert)
        assert "Given" in step_types
        assert "When" in step_types
        assert "Then" in step_types

        # Check fixture extraction
        given_texts = [s.text for s in sc.steps if s.step_type in ("Given", "And")]
        assert any("API test client" in t for t in given_texts)
        assert any("temporary directory" in t for t in given_texts)
        assert any("credentials" in t for t in given_texts)

    def test_extract_comparisons_as_then(self):
        extractor = ASTScenarioExtractor()
        code = '''
def test_metrics_evaluation():
    score = 95
    assert score == 95
    assert score > 90
    assert score < 100
    assert "9" in str(score)
'''
        features = extractor.extract_from_source(code, "test_metrics.py")
        sc = features[0].scenarios[0]
        then_steps = [s for s in sc.steps if s.step_type in ("Then", "And")]

        texts = [s.text for s in then_steps]
        assert any("should equal 95" in t for t in texts)
        assert any("should be greater than 90" in t for t in texts)
        assert any("should be less than 100" in t for t in texts)
        assert any("should be included in" in t for t in texts)

    def test_extract_unary_not_and_boolean_asserts(self):
        extractor = ASTScenarioExtractor()
        code = '''
def test_flags():
    is_failed = False
    is_ready = True
    assert not is_failed
    assert is_ready
'''
        features = extractor.extract_from_source(code, "test_flags.py")
        sc = features[0].scenarios[0]
        texts = [s.text for s in sc.steps if s.step_type in ("Then", "And")]

        assert any("'is_failed' should be false" in t for t in texts)
        assert any("'is_ready' should be satisfied" in t for t in texts)

    def test_extract_pytest_raises_exception(self):
        extractor = ASTScenarioExtractor()
        code = '''
def test_error_condition():
    with pytest.raises(ValueError, match="Geçersiz"):
        do_something()
'''
        features = extractor.extract_from_source(code, "test_error.py")
        sc = features[0].scenarios[0]
        then_steps = [s.text for s in sc.steps if s.step_type in ("Then", "And")]

        assert any("ValueError exception should be raised with message matching ''Geçersiz''" in t for t in then_steps)

    def test_extract_test_classes_and_methods(self):
        extractor = ASTScenarioExtractor()
        code = '''
class TestSecurityScan:
    """Security scanner integration tests."""

    def test_cve_lookup(self):
        pass

    def test_secret_detection(self):
        pass
'''
        features = extractor.extract_from_source(code, "test_sec.py")
        assert len(features) == 1
        feat = features[0]
        assert "Security Scan" in feat.feature_name
        assert feat.description == "Security scanner integration tests."
        assert len(feat.scenarios) == 2
        assert feat.scenarios[0].name == "Cve lookup"
        assert feat.scenarios[1].name == "Secret detection"

    def test_infer_tags(self):
        extractor = ASTScenarioExtractor()
        tags_sec = extractor._infer_tags("tests/test_security_audit.py", "test_cve_injection")
        assert "security" in tags_sec
        assert "unit" in tags_sec

        tags_api = extractor._infer_tags("tests/test_api_dashboard.py", "test_get_metrics")
        assert "api" in tags_api
        assert "integration" in tags_api


class TestGherkinAndMarkdownFormatting:
    """Verifies conversion of BDD models into Gherkin .feature syntax and Markdown."""

    def test_scenario_to_gherkin(self):
        sc = BDDScenario(
            name="Verify valid audit",
            description="Audit scorecard meets minimum threshold",
            source_file="test_audit.py",
            test_function="test_valid_audit",
            line_number=10,
            tags=["unit", "quality_gate"],
            steps=[
                BDDStep("Given", "a project repository is initialized"),
                BDDStep("When", "the audit engine runs"),
                BDDStep("Then", "'score' should be greater than 80"),
                BDDStep("And", "'grade' should equal 'A'"),
            ],
        )

        gherkin = sc.to_gherkin()
        assert "@unit @quality_gate" in gherkin
        assert "Scenario: Verify valid audit" in gherkin
        assert "Given a project repository is initialized" in gherkin
        assert "When the audit engine runs" in gherkin
        assert "Then 'score' should be greater than 80" in gherkin
        assert "And 'grade' should equal 'A'" in gherkin

    def test_feature_to_gherkin(self):
        feat = BDDFeature(
            feature_name="Quality Gate Governance",
            description="As a DevOps Engineer\nI want automated quality gates\nSo that bad code is rejected",
            source_file="tests/test_gate.py",
            scenarios=[],
            tags=["governance", "ci"],
        )

        gherkin = feat.to_gherkin()
        assert "@governance @ci" in gherkin
        assert "Feature: Quality Gate Governance" in gherkin
        assert "As a DevOps Engineer" in gherkin

    def test_suite_report_to_markdown(self):
        feat = BDDFeature(
            feature_name="Sample Feature",
            description="Feature description",
            source_file="test_sample.py",
            scenarios=[
                BDDScenario(
                    name="Sample Scenario",
                    description="Scenario description",
                    source_file="test_sample.py",
                    test_function="test_sample",
                    line_number=5,
                    tags=["sample"],
                    steps=[BDDStep("Given", "setup"), BDDStep("When", "action"), BDDStep("Then", "check")],
                )
            ],
        )

        rep = BDDSuiteReport(
            target_path="tests",
            total_features=1,
            total_scenarios=1,
            total_steps=3,
            features=[feat],
        )

        md = rep.to_markdown()
        assert "# 🥒 WARDEN BDD Senaryo & Test Dokümantasyon Kataloğu" in md
        assert "Sample Feature" in md
        assert "Sample Scenario" in md
        assert "```gherkin" in md


class TestBDDScenarioGeneratorService:
    """Verifies file discovery, report synthesis, and export functionality."""

    def test_generate_from_single_file(self):
        service = BDDScenarioGeneratorService()
        rep = service.generate_from_path("tests/test_score_anomaly.py")

        assert rep.total_features > 0
        assert rep.total_scenarios >= 10
        assert rep.total_steps > 30
        assert len(rep.features) == rep.total_features

    def test_export_feature_files_and_markdown(self, tmp_path):
        service = BDDScenarioGeneratorService()
        rep = service.generate_from_path("tests/test_score_anomaly.py")

        feature_dir = tmp_path / "features"
        exported = service.export_feature_files(rep, feature_dir)
        assert len(exported) == rep.total_features
        for p in exported:
            assert p.is_file()
            assert p.suffix == ".feature"
            assert "Feature:" in p.read_text(encoding="utf-8")

        md_file = tmp_path / "TEST_SCENARIOS.md"
        out_md = service.export_markdown_report(rep, md_file)
        assert out_md.is_file()
        assert "## 📦 Özellik:" in out_md.read_text(encoding="utf-8")


class TestBDDApiEndpoints:
    """Verifies REST API endpoints in core/api/dashboard.py."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_get_bdd_summary_endpoint(self):
        res = self.client.get("/api/v1/dashboard/bdd/summary?path=tests/test_score_anomaly.py")
        assert res.status_code == 200
        data = res.json()
        assert "total_features" in data
        assert "total_scenarios" in data
        assert "features" in data
        assert data["total_scenarios"] >= 10

    def test_post_bdd_generate_endpoint(self, tmp_path):
        payload = {
            "target_path": "tests/test_score_anomaly.py",
            "feature_dir": str(tmp_path / "features"),
            "markdown_output": str(tmp_path / "bdd.md"),
            "enrich_llm": False,
        }
        res = self.client.post("/api/v1/dashboard/bdd/generate", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert len(data["exported_feature_files"]) > 0
        assert Path(data["markdown_file"]).is_file()


class TestBDDCLICommand:
    """Verifies warden bdd CLI command."""

    def test_cli_bdd_json_output(self, capsys):
        _run_bdd_command("tests/test_score_anomaly.py", as_json=True)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "total_features" in data
        assert "features" in data

    def test_cli_bdd_export_flags(self, tmp_path, capsys):
        f_dir = tmp_path / "features"
        m_file = tmp_path / "scenarios.md"

        _run_bdd_command(
            "tests/test_score_anomaly.py",
            feature_dir=str(f_dir),
            output_file=str(m_file),
            as_json=False,
        )

        captured = capsys.readouterr()
        assert "WARDEN BDD & GHERKIN" in captured.out
        assert f_dir.is_dir()
        assert m_file.is_file()

    def test_cli_bdd_invalid_path(self, capsys):
        _run_bdd_command("non_existent_directory_xyz")
        captured = capsys.readouterr()
        assert "[!] Hata:" in captured.out
