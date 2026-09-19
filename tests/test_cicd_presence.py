import pytest
from pathlib import Path
from core.services.cicd_presence import CiCdPresenceService

@pytest.mark.asyncio
async def test_cicd_presence():
    service = CiCdPresenceService()
    res = await service.analyze(Path("."))
    
    assert res.score in [0.0, 50.0, 100.0]
    assert isinstance(res.has_file, bool)
    assert isinstance(res.has_valid_content, bool)
