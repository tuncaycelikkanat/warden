"""Benchmark execution harness evaluating detector Precision, Recall, and F1-score."""

from __future__ import annotations

import ast
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from benchmarks.dataset import BenchmarkSample, load_benchmark_dataset
from core.services.ai_slop_classifier import AISlopClassifier
from core.services.entropy_analyzer import EntropyAnalyzerService
from core.services.resilience import ResilienceAnalyzerService

logger = logging.getLogger(__name__)


@dataclass
class MetricSummary:
    """Confusion matrix and statistical metrics for a single detector category."""

    category: str
    total_samples: int = 0
    tp: int = 0  # True Positives
    fp: int = 0  # False Positives
    tn: int = 0  # True Negatives
    fn: int = 0  # False Negatives

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return (self.tp / denom) if denom > 0 else 1.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return (self.tp / denom) if denom > 0 else 1.0

    @property
    def f1_score(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r / (p + r)) if (p + r) > 0 else 0.0

    @property
    def accuracy(self) -> float:
        denom = self.total_samples
        return ((self.tp + self.tn) / denom) if denom > 0 else 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "total_samples": self.total_samples,
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "accuracy": round(self.accuracy, 4),
        }


@dataclass
class BenchmarkReport:
    """Aggregated benchmark evaluation report."""

    category_metrics: dict[str, MetricSummary] = field(default_factory=dict)
    failures: list[dict[str, Any]] = field(default_factory=list)

    @property
    def overall_accuracy(self) -> float:
        total = sum(m.total_samples for m in self.category_metrics.values())
        correct = sum(m.tp + m.tn for m in self.category_metrics.values())
        return (correct / total) if total > 0 else 1.0

    @property
    def macro_f1(self) -> float:
        if not self.category_metrics:
            return 1.0
        return sum(m.f1_score for m in self.category_metrics.values()) / len(self.category_metrics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_accuracy": round(self.overall_accuracy, 4),
            "macro_f1": round(self.macro_f1, 4),
            "categories": {k: m.to_dict() for k, m in self.category_metrics.items()},
            "failure_count": len(self.failures),
            "failures": self.failures,
        }

    def format_table(self) -> str:
        """Formats the evaluation results as a clean Markdown table."""
        lines = [
            "| Detector / Category | Samples | TP | FP | TN | FN | Precision | Recall | F1-Score | Accuracy |",
            "|:--------------------|:-------:|:--:|:--:|:--:|:--:|:---------:|:------:|:--------:|:--------:|",
        ]
        for cat, m in sorted(self.category_metrics.items()):
            lines.append(
                f"| `{cat}` | {m.total_samples} | {m.tp} | {m.fp} | {m.tn} | {m.fn} | "
                f"{m.precision:.1%} | {m.recall:.1%} | {m.f1_score:.3f} | {m.accuracy:.1%} |"
            )
        lines.append(
            f"| **OVERALL (Macro)** | "
            f"{sum(m.total_samples for m in self.category_metrics.values())} | "
            f"{sum(m.tp for m in self.category_metrics.values())} | "
            f"{sum(m.fp for m in self.category_metrics.values())} | "
            f"{sum(m.tn for m in self.category_metrics.values())} | "
            f"{sum(m.fn for m in self.category_metrics.values())} | "
            f"- | - | **{self.macro_f1:.3f}** | **{self.overall_accuracy:.1%}** |"
        )
        return "\n".join(lines)


class BenchmarkRunner:
    """Executes the benchmark suite and compiles statistical metrics."""

    def __init__(self) -> None:
        self.resilience_service = ResilienceAnalyzerService()
        self.entropy_service = EntropyAnalyzerService()
        self.slop_service = AISlopClassifier()

    def run_suite(self, samples: list[BenchmarkSample] | None = None) -> BenchmarkReport:
        """Runs evaluation over all samples and computes performance metrics."""
        dataset = samples if samples is not None else load_benchmark_dataset()
        metrics: dict[str, MetricSummary] = {}
        failures: list[dict[str, Any]] = []

        for sample in dataset:
            cat = sample.category
            if cat not in metrics:
                metrics[cat] = MetricSummary(category=cat)

            m = metrics[cat]
            m.total_samples += 1

            detected = self._evaluate_sample(sample)
            expected = sample.is_positive

            if detected and expected:
                m.tp += 1
            elif detected and not expected:
                m.fp += 1
                failures.append({
                    "id": sample.id,
                    "category": cat,
                    "type": "False Positive",
                    "description": sample.description,
                })
            elif not detected and not expected:
                m.tn += 1
            else:  # not detected and expected
                m.fn += 1
                failures.append({
                    "id": sample.id,
                    "category": cat,
                    "type": "False Negative",
                    "description": sample.description,
                })

        return BenchmarkReport(category_metrics=metrics, failures=failures)

    def _evaluate_sample(self, sample: BenchmarkSample) -> bool:
        """Invokes the corresponding detector on the code sample."""
        cat = sample.category

        if cat in ("missing_timeout", "bare_except", "silent_swallow"):
            try:
                tree = ast.parse(sample.code, filename=f"{sample.id}.py")
            except SyntaxError:
                return False

            defects = self.resilience_service._scan_rules(tree, f"{sample.id}.py")

            target_rule = "silent_exception_swallow" if cat == "silent_swallow" else cat
            return any(d.rule == target_rule for d in defects)

        if cat == "secret_entropy":
            findings = self.entropy_service.scan_code(sample.code, f"{sample.id}.py")
            return len(findings) > 0

        if cat == "ai_slop":
            res = self.slop_service.analyze_source_content(sample.code, filename=f"{sample.id}.py")
            return (res["slop_comments_count"] + res["mixed_comments_count"]) > 0

        raise ValueError(f"Unknown benchmark category: {cat}")


def main() -> None:
    """CLI entrypoint to run the benchmark suite and print the score table."""
    runner = BenchmarkRunner()
    report = runner.run_suite()

    print("\n==================== WARDEN DETECTOR BENCHMARK ====================")
    print(report.format_table())
    print("===================================================================\n")

    if report.failures:
        print(f"⚠️  {len(report.failures)} Misclassifications:")
        for f in report.failures:
            print(f"  - [{f['type']}] ({f['category']}) {f['id']}: {f['description']}")
    else:
        print("🎯 100% Precision & Recall across all benchmark categories!")

    # Save to benchmarks/results.json
    results_path = Path("benchmarks/results.json")
    results_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(f"\n[+] Saved detailed benchmark metrics to {results_path.resolve()}\n")


if __name__ == "__main__":
    main()
