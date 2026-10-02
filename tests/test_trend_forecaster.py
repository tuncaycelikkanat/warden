"""Unit and integration tests for Section C3 Time-Series Trend Forecaster."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core.main import app
from core.services.trend_forecaster import (
    DimensionForecast,
    ForecastPoint,
    QualityForecastReport,
    TrendForecasterService,
    get_grade_for_score,
)


class TestHoltMathematics:
    """Tests the mathematical correctness of Holt's Linear Exponential Smoothing."""

    def test_grade_thresholds(self):
        assert get_grade_for_score(96.0) == "A+"
        assert get_grade_for_score(91.0) == "A"
        assert get_grade_for_score(85.0) == "B"
        assert get_grade_for_score(75.0) == "C"
        assert get_grade_for_score(65.0) == "D"
        assert get_grade_for_score(50.0) == "F"

    def test_constant_series_forecast(self):
        svc = TrendForecasterService()
        series = [80.0, 80.0, 80.0, 80.0, 80.0, 80.0]
        res = svc.forecast_series(series, horizon=5)

        assert res.trend_direction == "STABLE"
        assert abs(res.velocity_per_audit) < 0.1
        assert len(res.forecast_points) == 5
        for p in res.forecast_points:
            assert abs(p.predicted_score - 80.0) < 1.0
            assert p.lower_bound_95 <= p.predicted_score <= p.upper_bound_95

    def test_improving_series_forecast(self):
        svc = TrendForecasterService()
        series = [60.0, 65.0, 70.0, 75.0, 80.0, 85.0]
        res = svc.forecast_series(series, horizon=3)

        assert res.velocity_per_audit > 0.5
        assert res.trend_direction == "IMPROVING"
        assert res.forecast_points[0].predicted_score > 85.0
        assert res.forecast_points[2].predicted_score > res.forecast_points[0].predicted_score
        assert "pozitif ivmeyle" in (res.early_warning or "")

    def test_degrading_series_forecast(self):
        svc = TrendForecasterService()
        series = [95.0, 90.0, 85.0, 80.0, 75.0, 70.0]
        res = svc.forecast_series(series, horizon=4)

        assert res.velocity_per_audit < -0.5
        assert res.trend_direction in ("DEGRADING", "CRITICAL_DROP")
        assert res.forecast_points[0].predicted_score < 70.0
        assert res.forecast_points[3].predicted_score < res.forecast_points[0].predicted_score

    def test_clamping_to_zero_and_hundred(self):
        svc = TrendForecasterService()
        # High upward velocity
        rising = [85.0, 90.0, 95.0, 98.0, 99.0, 100.0]
        res_rise = svc.forecast_series(rising, horizon=5)
        for p in res_rise.forecast_points:
            assert p.predicted_score <= 100.0
            assert p.upper_bound_95 <= 100.0

        # Steep downward velocity
        falling = [30.0, 20.0, 15.0, 10.0, 5.0, 2.0]
        res_fall = svc.forecast_series(falling, horizon=5)
        for p in res_fall.forecast_points:
            assert p.predicted_score >= 0.0
            assert p.lower_bound_95 >= 0.0


class TestDataVolumeHandling:
    """Tests forecaster behavior under varying historical data sizes."""

    def test_empty_series_insufficient_data(self):
        svc = TrendForecasterService()
        res = svc.forecast_series([])
        assert res.status == "INSUFFICIENT_DATA"
        assert len(res.forecast_points) == 0

    def test_single_value_insufficient_data(self):
        svc = TrendForecasterService()
        res = svc.forecast_series([85.0])
        assert res.status == "INSUFFICIENT_DATA"
        assert res.current_score == 85.0
        assert len(res.forecast_points) == 0

    def test_limited_data_fallback(self):
        svc = TrendForecasterService()
        # 3 points: between 2 and 4 -> LIMITED_DATA
        res = svc.forecast_series([70.0, 75.0, 80.0], horizon=3)
        assert res.status == "LIMITED_DATA"
        assert len(res.forecast_points) == 3
        assert res.velocity_per_audit == 5.0  # (80 - 70) / 2
        assert res.forecast_points[0].predicted_score == 85.0

    def test_rich_data_holt_model(self):
        svc = TrendForecasterService()
        res = svc.forecast_series([60.0, 65.0, 70.0, 75.0, 80.0, 85.0, 90.0], horizon=4)
        assert res.status == "OK"
        assert len(res.forecast_points) == 4


class TestEarlyWarningAndFloorDetection:
    """Tests early warning alerts when quality approaches critical floors."""

    def test_early_warning_approaching_c_grade(self):
        svc = TrendForecasterService()
        # Current score 80 (B), dropping ~3 pts per audit towards C (70)
        series = [92.0, 89.0, 86.0, 83.0, 80.0]
        res = svc.forecast_series(series, horizon=5)

        assert res.velocity_per_audit < 0
        assert res.steps_to_grade_drop is not None
        assert res.steps_to_grade_drop > 0
        assert res.early_warning is not None
        assert "notunun" in res.early_warning

    def test_early_warning_already_below_critical(self):
        svc = TrendForecasterService()
        # Current score 50 (F), dropping further
        series = [60.0, 58.0, 55.0, 52.0, 50.0]
        res = svc.forecast_series(series, horizon=3)

        assert res.early_warning is not None
        assert "kritik eşiğin altında" in res.early_warning


class TestMultidimensionalHistoryForecast:
    """Tests forecasting across multiple quality dimensions from historical records."""

    def test_forecast_from_history(self):
        svc = TrendForecasterService()
        history = [
            {
                "total_score": 70.0,
                "group_security": 60.0,
                "group_code_health": 80.0,
            },
            {
                "total_score": 75.0,
                "group_security": 65.0,
                "group_code_health": 82.0,
            },
            {
                "total_score": 80.0,
                "group_security": 70.0,
                "group_code_health": 85.0,
            },
        ]
        rep = svc.forecast_from_history(history, horizon=3)

        assert isinstance(rep, QualityForecastReport)
        assert rep.total_audits_analyzed == 3
        assert rep.overall_forecast.current_score == 80.0
        assert "group_security" in rep.dimension_forecasts
        assert "group_code_health" in rep.dimension_forecasts
        assert rep.summary != ""

        d = rep.to_dict()
        assert d["horizon"] == 3
        assert "overall_forecast" in d
        assert "group_security" in d["dimension_forecasts"]

    def test_forecast_from_empty_history(self):
        svc = TrendForecasterService()
        rep = svc.forecast_from_history([])
        assert rep.total_audits_analyzed == 0
        assert rep.overall_forecast.status == "INSUFFICIENT_DATA"


class TestDashboardForecastAPI:
    """Tests FastAPI endpoint GET /api/v1/dashboard/forecast."""

    def test_dashboard_forecast_endpoint(self):
        client = TestClient(app)
        resp = client.get("/api/v1/dashboard/forecast?repo_path=.&horizon=4")
        assert resp.status_code == 200
        data = resp.json()

        assert "repo_path" in data
        assert data["horizon"] == 4
        assert "overall_forecast" in data
        assert "model_name" in data


class TestCLIForecastCommand:
    """Tests CLI `warden forecast` command."""

    def test_cli_forecast_text_output(self, capsys):
        from core.main import _run_forecast_command

        _run_forecast_command(".", horizon=3, dimension="total")
        captured = capsys.readouterr()

        assert "WARDEN KALİTE TREND TAHMİNLEME" in captured.out
        assert "Gelecek 3 Denetim Tahmini" in captured.out
        assert "Kalite İvmesi" in captured.out

    def test_cli_forecast_all_dimensions(self, capsys):
        from core.main import _run_forecast_command

        _run_forecast_command(".", horizon=2, dimension="all")
        captured = capsys.readouterr()

        assert "WARDEN KALİTE TREND TAHMİNLEME" in captured.out
        assert "ALT GRUP KALİTE İVMELERİ" in captured.out

    def test_cli_forecast_json_output(self, capsys, tmp_path: Path):
        from core.main import _run_forecast_command

        out_json = tmp_path / "forecast_test.json"
        _run_forecast_command(".", horizon=2, as_json=True, output_file=str(out_json))
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        assert data["horizon"] == 2
        assert "overall_forecast" in data
        assert out_json.is_file()
