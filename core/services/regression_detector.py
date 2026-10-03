"""Regression detector — compares consecutive audits and flags significant score drops."""

import logging
from dataclasses import dataclass, field
from typing import Any

from core.services.anomaly_detector import AnomalyDetector, AnomalyReport

logger = logging.getLogger(__name__)

# Puanın kaç puan düşmesi "regresyon" sayılır
REGRESSION_THRESHOLD = 5
GROUP_REGRESSION_THRESHOLD = 8  # Grup bazında eşik biraz daha yüksek


@dataclass
class RegressionWarning:
    """Represents a detected score regression between two audit reports."""

    dimension: str        # "total", "security", "code_health", …
    previous_score: float
    current_score: float
    delta: float          # always negative for regressions
    severity: str         # "CRITICAL" | "HIGH" | "MEDIUM"
    message: str


@dataclass
class RegressionReport:
    """Full regression analysis result comparing two audits."""

    has_regression: bool
    warnings: list[RegressionWarning] = field(default_factory=list)
    improvements: list[dict[str, Any]] = field(default_factory=list)
    total_delta: float = 0.0
    summary: str = ""
    anomaly_report: AnomalyReport | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_regression": self.has_regression,
            "total_delta": self.total_delta,
            "summary": self.summary,
            "warnings_count": len(self.warnings),
            "warnings": [
                {
                    "dimension": w.dimension,
                    "previous_score": w.previous_score,
                    "current_score": w.current_score,
                    "delta": w.delta,
                    "severity": w.severity,
                    "message": w.message,
                }
                for w in self.warnings
            ],
            "improvements": self.improvements,
            "anomaly": self.anomaly_report.to_dict() if self.anomaly_report else None,
        }


class RegressionDetector:
    """Detects score regressions between consecutive or baseline audit reports.

    Usage:
        detector = RegressionDetector()
        report = detector.detect(current_audit_dict, previous_audit_dict)
        if report.has_regression:
            for w in report.warnings:
                print(w.message)
    """

    def __init__(self, anomaly_detector: AnomalyDetector | None = None) -> None:
        self.anomaly_detector = anomaly_detector or AnomalyDetector()

    def detect_anomalies(self, current: dict[str, Any]) -> AnomalyReport:
        """Evaluates an individual scorecard for statistical/ML anomalies using Isolation Forest."""
        sc_curr = current.get("scorecard", current)
        return self.anomaly_detector.detect_anomalies(sc_curr)

    def _check_total_delta(
        self, curr_total: float, prev_total: float
    ) -> tuple[RegressionWarning | None, dict[str, Any] | None]:
        """Evaluates score variance across overall total scores."""
        total_delta = curr_total - prev_total
        if total_delta <= -REGRESSION_THRESHOLD:
            severity = "CRITICAL" if total_delta <= -15 else "HIGH" if total_delta <= -8 else "MEDIUM"
            warning = RegressionWarning(
                dimension="total",
                previous_score=prev_total,
                current_score=curr_total,
                delta=total_delta,
                severity=severity,
                message=f"Toplam skor {abs(total_delta)} puan düştü: {prev_total} → {curr_total}",
            )
            return warning, None
        if total_delta >= REGRESSION_THRESHOLD:
            improvement = {
                "dimension": "total",
                "delta": total_delta,
                "message": f"Toplam skor {total_delta} puan arttı: {prev_total} → {curr_total}",
            }
            return None, improvement
        return None, None

    def _check_layer_deltas(
        self, sc_curr: dict[str, Any], sc_prev: dict[str, Any]
    ) -> list[RegressionWarning]:
        """Detects regressions within Layer 1 and Layer 2 aggregate dimensions."""
        warnings: list[RegressionWarning] = []
        layers = [("layer1_score", "Katman 1"), ("layer2_score", "Katman 2 (LLM)")]
        for layer_key, label in layers:
            cv = sc_curr.get(layer_key)
            pv = sc_prev.get(layer_key)
            if cv is not None and pv is not None and pv != -1 and cv != -1:
                delta = cv - pv
                if delta <= -REGRESSION_THRESHOLD:
                    severity = "HIGH" if delta <= -10 else "MEDIUM"
                    warnings.append(
                        RegressionWarning(
                            dimension=layer_key,
                            previous_score=pv,
                            current_score=cv,
                            delta=delta,
                            severity=severity,
                            message=f"{label} skoru {abs(delta)} puan düştü: {pv} → {cv}",
                        )
                    )
        return warnings

    def _check_group_deltas(
        self, sc_curr: dict[str, Any], sc_prev: dict[str, Any]
    ) -> tuple[list[RegressionWarning], list[dict[str, Any]]]:
        """Detects regressions and improvements across 5 architectural score categories."""
        warnings: list[RegressionWarning] = []
        improvements: list[dict[str, Any]] = []
        group_labels = {
            "group_security": "🛡 Güvenlik",
            "group_code_health": "🧪 Kod Sağlığı",
            "group_structural": "🏗 Yapısal",
            "group_resilience": "⚙ Dayanıklılık",
            "group_dev_hygiene": "🔧 DevOps/Hijyen",
        }
        for gkey, glabel in group_labels.items():
            cv = sc_curr.get(gkey)
            pv = sc_prev.get(gkey)
            if cv is None or pv is None:
                continue
            delta = round(cv - pv, 2)
            if delta <= -GROUP_REGRESSION_THRESHOLD:
                severity = "HIGH" if delta <= -15 else "MEDIUM"
                warnings.append(
                    RegressionWarning(
                        dimension=gkey,
                        previous_score=pv,
                        current_score=cv,
                        delta=delta,
                        severity=severity,
                        message=f"{glabel} grubu {abs(delta):.1f} puan düştü: {pv:.1f} → {cv:.1f}",
                    )
                )
            elif delta >= GROUP_REGRESSION_THRESHOLD:
                improvements.append({
                    "dimension": gkey,
                    "delta": delta,
                    "message": f"{glabel} grubu {delta:.1f} puan arttı",
                })
        return warnings, improvements

    def _check_anomaly_warnings(
        self, anomaly_report: AnomalyReport | None
    ) -> list[RegressionWarning]:
        """Extracts statistical/ML regression warnings from anomaly report."""
        warnings: list[RegressionWarning] = []
        if anomaly_report and anomaly_report.is_anomaly:
            for ad in anomaly_report.anomalous_dimensions:
                warnings.append(
                    RegressionWarning(
                        dimension=f"anomaly_{ad.dimension}",
                        previous_score=ad.expected_mean,
                        current_score=ad.value,
                        delta=round(ad.value - ad.expected_mean, 2),
                        severity=ad.severity,
                        message=f"[ANOMALİ] {ad.message}",
                    )
                )
        return warnings

    def _build_summary(
        self,
        has_regression: bool,
        warnings: list[RegressionWarning],
        improvements: list[dict[str, Any]],
        curr_total: float,
        prev_total: float,
        total_delta: float,
    ) -> str:
        """Constructs human-readable regression and delta summary."""
        if not has_regression and not improvements:
            return f"Skor sabit: {curr_total}/100 (önceki: {prev_total}/100)"
        if has_regression:
            critical = [w for w in warnings if w.severity == "CRITICAL"]
            return (
                f"⚠️ {len(warnings)} regresyon/anomali tespit edildi. "
                f"{'🚨 KRİTİK düşüş/anomali var! ' if critical else ''}"
                f"Toplam: {prev_total} → {curr_total} ({int(total_delta):+d})"
            )
        return (
            f"✅ {len(improvements)} iyileştirme. "
            f"Toplam: {prev_total} → {curr_total} ({int(total_delta):+d})"
        )

    def detect(
        self,
        current: dict[str, Any],
        previous: dict[str, Any],
        check_anomalies: bool = False,
    ) -> RegressionReport:
        """Compares two audit result dicts and returns a RegressionReport.

        Args:
            current: scorecard dict from the new audit (from run_full_audit)
            previous: scorecard dict from the reference/previous audit
            check_anomalies: whether to trigger ML anomaly detection
        """
        sc_curr = current.get("scorecard", current)
        sc_prev = previous.get("scorecard", previous)

        curr_total = sc_curr.get("total_score", 0)
        prev_total = sc_prev.get("total_score", 0)
        total_delta = curr_total - prev_total

        total_warn, total_imp = self._check_total_delta(curr_total, prev_total)
        warnings: list[RegressionWarning] = [total_warn] if total_warn else []
        improvements: list[dict[str, Any]] = [total_imp] if total_imp else []

        warnings.extend(self._check_layer_deltas(sc_curr, sc_prev))

        grp_warns, grp_imps = self._check_group_deltas(sc_curr, sc_prev)
        warnings.extend(grp_warns)
        improvements.extend(grp_imps)

        anomaly_report = self.anomaly_detector.detect_anomalies(sc_curr) if check_anomalies else None
        warnings.extend(self._check_anomaly_warnings(anomaly_report))

        has_regression = bool(warnings)
        summary = self._build_summary(has_regression, warnings, improvements, curr_total, prev_total, total_delta)

        if has_regression:
            logger.warning(f"Regresyon/anomali tespit edildi: {summary}")

        return RegressionReport(
            has_regression=has_regression,
            warnings=warnings,
            improvements=improvements,
            total_delta=total_delta,
            summary=summary,
            anomaly_report=anomaly_report,
        )
