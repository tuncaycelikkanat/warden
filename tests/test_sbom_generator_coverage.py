"""Extended coverage tests for SBOMGeneratorService — targeting uncovered lines."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from core.services.sbom_generator import CycloneDXBOM, SBOMComponent, SBOMGeneratorService


class TestSBOMGeneratorCoverage:
    """Coverage-targeted tests for uncovered SBOM generator paths."""

    def setup_method(self) -> None:
        self.service = SBOMGeneratorService()

    def test_parse_uv_lock_returns_pinned_components(self, tmp_path: Path) -> None:
        """uv.lock TOML parsed correctly; pinned components returned."""
        lock_content = textwrap.dedent("""\
            [[package]]
            name = "fastapi"
            version = "0.115.0"

            [[package]]
            name = "httpx"
            version = "0.27.0"
        """)
        (tmp_path / "uv.lock").write_text(lock_content, encoding="utf-8")
        bom = self.service.generate_sbom(tmp_path)
        names = {c.name for c in bom.components}
        assert "fastapi" in names
        assert "httpx" in names

    def test_parse_uv_lock_skips_packages_without_name(self, tmp_path: Path) -> None:
        """Packages missing a name key are silently skipped."""
        lock_content = textwrap.dedent("""\
            [[package]]
            version = "1.0.0"

            [[package]]
            name = "pydantic"
            version = "2.9.0"
        """)
        (tmp_path / "uv.lock").write_text(lock_content, encoding="utf-8")
        bom = self.service.generate_sbom(tmp_path)
        names = {c.name for c in bom.components}
        assert "pydantic" in names
        assert len(bom.components) == 1

    def test_parse_uv_lock_handles_corrupt_toml_gracefully(self, tmp_path: Path) -> None:
        """A corrupt uv.lock falls back to requirements.txt without crashing."""
        (tmp_path / "uv.lock").write_text("NOT_VALID_TOML = [[[broken", encoding="utf-8")
        (tmp_path / "requirements.txt").write_text("click==8.1.7\n", encoding="utf-8")
        bom = self.service.generate_sbom(tmp_path)
        assert isinstance(bom, CycloneDXBOM)

    def test_extract_metadata_handles_corrupt_pyproject(self, tmp_path: Path) -> None:
        """Corrupt pyproject.toml in metadata path does not crash the service."""
        (tmp_path / "pyproject.toml").write_text("INVALID = [[[broken TOML", encoding="utf-8")
        bom = self.service.generate_sbom(tmp_path)
        assert bom.metadata["component"]["name"] == tmp_path.name

    def test_dependency_groups_parsed_as_optional(self, tmp_path: Path) -> None:
        """PEP 735 dependency-groups are parsed and marked optional scope."""
        pyproject_content = textwrap.dedent("""\
            [project]
            name = "myapp"
            version = "1.0.0"
            dependencies = ["fastapi>=0.115"]

            [dependency-groups]
            dev = ["pytest>=8.0", "ruff>=0.6"]
        """)
        (tmp_path / "pyproject.toml").write_text(pyproject_content, encoding="utf-8")
        bom = self.service.generate_sbom(tmp_path)
        names_scopes = {c.name.lower(): c.scope for c in bom.components}
        assert "fastapi" in names_scopes
        assert names_scopes.get("pytest") == "optional"
        assert names_scopes.get("ruff") == "optional"

    def test_optional_dependencies_deduplication(self, tmp_path: Path) -> None:
        """A package in both main deps and optional deps appears only once."""
        pyproject_content = textwrap.dedent("""\
            [project]
            name = "myapp"
            version = "0.1"
            dependencies = ["httpx>=0.27"]

            [project.optional-dependencies]
            extra = ["httpx>=0.27", "pydantic>=2"]
        """)
        (tmp_path / "pyproject.toml").write_text(pyproject_content, encoding="utf-8")
        bom = self.service.generate_sbom(tmp_path)
        names = [c.name.lower() for c in bom.components]
        assert names.count("httpx") == 1

    def test_export_json_creates_nested_output_dir(self, tmp_path: Path) -> None:
        """export_json creates missing parent directories before writing."""
        (tmp_path / "requirements.txt").write_text("rich==13.7.0\n", encoding="utf-8")
        nested_output = tmp_path / "reports" / "sbom" / "bom.json"
        result = self.service.export_json(tmp_path, output_path=nested_output)
        assert nested_output.exists()
        loaded = json.loads(nested_output.read_text())
        assert loaded["bomFormat"] == "CycloneDX"
        assert "rich" in result

    def test_export_json_without_output_path_returns_string(self, tmp_path: Path) -> None:
        """export_json without output_path returns JSON string, writes no file."""
        (tmp_path / "requirements.txt").write_text("click==8.1.7\n", encoding="utf-8")
        json_str = self.service.export_json(tmp_path, output_path=None)
        parsed = json.loads(json_str)
        assert parsed["specVersion"] == "1.5"
        assert not (tmp_path / "bom.json").exists()

    def test_bom_with_no_components_has_empty_dependencies(self, tmp_path: Path) -> None:
        """When no components are found, dependency section is empty."""
        bom = self.service.generate_sbom(tmp_path)
        assert bom.dependencies == []

    def test_component_with_description_in_dict(self) -> None:
        """Description field is present in to_dict() output when set."""
        comp = SBOMComponent(name="rich", version="13.7.0", description="Terminal UI library")
        d = comp.to_dict()
        assert d["description"] == "Terminal UI library"

    def test_component_without_description_not_in_dict(self) -> None:
        """Description field is absent from to_dict() when not set."""
        comp = SBOMComponent(name="click", version="8.1.7")
        d = comp.to_dict()
        assert "description" not in d
