"""Advanced Multi-Dimensional Score Anomaly Engine for WARDEN (Section C4).

Combines:
1. Multivariate Mahalanobis Distance (accounting for cross-metric covariance & Chi-Square p-value).
2. Autoencoder Reconstruction Error (bottleneck projection capturing manifold breakages).
3. Isolation Forest consensus score (tree-based outlier isolation).
4. Explainable Root Cause Attribution (Top Contributors and Actionable Recommendations).
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import chi2
from sklearn.decomposition import PCA

from core.services.anomaly_detector import FEATURE_NAMES, AnomalyDetector

logger = logging.getLogger(__name__)

ACTION_RECOMMENDATIONS: dict[str, str] = {
    "group_security": "Kritik güvenlik açıklarını (CVE/Semgrep) giderin ve SBOM bağımlılık risklerini güncelleyin.",
    "group_code_health": "Test kapsamını (%80+) artırın ve AST mutasyon testinde hayatta kalan mutantları temizleyin.",
    "group_structural": "Döngüsel importları (circular imports) çözün ve Cyclomatic Complexity / SQALE teknik borcunu azaltın.",
    "group_resilience": "Hata yakalama (bare except), mock sızıntıları ve resilience desenlerini iyileştirin.",
    "group_dev_hygiene": "Dökümantasyon, docstring kapsamı ve commit hijyeni standartlarını sağlayın.",
    "total_score": "Genel mimari kalite eşiklerinin altına inildi; kritik kalite kapısı aksiyonlarını uygulayın.",
    "layer1_score": "Statik analiz kurallarında (linter, tip kontrolü, güvenlik) toplu kalite gerilemesi tespit edildi.",
    "layer2_score": "LLM mimari değerlendirme rubriklerinde yapısal ve kod kalitesi kırılmaları gözlendi.",
}


@dataclass
class AnomalyContribution:
    """Explains a single dimension's contribution to the detected anomaly."""

    dimension: str
    contribution_pct: float  # 0.0 - 100.0%
    actual_value: float
    expected_mean: float
    deviation: float
    direction: str  # "DROP" | "SURGE"
    action_recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AdvancedAnomalyReport:
    """Comprehensive anomaly report with consensus scoring and root-cause analysis."""

    is_anomaly: bool
    consensus_score: float  # 0.0 (normal) - 100.0 (extreme anomaly)
    severity: str  # "NORMAL" | "MEDIUM" | "HIGH" | "CRITICAL"
    method: str  # "hybrid" | "mahalanobis" | "autoencoder" | "isolation_forest"
    mahalanobis_distance: float
    p_value: float
    reconstruction_mse: float
    isolation_forest_score: float
    top_contributors: list[AnomalyContribution] = field(default_factory=list)
    remediation_actions: list[str] = field(default_factory=list)
    verdict_summary: str = ""
    raw_vector: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_anomaly"] = bool(self.is_anomaly)
        data["top_contributors"] = [c.to_dict() if hasattr(c, "to_dict") else c for c in self.top_contributors]
        return data


class MahalanobisDetector:
    """Detects multi-dimensional correlation anomalies via regularized covariance & Chi-Square test."""

    def __init__(self, ridge_epsilon: float = 1e-3) -> None:
        self.ridge_epsilon = ridge_epsilon
        self.mean_vector: np.ndarray | None = None
        self.inv_covariance: np.ndarray | None = None
        self.df: int = len(FEATURE_NAMES)
        self.is_fitted: bool = False

    def fit(self, X: np.ndarray) -> None:
        """Computes empirical mean and regularized inverse covariance matrix."""
        if len(X) < 2:
            return

        self.mean_vector = np.mean(X, axis=0)
        # Compute sample covariance matrix
        cov = np.cov(X, rowvar=False)
        if cov.ndim == 0:
            cov = np.array([[float(cov)]])
        elif cov.ndim == 1:
            cov = np.diag(cov)

        # Apply ridge regularization to guarantee invertibility (Sigma + eps * I)
        dim = cov.shape[0]
        self.df = dim
        reg_cov = cov + (self.ridge_epsilon * np.eye(dim))

        try:
            self.inv_covariance = np.linalg.pinv(reg_cov)
            self.is_fitted = True
        except Exception as err:
            logger.warning(f"Mahalanobis covariance inversion failed: {err}")
            self.inv_covariance = np.eye(dim)
            self.is_fitted = True

    def evaluate(self, x: np.ndarray) -> tuple[float, float, np.ndarray]:
        """Calculates Mahalanobis distance squared (D_M^2), Chi-Square p-value, and per-feature contributions."""
        if not self.is_fitted or self.mean_vector is None or self.inv_covariance is None:
            return 0.0, 1.0, np.zeros_like(x)

        diff = x - self.mean_vector
        # D_M^2 = diff^T * inv_cov * diff
        intermediate = np.dot(self.inv_covariance, diff)
        d_squared = float(np.dot(diff, intermediate))
        d_squared = max(0.0, d_squared)

        # p-value from Chi-square survival function (1 - CDF)
        p_val = float(chi2.sf(d_squared, df=self.df))

        # Per-dimension attribution: c_i = diff_i * intermediate_i
        contributions = diff * intermediate
        return d_squared, p_val, contributions


class AutoencoderDetector:
    """Unsupervised low-rank projection bottleneck autoencoder for structural manifold anomaly detection."""

    def __init__(self, n_components: int = 3) -> None:
        self.n_components = n_components
        self.pca: PCA | None = None
        self.mean_vector: np.ndarray | None = None
        self.threshold_mse: float = 25.0
        self.is_fitted: bool = False

    def fit(self, X: np.ndarray) -> None:
        """Fits PCA projection bottleneck and establishes baseline reconstruction error threshold."""
        n_samples, n_features = X.shape
        if n_samples < 3:
            return

        k = min(self.n_components, n_features, n_samples - 1)
        self.mean_vector = np.mean(X, axis=0)
        self.pca = PCA(n_components=k, random_state=42)
        try:
            self.pca.fit(X)
            # Reconstruct training samples to calculate 95th percentile baseline MSE
            projected = self.pca.transform(X)
            reconstructed = self.pca.inverse_transform(projected)
            sample_mses = np.mean((X - reconstructed) ** 2, axis=1)
            p95 = float(np.percentile(sample_mses, 95))
            self.threshold_mse = max(10.0, p95)
            self.is_fitted = True
        except Exception as err:
            logger.warning(f"Autoencoder PCA fitting failed: {err}")
            self.threshold_mse = 25.0
            self.is_fitted = False

    def evaluate(self, x: np.ndarray) -> tuple[float, np.ndarray]:
        """Projects vector through bottleneck, computes reconstruction MSE and per-feature squared errors."""
        if not self.is_fitted or self.pca is None:
            # Fallback simple baseline
            return 0.0, np.zeros_like(x)

        x_2d = x.reshape(1, -1)
        projected = self.pca.transform(x_2d)
        reconstructed = self.pca.inverse_transform(projected)[0]

        sq_errors = (x - reconstructed) ** 2
        mse = float(np.mean(sq_errors))
        return mse, sq_errors


class ScoreAnomalyService:
    """Orchestrates multi-model score anomaly detection, consensus evaluation, and root-cause analysis."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        contamination: float = 0.08,
    ) -> None:
        self.db_path = Path(db_path) if db_path else Path("warden.db")
        self.contamination = contamination
        self.mahalanobis = MahalanobisDetector()
        self.autoencoder = AutoencoderDetector()
        self.isolation_forest = AnomalyDetector(db_path=self.db_path, contamination=contamination)
        self.feature_means: dict[str, float] = {}
        self.feature_stds: dict[str, float] = {}
        self._is_trained = False

    def _extract_vector_from_dict(self, sc: dict[str, Any]) -> np.ndarray:
        """Extracts ordered 8-element numpy float vector from a scorecard dict."""
        card = sc.get("scorecard", sc)
        # Check if groups are nested
        groups = card.get("groups", card.get("group_scores", {}))

        vec: list[float] = []
        for name in FEATURE_NAMES:
            val = card.get(name)
            if val is None or val == -1:
                # Check nested groups without "group_" prefix
                short_name = name.replace("group_", "")
                val = groups.get(short_name, groups.get(name, None))

            if val is None or val == -1:
                vec.append(70.0)
            else:
                try:
                    vec.append(float(val))
                except (ValueError, TypeError):
                    vec.append(70.0)
        return np.array(vec, dtype=np.float64)

    def _load_history_from_db(self) -> np.ndarray:
        """Loads historical audit score vectors from SQLite."""
        if not self.db_path.is_file():
            return np.empty((0, len(FEATURE_NAMES)))

        rows: list[list[float]] = []
        try:
            con = sqlite3.connect(str(self.db_path))
            cur = con.cursor()
            cols = ", ".join(FEATURE_NAMES)
            query = f"SELECT {cols} FROM auditreport WHERE total_score IS NOT NULL ORDER BY id DESC LIMIT 500"
            for row in cur.execute(query).fetchall():
                cleaned = []
                for val in row:
                    if val is None or val == -1:
                        cleaned.append(70.0)
                    else:
                        cleaned.append(float(val))
                if len(cleaned) == len(FEATURE_NAMES):
                    rows.append(cleaned)
            con.close()
        except Exception as err:
            logger.debug(f"Could not load historical audits for ScoreAnomalyService: {err}")

        return np.array(rows, dtype=np.float64) if rows else np.empty((0, len(FEATURE_NAMES)))

    def _generate_synthetic_baseline(self) -> np.ndarray:
        """Synthesizes calibrated multidimensional baseline distribution when history is sparse."""
        base_means = [82.0, 80.0, 84.0, 85.0, 80.0, 78.0, 82.0, 75.0]
        stds = [6.0, 7.0, 6.0, 8.0, 7.0, 6.0, 8.0, 8.0]
        rows = []
        for i in range(60):
            row = []
            for dim_idx, (m, s) in enumerate(zip(base_means, stds)):
                shift = ((( (i + dim_idx * 7) % 9) - 4) * (s / 3.5)) + ((( (i * 3 + dim_idx * 5) % 5) - 2) * 1.0)
                row.append(max(0.0, min(100.0, m + shift)))
            rows.append(row)
        return np.array(rows, dtype=np.float64)

    def fit(self, training_data: np.ndarray | list[list[float]] | None = None) -> None:
        """Fits Mahalanobis, Autoencoder, and Isolation Forest models."""
        if training_data is None:
            data = self._load_history_from_db()
            if len(data) < 10:
                data = self._generate_synthetic_baseline()
        elif isinstance(training_data, list):
            data = np.array(training_data, dtype=np.float64)
        else:
            data = training_data

        if len(data) == 0:
            return

        # Store univariate means & stds
        for idx, feat in enumerate(FEATURE_NAMES):
            col = data[:, idx]
            self.feature_means[feat] = float(np.mean(col))
            self.feature_stds[feat] = max(1.0, float(np.std(col)))

        # Fit sub-detectors
        self.mahalanobis.fit(data)
        self.autoencoder.fit(data)
        self.isolation_forest.fit(data.tolist())
        self._is_trained = True

    def evaluate_scorecard(
        self,
        scorecard: dict[str, Any],
        method: str = "hybrid",
    ) -> AdvancedAnomalyReport:
        """Evaluates a single scorecard against learned distributions and identifies root causes."""
        if not self._is_trained:
            self.fit()

        x = self._extract_vector_from_dict(scorecard)
        raw_vec_dict = {FEATURE_NAMES[i]: round(float(x[i]), 1) for i in range(len(FEATURE_NAMES))}

        # 1. Mahalanobis Evaluation
        d_squared, p_val, mah_contribs = self.mahalanobis.evaluate(x)
        # Convert p-value to 0-100 anomaly intensity
        if p_val <= 0.001:
            mah_score = 98.0
        elif p_val <= 0.01:
            mah_score = 85.0 + (0.01 - p_val) * 1300.0
        elif p_val <= 0.05:
            mah_score = 65.0 + (0.05 - p_val) * 500.0
        else:
            # Normal distribution: scale gracefully from 0 to 60
            mah_score = max(0.0, min(60.0, (1.0 - p_val) * 60.0))

        # 2. Autoencoder Reconstruction Evaluation
        mse, ae_sq_errors = self.autoencoder.evaluate(x)
        tau = self.autoencoder.threshold_mse
        if mse <= tau:
            ae_score = min(50.0, (mse / max(1.0, tau)) * 50.0)
        else:
            ratio = mse / max(1.0, tau)
            ae_score = min(100.0, 50.0 + (ratio - 1.0) * 35.0)

        # 3. Isolation Forest Evaluation
        if_report = self.isolation_forest.detect_anomalies(scorecard)
        if_score = if_report.anomaly_score

        # 4. Consensus Score Calculation
        method_lower = method.lower()
        if method_lower == "mahalanobis":
            consensus_score = mah_score
        elif method_lower == "autoencoder":
            consensus_score = ae_score
        elif method_lower == "isolation_forest":
            consensus_score = if_score
        else:
            # Tri-Model Hybrid Consensus (40% Mahalanobis + 35% Autoencoder + 25% Isolation Forest)
            consensus_score = (0.40 * mah_score) + (0.35 * ae_score) + (0.25 * if_score)

        # Trigger logic
        if method_lower == "mahalanobis":
            is_anomaly = bool(p_val <= 0.01)
        elif method_lower == "autoencoder":
            is_anomaly = bool(mse >= (2.0 * tau))
        elif method_lower == "isolation_forest":
            is_anomaly = bool(if_report.is_anomaly)
        else:
            is_anomaly = bool(
                consensus_score >= 65.0
                or (p_val <= 0.01 and mse >= (1.5 * tau))
            )

        # Severity
        if consensus_score >= 85.0 or p_val <= 0.001:
            severity = "CRITICAL"
        elif consensus_score >= 70.0 or p_val <= 0.01:
            severity = "HIGH"
        elif consensus_score >= 60.0 or is_anomaly:
            severity = "MEDIUM"
        else:
            severity = "NORMAL"

        # 5. Root Cause Attribution (Top Contributors)
        # Combine Mahalanobis positive projection and Autoencoder squared errors
        mah_pos = np.maximum(0.0, mah_contribs)
        sum_mah = float(np.sum(mah_pos))
        sum_ae = float(np.sum(ae_sq_errors))

        normalized_mah = (mah_pos / sum_mah) if sum_mah > 1e-6 else np.ones(len(x)) / len(x)
        normalized_ae = (ae_sq_errors / sum_ae) if sum_ae > 1e-6 else np.ones(len(x)) / len(x)

        combined_weights = (0.50 * normalized_mah) + (0.50 * normalized_ae)

        # Build list of candidate contributions
        contrib_list: list[AnomalyContribution] = []
        for idx, feat in enumerate(FEATURE_NAMES):
            weight = float(combined_weights[idx])
            val = float(x[idx])
            mean_val = self.feature_means.get(feat, 75.0)
            dev = val - mean_val
            direction = "DROP" if dev < 0 else "SURGE"
            rec = ACTION_RECOMMENDATIONS.get(feat, "Metrik sapmasını inceleyin.")

            contrib_list.append(
                AnomalyContribution(
                    dimension=feat,
                    contribution_pct=round(weight * 100.0, 1),
                    actual_value=round(val, 1),
                    expected_mean=round(mean_val, 1),
                    deviation=round(dev, 1),
                    direction=direction,
                    action_recommendation=rec,
                )
            )

        # Sort by contribution descending and take top 3
        contrib_list.sort(key=lambda c: c.contribution_pct, reverse=True)
        top_3 = contrib_list[:3]

        remediation_actions = [c.action_recommendation for c in top_3 if c.direction == "DROP" or abs(c.deviation) > 10.0]
        if not remediation_actions:
            remediation_actions = [top_3[0].action_recommendation] if top_3 else []

        # 6. Verdict Summary
        if is_anomaly:
            top_dim_names = ", ".join(f"{c.dimension} (%{c.contribution_pct:.1f})" for c in top_3[:2])
            verdict_summary = (
                f"🚨 Anomali Tespit Edildi ({severity} - Konsensüs: %{consensus_score:.1f}). "
                f"Kovaryans mesafesi D_M^2={d_squared:.1f} (p={p_val:.4f}), Rekonstrüksiyon MSE={mse:.1f}. "
                f"En çok sapan boyutlar: {top_dim_names}."
            )
        else:
            verdict_summary = (
                f"✓ Normal Skor Dağılımı (Konsensüs: %{consensus_score:.1f}, p={p_val:.3f}, MSE={mse:.1f}). "
                f"Metrikler tarihsel korelasyon ve rekonstrüksiyon sınırları dahilinde."
            )

        return AdvancedAnomalyReport(
            is_anomaly=is_anomaly,
            consensus_score=round(consensus_score, 1),
            severity=severity,
            method=method,
            mahalanobis_distance=round(d_squared, 2),
            p_value=round(p_val, 4),
            reconstruction_mse=round(mse, 2),
            isolation_forest_score=round(if_score, 1),
            top_contributors=top_3,
            remediation_actions=remediation_actions,
            verdict_summary=verdict_summary,
            raw_vector=raw_vec_dict,
        )

    def evaluate_audit_id(self, audit_id: int, method: str = "hybrid") -> AdvancedAnomalyReport:
        """Fetches an audit report by ID from database and evaluates it for anomalies."""
        from sqlmodel import Session, select

        from core.infra.database import engine
        from core.models.audit import AuditReport

        with Session(engine) as session:
            report = session.exec(select(AuditReport).where(AuditReport.id == audit_id)).first()
            if not report:
                raise ValueError(f"Audit #{audit_id} veritabanında bulunamadı.")

            scorecard = {
                "total_score": report.total_score,
                "layer1_score": report.layer1_score,
                "layer2_score": report.layer2_score,
                "group_security": report.group_security,
                "group_code_health": report.group_code_health,
                "group_structural": report.group_structural,
                "group_resilience": report.group_resilience,
                "group_dev_hygiene": report.group_dev_hygiene,
            }

        return self.evaluate_scorecard(scorecard, method=method)

    def evaluate_latest(self, repo_path: str = ".", method: str = "hybrid") -> AdvancedAnomalyReport:
        """Evaluates the most recent audit report for a given repository path."""
        from sqlmodel import Session, select

        from core.infra.database import engine
        from core.models.audit import AuditReport

        resolved_path = str(Path(repo_path).resolve())
        short_path = str(Path(repo_path))

        with Session(engine) as session:
            stmt = (
                select(AuditReport)
                .where(
                    (AuditReport.repo_path == resolved_path)
                    | (AuditReport.repo_path == short_path)
                    | (AuditReport.repo_path == ".")
                )
                .order_by(AuditReport.id.desc())  # type: ignore[union-attr]
            )
            report = session.exec(stmt).first()

            if not report:
                # If no report found for path, try getting the absolute latest report
                report = session.exec(select(AuditReport).order_by(AuditReport.id.desc())).first()  # type: ignore[union-attr]

            if not report:
                raise ValueError("Analiz edilecek herhangi bir denetim raporu bulunamadı.")

            scorecard = {
                "total_score": report.total_score,
                "layer1_score": report.layer1_score,
                "layer2_score": report.layer2_score,
                "group_security": report.group_security,
                "group_code_health": report.group_code_health,
                "group_structural": report.group_structural,
                "group_resilience": report.group_resilience,
                "group_dev_hygiene": report.group_dev_hygiene,
            }

        return self.evaluate_scorecard(scorecard, method=method)
