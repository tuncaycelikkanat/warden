"""Comprehensive tests for LicenseComplianceService edge cases, heuristics, and compatibility."""

from unittest.mock import MagicMock, patch

import pytest

from core.services.license_compliance import (
    LicenseComplianceService,
    _load_dev_dependency_names,
    normalize_license,
    resolve_multi_license,
)
from core.services.repo_license_detector import RepoLicenseInfo


def test_normalize_license_edge_cases():
    # None or whitespace
    assert normalize_license(None) is None
    assert normalize_license("") is None
    assert normalize_license("   ") is None

    # In normalization map
    assert normalize_license("apache 2.0") == "Apache-2.0"
    assert normalize_license("bsd license") == "BSD-3-Clause"

    # Direct SPDX ID
    assert normalize_license("MIT") == "MIT"
    assert normalize_license("GPL-3.0-only") == "GPL-3.0-only"

    # Heuristics (using strings not present in normalization map)
    assert normalize_license("Custom GNU AGPLv3 Variant") == "AGPL-3.0-only"
    assert normalize_license("Custom GNU LGPL v3 Variant") == "LGPL-3.0-only"
    assert normalize_license("Custom GNU LGPL 2.1 Variant") == "LGPL-2.1-only"
    assert normalize_license("Custom GNU GPL v3 Variant") == "GPL-3.0-only"
    assert normalize_license("Custom GNU GPL v2 Variant") == "GPL-2.0-only"
    assert normalize_license("Custom GNU GPL Variant") == "GPL-3.0-only"
    assert normalize_license("Something Apache Custom") == "Apache-2.0"
    assert normalize_license("Something MIT Custom") == "MIT"
    assert normalize_license("Something BSD Custom") == "BSD-3-Clause"
    assert normalize_license("Something Mozilla MPL Custom") == "MPL-2.0"
    assert normalize_license("Something ISC Custom") == "ISC"
    assert normalize_license("Some Unknown Obscure License XYZ") is None


def test_resolve_multi_license():
    assert resolve_multi_license(None) is None
    assert resolve_multi_license("") is None

    # OR expression: picks most permissive (MIT over GPL-3.0)
    assert resolve_multi_license("MIT OR GPL-3.0-only") == "MIT"
    assert resolve_multi_license("GPL-3.0-only OR MIT") == "MIT"
    assert resolve_multi_license("LGPL-3.0-only OR GPL-3.0-only") == "LGPL-3.0-only"
    # OR with invalid components
    assert resolve_multi_license("FOO OR BAR") is None

    # AND expression: picks most restrictive (GPL-3.0 over MIT)
    assert resolve_multi_license("MIT AND GPL-3.0-only") == "GPL-3.0-only"
    assert resolve_multi_license("Apache-2.0 AND LGPL-3.0-only") == "LGPL-3.0-only"
    # AND with invalid components
    assert resolve_multi_license("FOO AND BAR") is None


def test_load_dev_dependency_names(tmp_path):
    # 1. pyproject.toml with PEP 621 optional-dependencies and poetry groups
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
name = "my-app"
[project.optional-dependencies]
dev = ["black>=22.0", "ruff"]
test = ["pytest-cov"]

[tool.poetry.group.docs.dependencies]
mkdocs = "^1.0"
        """,
        encoding="utf-8",
    )

    # 2. dev-requirements.txt
    dev_req = tmp_path / "dev-requirements.txt"
    dev_req.write_text("# dev requirements\nflake8==5.0.0\n-r other.txt\n", encoding="utf-8")

    names = _load_dev_dependency_names(tmp_path)
    assert "black" in names
    assert "ruff" in names
    assert "pytest-cov" in names
    assert "mkdocs" in names
    assert "flake8" in names
    assert "pytest" in names  # From fallback dev tools


def test_load_dev_dependency_names_corrupt_files(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("corrupted [[[[ toml content", encoding="utf-8")
    dev_req = tmp_path / "dev-requirements.txt"
    dev_req.write_text("valid-tool", encoding="utf-8")

    # Should not raise exception
    names = _load_dev_dependency_names(tmp_path)
    assert "valid-tool" in names


def test_evaluate_compatibility():
    service = LicenseComplianceService()

    # 1. Proprietary repo ("all_rights_reserved_by_default")
    repo_prop = RepoLicenseInfo(spdx_id=None, category="all_rights_reserved_by_default", confidence="high", source="none")
    assert service._evaluate_compatibility(repo_prop, "strong_copyleft") == ("high", 20.0)
    assert service._evaluate_compatibility(repo_prop, "weak_copyleft") == ("medium", 8.0)
    assert service._evaluate_compatibility(repo_prop, "unknown") == ("medium", 5.0)
    assert service._evaluate_compatibility(repo_prop, "permissive") == ("none", 0.0)

    # 2. Strong copyleft repo (GPL repo)
    repo_gpl = RepoLicenseInfo(spdx_id="GPL-3.0-only", category="strong_copyleft", confidence="high", source="license_file")
    assert service._evaluate_compatibility(repo_gpl, "strong_copyleft") == ("none", 0.0)
    assert service._evaluate_compatibility(repo_gpl, "unknown") == ("low", 5.0)

    # 3. Permissive repo (MIT repo)
    repo_mit = RepoLicenseInfo(spdx_id="MIT", category="permissive", confidence="high", source="license_file")
    assert service._evaluate_compatibility(repo_mit, "strong_copyleft") == ("high", 20.0)
    assert service._evaluate_compatibility(repo_mit, "weak_copyleft") == ("low", 3.0)
    assert service._evaluate_compatibility(repo_mit, "unknown") == ("low", 5.0)
    assert service._evaluate_compatibility(repo_mit, "permissive") == ("none", 0.0)


@pytest.mark.asyncio
async def test_analyze_empty_repo(tmp_path):
    service = LicenseComplianceService()
    with patch.object(service, "_run_pip_licenses", return_value=[]):
        res = await service.analyze(tmp_path)
        assert res.score == 100.0
        assert res.method == "empty_repo"
        assert res.measured is True


@pytest.mark.asyncio
async def test_analyze_manifest_exists_but_no_deps_resolved(tmp_path):
    service = LicenseComplianceService()
    req = tmp_path / "requirements.txt"
    req.write_text("# only comments\n", encoding="utf-8")

    with patch.object(service, "_run_pip_licenses", return_value=[]):
        res = await service.analyze(tmp_path)
        assert res.score is None
        assert res.measured is False
        assert res.method == "unmeasured"


@pytest.mark.asyncio
async def test_analyze_static_fallback_and_scoring(tmp_path):
    service = LicenseComplianceService()
    req = tmp_path / "requirements.txt"
    req.write_text("requests>=2.25.0\npeewee\nunknown-package-xyz\n", encoding="utf-8")

    with patch.object(service, "_run_pip_licenses", return_value=[]):
        res = await service.analyze(tmp_path)
        assert res.method == "static_fallback"
        assert res.measured is True
        assert len(res.dependencies) == 3

        # requests is Apache-2.0 (permissive), peewee is MIT (permissive), unknown-pkg is UNKNOWN
        dep_map = {d["name"]: d for d in res.dependencies}
        assert dep_map["requests"]["category"] == "permissive"
        assert dep_map["peewee"]["category"] == "permissive"
        assert dep_map["unknown-package-xyz"]["category"] == "unknown"


@pytest.mark.asyncio
async def test_analyze_pip_licenses_with_dev_and_copyleft(tmp_path):
    service = LicenseComplianceService()

    # Pyproject declaring test dev dependency
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
name = "my_custom_project"
[project.optional-dependencies]
dev = ["pytest"]
        """,
        encoding="utf-8",
    )

    mock_pip_output = [
        {"Name": "my_custom_project", "License": "MIT"},  # Root project (should be skipped)
        {"Name": "pytest", "License": "MIT"},             # Dev tool (should not be penalized)
        {"Name": "copyleft_lib", "License": "GPL-3.0-only"}, # Copyleft in proprietary project -> high risk penalty
        {"Name": "fastapi", "License": "UNKNOWN"},        # In KNOWN_PACKAGE_LICENSES -> fallback to MIT
    ]

    with patch.object(service, "_run_pip_licenses", return_value=mock_pip_output):
        res = await service.analyze(tmp_path)
        assert res.copyleft_count == 1
        assert res.score == 80.0  # 100 - 20 (strong copyleft penalty)
        dep_map = {d["name"]: d for d in res.dependencies}

        assert "my_custom_project" not in dep_map  # Skipped root project
        assert dep_map["pytest"]["is_dev"] is True
        assert dep_map["pytest"]["penalty"] == 0.0
        assert dep_map["copyleft_lib"]["is_copyleft"] is True
        assert dep_map["copyleft_lib"]["penalty"] == 20.0
        assert dep_map["fastapi"]["category"] == "permissive"


def test_run_pip_licenses_success(tmp_path):
    service = LicenseComplianceService()
    mock_res = MagicMock(stdout='[{"Name": "pytest", "License": "MIT"}]')
    with patch("subprocess.run", return_value=mock_res):
        out = service._run_pip_licenses(tmp_path)
        assert len(out) == 1
        assert out[0]["Name"] == "pytest"


def test_run_pip_licenses_failure_and_empty(tmp_path):
    service = LicenseComplianceService()
    # Empty stdout
    mock_res = MagicMock(stdout="   ")
    with patch("subprocess.run", return_value=mock_res):
        out = service._run_pip_licenses(tmp_path)
        assert out == []

    # Exception thrown
    with patch("subprocess.run", side_effect=Exception("Execution timed out")):
        out = service._run_pip_licenses(tmp_path)
        assert out == []


def test_static_fallback_pyproject(tmp_path):
    service = LicenseComplianceService()
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
name = "demo-pkg"
dependencies = [
    "requests>=2.28",
    "sqlalchemy",
    "nonexistent-lib"
]
        """,
        encoding="utf-8",
    )
    results = service._static_fallback(tmp_path)
    assert len(results) == 3
    names = {r["Name"] for r in results}
    assert "requests" in names
    assert "sqlalchemy" in names
    assert "nonexistent-lib" in names

