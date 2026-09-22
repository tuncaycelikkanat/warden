from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from core.services.dependency_health import DependencyHealthService
from core.services.scorecard import ScorecardAggregatorService


@pytest.mark.asyncio
async def test_osv_network_error_tolerance(tmp_path: Path):
    """
    Roadmap Step 8.8: When OSV.dev is unreachable or throws a network error,
    DependencyHealthService should not crash, but return gracefully with empty vulns.
    """
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("requests==2.31.0\nflask==3.0.0\n")

    service = DependencyHealthService()

    with patch.object(service._http, "post", side_effect=httpx.ConnectError("Connection refused by api.osv.dev")):
        result = await service.check_manifest(tmp_path)

        assert len(result.entries) == 2
        for entry in result.entries:
            assert entry.known_vulnerabilities == []
            assert entry.name in ["requests", "flask"]

    await service.close()


@pytest.mark.asyncio
async def test_manifest_parsing(tmp_path: Path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("""
    # Comments should be ignored
    pytest>=7.0.0
    httpx==0.24.1
    black
    """)

    service = DependencyHealthService()
    packages = service._parse_manifest(tmp_path)
    await service.close()

    names = [p["name"] for p in packages]
    assert "pytest" in names
    assert "httpx" in names
    assert "black" in names


@pytest.mark.asyncio
async def test_manifest_parsing_extras_and_skipped_lines(tmp_path: Path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("""
    # Packages with extras and constraints
    celery[redis,auth]==5.3.0
    urllib3>=1.26.0,<2.0.0
    fastapi[all]
    -e git+https://github.com/encode/uvicorn.git#egg=uvicorn
    --extra-index-url https://custom.repo.org/simple
    ./local_submodule
    """)

    service = DependencyHealthService()
    parse_result = service._parse_manifest(tmp_path)
    await service.close()

    pkg_map = {p["name"]: p for p in parse_result.packages}
    assert "celery" in pkg_map
    assert pkg_map["celery"]["version"] == "5.3.0"
    assert pkg_map["celery"]["pinned"] is True

    assert "urllib3" in pkg_map
    assert pkg_map["urllib3"]["version"] is None
    assert pkg_map["urllib3"]["pinned"] is False

    assert "fastapi" in pkg_map
    assert pkg_map["fastapi"]["version"] is None
    assert pkg_map["fastapi"]["pinned"] is False

    # Skipped lines verification
    skipped = parse_result.skipped_lines
    assert len(skipped) >= 2
    assert any("git+" in s["line"] or "uvicorn" in s["line"] for s in skipped)
    assert any("--extra-index-url" in s["line"] for s in skipped)


@pytest.mark.asyncio
async def test_manifest_fallback_pyproject_toml(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("""
[project]
name = "demo-app"
version = "0.1.0"
dependencies = [
    "requests==2.31.0",
    "pydantic[email]>=2.5.0",
    "ruff"
]
""")

    service = DependencyHealthService()
    parse_result = service._parse_manifest(tmp_path)
    await service.close()

    names = [p["name"] for p in parse_result.packages]
    assert "requests" in names
    assert "pydantic" in names
    assert "ruff" in names


@pytest.mark.asyncio
async def test_unpinned_dependencies_status_and_penalty(tmp_path: Path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("requests\nflask>=3.0\n")

    service = DependencyHealthService()

    # Mock integrity checker to return low risk for both
    with patch.object(service._integrity_checker, "calculate_risk_score", new_callable=AsyncMock) as mock_risk:
        mock_risk.return_value = {"risk_level": "low", "details": ["Normal package"]}
        result = await service.check_manifest(tmp_path)

        assert len(result.entries) == 2
        assert "requests" in result.unpinned_packages
        assert "flask" in result.unpinned_packages

        for entry in result.entries:
            assert entry.status == "version_unpinned"
            assert "sabitlenmemiş" in entry.note

        # Verify ScorecardAggregator applies -2 per unpinned dependency
        scorecard = ScorecardAggregatorService()
        dep_score = scorecard._score_dependencies([
            {"status": e.status, "known_vulnerabilities": e.known_vulnerabilities}
            for e in result.entries
        ])
        assert dep_score == 96.0  # 100 - (2 * 2)

    await service.close()


@pytest.mark.asyncio
async def test_osv_query_caching():
    service = DependencyHealthService()

    # First call puts dummy vuln into cache
    dummy_vuln = {"id": "CVE-2023-1234", "summary": "Sample CVE", "details": "Critical issue"}
    service._osv_cache.set("pypi", "test-pkg", "1.0.0", [dummy_vuln])

    # Calling _query_osv should return from cache without network request
    with patch.object(service._http, "post") as mock_post:
        vulns = await service._query_osv("test-pkg", "1.0.0", "PyPI")
        assert len(vulns) == 1
        assert vulns[0].cve_id == "CVE-2023-1234"
        mock_post.assert_not_called()

    await service.close()


@pytest.mark.asyncio
async def test_typosquatting_triggers_failed_check_and_penalty(tmp_path: Path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("reqeusts==2.31.0\n")

    service = DependencyHealthService()

    # Mock integrity checker to return high risk typosquatting
    with patch.object(service._integrity_checker, "calculate_risk_score", new_callable=AsyncMock) as mock_risk:
        mock_risk.return_value = {
            "risk_level": "high",
            "details": ["Typosquatting alert: suspiciously similar to popular package 'requests'"],
        }
        result = await service.check_manifest(tmp_path)

        assert len(result.entries) == 1
        assert result.entries[0].status == "failed_check"
        assert "Typosquatting alert" in result.entries[0].note

        scorecard = ScorecardAggregatorService()
        dep_score = scorecard._score_dependencies([
            {"status": result.entries[0].status, "known_vulnerabilities": []}
        ])
        assert dep_score == 80.0  # 100 - 20

    await service.close()


@pytest.mark.asyncio
async def test_vcs_urls_and_pyproject_error(tmp_path: Path):
    service = DependencyHealthService()

    # 1. VCS URLs
    req_file = tmp_path / "requirements.txt"
    req_file.write_text(
        "git+https://github.com/foo/bar.git#egg=bar-pkg\n"
        "git+https://github.com/foo/baz.git\n"
    )

    parse_res = service._parse_manifest(tmp_path)
    assert len(parse_res.packages) == 1
    assert parse_res.packages[0]["name"] == "bar-pkg"
    assert len(parse_res.skipped_lines) == 1
    assert parse_res.skipped_lines[0]["reason"] == "vcs_url_without_egg"

    # 2. Corrupt pyproject.toml
    req_file.unlink()
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("invalid [[[ toml content")
    corrupt_res = service._parse_manifest(tmp_path)
    assert corrupt_res.packages == []

    await service.close()


@pytest.mark.asyncio
async def test_osv_unexpected_error_and_review_status(tmp_path: Path):
    service = DependencyHealthService()

    # Unexpected exception in _query_osv
    with patch.object(service._http, "post", side_effect=Exception("Unexpected OSV failure")):
        vulns = await service._query_osv("requests", "2.31.0", "PyPI")
        assert vulns == []

    # Review risk level and Integrity check exception
    req = tmp_path / "requirements.txt"
    req.write_text("lib_review==1.0.0\nlib_err==1.0.0\n")

    async def mock_risk(name: str):
        if name == "lib_review":
            return {"risk_level": "review", "details": ["Manual review suggested"]}
        raise RuntimeError("Integrity crash")

    with patch.object(service._integrity_checker, "calculate_risk_score", side_effect=mock_risk), \
         patch.object(service, "_query_osv", new_callable=AsyncMock, return_value=[]):
        res = await service.check_manifest(tmp_path)
        assert len(res.entries) == 2
        entry_map = {e.name: e for e in res.entries}
        assert entry_map["lib_review"].status == "ok"
        assert "Manual review suggested" in entry_map["lib_review"].note
        assert entry_map["lib_err"].status == "failed_check"
        assert "Paket doğrulama hatası" in entry_map["lib_err"].note

    await service.close()

