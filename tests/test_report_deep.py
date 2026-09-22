"""Comprehensive tests for AuditReportService markdown generation and database persistence edge cases."""
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from core.services.report import AuditReportService, _make_json_safe


def test_make_json_safe():
    class CustomObj:
        def __init__(self):
            self.x = 10
            self.name = "test"

    raw = {
        "num": 1,
        "list": [CustomObj(), {1, 2}],
        "custom": CustomObj(),
    }
    safe = _make_json_safe(raw)
    assert safe["num"] == 1
    assert isinstance(safe["list"][0], dict)
    assert safe["custom"]["name"] == "test"


def test_fmt_delta_and_status():
    svc = AuditReportService()
    assert svc._fmt_delta(None, 50.0) == "—"
    assert svc._fmt_delta(50.02, 50.0) == "0.0 ⏸"
    assert "🚀" in svc._fmt_delta(80.0, 70.0)
    assert "↘" in svc._fmt_delta(60.0, 70.0)

    assert "Ölçülmedi" in svc._fmt_status(None)
    assert "Mükemmel" in svc._fmt_status(95.0)
    assert "Başarılı" in svc._fmt_status(80.0)
    assert "Geliştirilmeli" in svc._fmt_status(65.0)
    assert "Kritik" in svc._fmt_status(40.0)


def test_build_summary_and_l2_tables():
    svc = AuditReportService()

    # Summary table with weight_redistributed and curr_l2=None
    summary_rows = svc._build_summary_table(
        prev_label="Önceki",
        curr_label="Şimdiki",
        curr_total=85,
        prev_total=80,
        curr_grade="B",
        prev_grade="C",
        curr_l1=85,
        prev_l1=80,
        curr_l2=None,
        prev_l2=None,
        weight_redistributed=True,
    )
    assert any("KATMAN 2 DEĞERLENDİRİLEMEDİ" in r for r in summary_rows)

    # L2 table with both evaluated and unmeasured categories
    l2_cats = [
        {
            "category": "api_design",
            "label": "API Tasarımı",
            "rubric_verdict": {"level": 8, "justification": "RESTful endpoints well structured"}
        },
        {
            "category": "cloud_native",
            "label": "Bulut Mimarisi",
            "rubric_verdict": {"level": None, "justification": "Not applicable"}
        }
    ]
    l2_rows = svc._build_l2_table("Önceki", "Şimdiki", l2_cats, {"api_design": 70.0})
    assert any("L8" in r for r in l2_rows)
    assert any("Ölçülmedi" in r for r in l2_rows)


def test_resolve_prev_report_baseline_exception():
    svc = AuditReportService()
    with patch("core.services.report.Session", side_effect=RuntimeError("DB connect error")):
        prev = svc._resolve_prev_report("repo", current_id=2, baseline_id=1)
        assert prev is None


def test_generate_markdown_ai_failure_fallback(tmp_path: Path):
    svc = AuditReportService()
    data = {
        "scorecard": {
            "total_score": 88,
            "grade": "B",
            "layer1_score": 88,
            "layer2_score": -1,
            "group_scores": {},
            "breakdown": {"member_scores": {}}
        }
    }

    # Force AI call to fail so it hits lines 489-493
    with patch.object(svc, "_call_gemini_report", side_effect=RuntimeError("AI API down")):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test_key"}):
            out_file = svc.generate_markdown(str(tmp_path), data)
            content = Path(out_file).read_text(encoding="utf-8")
            assert "WARDEN Fallback Report" in content
            assert "Score: 88/100" in content
