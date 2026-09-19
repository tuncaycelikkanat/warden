import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import httpx

from core.services.dependency_health import DependencyHealthService

@pytest.mark.asyncio
async def test_osv_network_error_tolerance(tmp_path: Path):
    """
    Roadmap Step 8.8: When OSV.dev is unreachable or throws a network error,
    DependencyHealthService should not crash, but return gracefully with empty vulns.
    """
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("requests==2.31.0\nflask==3.0.0\n")

    service = DependencyHealthService()
    
    # Mock httpx.AsyncClient.post to simulate network failure (e.g. timeout / DNS error)
    with patch.object(service._http, "post", side_effect=httpx.ConnectError("Connection refused by api.osv.dev")):
        result = await service.check_manifest(tmp_path)
        
        assert len(result.entries) == 2
        for entry in result.entries:
            # Should have handled error gracefully, returning empty known_vulnerabilities without crashing
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
