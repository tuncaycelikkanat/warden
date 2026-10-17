"""WARDEN Detection Benchmarking Framework.

Provides curated ground-truth datasets and evaluation metrics (Precision, Recall,
F1-Score, False Positive Rate) for static analysis detectors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from benchmarks.dataset import BenchmarkSample, load_benchmark_dataset
    from benchmarks.runner import BenchmarkReport, BenchmarkRunner

__all__ = [
    "BenchmarkReport",
    "BenchmarkRunner",
    "BenchmarkSample",
    "load_benchmark_dataset",
]


def __getattr__(name: str) -> Any:
    if name in ("BenchmarkSample", "load_benchmark_dataset"):
        from benchmarks import dataset

        return getattr(dataset, name)
    if name in ("BenchmarkReport", "BenchmarkRunner"):
        from benchmarks import runner

        return getattr(runner, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
