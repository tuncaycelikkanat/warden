"""Unit tests for the ProjectTypeClassifier service (C5)."""

from pathlib import Path

import pytest

from core.services.project_classifier import (
    ProjectTypeClassifier,
)


class TestProjectTypeClassifier:
    @pytest.fixture
    def classifier(self) -> ProjectTypeClassifier:
        return ProjectTypeClassifier()

    def test_classify_fastapi_project(self, classifier: ProjectTypeClassifier, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("""
[project]
name = "my-fastapi-service"
dependencies = ["fastapi>=0.115.0", "uvicorn>=0.30.0"]
""")
        api_dir = tmp_path / "api"
        api_dir.mkdir()
        (api_dir / "routes.py").write_text("from fastapi import APIRouter\nrouter = APIRouter()\n")

        res = classifier.classify(tmp_path)
        assert res.archetype == "FASTAPI_API"
        assert res.confidence >= 0.7
        assert any("fastapi" in t for t in res.matched_traits)
        assert "FASTAPI_API" in res.suggested_weights or "group_security" in res.suggested_weights

    def test_classify_django_project(self, classifier: ProjectTypeClassifier, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("django>=4.2.0\npsycopg2-binary>=2.9.0\n")
        (tmp_path / "manage.py").write_text("#!/usr/bin/env python\nimport os\n")

        res = classifier.classify(tmp_path)
        assert res.archetype == "DJANGO_WEB"
        assert res.confidence >= 0.8
        assert "file:manage.py" in res.matched_traits

    def test_classify_cli_tool_project(self, classifier: ProjectTypeClassifier, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("""
[project]
name = "my-cli"
dependencies = ["typer>=0.12.0", "rich>=13.0.0"]

[project.scripts]
mycli = "my_cli.cli:main"
""")
        res = classifier.classify(tmp_path)
        assert res.archetype == "CLI_TOOL"
        assert res.confidence >= 0.6
        assert any("console_scripts" in t for t in res.matched_traits)

    def test_classify_data_science_project(
        self, classifier: ProjectTypeClassifier, tmp_path: Path
    ) -> None:
        (tmp_path / "requirements.txt").write_text("torch>=2.0.0\npandas>=2.0.0\nscikit-learn>=1.3.0\n")
        (tmp_path / "analysis.ipynb").write_text("{'cells': []}")

        res = classifier.classify(tmp_path)
        assert res.archetype == "DATA_SCIENCE_ML"
        assert res.confidence >= 0.7
        assert any("ml_libs" in t for t in res.matched_traits)

    def test_classify_generic_backend_fallback(
        self, classifier: ProjectTypeClassifier, tmp_path: Path
    ) -> None:
        (tmp_path / "domain.py").write_text("class Logic:\n    pass\n")

        res = classifier.classify(tmp_path)
        assert res.archetype == "GENERIC_BACKEND"
        assert res.confidence == 0.60
        assert "default:generic_python_structure" in res.matched_traits

    def test_to_dict_structure(self, classifier: ProjectTypeClassifier, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("fastapi>=0.115.0\n")
        res = classifier.classify(tmp_path)
        d = res.to_dict()
        assert "archetype" in d
        assert "label" in d
        assert "confidence" in d
        assert "matched_traits" in d
        assert "recommended_rubric" in d
        assert "suggested_weights" in d
