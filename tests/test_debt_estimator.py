"""Unit tests for TechDebtEstimator (SQALE empirical effort estimation)."""

from __future__ import annotations

from core.services.debt_estimator import (
    TechDebtEstimator,
    TechDebtRemediationEstimate,
)
from core.services.tech_debt import FileChurnEntry, TodoMarker


class TestTechDebtEstimator:
    """Tests for TechDebtEstimator."""

    def setup_method(self):
        self.estimator = TechDebtEstimator()

    def test_estimate_empty_inputs(self):
        """Test with empty markers, churn, and complexity."""
        est = self.estimator.estimate()
        assert isinstance(est, TechDebtRemediationEstimate)
        assert est.total_hours == 0.0
        assert est.total_days == 0.0
        assert len(est.priority_items) == 0

    def test_estimate_marker_efforts(self):
        """Test effort calculation for TODO, FIXME, and HACK markers."""
        markers = [
            TodoMarker(file="app.py", line=10, marker="TODO", text="Refactor database call"),
            TodoMarker(file="auth.py", line=42, marker="FIXME", text="Security token expiration"),
            TodoMarker(file="utils.py", line=105, marker="HACK", text="Temporary workaround"),
        ]
        # Breakdown: fixme=1.0, hack=1.5, todo=0.5 -> Total 3.0 hours
        est = self.estimator.estimate(todo_markers=markers)
        assert est.markers_hours == 3.0
        assert est.total_hours == 3.0
        assert est.breakdown["markers"] == 3.0
        # Priority items should contain FIXME and HACK
        assert len(est.priority_items) == 2
        categories = {item.category for item in est.priority_items}
        assert "marker" in categories

    def test_estimate_complexity_efforts(self):
        """Test effort calculation for cyclomatic complexity outliers."""
        outliers = [
            {"file": "parser.py", "name": "parse_payload", "line": 20, "complexity": 15},  # 0.5 + 0.15*5 = 1.25 hrs
            {"file": "engine.py", "name": "execute_query", "line": 50, "complexity": 20},   # 0.5 + 0.15*10 = 2.0 hrs
            {"file": "simple.py", "name": "helper", "line": 5, "complexity": 8},            # CC <= 10 -> 0 hrs
        ]
        est = self.estimator.estimate(outlier_blocks=outliers)
        assert round(est.complexity_hours, 2) == 3.25
        assert est.total_hours == 3.25
        assert len(est.priority_items) == 2
        assert est.priority_items[0].category == "complexity"

    def test_estimate_churn_hotspots(self):
        """Test effort calculation for high-churn hotspot files."""
        churn = [
            # High churn hotspot (15 commits, 45 days old)
            FileChurnEntry(file="hotspot.py", commit_count=15, lines_changed=400, age_days=45),
            # Young or low-churn file (skipped)
            FileChurnEntry(file="clean.py", commit_count=2, lines_changed=10, age_days=5),
        ]
        est = self.estimator.estimate(churn_entries=churn)
        # min(4.0, 1.0 + 0.1*15) = 2.5 hrs
        assert round(est.churn_hotspot_hours, 1) == 2.5
        assert est.total_hours == 2.5
        assert len(est.priority_items) == 1
        assert est.priority_items[0].category == "hotspot"

    def test_estimate_comprehensive_combined(self):
        """Test comprehensive combination of all technical debt dimensions."""
        markers = [TodoMarker(file="a.py", line=1, marker="FIXME", text="bug")] # 1.0 hr
        outliers = [{"file": "b.py", "name": "f", "line": 10, "complexity": 12}] # 0.5 + 0.3 = 0.8 hr
        churn = [FileChurnEntry(file="c.py", commit_count=10, lines_changed=100, age_days=30)] # 1.0 + 1.0 = 2.0 hrs

        est = self.estimator.estimate(
            todo_markers=markers,
            churn_entries=churn,
            outlier_blocks=outliers,
        )
        assert round(est.total_hours, 1) == 3.8
        assert round(est.total_days, 1) == 0.5
        d = est.to_dict()
        assert d["total_hours"] == 3.8
        assert "complexity" in d["breakdown"]
        assert len(d["priority_items"]) == 3
