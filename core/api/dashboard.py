"""Dashboard API endpoints for WARDEN — trend analysis, report history, comparisons."""

import json
import os
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


@router.get("/forecast")
async def get_forecast(
    repo_path: str = Query(default=".", description="Repository path to forecast quality trends for"),
    horizon: int = Query(default=5, ge=1, le=20, description="Number of steps into future to predict"),
) -> dict[str, Any]:
    """Returns time-series quality forecast with 95% confidence intervals and early warnings (C3)."""
    from core.services.trend_forecaster import TrendForecasterService

    service = TrendForecasterService()
    report = service.forecast_for_repo(repo_path=repo_path, horizon=horizon)
    return report.to_dict()


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


@router.get("/report/{report_id}/sarif")
async def get_report_sarif(report_id: int):
    """Exports audit findings in OASIS SARIF v2.1.0 standard JSON."""
    from fastapi.responses import JSONResponse

    from core.services.sarif_service import SarifReportService

    with Session(engine) as session:
        report = session.exec(select(AuditReport).where(AuditReport.id == report_id)).first()
        if not report:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    sarif_service = SarifReportService()
    data = report.raw_data or {}
    if not data.get("scorecard"):
        data["scorecard"] = {
            "total_score": report.total_score,
            "grade": report.grade,
            "layer1_score": report.layer1_score,
            "layer2_score": report.layer2_score,
        }

    sarif_doc = sarif_service.generate_sarif(data, repo_path=report.repo_path)
    return JSONResponse(
        content=sarif_doc,
        media_type="application/sarif+json",
        headers={"Content-Disposition": f"inline; filename=warden-report-{report_id}.sarif"},
    )


@router.get("/report/{report_id}/pdf")
async def get_report_pdf(report_id: int):
    """Generates and downloads a corporate PDF Executive Summary report."""
    from fastapi import Response

    from core.services.pdf_report_service import PdfReportService

    with Session(engine) as session:
        report = session.exec(select(AuditReport).where(AuditReport.id == report_id)).first()
        if not report:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    pdf_service = PdfReportService()
    data = report.raw_data or {}
    if not data.get("scorecard"):
        data["scorecard"] = {
            "total_score": report.total_score,
            "grade": report.grade,
            "layer1_score": report.layer1_score,
            "layer2_score": report.layer2_score,
            "group_scores": {
                "security_supply_chain": report.group_security or 0.0,
                "code_health_test": report.group_code_health or 0.0,
                "structural_health": report.group_structural or 0.0,
                "resilience_performance": report.group_resilience or 0.0,
                "dev_hygiene_devops": report.group_dev_hygiene or 0.0,
            },
        }

    pdf_bytes = pdf_service.generate_pdf_bytes(data, repo_path=report.repo_path)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=warden-executive-report-{report_id}.pdf"},
    )


from pydantic import BaseModel, Field


class DashboardQueryRequest(BaseModel):
    query: str = Field(..., description="Doğal dilde analiz veya dashboard sorusu")
    provider: str | None = Field(default=None, description="Opsiyonel LLM sağlayıcı adı (örn: gemini, openai, ollama)")


@router.post("/query")
async def execute_dashboard_query(body: DashboardQueryRequest) -> dict[str, Any]:
    """Translates natural language questions to secure SQL queries and returns tabular results with chart recommendations."""
    from core.services.nl_query_service import NaturalLanguageQueryService

    service = NaturalLanguageQueryService()
    try:
        return service.execute_query(body.query, provider_name=body.provider)
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err)) from val_err
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Sorgu yürütülürken hata oluştu: {exc}") from exc


class ScoreAnomalyEvaluateRequest(BaseModel):
    scorecard: dict[str, Any] = Field(..., description="Denetim skor kartı veya metrik sözlüğü")
    method: str = Field(default="hybrid", description="Anomali yöntemi: hybrid | mahalanobis | autoencoder | isolation_forest")


@router.get("/anomaly/{audit_id}")
async def get_audit_anomaly(
    audit_id: int,
    method: str = Query(default="hybrid", description="Anomali yöntemi: hybrid | mahalanobis | autoencoder | isolation_forest"),
) -> dict[str, Any]:
    """Evaluates historical audit by ID for multi-dimensional statistical, correlation, and structural anomalies."""
    from core.services.score_anomaly_service import ScoreAnomalyService

    service = ScoreAnomalyService()
    try:
        report = service.evaluate_audit_id(audit_id, method=method)
    except ValueError as val_err:
        raise HTTPException(status_code=404, detail=str(val_err)) from val_err
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Anomali analizi yürütülürken hata: {exc}") from exc

    return {
        "audit_id": audit_id,
        "anomaly": report.to_dict(),
    }


@router.post("/anomaly/evaluate")
async def evaluate_scorecard_anomaly(body: ScoreAnomalyEvaluateRequest) -> dict[str, Any]:
    """Dynamically evaluates an arbitrary scorecard for statistical, correlation, and reconstruction anomalies."""
    from core.services.score_anomaly_service import ScoreAnomalyService

    service = ScoreAnomalyService()
    try:
        report = service.evaluate_scorecard(body.scorecard, method=body.method)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Skor kartı değerlendirilirken hata: {exc}") from exc

    return {
        "evaluation": report.to_dict(),
    }


class BDDGenerateRequest(BaseModel):
    target_path: str = Field(default="tests", description="Taranacak test dizini veya dosyası")
    feature_dir: str | None = Field(default=None, description="Opsiyonel .feature dosyalarının yazılacağı dizin")
    markdown_output: str | None = Field(default=None, description="Opsiyonel Markdown dokümantasyon dosya yolu")
    enrich_llm: bool = Field(default=False, description="LLM ile senaryo başlıklarını zenginleştir")
    provider: str | None = Field(default=None, description="Opsiyonel LLM sağlayıcı adı")


@router.get("/bdd/summary")
async def get_bdd_summary(
    path: str = Query(default="tests", description="Taranacak test dizini veya dosyası"),
    limit_features: int = Query(default=30, ge=1, le=100),
) -> dict[str, Any]:
    """Extracts and catalogs BDD features and Given-When-Then scenarios from Python tests."""
    from core.services.bdd_scenario_generator import BDDScenarioGeneratorService

    service = BDDScenarioGeneratorService()
    try:
        report = service.generate_from_path(path)
        data = report.to_dict()
        data["features"] = data["features"][:limit_features]
        return data
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"BDD senaryoları çıkarılırken hata: {exc}") from exc


@router.post("/bdd/generate")
async def generate_bdd_scenarios(body: BDDGenerateRequest) -> dict[str, Any]:
    """Generates BDD scenarios, exports .feature files, and builds Markdown catalog."""
    from core.services.bdd_scenario_generator import BDDScenarioGeneratorService

    service = BDDScenarioGeneratorService()
    try:
        report = service.generate_from_path(
            body.target_path,
            enrich_with_llm=body.enrich_llm,
            provider_name=body.provider,
        )

        exported_features: list[str] = []
        if body.feature_dir:
            paths = service.export_feature_files(report, body.feature_dir)
            exported_features = [str(p) for p in paths]

        md_file_str: str | None = None
        if body.markdown_output:
            md_path = service.export_markdown_report(report, body.markdown_output)
            md_file_str = str(md_path)

        return {
            "success": True,
            "target_path": body.target_path,
            "total_features": report.total_features,
            "total_scenarios": report.total_scenarios,
            "total_steps": report.total_steps,
            "exported_feature_files": exported_features,
            "markdown_file": md_file_str,
            "summary": report.summary,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"BDD senaryoları oluşturulurken hata: {exc}") from exc


class PRReviewRequest(BaseModel):
    owner: str = Field(..., description="GitHub repository owner / organization")
    repo: str = Field(..., description="GitHub repository name")
    pull_number: int = Field(..., description="Pull Request number")
    min_score: int = Field(default=80, description="Minimum quality gate score threshold")
    post_to_github: bool = Field(default=False, description="Post comment or review to GitHub API")
    scorecard: dict[str, Any] | None = Field(default=None, description="Opsiyonel hazır denetim skor kartı")
    findings: list[dict[str, Any]] | None = Field(default=None, description="Opsiyonel bulgular listesi")
    token: str | None = Field(default=None, description="GitHub API token")


@router.post("/pr-review")
async def review_pull_request_endpoint(body: PRReviewRequest) -> dict[str, Any]:
    """Evaluates a Pull Request, computes quality gate status, and optionally posts a review comment."""
    from core.services.github_pr_bot import GitHubPRReviewBot

    bot = GitHubPRReviewBot(token=body.token)
    card = body.scorecard or {"total_score": 85.0, "grade": "B", "layer1_score": 82.0}

    try:
        report = bot.review_pull_request(
            scorecard=card,
            owner=body.owner,
            repo=body.repo,
            pull_number=body.pull_number,
            findings=body.findings,
            min_score=body.min_score,
            post_to_github=body.post_to_github,
        )
        return report.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PR değerlendirilirken hata oluştu: {exc}") from exc


@router.post("/github/webhook")
async def github_webhook_endpoint(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Receives and processes GitHub pull_request webhook events."""
    action = payload.get("action")
    pull_request = payload.get("pull_request")
    repository = payload.get("repository", {})

    if not pull_request or action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "reason": f"Event action '{action}' is not monitored for PR review."}

    owner = repository.get("owner", {}).get("login", "")
    repo_name = repository.get("name", "")
    pr_number = pull_request.get("number", 0)
    head_sha = pull_request.get("head", {}).get("sha")

    from core.services.github_pr_bot import GitHubPRReviewBot
    bot = GitHubPRReviewBot()

    # Default baseline scorecard for webhook trigger
    default_card = {"total_score": 82.0, "grade": "B", "layer1_score": 80.0}
    report = bot.review_pull_request(
        scorecard=default_card,
        owner=owner,
        repo=repo_name,
        pull_number=pr_number,
        commit_sha=head_sha,
        post_to_github=bool(os.getenv("GITHUB_TOKEN")),
    )

    return {
        "status": "processed",
        "action": action,
        "owner": owner,
        "repo": repo_name,
        "pr_number": pr_number,
        "passed_quality_gate": report.passed_quality_gate,
        "action_event": report.action_event,
    }


@router.get("/metrics/ck")
async def get_ck_metrics(
    target: str = Query(default="core", description="Taranacak dizin veya paket"),
    top: int = Query(default=15, ge=1, le=100, description="Döndürülecek en karmaşık sınıf sayısı"),
    smells_only: bool = Query(default=False, description="Yalnızca mimari kokusu olan sınıfları listele"),
) -> dict[str, Any]:
    """Computes Chidamber & Kemerer (CK) Object-Oriented metrics and architectural smell detections."""
    from core.services.ck_metrics_analyzer import CKMetricsAnalyzer

    analyzer = CKMetricsAnalyzer()
    try:
        report = analyzer.analyze(target)
        classes = report.high_risk_classes if smells_only else report.classes
        return {
            "target_path": report.target_path,
            "total_classes_analyzed": report.total_classes_analyzed,
            "avg_wmc": report.avg_wmc,
            "max_wmc": report.max_wmc,
            "avg_dit": report.avg_dit,
            "max_dit": report.max_dit,
            "avg_cbo": report.avg_cbo,
            "max_cbo": report.max_cbo,
            "avg_lcom4": report.avg_lcom4,
            "smells_summary": report.smells_summary,
            "classes": [c.to_dict() for c in classes[:top]],
            "summary": report.summary,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CK metrikleri hesaplanırken hata: {exc}") from exc






