"""Coverage-targeted unit tests for core/services/score_anomaly_service.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from sqlmodel import Session, SQLModel, create_engine

from core.models.audit import AuditReport
from core.services.anomaly_detector import FEATURE_NAMES
from core.services.score_anomaly_service import (
    AutoencoderDetector,
    MahalanobisDetector,
    ScoreAnomalyService,
)


class TestScoreAnomalyCoverage:
    """Covers edge cases and branches in ScoreAnomalyService and subdetectors."""

    def test_mahalanobis_fit_short_sample(self):
        detector = MahalanobisDetector()
        detector.fit(np.array([[10.0]]))
        assert not detector.is_fitted
        d2, p, contrib = detector.evaluate(np.array([10.0]))
        assert d2 == 0.0
        assert p == 1.0

    def test_mahalanobis_pinv_exception(self):
        detector = MahalanobisDetector()
        X = np.random.normal(50, 10, size=(10, 8))
        with patch("numpy.linalg.pinv", side_effect=RuntimeError("pinv failed")):
            detector.fit(X)
            assert detector.is_fitted
            assert detector.inv_covariance is not None
            d2, p, contrib = detector.evaluate(X[0])
            assert d2 >= 0.0

    def test_autoencoder_fit_short_sample(self):
        ae = AutoencoderDetector()
        ae.fit(np.array([[1.0, 2.0], [3.0, 4.0]]))
        assert not ae.is_fitted
        mse, sq_err = ae.evaluate(np.array([1.0, 2.0]))
        assert mse == 0.0

    def test_autoencoder_fit_exception(self):
        ae = AutoencoderDetector()
        X = np.random.normal(50, 5, size=(10, 8))
        with patch("sklearn.decomposition.PCA.fit", side_effect=Exception("PCA error")):
            ae.fit(X)
            assert not ae.is_fitted
            assert ae.threshold_mse == 25.0

    def test_extract_vector_invalid_values(self):
        service = ScoreAnomalyService(db_path=Path("nonexistent.db"))
        sc = {
            "scorecard": {
                "total_score": "not_a_number",
                "layer1_score": None,
                "layer2_score": -1,
                "groups": {
                    "security": object(),
                    "code_health": 85.0,
                },
            }
        }
        vec = service._extract_vector_from_dict(sc)
        assert len(vec) == len(FEATURE_NAMES)
        assert vec[0] == 70.0
        assert vec[1] == 70.0
        assert vec[2] == 70.0
        assert vec[3] == 70.0

    def test_load_history_from_db_missing_and_corrupt(self, tmp_path: Path):
        service = ScoreAnomalyService(db_path=tmp_path / "missing.db")
        data = service._load_history_from_db()
        assert len(data) == 0

        corrupt_db = tmp_path / "corrupt.db"
        corrupt_db.write_text("corrupted content", encoding="utf-8")
        service_corrupt = ScoreAnomalyService(db_path=corrupt_db)
        data = service_corrupt._load_history_from_db()
        assert len(data) == 0

    def test_fit_with_empty_or_list_data(self):
        service = ScoreAnomalyService()
        service.fit(training_data=[])
        assert not service._is_trained

        synthetic_list = [[80.0 + (i % 5)] * 8 for i in range(15)]
        service.fit(training_data=synthetic_list)
        assert service._is_trained

    def test_evaluate_scorecard_p_val_branches_and_methods(self):
        service = ScoreAnomalyService()
        synthetic_list = [[80.0 + (i % 3)] * 8 for i in range(20)]
        service.fit(training_data=synthetic_list)

        card = {FEATURE_NAMES[i]: 80.0 for i in range(len(FEATURE_NAMES))}

        rep_m = service.evaluate_scorecard(card, method="mahalanobis")
        assert rep_m.method == "mahalanobis"
        rep_ae = service.evaluate_scorecard(card, method="autoencoder")
        assert rep_ae.method == "autoencoder"
        rep_if = service.evaluate_scorecard(card, method="isolation_forest")
        assert rep_if.method == "isolation_forest"

        with patch.object(service.mahalanobis, "evaluate", return_value=(20.0, 0.005, np.ones(8))):
            rep = service.evaluate_scorecard(card)
            assert rep.severity in ("CRITICAL", "HIGH", "MEDIUM")

        with patch.object(service.mahalanobis, "evaluate", return_value=(15.0, 0.03, np.ones(8))):
            rep = service.evaluate_scorecard(card)
            assert rep.severity in ("CRITICAL", "HIGH", "MEDIUM", "NORMAL")

    def test_remediation_actions_fallback(self):
        service = ScoreAnomalyService()
        service.fit([[80.0 + i] * 8 for i in range(15)])

        card = {feat: 87.0 for feat in FEATURE_NAMES}
        rep = service.evaluate_scorecard(card)
        assert len(rep.remediation_actions) >= 1

    def test_evaluate_audit_id_and_evaluate_latest(self, tmp_path: Path):
        test_db = tmp_path / "test_audit.db"
        test_engine = create_engine(f"sqlite:///{test_db}")
        SQLModel.metadata.create_all(test_engine)

        with Session(test_engine) as session:
            audit = AuditReport(
                repo_path=str(tmp_path),
                total_score=85,
                grade="B",
                profile_signature="default",
                layer1_score=80,
                layer2_score=90,
                group_security=88.0,
                group_code_health=84.0,
                group_structural=82.0,
                group_resilience=85.0,
                group_dev_hygiene=86.0,
            )
            session.add(audit)
            session.commit()
            session.refresh(audit)
            audit_id = audit.id

        service = ScoreAnomalyService(db_path=test_db)

        with patch("core.infra.database.engine", test_engine):
            report = service.evaluate_audit_id(audit_id)
            assert report is not None
            assert report.raw_vector["total_score"] == 85.0

            with pytest.raises(ValueError, match="bulunamadı"):
                service.evaluate_audit_id(999999)

            rep_latest = service.evaluate_latest(str(tmp_path))
            assert rep_latest is not None

            rep_fallback = service.evaluate_latest("/some/other/path")
            assert rep_fallback is not None

            empty_db = tmp_path / "empty_audit.db"
            empty_engine = create_engine(f"sqlite:///{empty_db}")
            SQLModel.metadata.create_all(empty_engine)
            with patch("core.infra.database.engine", empty_engine):
                with pytest.raises(ValueError, match="bulunamadı"):
                    service.evaluate_latest()
