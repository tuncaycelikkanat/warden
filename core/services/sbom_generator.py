"""CycloneDX Software Bill of Materials (SBOM) generator for WARDEN.

Generates industry-standard CycloneDX v1.5 JSON SBOMs covering application
manifests (requirements.txt, pyproject.toml, uv.lock, poetry.lock), package
URLs (purl), supply chain integrity metadata, and dependency relationship graphs.
"""

from __future__ import annotations

import json
import logging
import tomllib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.services.dependency_health import DependencyHealthService

logger = logging.getLogger(__name__)


@dataclass
class SBOMComponent:
    """Represents a component / library in the CycloneDX SBOM."""

    name: str
    version: str = "unpinned"
    component_type: str = "library"
    purl: str = ""
    scope: str = "required"  # "required" | "optional"
    bom_ref: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        clean_name = self.name.lower().replace("_", "-")
        clean_ver = self.version if self.version and self.version != "None" else "unpinned"
        if not self.bom_ref:
            self.bom_ref = f"pkg:pypi/{clean_name}@{clean_ver}"
        if not self.purl:
            self.purl = f"pkg:pypi/{clean_name}@{clean_ver}"

    def to_dict(self) -> dict[str, Any]:
        """Serializes component according to CycloneDX v1.5 component schema."""
        data: dict[str, Any] = {
            "type": self.component_type,
            "name": self.name,
            "version": self.version if self.version else "unpinned",
            "bom-ref": self.bom_ref,
            "purl": self.purl,
            "scope": self.scope,
        }
        if self.description:
            data["description"] = self.description
        return data


@dataclass
class CycloneDXBOM:
    """Represents a complete CycloneDX v1.5 Bill of Materials document."""

    serial_number: str
    version: int
    metadata: dict[str, Any]
    components: list[SBOMComponent] = field(default_factory=list)
    dependencies: list[dict[str, Any]] = field(default_factory=list)
    spec_version: str = "1.5"
    bom_format: str = "CycloneDX"

    def to_dict(self) -> dict[str, Any]:
        """Converts BOM to standard CycloneDX v1.5 JSON dictionary structure."""
        return {
            "bomFormat": self.bom_format,
            "specVersion": self.spec_version,
            "serialNumber": self.serial_number,
            "version": self.version,
            "metadata": self.metadata,
            "components": [c.to_dict() for c in self.components],
            "dependencies": self.dependencies,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serializes BOM to formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class SBOMGeneratorService:
    """Service to scan repository dependencies and construct CycloneDX SBOMs."""

    def __init__(self) -> None:
        self._dep_service = DependencyHealthService()

    def _extract_project_metadata(self, repo_path: Path) -> dict[str, Any]:
        """Extracts root project name and version from pyproject.toml or directory name."""
        project_name = repo_path.resolve().name
        project_version = "0.1.0"

        pyproject_path = repo_path / "pyproject.toml"
        if pyproject_path.exists():
            try:
                data = tomllib.loads(pyproject_path.read_text(encoding="utf-8", errors="ignore"))
                project_section = data.get("project", {})
                project_name = project_section.get("name", project_name)
                project_version = project_section.get("version", project_version)
            except Exception as err:
                logger.debug(f"Failed to read project info from pyproject.toml: {err}")

        root_bom_ref = f"pkg:pypi/{project_name}@{project_version}"

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "tools": [
                {
                    "vendor": "WARDEN",
                    "name": "WARDEN Autonomous QA & Security Governance Engine",
                    "version": "0.1.0",
                }
            ],
            "component": {
                "type": "application",
                "name": project_name,
                "version": project_version,
                "bom-ref": root_bom_ref,
            },
        }

    def _parse_uv_lock(self, repo_path: Path) -> list[SBOMComponent]:
        """Parses uv.lock if available for exact pinned dependencies."""
        lock_file = repo_path / "uv.lock"
        if not lock_file.exists():
            return []

        components: list[SBOMComponent] = []
        try:
            data = tomllib.loads(lock_file.read_text(encoding="utf-8", errors="ignore"))
            packages = data.get("package", [])
            for pkg in packages:
                name = pkg.get("name")
                version = pkg.get("version", "unpinned")
                if not name:
                    continue
                components.append(
                    SBOMComponent(
                        name=name,
                        version=version,
                        component_type="library",
                        scope="required",
                    )
                )
        except Exception as err:
            logger.debug(f"Could not parse uv.lock: {err}")
        return components

    def _parse_manifests(self, repo_path: Path) -> list[SBOMComponent]:
        """Parses requirements.txt or pyproject.toml for declared dependencies."""
        components: list[SBOMComponent] = []
        seen_names: set[str] = set()

        # Check uv.lock first for pinned precision
        lock_comps = self._parse_uv_lock(repo_path)
        if lock_comps:
            return lock_comps

        # Parse standard manifests via DependencyHealthService
        parse_res = self._dep_service._parse_manifest(repo_path)
        for pkg in parse_res.packages:
            name = pkg.get("name", "").strip()
            if not name or name.lower() in seen_names:
                continue
            seen_names.add(name.lower())
            version = pkg.get("version") or "unpinned"
            components.append(
                SBOMComponent(
                    name=name,
                    version=version,
                    component_type="library",
                    scope="required",
                )
            )

        # Check for optional/dev dependencies in pyproject.toml
        pyproject_path = repo_path / "pyproject.toml"
        if pyproject_path.exists():
            try:
                data = tomllib.loads(pyproject_path.read_text(encoding="utf-8", errors="ignore"))
                # PEP 621 optional-dependencies
                opt_deps = data.get("project", {}).get("optional-dependencies", {})
                for group, dep_list in opt_deps.items():
                    if isinstance(dep_list, list):
                        parsed_list, _ = self._dep_service._parse_requirements_content("\n".join(str(d) for d in dep_list))
                        for pkg in parsed_list:
                            pname = pkg.get("name", "").strip()
                            if pname and pname.lower() not in seen_names:
                                seen_names.add(pname.lower())
                                components.append(
                                    SBOMComponent(
                                        name=pname,
                                        version=pkg.get("version") or "unpinned",
                                        component_type="library",
                                        scope="optional",
                                        description=f"Optional group: {group}",
                                    )
                                )
                # Dependency groups (PEP 735 / uv)
                dep_groups = data.get("dependency-groups", {})
                for group, dep_list in dep_groups.items():
                    if isinstance(dep_list, list):
                        parsed_list, _ = self._dep_service._parse_requirements_content("\n".join(str(d) for d in dep_list if isinstance(d, str)))
                        for pkg in parsed_list:
                            pname = pkg.get("name", "").strip()
                            if pname and pname.lower() not in seen_names:
                                seen_names.add(pname.lower())
                                components.append(
                                    SBOMComponent(
                                        name=pname,
                                        version=pkg.get("version") or "unpinned",
                                        component_type="library",
                                        scope="optional",
                                        description=f"Dependency group: {group}",
                                    )
                                )
            except Exception as err:
                logger.debug(f"Failed to read optional dependencies from pyproject.toml: {err}")

        return components

    def generate_sbom(self, repo_path: Path) -> CycloneDXBOM:
        """Scans the repository and returns a complete CycloneDX v1.5 BOM object."""
        repo_path = repo_path.resolve()
        metadata = self._extract_project_metadata(repo_path)
        components = self._parse_manifests(repo_path)

        root_bom_ref = metadata["component"]["bom-ref"]

        # Build dependencies section (root application depends on all components)
        dependencies: list[dict[str, Any]] = []
        if components:
            dependencies.append(
                {
                    "ref": root_bom_ref,
                    "dependsOn": [c.bom_ref for c in components],
                }
            )
            for c in components:
                dependencies.append({"ref": c.bom_ref, "dependsOn": []})

        serial_number = f"urn:uuid:{uuid.uuid4()}"

        return CycloneDXBOM(
            serial_number=serial_number,
            version=1,
            metadata=metadata,
            components=components,
            dependencies=dependencies,
            spec_version="1.5",
            bom_format="CycloneDX",
        )

    def export_json(self, repo_path: Path, output_path: Path | None = None, indent: int = 2) -> str:
        """Generates and exports CycloneDX JSON. Writes to file if output_path is provided."""
        bom = self.generate_sbom(repo_path)
        json_content = bom.to_json(indent=indent)

        if output_path is not None:
            out_file = output_path.resolve()
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(json_content, encoding="utf-8")
            logger.info(f"CycloneDX SBOM exported to {out_file}")

        return json_content
