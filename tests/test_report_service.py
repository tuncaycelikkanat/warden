"""Comprehensive unit tests for AuditReportService and report formatting."""

import dataclasses
import uuid
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session, select

from core.infra.database import create_db_and_tables, engine
from core.models.audit import AuditReport
from core.services.report import AuditReportService, _make_json_safe


@dataclasses.dataclass
class SampleData:
    name: str
    count: int


def test_make_json_safe():
    now = datetime.now()
    today = date.today()
    path = Path("/tmp/test")
    sample_dc = SampleData("test", 10)

    class CustomObj:
        def __init__(self):
            self.x = 1
            self.y = "abc"

    raw = {
        "str": "hello",
        "int": 42,
        "float": 3.14,
        "bool": True,
        "none": None,
        "dt": now,
        "d": today,
        "path": path,
        "dc": sample_dc,
        "obj": CustomObj(),
        "set": {1, 2, 3},
        "tuple": (4, 5),
    }

    safe = _make_json_safe(raw)
    assert safe["str"] == "hello"
    assert safe["dt"] == now.isoformat()
    assert safe["d"] == today.isoformat()
    assert safe["path"] == str(path)
    assert safe["dc"] == {"name": "test", "count": 10}
    assert safe["obj"] == {"x": 1, "y": "abc"}
    assert safe["set"] == [1, 2, 3]
    assert safe["tuple"] == [4, 5]


def test_fmt_delta_and_status():
    svc = AuditReportService()
    # _fmt_delta
    assert svc._fmt_delta(None, 80) == "—"
    assert svc._fmt_delta(80, None) == "—"
    assert svc._fmt_delta(80.0, 80.02) == "0.0 ⏸"
    assert "+5.0 🚀" in svc._fmt_delta(85, 80)
    assert "-5.0 ↘" in svc._fmt_delta(75, 80)

    # _fmt_status
    assert svc._fmt_status(None) == "⚪ Ölçülmedi"
    assert "Mükemmel" in svc._fmt_status(95)
    assert "Başarılı" in svc._fmt_status(80)
    assert "Geliştirilmeli" in svc._fmt_status(65)
    assert "Kritik" in svc._fmt_status(40)


def test_inject_scorecard_matrix_and_header():
    svc = AuditReportService()

    # Matrix injection
    # 1. Already contains matrix
    content1 = "### 🎓 WARDEN Hiyerarşik Denetim Karnesi\nDetails"
    assert svc._inject_scorecard_matrix(content1, "NEW MATRIX") == content1

    # 2. Contains ## 6. and ## 7.
    content2 = "# Report\n## 6. Scorecard\nOld score\n## 7. Next Steps\nDo this"
    injected2 = svc._inject_scorecard_matrix(content2, "NEW MATRIX")
    assert "NEW MATRIX" in injected2
    assert "## 7. Next Steps" in injected2

    # 3. Neither
    content3 = "# Simple Report\nSome text"
    injected3 = svc._inject_scorecard_matrix(content3, "NEW MATRIX")
    assert "## 6. Genel Puan Tablosu" in injected3

    # Header metadata injection
    badge = "> 📅 Date badge"
    # 1. Already present
    assert svc._inject_header_metadata(f"{badge}\n# Title", badge) == f"{badge}\n# Title"
    # 2. Injected after # Title
    injected_hdr = svc._inject_header_metadata("# Title\nBody text", badge)
    assert badge in injected_hdr
    assert injected_hdr.startswith("# Title")
    # 3. No # Title
    injected_no_hdr = svc._inject_header_metadata("Just body text", badge)
    assert injected_no_hdr.startswith(badge)


def test_save_to_db_and_get_comparison_report(tmp_path):
    create_db_and_tables()
    svc = AuditReportService()

    repo_str = str(tmp_path / f"repo_report_test_{uuid.uuid4().hex}")

    data = {
        "profile_signature": "sig_test_1",
        "scorecard": {
            "total_score": 85,
            "grade": "B",
            "layer1_score": 85,
            "layer2_score": 85,
            "group_scores": {
                "security_supply_chain": 90.0,
                "code_health_test": 80.0,
                "structural_health": 85.0,
                "resilience_performance": 85.0,
                "dev_hygiene_devops": 85.0,
            },
            "breakdown": {
                "member_scores": {
                    "sec_secrets": 100.0,
                    "code_complexity": 75.0,
                }
            },
        },
    }

    # 1. Save first report
    id1 = svc.save_to_db(repo_str, data)
    assert id1 > 0

    # 2. Save second report
    data2 = dict(data)
    data2["scorecard"] = dict(data["scorecard"])
    data2["scorecard"]["total_score"] = 92
    data2["scorecard"]["grade"] = "A"
    id2 = svc.save_to_db(repo_str, data2)
    assert id2 > id1

    # Get comparison report for id2 -> should be id1
    prev = svc._get_comparison_report(repo_str, current_id=id2)
    assert prev is not None
    assert prev.id == id1

    # Mark id1 as milestone
    with Session(engine) as session:
        rep1 = session.exec(select(AuditReport).where(AuditReport.id == id1)).first()
        rep1.is_milestone = True
        rep1.milestone_label = "v1-baseline"
        session.add(rep1)
        session.commit()

    # Save third report
    id3 = svc.save_to_db(repo_str, data)
    # Comparison report should prefer milestone id1 over id2!
    comp = svc._get_comparison_report(repo_str, current_id=id3)
    assert comp is not None
    assert comp.id == id1
    assert comp.is_milestone is True


def test_call_gemini_report_fallback_and_failure():
    svc = AuditReportService()
    mock_client = MagicMock()

    # First model fails, second succeeds
    mock_resp = MagicMock(text="# Executive Report")
    mock_client.models.generate_content.side_effect = [
        Exception("404 Model Not Found"),
        mock_resp,
    ]

    res = svc._call_gemini_report(mock_client, "Audit Prompt")
    assert res == "# Executive Report"

    # All models fail
    mock_client.models.generate_content.side_effect = Exception("Quota exceeded")
    with pytest.raises(Exception, match="Quota exceeded"):
        svc._call_gemini_report(mock_client, "Audit Prompt")


def test_generate_markdown_without_gemini_key(tmp_path):
    svc = AuditReportService()
    data = {
        "scorecard": {
            "total_score": 88,
            "grade": "B",
            "layer1_score": 90,
            "layer2_score": 85,
            "group_scores": {},
            "breakdown": {"member_scores": {}},
        },
    }

    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        out_path = svc.generate_markdown(str(tmp_path), data)
        assert Path(out_path).exists()
        content = Path(out_path).read_text(encoding="utf-8")
        assert "WARDEN Denetim Raporu" in content
        assert "88" in content


def test_generate_markdown_with_gemini_key_success(tmp_path):
    svc = AuditReportService()
    data = {
        "scorecard": {
            "total_score": 95,
            "grade": "A",
            "layer1_score": 95,
            "layer2_score": 95,
            "group_scores": {},
            "breakdown": {"member_scores": {}},
        },
    }

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MagicMock(
        text="# WARDEN — Kapsamlı Proje İnceleme ve Denetim Raporu\n\n## 1. Yönetici Özeti\nİyi durumda."
    )

    with patch.dict("os.environ", {"GEMINI_API_KEY": "dummy-key"}), \
         patch("google.genai.Client", return_value=mock_client):
        out_path = svc.generate_markdown(str(tmp_path), data)
        assert Path(out_path).exists()
        content = Path(out_path).read_text(encoding="utf-8")
        assert "WARDEN" in content
        assert "Denetim Tarihi" in content


def test_build_comparison_scorecard_comprehensive(tmp_path):
    create_db_and_tables()
    svc = AuditReportService()

    repo_str = str(tmp_path / f"repo_full_matrix_{uuid.uuid4().hex}")

    # Previous baseline report
    prev_data = {
        "profile_signature": "sig_prev",
        "scorecard": {
            "total_score": 70,
            "grade": "C",
            "layer1_score": 75,
            "layer2_score": 65,
            "group_scores": {
                "security_supply_chain": 70.0,
                "code_health_test": 70.0,
                "structural_health": 70.0,
                "resilience_performance": 70.0,
                "dev_hygiene_devops": 70.0,
            },
            "breakdown": {
                "member_scores": {
                    "sec_secrets": 80.0,
                    "code_complexity": 60.0,
                }
            },
        },
    }
    prev_id = svc.save_to_db(repo_str, prev_data)

    # Current report with L2 rubric verdicts and Vibe data
    curr_data = {
        "profile_signature": "sig_curr",
        "scorecard": {
            "total_score": 88,
            "grade": "B",
            "layer1_score": 90,
            "layer2_score": 85,
            "weight_redistributed": False,
            "group_scores": {
                "security_supply_chain": 90.0,
                "code_health_test": 85.0,
                "structural_health": 88.0,
                "resilience_performance": 90.0,
                "dev_hygiene_devops": 85.0,
            },
            "breakdown": {
                "member_scores": {
                    "sec_secrets": 100.0,
                    "code_complexity": 80.0,
                },
                "layer2_raw": [
                    {
                        "category": "architecture_modularity",
                        "level": 8,
                        "rationale": "High modularity with clean interfaces.",
                    },
                    {
                        "category": "error_handling",
                        "level": None,  # Test unmeasured branch
                        "rationale": "Not evaluated.",
                    },
                ],
            },
        },
    }

    curr_id = svc.save_to_db(repo_str, curr_data)

    matrix = svc.build_comparison_scorecard(repo_str, curr_data, current_id=curr_id)
    assert "### 🎓 WARDEN Hiyerarşik Denetim Karnesi" in matrix
    assert "Katman 1 (Mekanik & Deterministik %60)" in matrix
    assert "Katman 2 (Mimari LLM Rubrik %40)" in matrix
    assert "architecture_modularity" in matrix
    assert "Ölçülmedi" in matrix  # For None level

