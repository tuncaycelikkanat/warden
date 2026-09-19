import pytest
from pathlib import Path
from core.services.docker_readiness import DockerReadinessService

@pytest.mark.asyncio
async def test_docker_readiness():
    service = DockerReadinessService()
    res = await service.analyze(Path("."))
    
    assert res.score in [0.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    assert isinstance(res.has_dockerfile, bool)
    assert isinstance(res.has_healthcheck, bool)
