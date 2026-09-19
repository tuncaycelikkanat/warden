import pytest
from pathlib import Path
from core.services.type_safety import TypeSafetyService

@pytest.mark.asyncio
async def test_type_safety():
    service = TypeSafetyService()
    res = await service.analyze(Path("."))
    
    assert res.score >= 20.0 and res.score <= 100.0
    assert res.error_count >= 0
    assert res.file_count >= 0
