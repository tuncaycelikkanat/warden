"""FastAPI routes for PyPI package integrity and supply-chain risk checking."""

from fastapi import APIRouter
from pydantic import BaseModel

from core.services.package import PackageCheckerService

router = APIRouter(prefix="/api/v1")


class PackageCheckRequest(BaseModel):
    """Request payload for single package risk check."""
    package_name: str


@router.post("/packages/check")
async def check_package(request: PackageCheckRequest):
    """Calculates risk score and supply-chain integrity for given PyPI package."""
    service = PackageCheckerService()
    result = await service.calculate_risk_score(request.package_name)
    return result
