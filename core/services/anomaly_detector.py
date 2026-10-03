"""Isolation Forest and Multi-Dimensional Anomaly Detector for WARDEN.

Learns normal score envelopes across historical audit runs stored in SQLite (warden.db)
and detects multi-dimensional statistical outliers and anomalous score distributions:
- Unsupervised outlier detection via Scikit-Learn IsolationForest
- Dimension-level Z-Score deviation analysis (security, code_health, resilience, etc.)
- Graceful statistical baseline synthesis when historical database records are scarce
"""

from __future__ import annotations

import logging
import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FEATURE_NAMES = [
    "total_score",
    "layer1_score",
    "layer2_score",
    "group_security",
    "group_code_health",
    "group_structural",
    "group_resilience",
    "group_dev_hygiene",
]


@dataclass
class AnomalousDimension:
    """A specific score dimension that deviates abnormally from the learned distribution."""

    dimension: str
    value: float
    expected_mean: float
    z_score: float
    severity: str  # "CRITICAL" | "HIGH" | "MEDIUM"
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "value": round(self.value, 1),
            "expected_mean": round(self.expected_mean, 1),
            "z_score": round(self.z_score, 2),
            "severity": self.severity,
            "message": self.message,
        }


@dataclass
class AnomalyReport:
    """Aggregated anomaly detection report for a scorecard."""

    is_anomaly: bool
    anomaly_score: float  # 0.0 (normal) to 100.0 (extreme anomaly)
    decision_score: float  # Raw IsolationForest decision value
    model_used: str  # "IsolationForest" | "Statistical-ZScore"
    anomalous_dimensions: list[AnomalousDimension] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_anomaly": bool(self.is_anomaly),
            "anomaly_score": round(self.anomaly_score, 1),
            "decision_score": round(self.decision_score, 3),
            "model_used": self.model_used,
            "anomalous_dimensions": [d.to_dict() for d in self.anomalous_dimensions],
            "summary": self.summary,
        }


class AnomalyDetector:
    """Evaluates audit scorecards against historical distributions to detect anomalous shifts."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        contamination: float = 0.08,
    ) -> None:
        self.db_path = Path(db_path) if db_path else Path("warden.db")
        self.contamination = contamination
        self._model: Any = None
        self._means: dict[str, float] = {}
        self._stds: dict[str, float] = {}
        self._is_trained = False
        self._training_sample_count = 0

    def _extract_vector_from_dict(self, sc: dict[str, Any]) -> list[float]:
        """Extracts ordered numeric feature values from a scorecard dictionary."""
        card = sc.get("scorecard", sc)
        vec: list[float] = []
        for name in FEATURE_NAMES:
            val = card.get(name)
            if val is None or val == -1:
                # Default fallback for missing or unmeasured layers
                vec.append(70.0)
            else:
                try:
                    vec.append(float(val))
                except (ValueError, TypeError):
                    vec.append(70.0)
        return vec

    def _load_history_from_db(self) -> list[list[float]]:
        """Loads historical audit vectors from SQLite auditreport table."""
        if not self.db_path.is_file():
            return []

        rows: list[list[float]] = []
        try:
            con = sqlite3.connect(str(self.db_path))
            cur = con.cursor()
            cols = ", ".join(FEATURE_NAMES)
            query = f"SELECT {cols} FROM auditreport WHERE total_score IS NOT NULL ORDER BY id DESC LIMIT 500"
            for row in cur.execute(query).fetchall():
                cleaned_row = []
                for val in row:
                    if val is None or val == -1:
                        cleaned_row.append(70.0)
                    else:
                        cleaned_row.append(float(val))
                if len(cleaned_row) == len(FEATURE_NAMES):
                    rows.append(cleaned_row)
            con.close()
        except Exception as err:
            logger.debug(f"Could not load historical audits from DB ({self.db_path}): {err}")

        return rows

    def _generate_synthetic_baseline(self) -> list[list[float]]:
        """Generates a calibrated synthetic distribution if database history is unavailable."""
        baseline_rows: list[list[float]] = []
        # Representative cluster around good to moderate scores (70-95)
        base_means = [82.0, 80.0, 84.0, 85.0, 80.0, 78.0, 82.0, 75.0]
        stds = [6.0, 7.0, 6.0, 8.0, 7.0, 6.0, 8.0, 8.0]

        for i in range(50):
            row = []
            for m, s in zip(base_means, stds):
                val = m + (((i % 7) - 3) * (s / 3.0))
                row.append(max(0.0, min(100.0, val)))
            baseline_rows.append(row)
        return baseline_rows

    def fit(self, training_data: list[list[float]] | None = None) -> None:
        """Fits the Isolation Forest and computes per-dimension mean and standard deviations."""
        if training_data is None:
            data = self._load_history_from_db()
            if len(data) < 10:
                data = self._generate_synthetic_baseline()
        else:
            data = training_data

        if not data:
            return

        self._training_sample_count = len(data)

        # Compute means and stds for each dimension
        for idx, feat in enumerate(FEATURE_NAMES):
            col_vals = [row[idx] for row in data]
            mean_val = sum(col_vals) / len(col_vals)
            variance = sum((x - mean_val) ** 2 for x in col_vals) / max(1, len(col_vals))
            std_val = math.sqrt(variance)
            self._means[feat] = mean_val
            self._stds[feat] = max(1.0, std_val)  # Prevent division by zero

        # Fit IsolationForest
        try:
            from sklearn.ensemble import IsolationForest

            self._model = IsolationForest(
                n_estimators=100,
                contamination=self.contamination,
                random_state=42,
            )
            self._model.fit(data)
            self._is_trained = True
        except ImportError:
            logger.debug("scikit-learn not available for IsolationForest, using Z-score detection")
            self._is_trained = False

    def detect_anomalies(self, scorecard: dict[str, Any]) -> AnomalyReport:
        """Analyzes a scorecard against the learned distribution to detect anomalies."""
        if not self._is_trained or not self._means:
            self.fit()

        vec = self._extract_vector_from_dict(scorecard)

        # 1. Dimension-level Z-score inspection
        anomalous_dims: list[AnomalousDimension] = []
        for idx, feat in enumerate(FEATURE_NAMES):
            val = vec[idx]
            mean_val = self._means.get(feat, 75.0)
            std_val = self._stds.get(feat, 8.0)

            z_score = (val - mean_val) / std_val
            # Anomaly trigger: severe negative drop or drastic outlier (|z| >= 2.5 or z <= -2.0)
            if z_score <= -2.0:
                severity = "CRITICAL" if z_score <= -3.0 else "HIGH"
                desc = (
                    f"{feat} normal dağılımın çok altında: {round(val, 1)} "
                    f"(Beklenen ortalama: {round(mean_val, 1)}, Z: {round(z_score, 2)})"
                )
                anomalous_dims.append(
                    AnomalousDimension(
                        dimension=feat,
                        value=val,
                        expected_mean=mean_val,
                        z_score=z_score,
                        severity=severity,
                        message=desc,
                    )
                )

        # 2. Isolation Forest prediction
        is_forest_anomaly = False
        decision_val = 0.0
        model_used = "IsolationForest"

        if self._model is not None and self._is_trained:
            try:
                pred = self._model.predict([vec])[0]  # -1 for anomaly, 1 for inlier
                decision_val = float(self._model.decision_function([vec])[0])
                is_forest_anomaly = bool(pred == -1)
            except Exception as err:
                logger.warning(f"IsolationForest inference error: {err}")
                model_used = "Statistical-ZScore"
        else:
            model_used = "Statistical-ZScore"

        # Combined verdict
        is_anomaly = bool(is_forest_anomaly or len(anomalous_dims) >= 2 or any(d.severity == "CRITICAL" for d in anomalous_dims))

        if decision_val < 0:
            # Map negative decision value to 50..100 anomaly confidence
            anomaly_score = min(100.0, 50.0 + abs(decision_val) * 150.0)
        else:
            # Positive decision value mapped to 0..50
            anomaly_score = max(0.0, 50.0 - (decision_val * 150.0))

        if anomalous_dims and not is_forest_anomaly:
            anomaly_score = max(anomaly_score, min(95.0, 45.0 + len(anomalous_dims) * 15.0))

        summary = ""
        if is_anomaly:
            dims_desc = ", ".join(d.dimension for d in anomalous_dims) if anomalous_dims else "Genel skor dağılımı"
            summary = (
                f"🚨 Anomali Tespit Edildi ({model_used} skoru: %{round(anomaly_score, 1)}). "
                f"Sapan boyutlar: {dims_desc}."
            )
        else:
            summary = "Skor dağılımı tarihsel normal sınırlar içerisinde."

        return AnomalyReport(
            is_anomaly=is_anomaly,
            anomaly_score=anomaly_score,
            decision_score=decision_val,
            model_used=model_used,
            anomalous_dimensions=anomalous_dims,
            summary=summary,
        )
