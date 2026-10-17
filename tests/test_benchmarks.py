"""Unit tests for the benchmarking dataset, metrics calculation, and evaluation runner."""

from __future__ import annotations

from pathlib import Path

from benchmarks.dataset import load_benchmark_dataset
from benchmarks.runner import BenchmarkReport, BenchmarkRunner, MetricSummary


def test_metric_summary_calculations():
    # Test perfect classification
    m = MetricSummary(category="test", total_samples=10, tp=5, fp=0, tn=5, fn=0)
    assert m.precision == 1.0
    assert m.recall == 1.0
    assert m.f1_score == 1.0
    assert m.accuracy == 1.0

    # Test imperfect classification
    # TP=4, FP=1, FN=2, TN=3 -> Total=10
    # Precision = 4 / (4+1) = 0.8
    # Recall = 4 / (4+2) = 0.6667
    m2 = MetricSummary(category="test2", total_samples=10, tp=4, fp=1, tn=3, fn=2)
    assert round(m2.precision, 4) == 0.8
    assert round(m2.recall, 4) == 0.6667
    expected_f1 = 2 * (0.8 * (4 / 6)) / (0.8 + (4 / 6))
    assert round(m2.f1_score, 4) == round(expected_f1, 4)
    assert m2.accuracy == 0.7


def test_benchmark_dataset_integrity():
    samples = load_benchmark_dataset()
    assert len(samples) >= 30

    categories = {s.category for s in samples}
    expected_categories = {
        "missing_timeout",
        "bare_except",
        "silent_swallow",
        "secret_entropy",
        "ai_slop",
    }
    assert expected_categories.issubset(categories)

    # Ensure every category has both positive and negative samples
    for cat in expected_categories:
        cat_samples = [s for s in samples if s.category == cat]
        pos = [s for s in cat_samples if s.is_positive]
        neg = [s for s in cat_samples if not s.is_positive]
        assert len(pos) >= 2, f"Category {cat} needs at least 2 positive samples"
        assert len(neg) >= 2, f"Category {cat} needs at least 2 negative samples"


def test_benchmark_runner_execution(tmp_path: Path):
    runner = BenchmarkRunner()
    report = runner.run_suite()

    assert isinstance(report, BenchmarkReport)
    assert report.macro_f1 >= 0.90
    assert report.overall_accuracy >= 0.90
    assert len(report.failures) == 0

    table = report.format_table()
    assert "| Detector / Category |" in table
    assert "ai_slop" in table
    assert "missing_timeout" in table

    # Test JSON serialization
    data = report.to_dict()
    assert "overall_accuracy" in data
    assert "macro_f1" in data
    assert "categories" in data
