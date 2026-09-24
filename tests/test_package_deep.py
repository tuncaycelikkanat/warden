"""Comprehensive unit tests for PackageCheckerService logic, metrics, and caching."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from core.services.package import PackageCheckerService, _levenshtein_distance


def test_levenshtein_distance():
    assert _levenshtein_distance("", "") == 0
    assert _levenshtein_distance("a", "") == 1
    assert _levenshtein_distance("", "b") == 1
    assert _levenshtein_distance("kitten", "sitting") == 3
    assert _levenshtein_distance("requests", "reqeusts") == 2


@pytest.mark.asyncio
async def test_get_pypi_metadata_and_stats_mocked():
    svc = PackageCheckerService()

    # 1. 200 Success
    resp_200 = httpx.Response(
        200,
        json={"info": {"name": "mypkg", "version": "1.0.0"}, "releases": {"1.0.0": []}},
        request=httpx.Request("GET", "https://pypi.org"),
    )
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=resp_200):
        data = await svc.get_pypi_metadata("mypkg")
        assert data["info"]["name"] == "mypkg"

        # Cached call
        data_cached = await svc.get_pypi_metadata("mypkg")
        assert data_cached == data

    # 2. 404 Not Found
    resp_404 = httpx.Response(404, request=httpx.Request("GET", "https://pypi.org"))
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=resp_404):
        assert await svc.get_pypi_metadata("missing_pkg") is None

    # 3. 500 Server Error
    resp_500 = httpx.Response(500, request=httpx.Request("GET", "https://pypi.org"))
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=resp_500):
        assert await svc.get_pypi_metadata("error_pkg") is None

    # 4. Network error
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("Connection failed")):
        net_err = await svc.get_pypi_metadata("offline_pkg")
        assert net_err.get("_network_error") is True

    # 5. Stats 200
    stats_200 = httpx.Response(200, json={"data": {"last_month": 5000}}, request=httpx.Request("GET", "https://pypistats.org"))
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=stats_200):
        assert await svc.get_pypi_stats("mypkg") == 5000
        # Cached
        assert await svc.get_pypi_stats("mypkg") == 5000

    # 6. Stats error
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=Exception("Stats down")):
        assert await svc.get_pypi_stats("error_stats") == 0


def test_evaluate_risk_level_matrix():
    svc = PackageCheckerService()

    # 1. Typo mimic with mature history -> "review"
    r1, d1 = svc._evaluate_risk_level("requests", total_releases=15, stats=500)
    assert r1 == "review"

    # 2. Typo mimic with high downloads -> "review"
    r2, d2 = svc._evaluate_risk_level("requests", total_releases=2, stats=50000)
    assert r2 == "review"

    # 3. Typo mimic with low activity -> "high"
    r3, d3 = svc._evaluate_risk_level("requests", total_releases=1, stats=10)
    assert r3 == "high"

    # 4. Zero releases -> "high"
    r4, d4 = svc._evaluate_risk_level(None, total_releases=0, stats=0)
    assert r4 == "high"

    # 5. Mature package (>50 releases or >10000 stats) -> "low"
    r5, d5 = svc._evaluate_risk_level(None, total_releases=60, stats=100)
    assert r5 == "low"

    # 6. Low releases (< 3) -> "medium"
    r6, d6 = svc._evaluate_risk_level(None, total_releases=2, stats=2000)
    assert r6 == "medium"

    # 7. Low downloads (< 1000) -> "medium"
    r7, d7 = svc._evaluate_risk_level(None, total_releases=10, stats=500)
    assert r7 == "medium"

    # 8. Acceptable metrics -> "low"
    r8, d8 = svc._evaluate_risk_level(None, total_releases=10, stats=5000)
    assert r8 == "low"


@pytest.mark.asyncio
async def test_calculate_risk_score_mocked():
    svc = PackageCheckerService()

    # 1. Network error
    with patch.object(svc, "get_pypi_metadata", return_value={"_network_error": True}):
        res1 = await svc.calculate_risk_score("requests")
        assert res1["risk_level"] in ("low", "medium")

    # 2. Package not found
    with patch.object(svc, "get_pypi_metadata", return_value=None):
        res2 = await svc.calculate_risk_score("definitely_non_existent_12345")
        assert res2["risk_level"] == "high"
        assert "Package not found" in res2["details"][0]

    # 3. Normal package
    mock_meta = {
        "info": {"name": "goodpkg", "version": "2.0.0"},
        "releases": {"1.0": [], "2.0": []},
    }
    with patch.object(svc, "get_pypi_metadata", return_value=mock_meta), \
         patch.object(svc, "get_pypi_stats", return_value=15000):
        res3 = await svc.calculate_risk_score("goodpkg")
        assert res3["risk_level"] == "low"
