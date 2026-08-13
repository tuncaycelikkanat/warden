from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any
import os
import json
from sqlmodel import Session

from core.services.scanner import SecurityScannerService
from core.infra.database import engine
from core.models.scan import ScanResult

router = APIRouter(prefix="/api/v1")

class ScanRequest(BaseModel):
    file_path: str

def get_session():
    with Session(engine) as session:
        yield session

@router.post("/scan")
async def scan_file(request: ScanRequest, session: Session = Depends(get_session)):
    if not os.path.exists(request.file_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    scanner = SecurityScannerService()
    findings = scanner.scan_file(request.file_path)
    risk_level = scanner.calculate_risk_level(findings)
    
    scan_result = ScanResult(
        repo_path=".",
        file_path=request.file_path,
        risk_level=risk_level,
        findings_json=json.dumps(findings)
    )
    
    session.add(scan_result)
    session.commit()
    session.refresh(scan_result)
    
    return {
        "risk_level": risk_level,
        "findings": findings,
        "scan_id": scan_result.id
    }
