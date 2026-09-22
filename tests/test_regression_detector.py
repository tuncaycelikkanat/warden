"""Tests for regression detection between consecutive audit reports."""

import pytest

from core.services.regression_detector import RegressionDetector, REGRESSION_THRESHOLD


@pytest.fixture
def detector() -> RegressionDetector:
    return RegressionDetector()


def _make_scorecard(
    total: int = 75,
    grade: str = "B",
    l1: int = 70,
    l2: int = 80,
    security: float = 80.0,
    code_health: float = 75.0,
    structural: float = 70.0,
    resilience: float = 85.0,
    dev_hygiene: float = 65.0,
) -> dict:
    return {
        "scorecard": {
            "total_score": total,
            "grade": grade,
            "layer1_score": l1,
            "layer2_score": l2,
            "group_security": security,
            "group_code_health": code_health,
            "group_structural": structural,
            "group_resilience": resilience,
            "group_dev_hygiene": dev_hygiene,
        }
    }


class TestNoRegression:
    def test_identical_audits(self, detector: RegressionDetector) -> None:
        audit = _make_scorecard(total=80)
        result = detector.detect(audit, audit)
        assert not result.has_regression
        assert result.total_delta == 0

    def test_minor_drop_below_threshold(self, detector: RegressionDetector) -> None:
        """A drop smaller than REGRESSION_THRESHOLD should not trigger."""
        curr = _make_scorecard(total=78)
        prev = _make_scorecard(total=80)
        result = detector.detect(curr, prev)
        assert not result.has_regression

    def test_improvement_detected(self, detector: RegressionDetector) -> None:
        curr = _make_scorecard(total=90)
        prev = _make_scorecard(total=78)
        result = detector.detect(curr, prev)
        assert not result.has_regression
        assert result.total_delta == 12
        assert len(result.improvements) >= 1


class TestTotalScoreRegression:
    def test_medium_regression_detected(self, detector: RegressionDetector) -> None:
        curr = _make_scorecard(total=70)
        prev = _make_scorecard(total=78)
        result = detector.detect(curr, prev)
        assert result.has_regression
        assert result.total_delta == -8
        regressions = [w for w in result.warnings if w.dimension == "total"]
        assert regressions
        assert regressions[0].severity in ("MEDIUM", "HIGH")

    def test_critical_regression_detected(self, detector: RegressionDetector) -> None:
        curr = _make_scorecard(total=50)
        prev = _make_scorecard(total=80)
        result = detector.detect(curr, prev)
        assert result.has_regression
        total_reg = next(w for w in result.warnings if w.dimension == "total")
        assert total_reg.severity == "CRITICAL"
        assert total_reg.delta == -30


class TestGroupRegression:
    def test_security_group_regression(self, detector: RegressionDetector) -> None:
        curr = _make_scorecard(security=60.0)
        prev = _make_scorecard(security=90.0)
        result = detector.detect(curr, prev)
        assert result.has_regression
        sec_warnings = [w for w in result.warnings if w.dimension == "group_security"]
        assert sec_warnings
        assert sec_warnings[0].delta == pytest.approx(-30.0)

    def test_all_groups_stable(self, detector: RegressionDetector) -> None:
        same = _make_scorecard()
        result = detector.detect(same, same)
        group_warnings = [w for w in result.warnings if w.dimension.startswith("group_")]
        assert not group_warnings


class TestSummary:
    def test_summary_contains_scores(self, detector: RegressionDetector) -> None:
        curr = _make_scorecard(total=65)
        prev = _make_scorecard(total=80)
        result = detector.detect(curr, prev)
        assert "80" in result.summary
        assert "65" in result.summary

    def test_no_regression_summary(self, detector: RegressionDetector) -> None:
        same = _make_scorecard(total=75)
        result = detector.detect(same, same)
        assert "sabit" in result.summary.lower() or "75" in result.summary
