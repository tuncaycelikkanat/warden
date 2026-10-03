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
        """
        sc_curr = current.get("scorecard", current)
        sc_prev = previous.get("scorecard", previous)

        warnings: list[RegressionWarning] = []
        improvements: list[dict[str, Any]] = []

        # ── Total score ────────────────────────────────────────────────────────
        curr_total = sc_curr.get("total_score", 0)
        prev_total = sc_prev.get("total_score", 0)
        total_delta = curr_total - prev_total

        if total_delta <= -REGRESSION_THRESHOLD:
            severity = "CRITICAL" if total_delta <= -15 else "HIGH" if total_delta <= -8 else "MEDIUM"
            warnings.append(RegressionWarning(
                dimension="total",
                previous_score=prev_total,
                current_score=curr_total,
                delta=total_delta,
                severity=severity,
                message=f"Toplam skor {abs(total_delta)} puan düştü: {prev_total} → {curr_total}",
            ))
        elif total_delta >= REGRESSION_THRESHOLD:
            improvements.append({
                "dimension": "total",
                "delta": total_delta,
                "message": f"Toplam skor {total_delta} puan arttı: {prev_total} → {curr_total}",
            })

        # ── Layer 1 / Layer 2 ─────────────────────────────────────────────────
        for layer_key, label in [("layer1_score", "Katman 1"), ("layer2_score", "Katman 2 (LLM)")]:
            cv = sc_curr.get(layer_key)
            pv = sc_prev.get(layer_key)
            if cv is not None and pv is not None and pv != -1 and cv != -1:
                delta = cv - pv
                if delta <= -REGRESSION_THRESHOLD:
                    severity = "HIGH" if delta <= -10 else "MEDIUM"
                    warnings.append(RegressionWarning(
                        dimension=layer_key,
                        previous_score=pv,
                        current_score=cv,
                        delta=delta,
                        severity=severity,
                        message=f"{label} skoru {abs(delta)} puan düştü: {pv} → {cv}",
                    ))

        # ── Group scores ──────────────────────────────────────────────────────
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
            if cv is not None and pv is not None:
                delta = round(cv - pv, 2)
                if delta <= -GROUP_REGRESSION_THRESHOLD:
                    severity = "HIGH" if delta <= -15 else "MEDIUM"
                    warnings.append(RegressionWarning(
                        dimension=gkey,
                        previous_score=pv,
                        current_score=cv,
                        delta=delta,
                        severity=severity,
                        message=f"{glabel} grubu {abs(delta):.1f} puan düştü: {pv:.1f} → {cv:.1f}",
                    ))
                elif delta >= GROUP_REGRESSION_THRESHOLD:
                    improvements.append({
                        "dimension": gkey,
                        "delta": delta,
                        "message": f"{glabel} grubu {delta:.1f} puan arttı",
                    })

        # ── Anomaly Check (C2: Isolation Forest) ──────────────────────────────
        anomaly_report = None
        if check_anomalies:
            anomaly_report = self.anomaly_detector.detect_anomalies(sc_curr)
            if anomaly_report.is_anomaly:
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

        has_regression = bool(warnings)

        # ── Summary ───────────────────────────────────────────────────────────
        if not has_regression and not improvements:
            summary = f"Skor sabit: {curr_total}/100 (önceki: {prev_total}/100)"
        elif has_regression:
            critical = [w for w in warnings if w.severity == "CRITICAL"]
            summary = (
                f"⚠️ {len(warnings)} regresyon/anomali tespit edildi. "
                f"{'🚨 KRİTİK düşüş/anomali var! ' if critical else ''}"
                f"Toplam: {prev_total} → {curr_total} ({int(total_delta):+d})"
            )
        else:
            summary = (
                f"✅ {len(improvements)} iyileştirme. "
                f"Toplam: {prev_total} → {curr_total} ({int(total_delta):+d})"
            )

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
