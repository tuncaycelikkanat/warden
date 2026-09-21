from pathlib import Path
from unittest.mock import patch

import pytest

from core.services.license_compliance import (
    LicenseComplianceService,
    normalize_license,
    resolve_multi_license,
)
from core.services.repo_license_detector import RepoLicenseDetector


@pytest.mark.asyncio
async def test_license_compliance_smoke():
    service = LicenseComplianceService()
    res = await service.analyze(Path("."))
    assert res.score is not None and res.score >= 0
    assert isinstance(res.copyleft_count, int)
    assert isinstance(res.unknown_count, int)
    assert isinstance(res.dependencies, list)


def test_license_normalization():
    # Free text to standard SPDX mappings
    assert normalize_license("GNU Lesser General Public License v2.1 (LGPLv2.1)") == "LGPL-2.1-only"
    assert normalize_license("GNU General Public License v3 (GPLv3)") == "GPL-3.0-only"
    assert normalize_license("Apache Software License") == "Apache-2.0"
    assert normalize_license("BSD License") == "BSD-3-Clause"
    assert normalize_license("MIT License") == "MIT"
    assert normalize_license("Mozilla Public License 2.0 (MPL 2.0)") == "MPL-2.0"
    assert normalize_license("") is None
    assert normalize_license("Unknown Custom Gibberish 999") is None


def test_multi_license_resolution():
    # OR: Pick most permissive
    assert resolve_multi_license("MIT OR GPL-2.0") == "MIT"
    assert resolve_multi_license("Apache Software License OR GPL-3.0-only") == "Apache-2.0"

    # AND: Pick most restrictive
    assert resolve_multi_license("GPL-2.0 AND MIT") == "GPL-2.0-only"
    assert resolve_multi_license("MIT AND AGPL-3.0-only") == "AGPL-3.0-only"


def test_repo_license_detector(tmp_path: Path):
    detector = RepoLicenseDetector()

    # 1. MIT LICENSE file
    (tmp_path / "LICENSE").write_text("MIT License\n\nPermission is hereby granted, free of charge...")
    info_mit = detector.detect(tmp_path)
    assert info_mit.spdx_id == "MIT"
    assert info_mit.category == "permissive"
    assert info_mit.confidence == "high"

    # 2. GPL-3.0 LICENSE file
    (tmp_path / "LICENSE").write_text("GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007...")
    info_gpl = detector.detect(tmp_path)
    assert info_gpl.spdx_id == "GPL-3.0-only"
    assert info_gpl.category == "strong_copyleft"

    # 3. No LICENSE file -> all_rights_reserved_by_default
    empty_dir = tmp_path / "empty_repo"
    empty_dir.mkdir()
    info_none = detector.detect(empty_dir)
    assert info_none.spdx_id is None
    assert info_none.category == "all_rights_reserved_by_default"


@pytest.mark.asyncio
async def test_project_license_compatibility_regression(tmp_path: Path):
    """
    Critical regression test:
    The exact same GPL-3.0 dependency must receive 0 penalty in a GPL-3.0 project,
    but -20 penalty in an MIT project!
    """
    gpl_dep = [{"Name": "gpl-library", "License": "GNU General Public License v3 (GPLv3)"}]
    service = LicenseComplianceService()

    # Case A: GPL project using GPL dependency -> 100/100, 0 penalty
    (tmp_path / "LICENSE").write_text("GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007...")
    with patch.object(service, "_run_pip_licenses", return_value=gpl_dep):
        res_gpl = await service.analyze(tmp_path)
        assert res_gpl.score == 100.0
        assert res_gpl.copyleft_count == 0
        assert res_gpl.dependencies[0]["risk_level"] == "none"
        assert res_gpl.dependencies[0]["penalty"] == 0.0

    # Case B: MIT project using GPL dependency -> 80/100, -20 penalty
    (tmp_path / "LICENSE").write_text("MIT License\n\nPermission is hereby granted, free of charge...")
    with patch.object(service, "_run_pip_licenses", return_value=gpl_dep):
        res_mit = await service.analyze(tmp_path)
        assert res_mit.score == 80.0
        assert res_mit.copyleft_count == 1
        assert res_mit.dependencies[0]["risk_level"] == "high"
        assert res_mit.dependencies[0]["penalty"] == 20.0


@pytest.mark.asyncio
async def test_no_license_file_nuance(tmp_path: Path):
    """
    No LICENSE file means all_rights_reserved_by_default.
    An AGPL dependency in an unlicensed repo must produce high risk (-20 penalty).
    """
    service = LicenseComplianceService()
    agpl_dep = [{"Name": "agpl-tool", "License": "AGPLv3"}]

    with patch.object(service, "_run_pip_licenses", return_value=agpl_dep):
        res = await service.analyze(tmp_path)
        assert res.repo_category == "all_rights_reserved_by_default"
        assert res.score == 80.0
        assert res.copyleft_count == 1
        assert res.dependencies[0]["risk_level"] == "high"


@pytest.mark.asyncio
async def test_weak_vs_strong_copyleft_distinction(tmp_path: Path):
    """
    In an MIT project:
    Weak copyleft (LGPL-2.1) should receive a low penalty (-3),
    while Strong copyleft (AGPL-3.0) should receive a high penalty (-20).
    """
    (tmp_path / "LICENSE").write_text("MIT License\n\nPermission is hereby granted...")
    service = LicenseComplianceService()

    deps = [
        {"Name": "weak-copyleft-pkg", "License": "GNU Lesser General Public License v2.1 (LGPLv2.1)"},
        {"Name": "strong-copyleft-pkg", "License": "AGPLv3"},
    ]

    with patch.object(service, "_run_pip_licenses", return_value=deps):
        res = await service.analyze(tmp_path)
        weak_entry = next(d for d in res.dependencies if d["name"] == "weak-copyleft-pkg")
        strong_entry = next(d for d in res.dependencies if d["name"] == "strong-copyleft-pkg")

        assert weak_entry["risk_level"] == "low"
        assert weak_entry["penalty"] == 3.0

        assert strong_entry["risk_level"] == "high"
        assert strong_entry["penalty"] == 20.0

        assert res.score == 100.0 - (3.0 + 20.0)


@pytest.mark.asyncio
async def test_manifest_dev_dependency_exemption(tmp_path: Path):
    """
    Dependencies defined in pyproject.toml dev groups or dev-requirements.txt
    must be recognized as dev dependencies and exempt from copyleft penalty.
    """
    (tmp_path / "LICENSE").write_text("MIT License\n\nPermission is hereby granted...")
    (tmp_path / "pyproject.toml").write_text("""
[project]
name = "demo"
version = "0.1.0"

[project.optional-dependencies]
dev = [
    "custom-gpl-linter>=1.0.0"
]
""")

    service = LicenseComplianceService()
    deps = [
        {"Name": "custom-gpl-linter", "License": "GPLv3"}
    ]

    with patch.object(service, "_run_pip_licenses", return_value=deps):
        res = await service.analyze(tmp_path)
        assert res.dependencies[0]["is_dev"] is True
        assert res.dependencies[0]["penalty"] == 0.0
        assert res.copyleft_count == 0
        assert res.score == 100.0


@pytest.mark.asyncio
async def test_unmeasured_behavior_when_no_venv_and_no_packages(tmp_path: Path):
    """
    When pip-licenses fails and manifest has unresolvable dependencies,
    it must NOT silently return 100. It must return measured=False and score=None!
    """
    # Create a requirements.txt with unknown package
    (tmp_path / "requirements.txt").write_text("totally-unresolvable-private-pkg==1.0\n")
    service = LicenseComplianceService()

    # Mock pip-licenses and static fallback returning empty
    with patch.object(service, "_run_pip_licenses", return_value=[]), \
         patch.object(service, "_static_fallback", return_value=[]):
        res = await service.analyze(tmp_path)
        assert res.measured is False
        assert res.score is None
        assert res.method == "unmeasured"
