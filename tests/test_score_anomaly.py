"""Unit and integration tests for Section C4 Advanced Multi-Dimensional Score Anomaly Engine."""

from __future__ import annotations

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from core.main import _run_anomaly_command, app
from core.services.score_anomaly_service import (
    AdvancedAnomalyReport,
    AutoencoderDetector,
    MahalanobisDetector,
    ScoreAnomalyService,
)


class TestMahalanobisMathematics:
    """Verifies the mathematical correctness of regularized Mahalanobis distance & Chi-Square p-values."""

    def test_fit_and_evaluate_at_mean(self):
        detector = MahalanobisDetector()
        # Synthetic clustered data around [80, 80]
        data = np.array([
            [80.0, 80.0],
            [82.0, 78.0],
            [79.0, 81.0],
            [81.0, 79.0],
            [80.0, 82.0],
        ])
        detector.fit(data)

        mean_vec = detector.mean_vector
        d_sq, p_val, contribs = detector.evaluate(mean_vec)

        # Distance at exact mean should be practically 0
        assert d_sq < 1e-4
        assert p_val > 0.99
        assert np.all(np.abs(contribs) < 1e-4)

    def test_outlier_vector_produces_high_distance(self):
        detector = MahalanobisDetector()
        data = np.array([
            [80.0, 80.0],
            [81.0, 79.0],
            [79.0, 81.0],
            [80.0, 82.0],
            [82.0, 78.0],
        ])
        detector.fit(data)

        # Extreme outlier at [20.0, 20.0]
        outlier = np.array([20.0, 20.0])
        d_sq, p_val, contribs = detector.evaluate(outlier)

        assert d_sq > 20.0
        assert p_val < 0.001
        assert len(contribs) == 2

    def test_ridge_regularization_handles_zero_variance(self):
        detector = MahalanobisDetector(ridge_epsilon=1e-3)
        # Identical points leading to zero covariance matrix
        singular_data = np.array([
            [80.0, 80.0],
            [80.0, 80.0],
            [80.0, 80.0],
        ])
        # Should not raise LinAlgError
        detector.fit(singular_data)
        assert detector.is_fitted
        d_sq, p_val, _ = detector.evaluate(np.array([80.0, 80.0]))
        assert d_sq == 0.0


class TestAutoencoderMathematics:
    """Verifies low-rank bottleneck projection and reconstruction error."""

    def test_fit_and_reconstruction_inlier(self):
        ae = AutoencoderDetector(n_components=2)
        # Correlated 4D synthetic data
        rng = np.random.default_rng(42)
        base = rng.normal(80.0, 5.0, (40, 1))
        X = np.hstack([base, base + 2.0, base - 1.0, base + 0.5])

        ae.fit(X)
        assert ae.is_fitted

        # Inlier should reconstruct with very small MSE
        inlier = X[0]
        mse, sq_errors = ae.evaluate(inlier)
        assert mse < ae.threshold_mse
        assert len(sq_errors) == 4

    def test_outlier_reconstruction_spike(self):
        ae = AutoencoderDetector(n_components=2)
        rng = np.random.default_rng(42)
        base = rng.normal(80.0, 5.0, (40, 1))
        X = np.hstack([base, base + 2.0, base - 1.0, base + 0.5])

        ae.fit(X)
        # Contradictory outlier breaking the correlated manifold
        outlier = np.array([80.0, 20.0, 80.0, 80.0])
        mse, sq_errors = ae.evaluate(outlier)

        # Dimension index 1 should have the largest squared reconstruction error
        assert mse > 10.0
        assert np.argmax(sq_errors) == 1


class TestScoreAnomalyService:
    """Verifies end-to-end multi-model score anomaly evaluation and root-cause analysis."""

    def test_normal_scorecard_true_negative(self):
        service = ScoreAnomalyService()
        normal_card = {
            "total_score": 82.0,
            "layer1_score": 80.0,
            "layer2_score": 84.0,
            "group_security": 85.0,
            "group_code_health": 80.0,
            "group_structural": 78.0,
            "group_resilience": 82.0,
            "group_dev_hygiene": 75.0,
        }
        report = service.evaluate_scorecard(normal_card, method="hybrid")

        assert isinstance(report, AdvancedAnomalyReport)
        assert not report.is_anomaly
        assert report.severity == "NORMAL"
        assert report.consensus_score < 50.0
        assert "Normal Skor Dağılımı" in report.verdict_summary

    def test_corrupted_scorecard_true_positive_with_root_cause(self):
        service = ScoreAnomalyService()
        corrupted_card = {
            "total_score": 45.0,
            "layer1_score": 40.0,
            "layer2_score": 50.0,
            "group_security": 15.0,  # Catastrophic drop
            "group_code_health": 30.0,
            "group_structural": 50.0,
            "group_resilience": 25.0,
            "group_dev_hygiene": 40.0,
        }
        report = service.evaluate_scorecard(corrupted_card, method="hybrid")

        assert report.is_anomaly
        assert report.severity in ("HIGH", "CRITICAL")
        assert report.consensus_score >= 65.0
        assert len(report.top_contributors) > 0
        assert len(report.remediation_actions) > 0

        # One of the top contributors should be security or layer1
        top_dims = [c.dimension for c in report.top_contributors]
        assert "group_security" in top_dims or "layer1_score" in top_dims

    def test_method_selection(self):
        service = ScoreAnomalyService()
        card = {
            "total_score": 50.0,
            "layer1_score": 45.0,
            "layer2_score": 55.0,
            "group_security": 20.0,
            "group_code_health": 40.0,
            "group_structural": 50.0,
            "group_resilience": 35.0,
            "group_dev_hygiene": 45.0,
        }

        rep_mah = service.evaluate_scorecard(card, method="mahalanobis")
        assert rep_mah.method == "mahalanobis"

        rep_ae = service.evaluate_scorecard(card, method="autoencoder")
        assert rep_ae.method == "autoencoder"

        rep_if = service.evaluate_scorecard(card, method="isolation_forest")
        assert rep_if.method == "isolation_forest"

    def test_extract_vector_with_nested_groups(self):
        service = ScoreAnomalyService()
        nested_card = {
            "scorecard": {
                "total_score": 88.0,
                "layer1_score": 85.0,
                "layer2_score": 90.0,
                "groups": {
                    "security": 92.0,
                    "code_health": 87.0,
                    "structural": 84.0,
                    "resilience": 89.0,
                    "dev_hygiene": 82.0,
                },
            }
        }
        vec = service._extract_vector_from_dict(nested_card)
        assert len(vec) == 8
        assert vec[0] == 88.0
        assert vec[3] == 92.0  # security
        assert vec[4] == 87.0  # code_health

    def test_missing_audit_id_raises_value_error(self):
        service = ScoreAnomalyService()
        with pytest.raises(ValueError, match="bulunamadı"):
            service.evaluate_audit_id(99999999)


class TestScoreAnomalyAPI:
    """Verifies REST API endpoints in core/api/dashboard.py."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_post_evaluate_scorecard(self):
        payload = {
            "scorecard": {
                "total_score": 85.0,
                "layer1_score": 82.0,
                "layer2_score": 88.0,
                "group_security": 88.0,
                "group_code_health": 82.0,
                "group_structural": 80.0,
                "group_resilience": 84.0,
                "group_dev_hygiene": 78.0,
            },
            "method": "hybrid",
        }
        res = self.client.post("/api/v1/dashboard/anomaly/evaluate", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "evaluation" in data
        assert "consensus_score" in data["evaluation"]
        assert "top_contributors" in data["evaluation"]

    def test_get_audit_anomaly_not_found(self):
        res = self.client.get("/api/v1/dashboard/anomaly/99999999")
        assert res.status_code == 404

    def test_get_audit_anomaly_success(self):
        # Find first valid audit ID from /api/v1/dashboard/repos
        repos_res = self.client.get("/api/v1/dashboard/repos")
        if repos_res.status_code == 200 and repos_res.json().get("repos"):
            first_audit_id = repos_res.json()["repos"][0]["id"]
            res = self.client.get(f"/api/v1/dashboard/anomaly/{first_audit_id}")
            assert res.status_code == 200
            data = res.json()
            assert data["audit_id"] == first_audit_id
            assert "anomaly" in data
            assert "mahalanobis_distance" in data["anomaly"]


class TestScoreAnomalyCLI:
    """Verifies CLI command warden anomaly."""

    def test_cli_anomaly_json(self, capsys):
        _run_anomaly_command(".", as_json=True)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "consensus_score" in data
        assert "mahalanobis_distance" in data
        assert "top_contributors" in data

    def test_cli_anomaly_output_file(self, tmp_path):
        out_file = tmp_path / "anomaly_out.json"
        _run_anomaly_command(".", output_file=str(out_file))
        assert out_file.is_file()
        content = json.loads(out_file.read_text(encoding="utf-8"))
        assert "verdict_summary" in content

    def test_cli_anomaly_invalid_target(self, capsys):
        _run_anomaly_command("99999999")
        captured = capsys.readouterr()
        assert "[!] Hata:" in captured.out
