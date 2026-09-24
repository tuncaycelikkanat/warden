"""Comprehensive unit and integration tests for WARDEN Dashboard API endpoints."""

from datetime import datetime

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from core.infra.database import engine
from core.main import app
from core.models.audit import AuditCoreMember, AuditReport

client = TestClient(app)


def test_dashboard_empty_summary():
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    assert "total_repos" in data
    assert "total_audits" in data
    assert "average_score" in data
    assert "grade_distribution" in data
    assert "latest_audits" in data


def test_dashboard_repos_and_trend_flow():
    # Insert two test reports
    with Session(engine) as session:
        rep1 = AuditReport(
            repo_path="/test/repo/alpha",
            total_score=85,
            grade="B",
            layer1_score=50,
            layer2_score=35,
            profile_signature="sig_alpha",
            group_security=90.0,
            group_code_health=80.0,
            group_structural=85.0,
            group_resilience=80.0,
            group_dev_hygiene=90.0,
            raw_data={"test": "data_1"},
            created_at=datetime.now(),
        )
        rep2 = AuditReport(
            repo_path="/test/repo/alpha",
            total_score=92,
            grade="A",
            layer1_score=55,
            layer2_score=37,
            profile_signature="sig_alpha",
            group_security=95.0,
            group_code_health=90.0,
            group_structural=90.0,
            group_resilience=85.0,
            group_dev_hygiene=95.0,

            raw_data={
                "layer2_categories": [
                    {
                        "category": "api_design",
                        "label": "API Disiplini",
                        "rubric_verdict": {"level": 8, "justification": "Clean endpoints"},
                    }
                ]
            },
            created_at=datetime.now(),
        )
        session.add(rep1)
        session.add(rep2)
        session.commit()
        session.refresh(rep1)
        session.refresh(rep2)

        mem = AuditCoreMember(
            report_id=rep2.id,
            group_key="security_supply_chain",
            member_key="security_semgrep",
            member_label="Semgrep SAST",
            score=95.0,
            weight_at_time=0.25,
            details='{"findings": 0}',
        )
        session.add(mem)
        session.commit()

        id1, id2 = rep1.id, rep2.id

    try:
        # 1. Test /repos
        res_repos = client.get("/api/v1/dashboard/repos")
        assert res_repos.status_code == 200
        repos_data = res_repos.json()
        assert repos_data["total"] >= 1
        matching = [r for r in repos_data["repos"] if r["repo_path"] == "/test/repo/alpha"]
        assert len(matching) == 1
        assert matching[0]["total_score"] == 92

        # 2. Test /report/{id}
        res_detail = client.get(f"/api/v1/dashboard/report/{id2}")
        assert res_detail.status_code == 200
        detail_data = res_detail.json()
        assert detail_data["id"] == id2
        assert detail_data["grade"] == "A"
        assert len(detail_data["members"]) == 1
        assert detail_data["members"][0]["member_key"] == "security_semgrep"
        assert len(detail_data["layer2_categories"]) == 1

        # 3. Test /trend?repo_path=...
        res_trend = client.get("/api/v1/dashboard/trend?repo_path=/test/repo/alpha&limit=10")
        assert res_trend.status_code == 200
        trend_data = res_trend.json()
        assert trend_data["repo_path"] == "/test/repo/alpha"
        assert len(trend_data["reports"]) >= 2

        # 4. Test /trend/{report_id}
        res_trend_id = client.get(f"/api/v1/dashboard/trend/{id1}")
        assert res_trend_id.status_code == 200
        assert res_trend_id.json()["repo_path"] == "/test/repo/alpha"

        # 5. Test /compare/{id1}/{id2}
        res_compare = client.get(f"/api/v1/dashboard/compare/{id1}/{id2}")
        assert res_compare.status_code == 200
        comp_data = res_compare.json()
        assert comp_data["delta"]["total_score"] == 7.0  # 92 - 85
        assert comp_data["delta"]["regression"] is False

        # 6. Test regression in /compare
        res_reg = client.get(f"/api/v1/dashboard/compare/{id2}/{id1}")
        assert res_reg.status_code == 200
        assert res_reg.json()["delta"]["regression"] is True  # 85 - 92 = -7 < -5

        # 7. Test /milestone/{id} (POST and DELETE)
        res_ms_post = client.post(f"/api/v1/dashboard/milestone/{id2}?label=v2.0-stable")
        assert res_ms_post.status_code == 200
        assert res_ms_post.json()["milestone_label"] == "v2.0-stable"

        # Verify detail reflects milestone
        res_detail_ms = client.get(f"/api/v1/dashboard/report/{id2}")
        assert res_detail_ms.json()["is_milestone"] is True
        assert res_detail_ms.json()["milestone_label"] == "v2.0-stable"

        # Clear milestone
        res_ms_del = client.delete(f"/api/v1/dashboard/milestone/{id2}")
        assert res_ms_del.status_code == 200
        assert res_ms_del.json()["success"] is True

        res_detail_cleared = client.get(f"/api/v1/dashboard/report/{id2}")
        assert res_detail_cleared.json()["is_milestone"] is False

    finally:
        # Cleanup test records
        with Session(engine) as session:
            m = session.exec(select(AuditCoreMember).where(AuditCoreMember.report_id == id2)).all()
            for item in m:
                session.delete(item)
            r1 = session.exec(select(AuditReport).where(AuditReport.id == id1)).first()
            if r1:
                session.delete(r1)
            r2 = session.exec(select(AuditReport).where(AuditReport.id == id2)).first()
            if r2:
                session.delete(r2)
            session.commit()


def test_dashboard_not_found_errors():
    # Report detail 404
    assert client.get("/api/v1/dashboard/report/999999").status_code == 404

    # Trend 404 for nonexistent report id
    assert client.get("/api/v1/dashboard/trend/999999").status_code == 404

    # Trend 404 for nonexistent repo path
    assert client.get("/api/v1/dashboard/trend?repo_path=/does/not/exist/at/all").status_code == 404

    # Compare 404 for nonexistent reports
    assert client.get("/api/v1/dashboard/compare/999999/1").status_code == 404
    assert client.get("/api/v1/dashboard/compare/1/999999").status_code == 404

    # Milestone 404
    assert client.post("/api/v1/dashboard/milestone/999999").status_code == 404
    assert client.delete("/api/v1/dashboard/milestone/999999").status_code == 404
