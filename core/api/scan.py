from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import os

from core.services.scanner import SecurityScannerService

router = APIRouter(prefix="/api/v1")

class ScanRequest(BaseModel):
    file_path: str

@router.post("/scan")
async def scan_file(request: ScanRequest):
    if not os.path.exists(request.file_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    scanner = SecurityScannerService()
    findings = scanner.scan_file(request.file_path)
    
    return {"findings": findings}
