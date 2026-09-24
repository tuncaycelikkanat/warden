"""Dashboard API endpoints for WARDEN — trend analysis, report history, comparisons."""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session, select

from core.infra.database import engine
from core.models.audit import AuditCoreMember, AuditReport

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def _report_to_dict(r: AuditReport) -> dict[str, Any]:
    """Converts an AuditReport ORM object to a JSON-serializable dict."""
    return {
        "id": r.id,
        "repo_path": r.repo_path,
        "total_score": r.total_score,
        "grade": r.grade,
        "layer1_score": r.layer1_score,
        "layer2_score": r.layer2_score if r.layer2_score != -1 else None,
        "profile_signature": r.profile_signature,
        "is_milestone": r.is_milestone,
        "milestone_label": r.milestone_label,
        "groups": {
            "security": r.group_security,
            "code_health": r.group_code_health,
            "structural": r.group_structural,
            "resilience": r.group_resilience,
            "dev_hygiene": r.group_dev_hygiene,
        },
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/repos")
async def list_repos() -> dict[str, Any]:
    """Returns all audited repository paths with their latest score."""
    with Session(engine) as session:
        reports = session.exec(select(AuditReport).order_by(AuditReport.id.desc())).all()  # type: ignore[call-overload,union-attr]

    # Group by repo_path, keep latest
    seen: dict[str, dict[str, Any]] = {}
    for r in reports:
        if r.repo_path not in seen:
            seen[r.repo_path] = _report_to_dict(r)

    return {"repos": list(seen.values()), "total": len(seen)}


@router.get("/trend/{report_id}")
async def get_trend_for_repo(
    report_id: int,
    limit: int = Query(default=30, ge=1, le=200),
) -> dict[str, Any]:
    """Returns score trend for the same repo as the given report (last N audits)."""
    with Session(engine) as session:
        anchor = session.exec(select(AuditReport).where(AuditReport.id == report_id)).first()
        if not anchor:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

        history = session.exec(
            select(AuditReport)
            .where(AuditReport.repo_path == anchor.repo_path)
            .order_by(AuditReport.id.desc())  # type: ignore[call-overload,union-attr]
            .limit(limit)
        ).all()

    return {
        "repo_path": anchor.repo_path,
        "reports": [_report_to_dict(r) for r in reversed(history)],
    }


@router.get("/trend")
async def get_trend(
    repo_path: str = Query(..., description="Repository path to get trend for"),
    limit: int = Query(default=30, ge=1, le=200),
) -> dict[str, Any]:
    """Returns score trend for a specific repo path (last N audits)."""
    with Session(engine) as session:
        history = session.exec(
            select(AuditReport)
            .where(AuditReport.repo_path == repo_path)
            .order_by(AuditReport.id.desc())  # type: ignore[call-overload,union-attr]
            .limit(limit)
        ).all()

    if not history:
        raise HTTPException(status_code=404, detail=f"No audits found for repo: {repo_path}")

    return {
        "repo_path": repo_path,
        "reports": [_report_to_dict(r) for r in reversed(history)],
    }


@router.get("/report/{report_id}")
async def get_report_detail(report_id: int) -> dict[str, Any]:
    """Returns full details of a specific audit report including member scores."""
    with Session(engine) as session:
        report = session.exec(select(AuditReport).where(AuditReport.id == report_id)).first()
        if not report:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

        members = session.exec(
            select(AuditCoreMember).where(AuditCoreMember.report_id == report_id)
        ).all()

    result = _report_to_dict(report)
    result["members"] = [
        {
            "group_key": m.group_key,
            "member_key": m.member_key,
            "member_label": m.member_label,
            "score": m.score,
            "weight": m.weight_at_time,
            "details": json.loads(m.details) if m.details else None,
        }
        for m in members
    ]

    # Include raw_data layer2 categories if present
    raw = report.raw_data or {}
    if "layer2_categories" in raw:
        result["layer2_categories"] = raw["layer2_categories"]

    return result


@router.get("/compare/{id_a}/{id_b}")
async def compare_reports(id_a: int, id_b: int) -> dict[str, Any]:
    """Compares two audit reports and returns score deltas for all dimensions."""
    with Session(engine) as session:
        rep_a = session.exec(select(AuditReport).where(AuditReport.id == id_a)).first()
        rep_b = session.exec(select(AuditReport).where(AuditReport.id == id_b)).first()

    if not rep_a:
        raise HTTPException(status_code=404, detail=f"Report {id_a} not found")
    if not rep_b:
        raise HTTPException(status_code=404, detail=f"Report {id_b} not found")

    def _delta(a: float | None, b: float | None) -> float | None:
        if a is None or b is None:
            return None
        return round(float(b) - float(a), 2)

    return {
        "report_a": _report_to_dict(rep_a),
        "report_b": _report_to_dict(rep_b),
        "delta": {
            "total_score": _delta(rep_a.total_score, rep_b.total_score),
            "layer1_score": _delta(rep_a.layer1_score, rep_b.layer1_score),
            "layer2_score": _delta(
                rep_a.layer2_score if rep_a.layer2_score != -1 else None,
                rep_b.layer2_score if rep_b.layer2_score != -1 else None,
            ),
            "groups": {
                "security": _delta(rep_a.group_security, rep_b.group_security),
                "code_health": _delta(rep_a.group_code_health, rep_b.group_code_health),
                "structural": _delta(rep_a.group_structural, rep_b.group_structural),
                "resilience": _delta(rep_a.group_resilience, rep_b.group_resilience),
                "dev_hygiene": _delta(rep_a.group_dev_hygiene, rep_b.group_dev_hygiene),
            },
            "regression": (rep_b.total_score - rep_a.total_score) < -5,
        },
    }


@router.get("/summary")
async def get_summary(
    limit: int = Query(default=10, ge=1, le=100),
) -> dict[str, Any]:
    """Returns a high-level summary: latest audit per repo + overall health stats."""
    with Session(engine) as session:
        all_reports = session.exec(
            select(AuditReport).order_by(AuditReport.id.desc())  # type: ignore[call-overload,union-attr]
        ).all()

    # Latest per repo
    latest_per_repo: dict[str, AuditReport] = {}
    for r in all_reports:
        if r.repo_path not in latest_per_repo:
            latest_per_repo[r.repo_path] = r

    latest_list = list(latest_per_repo.values())[:limit]
    scores = [r.total_score for r in latest_list]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    grade_counts: dict[str, int] = {}
    for r in latest_list:
        grade_counts[r.grade] = grade_counts.get(r.grade, 0) + 1

    return {
        "total_repos": len(latest_per_repo),
        "total_audits": len(all_reports),
        "average_score": avg_score,
        "grade_distribution": grade_counts,
        "latest_audits": [_report_to_dict(r) for r in latest_list],
    }


@router.post("/milestone/{report_id}")
async def set_milestone(report_id: int, label: str = "baseline") -> dict[str, Any]:
    """Marks an audit report as a milestone baseline for comparison purposes."""
    with Session(engine) as session:
        report = session.exec(select(AuditReport).where(AuditReport.id == report_id)).first()
        if not report:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

        report.is_milestone = True
        report.milestone_label = label
        session.add(report)
        session.commit()
        session.refresh(report)

    return {
        "success": True,
        "report_id": report_id,
        "milestone_label": label,
        "message": f"Report #{report_id} marked as milestone: '{label}'",
    }


@router.delete("/milestone/{report_id}")
async def clear_milestone(report_id: int) -> dict[str, Any]:
    """Removes the milestone flag from an audit report."""
    with Session(engine) as session:
        report = session.exec(select(AuditReport).where(AuditReport.id == report_id)).first()
        if not report:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

        report.is_milestone = False
        report.milestone_label = None
        session.add(report)
        session.commit()

    return {"success": True, "report_id": report_id, "message": "Milestone cleared"}
