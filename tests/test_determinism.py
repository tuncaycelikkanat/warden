"""Determinism, purity, and idempotency tests for WARDEN scoring and analyzer registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.analyzers.protocol import AnalysisContext
from core.analyzers.registry import create_default_registry
from core.services.scorecard import ScorecardAggregatorService


def _create_sample_repo(base_dir: Path) -> Path:
    """Creates a deterministic multi-file sample Python project."""
    src = base_dir / "sample_pkg"
    src.mkdir(parents=True, exist_ok=True)

    (src / "__init__.py").write_text('"""Sample package."""\n__version__ = "0.1.0"\n', encoding="utf-8")
    (src / "math_utils.py").write_text(
        '"""Math utilities."""\n\n'
        "def add(a: int, b: int) -> int:\n"
        '    """Returns sum of two integers."""\n'
        "    return a + b\n\n"
        "def safe_divide(a: float, b: float) -> float | None:\n"
        '    """Divides a by b safely."""\n'
        "    try:\n"
        "        return a / b\n"
        "    except ZeroDivisionError:\n"
        "        return None\n",
        encoding="utf-8",
    )
    (src / "net_client.py").write_text(
        '"""Network client module."""\n\n'
        "import requests\n\n"
        "def fetch_data(url: str) -> dict:\n"
        '    """Fetches JSON with explicit timeout."""\n'
        "    response = requests.get(url, timeout=5.0)\n"
        "    return response.json()\n",
        encoding="utf-8",
    )

    tests_dir = base_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_math.py").write_text(
        "from sample_pkg.math_utils import add, safe_divide\n\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n\n"
        "def test_safe_divide():\n"
        "    assert safe_divide(10, 2) == 5.0\n"
        "    assert safe_divide(10, 0) is None\n",
        encoding="utf-8",
    )

    (base_dir / "pyproject.toml").write_text(
        '[project]\nname = "sample-pkg"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    return base_dir


def test_scorecard_aggregator_determinism():
    """Verifies that scorecard calculations are strictly deterministic and idempotent."""
    aggregator = ScorecardAggregatorService()

    sample_l1 = {
        "security": [
            {"severity": "INFO", "message": "informational note"},
            {"severity": "WARNING", "message": "mild warning"},
        ],
        "dependencies": [
            {"name": "requests", "status": "ok"},
            {"name": "urllib3", "status": "ok"},
        ],
        "complexity": {"average_complexity": 2.5, "outliers": []},
        "lint": {"error_count": 0, "warning_count": 2},
        "coverage": {"percent_covered": 88.5},
        "leaks": [],
        "resilience": {"defects": []},
        "documentation": {"score": 92.0},
    }

    # Run calculation multiple times
    results = [aggregator.calculate(sample_l1, []) for _ in range(25)]

    first = results[0]
    for idx, r in enumerate(results[1:], start=2):
        assert r.total_score == first.total_score, f"Drift at run {idx}: {r.total_score} != {first.total_score}"
        assert r.grade == first.grade
        assert r.layer1_score == first.layer1_score
        assert r.group_scores == first.group_scores


@pytest.mark.asyncio
async def test_analyzer_registry_idempotency(tmp_path: Path):
    """Verifies that running analyzer registry repeatedly on the same tree produces identical findings."""
    repo = _create_sample_repo(tmp_path)
    registry = create_default_registry()

    ctx = AnalysisContext(repo_path=repo)

    run1_data, run1_summary = await registry.run_all(ctx)
    run2_data, run2_summary = await registry.run_all(ctx)

    # Both runs should identify the exact same keys
    assert set(run1_data.keys()) == set(run2_data.keys())

    # Summary numbers must be identical
    for key in ("lint", "resilience", "leaks", "documentation"):
        if key in run1_summary and key in run2_summary:
            assert run1_summary[key] == run2_summary[key], f"Summary drift for key '{key}'"


@settings(max_examples=50)
@given(
    sec_errors=st.integers(min_value=0, max_value=10),
    sec_warnings=st.integers(min_value=0, max_value=20),
    coverage_pct=st.floats(min_value=0.0, max_value=100.0),
    lint_errors=st.integers(min_value=0, max_value=50),
)
def test_scorecard_boundedness_hypothesis(sec_errors, sec_warnings, coverage_pct, lint_errors):
    """Property test verifying that total_score is strictly bounded in [0, 100] for any input."""
    aggregator = ScorecardAggregatorService()

    findings: list[dict[str, Any]] = (
        [{"severity": "ERROR"}] * sec_errors + [{"severity": "WARNING"}] * sec_warnings
    )
    l1_data: dict[str, Any] = {
        "security": findings,
        "coverage": {"percent_covered": coverage_pct},
        "lint": {"error_count": lint_errors, "warning_count": 0},
    }

    result = aggregator.calculate(l1_data, [])
    assert 0 <= result.total_score <= 100
    assert result.grade in ("A+", "A", "B", "C", "D", "F")
