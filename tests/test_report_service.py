from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlmodel import Session, select

from core.infra.database import engine
from core.models.audit import AuditCoreMember, AuditReport
from core.services.report import AuditReportService


def test_fmt_delta():
    service = AuditReportService()
    assert service._fmt_delta(None, 10.0) == "—"
    assert service._fmt_delta(10.0, None) == "—"
    assert "⏸" in service._fmt_delta(50.0, 50.02)
    assert "🚀" in service._fmt_delta(80.0, 70.0)
    assert "↘" in service._fmt_delta(60.0, 70.0)


def test_fmt_status():
    service = AuditReportService()
    assert service._fmt_status(None) == "⚪ Ölçülmedi"
    assert service._fmt_status(96.0) == "🟢 Mükemmel"
    assert service._fmt_status(85.0) == "🟢 Başarılı"
    assert service._fmt_status(70.0) == "🟡 Geliştirilmeli"
    assert service._fmt_status(50.0) == "🔴 Kritik"


def test_build_summary_table():
    service = AuditReportService()
    lines = service._build_summary_table(
        prev_label="Audit #1",
        curr_label="Audit #2",
        curr_total=90,
        prev_total=80,
        curr_grade="A",
        prev_grade="B",
        curr_l1=55,
        prev_l1=50,
        curr_l2=35,
        prev_l2=30,
    )
    text = "\n".join(lines)
    assert "Audit #1" in text
    assert "Audit #2" in text
    assert "GENEL PUAN" in text


def test_build_l1_table():
    service = AuditReportService()
    curr_groups = {"security_supply_chain": 100.0}
    prev_groups = {"security_supply_chain": 90.0}
    curr_members = {"security_semgrep": 100.0}
    prev_members = {"security_semgrep": 90.0}

    lines = service._build_l1_table(
        prev_label="Prev",
        curr_label="Curr",
        curr_groups=curr_groups,
        prev_groups=prev_groups,
        curr_members=curr_members,
        prev_members=prev_members,
        has_prev=True,
    )
    text = "\n".join(lines)
    assert "Katman 1: 5 Grup" in text
    assert "Semgrep SAST" in text


def test_build_l2_table():
    service = AuditReportService()
    curr_l2 = [
        {
            "category": "api_design",
            "label": "API Tasarımı & OpenAPI",
            "rubric_verdict": {
                "level": 9,
                "justification": "RESTful endpoints with complete schemas",
            },
        }
    ]
    lines = service._build_l2_table("Prev", "Curr", curr_l2, {"api_design": 80.0})
    text = "\n".join(lines)
    assert "API Tasarımı & OpenAPI" in text
    assert "L9 (90)" in text


def test_save_to_db_and_resolve(tmp_path: Path):
    service = AuditReportService()
    mock_data = {
        "profile_signature": "cli",
        "scorecard": {
            "total_score": 92,
            "grade": "A",
            "layer1_score": 56,
            "layer2_score": 36,
            "group_scores": {
                "security_supply_chain": 100.0,
                "code_health_test": 95.0,
                "structural_health": 90.0,
                "resilience_performance": 100.0,
                "dev_hygiene_devops": 90.0,
            },
            "breakdown": {
                "member_scores": {
                    "security_semgrep": 100.0,
                    "test_coverage": 95.0,
                },
                "layer2_raw": [
                    {
                        "category": "api_design",
                        "label": "API Design",
                        "rubric_verdict": {"level": 9, "justification": "Clear contracts"},
                    }
                ],
            },
        },
    }

    report_id = service.save_to_db(str(tmp_path), mock_data)
    assert isinstance(report_id, int)

    # Check that AuditCoreMember records were inserted
    with Session(engine) as session:
        members = session.exec(
            select(AuditCoreMember).where(AuditCoreMember.report_id == report_id)
        ).all()
        assert len(members) >= 2

    # Check comparison scorecard generation
    scorecard_text = service.build_comparison_scorecard(str(tmp_path), mock_data, current_id=report_id)
    assert "WARDEN Hiyerarşik Denetim Karnesi" in scorecard_text

    # Cleanup DB records
    with Session(engine) as session:
        for m in members:
            session.delete(m)
        rep = session.exec(select(AuditReport).where(AuditReport.id == report_id)).first()
        if rep:
            session.delete(rep)
        session.commit()


def test_generate_markdown_fallback(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    service = AuditReportService()
    mock_data = {
        "profile_signature": "web",
        "scorecard": {
            "total_score": 95,
            "grade": "A+",
            "layer1_score": 58,
            "layer2_score": 37,
            "group_scores": {},
            "breakdown": {"member_scores": {}, "layer2_raw": []},
        },
    }
    out_file = service.generate_markdown(str(tmp_path), mock_data)
    assert Path(out_file).exists()
    content = Path(out_file).read_text(encoding="utf-8")
    assert "WARDEN Denetim Raporu" in content


def test_generate_markdown_with_gemini(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-api-key")
    service = AuditReportService()
    mock_data = {
        "profile_signature": "web",
        "scorecard": {
            "total_score": 95,
            "grade": "A+",
            "layer1_score": 58,
            "layer2_score": 37,
            "group_scores": {},
            "breakdown": {"member_scores": {}, "layer2_raw": []},
        },
    }

    mock_resp = MagicMock()
    mock_resp.text = "# WARDEN Executive Report\n## 6. Karne\nScorecard placeholder\n## 7. Actions\nNext steps"
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_resp

    with patch("google.genai.Client", return_value=mock_client):
        out_file = service.generate_markdown(str(tmp_path), mock_data)
        assert Path(out_file).exists()
        content = Path(out_file).read_text(encoding="utf-8")
        assert "WARDEN Executive Report" in content


def test_build_summary_table_unmeasured_layer2_warning():
    service = AuditReportService()
    rows = service._build_summary_table(
        prev_label="Audit #1",
        curr_label="Audit #2",
        curr_total=85,
        prev_total=80,
        curr_grade="B",
        prev_grade="B",
        curr_l1=85,
        prev_l1=80,
        curr_l2=None,
        prev_l2=70,
        weight_redistributed=True,
    )
    table_str = "".join(rows)
    assert "KATMAN 2 DEĞERLENDİRİLEMEDİ" in table_str
    assert "— (Ölçülmedi)" in table_str
    assert "⚪ Ölçülmedi" in table_str
    assert "(%100 Ağırlık)" in table_str


def test_save_to_db_with_unmeasured_layer2(tmp_path: Path):
    service = AuditReportService()
    mock_data = {
        "scorecard": {
            "total_score": 85,
            "grade": "B",
            "layer1_score": 85,
            "layer2_score": None,
            "group_scores": {},
            "breakdown": {"member_scores": {}},
            "weight_redistributed_to_layer1": True,
        },
        "profile_signature": "sig_unmeasured",
    }
    report_id = service.save_to_db(str(tmp_path), mock_data)
    assert report_id > 0

    with Session(engine) as session:
        rep = session.exec(select(AuditReport).where(AuditReport.id == report_id)).first()
        assert rep is not None
        assert rep.layer2_score == -1
        session.delete(rep)
        session.commit()

