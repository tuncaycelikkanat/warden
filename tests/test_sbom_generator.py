"""Unit tests for SBOMGeneratorService (CycloneDX v1.5 JSON)."""

from __future__ import annotations

import json
from pathlib import Path

from core.services.sbom_generator import CycloneDXBOM, SBOMComponent, SBOMGeneratorService


class TestSBOMGenerator:
    """Tests for CycloneDX SBOM generator."""

    def setup_method(self):
        self.service = SBOMGeneratorService()

    def test_component_purl_generation(self):
        """Test component PURL formatting according to standard."""
        comp = SBOMComponent(name="FastAPI", version="0.115.0", scope="required")
        assert comp.name == "FastAPI"
        assert comp.bom_ref == "pkg:pypi/fastapi@0.115.0"
        assert comp.purl == "pkg:pypi/fastapi@0.115.0"
        d = comp.to_dict()
        assert d["type"] == "library"
        assert d["version"] == "0.115.0"
        assert d["scope"] == "required"

    def test_unpinned_component_purl(self):
        """Test unpinned component defaults."""
        comp = SBOMComponent(name="requests")
        assert comp.version == "unpinned"
        assert comp.purl == "pkg:pypi/requests@unpinned"

    def test_cyclonedx_bom_structure(self):
        """Test CycloneDX BOM structure complies with v1.5 standard."""
        comp1 = SBOMComponent(name="pydantic", version="2.9.0")
        comp2 = SBOMComponent(name="pytest", version="8.3.0", scope="optional")

        bom = CycloneDXBOM(
            serial_number="urn:uuid:12345678-1234-5678-1234-567812345678",
            version=1,
            metadata={"component": {"name": "sample_app", "version": "1.0.0", "type": "application", "bom-ref": "sample_ref"}},
            components=[comp1, comp2],
            dependencies=[{"ref": "sample_ref", "dependsOn": [comp1.bom_ref, comp2.bom_ref]}],
        )

        bom_dict = bom.to_dict()
        assert bom_dict["bomFormat"] == "CycloneDX"
        assert bom_dict["specVersion"] == "1.5"
        assert bom_dict["version"] == 1
        assert bom_dict["serialNumber"].startswith("urn:uuid:")
        assert len(bom_dict["components"]) == 2
        assert len(bom_dict["dependencies"]) == 1

        json_str = bom.to_json()
        parsed = json.loads(json_str)
        assert parsed["specVersion"] == "1.5"
        assert parsed["components"][0]["name"] == "pydantic"

    def test_generate_sbom_from_requirements(self, tmp_path: Path):
        """Test generating SBOM from requirements.txt."""
        req_content = (
            "fastapi==0.110.0\n"
            "uvicorn[standard]>=0.28.0\n"
            "httpx\n"
        )
        (tmp_path / "requirements.txt").write_text(req_content, encoding="utf-8")

        bom = self.service.generate_sbom(tmp_path)
        assert isinstance(bom, CycloneDXBOM)
        assert bom.bom_format == "CycloneDX"
        names = {c.name.lower() for c in bom.components}
        assert "fastapi" in names
        assert "uvicorn" in names
        assert "httpx" in names

    def test_generate_sbom_from_pyproject_toml(self, tmp_path: Path):
        """Test generating SBOM from pyproject.toml."""
        pyproject_content = (
            '[project]\n'
            'name = "my-awesome-tool"\n'
            'version = "2.4.1"\n'
            'dependencies = [\n'
            '    "click>=8.0.0",\n'
            '    "rich==13.7.0",\n'
            ']\n'
            '[project.optional-dependencies]\n'
            'dev = ["pytest>=8.0"]\n'
        )
        (tmp_path / "pyproject.toml").write_text(pyproject_content, encoding="utf-8")

        bom = self.service.generate_sbom(tmp_path)
        assert bom.metadata["component"]["name"] == "my-awesome-tool"
        assert bom.metadata["component"]["version"] == "2.4.1"

        names = {c.name.lower() for c in bom.components}
        assert "click" in names
        assert "rich" in names
        assert "pytest" in names

        # Verify pytest is marked optional
        pytest_comp = next(c for c in bom.components if c.name.lower() == "pytest")
        assert pytest_comp.scope == "optional"

    def test_export_json(self, tmp_path: Path):
        """Test exporting SBOM directly to a file."""
        (tmp_path / "requirements.txt").write_text("sqlmodel==0.0.16\n", encoding="utf-8")
        out_file = tmp_path / "output_bom.json"

        json_out = self.service.export_json(tmp_path, output_path=out_file)
        assert json_out
        assert out_file.exists()
        loaded = json.loads(out_file.read_text(encoding="utf-8"))
        assert loaded["bomFormat"] == "CycloneDX"
        assert loaded["components"][0]["name"] == "sqlmodel"
