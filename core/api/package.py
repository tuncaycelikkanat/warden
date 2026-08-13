from fastapi import APIRouter
from pydantic import BaseModel

from core.services.package import PackageCheckerService

router = APIRouter(prefix="/api/v1")

class PackageCheckRequest(BaseModel):
    package_name: str

@router.post("/packages/check")
async def check_package(request: PackageCheckRequest):
    service = PackageCheckerService()
    result = await service.calculate_risk_score(request.package_name)
    return result
