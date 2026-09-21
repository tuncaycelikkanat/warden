"""FastAPI routes for file scanning and full repository auditing."""

import json
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from core.infra.database import engine
from core.models.scan import ScanResult
from core.services.scanner import SecurityScannerService

router = APIRouter(prefix="/api/v1")


class ScanRequest(BaseModel):
    """Request payload for scanning a specific file."""
    file_path: str


def get_session():
    """Database session dependency generator."""
    with Session(engine) as session:
        yield session


@router.post("/scan")
async def scan_file(request: ScanRequest, session: Session = Depends(get_session)):
    """Runs SAST security scanning against target file and persists findings."""
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


class AuditRequest(BaseModel):
    """Request payload for triggering repository audit."""
    repo_path: str


@router.post("/audit")
async def run_audit(request: AuditRequest):
    """Runs complete 2-layer WARDEN audit against target repository."""
    if not os.path.exists(request.repo_path):
        raise HTTPException(status_code=404, detail="Repo not found")
        
    from core.services.orchestrator import AuditOrchestrator
    from core.services.report import AuditReportService
    
    orch = AuditOrchestrator()
    res = await orch.run_full_audit(request.repo_path)
    
    reporter = AuditReportService()
    db_id = reporter.save_to_db(request.repo_path, res)
    md_path = reporter.generate_markdown(request.repo_path, res)
    
    return {
        "status": "success",
        "scorecard": res["scorecard"],
        "md_path": md_path,
        "db_id": db_id
    }
