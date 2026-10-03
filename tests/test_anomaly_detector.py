"""Unit tests for Isolation Forest AnomalyDetector and RegressionDetector integration (C2)."""

from pathlib import Path

import pytest

from core.services.anomaly_detector import AnomalyDetector
from core.services.regression_detector import RegressionDetector


class TestAnomalyDetector:
    @pytest.fixture
    def detector(self) -> AnomalyDetector:
        # Use synthetic baseline to keep unit test isolated and fast
        d = AnomalyDetector(db_path=Path("non_existent_test_warden.db"))
        d.fit()
        return d

    def test_normal_scorecard_not_flagged_as_anomaly(self, detector: AnomalyDetector) -> None:
        normal_card = {
            "scorecard": {
                "total_score": 82.0,
                "layer1_score": 80.0,
                "layer2_score": 85.0,
                "group_security": 84.0,
                "group_code_health": 80.0,
                "group_structural": 78.0,
                "group_resilience": 82.0,
                "group_dev_hygiene": 76.0,
            }
        }
        res = detector.detect_anomalies(normal_card)
        assert res.is_anomaly is False
        assert len(res.anomalous_dimensions) == 0
        assert res.anomaly_score < 50.0

    def test_severe_dimension_drop_detected_as_anomaly(self, detector: AnomalyDetector) -> None:
        abnormal_card = {
            "scorecard": {
                "total_score": 45.0,
                "layer1_score": 50.0,
                "layer2_score": 40.0,
                "group_security": 15.0,  # Drastic drop
                "group_code_health": 20.0,  # Drastic drop
                "group_structural": 75.0,
                "group_resilience": 70.0,
                "group_dev_hygiene": 65.0,
            }
        }
        res = detector.detect_anomalies(abnormal_card)
        assert res.is_anomaly is True
        flagged_dims = [d.dimension for d in res.anomalous_dimensions]
        assert "group_security" in flagged_dims
        assert "group_code_health" in flagged_dims
        assert any(d.severity in ("CRITICAL", "HIGH") for d in res.anomalous_dimensions)
        assert "🚨 Anomali Tespit Edildi" in res.summary

    def test_db_loading_when_db_exists(self) -> None:
        # warden.db exists in project root with 120 historical records
        real_db = Path("warden.db")
        if real_db.is_file():
            d = AnomalyDetector(db_path=real_db)
            d.fit()
            assert d._is_trained is True
            assert d._training_sample_count > 10

    def test_regression_detector_with_anomaly_check(self, detector: AnomalyDetector) -> None:
        reg_detector = RegressionDetector(anomaly_detector=detector)

        normal_prev = {
            "total_score": 85.0,
            "layer1_score": 85.0,
            "layer2_score": 85.0,
            "group_security": 85.0,
            "group_code_health": 85.0,
            "group_structural": 85.0,
            "group_resilience": 85.0,
            "group_dev_hygiene": 85.0,
        }
        anomalous_curr = {
            "total_score": 40.0,
            "layer1_score": 40.0,
            "layer2_score": 40.0,
            "group_security": 10.0,
            "group_code_health": 15.0,
            "group_structural": 70.0,
            "group_resilience": 70.0,
            "group_dev_hygiene": 70.0,
        }

        report = reg_detector.detect(anomalous_curr, normal_prev, check_anomalies=True)
        assert report.has_regression is True
        assert report.anomaly_report is not None
        assert report.anomaly_report.is_anomaly is True
        assert any("[ANOMALİ]" in w.message for w in report.warnings)

        d = report.to_dict()
        assert "anomaly" in d
        assert d["anomaly"]["is_anomaly"] is True
