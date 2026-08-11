import pytest
from core.services.package import PackageCheckerService

@pytest.mark.asyncio
async def test_get_pypi_metadata_existing_package():
    service = PackageCheckerService()
    metadata = await service.get_pypi_metadata("requests")
    
    assert metadata is not None
    assert "info" in metadata
    assert metadata["info"]["name"] == "requests"

@pytest.mark.asyncio
async def test_get_pypi_metadata_nonexistent_package():
    service = PackageCheckerService()
    # A totally random non-existent package
    metadata = await service.get_pypi_metadata("asdkjaskdj123")
    
    assert metadata is None
