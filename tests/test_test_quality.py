import pytest
from pathlib import Path
from core.services.test_quality import TestQualityService

@pytest.mark.asyncio
async def test_test_quality():
    service = TestQualityService()
    res = await service.analyze(Path("."))
    
    assert res.score >= 0.0 and res.score <= 100.0
    assert res.total_tests >= 0
    assert res.fake_tests >= 0
