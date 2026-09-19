import pytest
from pathlib import Path
from core.services.license_compliance import LicenseComplianceService

@pytest.mark.asyncio
async def test_license_compliance():
    service = LicenseComplianceService()
    # Path with no requirements or pip-licenses might fail or return empty, giving 100
    res = await service.analyze(Path("."))
    
    assert res.score >= 0
    assert isinstance(res.copyleft_count, int)
    assert isinstance(res.unknown_count, int)
    assert isinstance(res.dependencies, list)
