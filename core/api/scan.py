"""FastAPI routes for file scanning, synchronous auditing, and async background audit jobs."""

import json
import os
import time
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from core.api.auth import get_current_user
from core.infra.database import engine
from core.models.scan import ScanResult
from core.services.scanner import SecurityScannerService
from core.utils.path_validator import validate_audit_path, validate_scan_file_path

router = APIRouter(prefix="/api/v1")

# In-memory job store for async background audits (prevents reverse-proxy 504 timeouts)
_AUDIT_JOBS: dict[str, dict[str, Any]] = {}


class ScanRequest(BaseModel):
    """Request payload for scanning a specific file."""
    file_path: str


def get_session():
    """Database session dependency generator."""
    with Session(engine) as session:
        yield session


@router.post("/scan")
async def scan_file(
    request: ScanRequest,
    session: Session = Depends(get_session),
    _user: dict[str, Any] = Depends(get_current_user),
):
    """Runs SAST security scanning against target file and persists findings."""
    try:
        validated_file = validate_scan_file_path(request.file_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc

    scanner = SecurityScannerService()
    findings = scanner.scan_file(str(validated_file))
    risk_level = scanner.calculate_risk_level(findings)

    scan_result = ScanResult(
        repo_path=".",
        file_path=str(validated_file),
        risk_level=risk_level,
        findings_json=json.dumps(findings),
    )

    session.add(scan_result)
    session.commit()
    session.refresh(scan_result)

    return {
        "risk_level": risk_level,
        "findings": findings,
        "scan_id": scan_result.id,
    }


class AuditRequest(BaseModel):
    """Request payload for triggering repository audit."""
    repo_path: str
    incremental: bool = False


@router.post("/audit")
async def run_audit(
    request: AuditRequest,
    _user: dict[str, Any] = Depends(get_current_user),
):
    """Runs complete 2-layer WARDEN audit against target repository."""
    if not os.path.exists(request.repo_path):
        raise HTTPException(status_code=404, detail="Repo not found")

    from core.services.orchestrator import AuditOrchestrator
    from core.services.report import AuditReportService

    try:
        validated_path = validate_audit_path(request.repo_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    orch = AuditOrchestrator()
    res = await orch.run_full_audit(str(validated_path))

    reporter = AuditReportService()
    db_id = reporter.save_to_db(str(validated_path), res)
    md_path = reporter.generate_markdown(str(validated_path), res, current_id=db_id)

    return {
        "status": "success",
        "scorecard": res["scorecard"],
        "md_path": md_path,
        "db_id": db_id,
        "repo_path": str(validated_path),
    }


async def _execute_background_audit(job_id: str, validated_path: str, incremental: bool) -> None:
    """Executes an audit job asynchronously and updates the job state."""
    from core.services.orchestrator import AuditOrchestrator
    from core.services.report import AuditReportService

    _AUDIT_JOBS[job_id]["status"] = "running"
    _AUDIT_JOBS[job_id]["started_at"] = time.time()
    try:
        orch = AuditOrchestrator()
        res = await orch.run_full_audit(validated_path, incremental=incremental)
        reporter = AuditReportService()
        db_id = reporter.save_to_db(validated_path, res)
        md_path = reporter.generate_markdown(validated_path, res, current_id=db_id)

        _AUDIT_JOBS[job_id].update({
            "status": "completed",
            "completed_at": time.time(),
            "scorecard": res.get("scorecard"),
            "db_id": db_id,
            "md_path": md_path,
        })
    except Exception as exc:
        _AUDIT_JOBS[job_id].update({
            "status": "failed",
            "completed_at": time.time(),
            "error": str(exc),
        })


@router.post("/audit/async", status_code=status.HTTP_202_ACCEPTED)
async def run_audit_async(
    request: AuditRequest,
    background_tasks: BackgroundTasks,
    _user: dict[str, Any] = Depends(get_current_user),
):
    """Enqueues a non-blocking repository audit job, avoiding reverse-proxy 504 timeouts."""
    if not os.path.exists(request.repo_path):
        raise HTTPException(status_code=404, detail="Repo not found")

    try:
        validated_path = validate_audit_path(request.repo_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = str(uuid.uuid4())
    _AUDIT_JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "repo_path": str(validated_path),
        "incremental": request.incremental,
        "created_at": time.time(),
    }
    background_tasks.add_task(_execute_background_audit, job_id, str(validated_path), request.incremental)
    return {
        "job_id": job_id,
        "status": "queued",
        "status_url": f"/api/v1/audit/jobs/{job_id}",
    }


@router.get("/audit/jobs/{job_id}")
async def get_audit_job_status(
    job_id: str,
    _user: dict[str, Any] = Depends(get_current_user),
):
    """Returns current status and results of an asynchronous audit job."""
    job = _AUDIT_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Audit job '{job_id}' not found")
    return job


