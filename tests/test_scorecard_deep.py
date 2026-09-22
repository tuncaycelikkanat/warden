"""Comprehensive unit tests for ScorecardAggregatorService edge cases and dataclass handling."""

from dataclasses import dataclass
from pathlib import Path
import pytest

from core.services.scorecard import ScorecardAggregatorService


@dataclass
class DummyChurnEntry:
    file: str
    commit_count: int
    age_days: int


@dataclass
class DummyTodoMarker:
    file: str
    line: int
    tag: str


@dataclass
class DummyTechDebtResult:
    measured: bool = True
    total_commits_in_window: int = 10
    churn_entries: list = None
    todo_markers: list = None


@dataclass
class DummyResilienceDefect:
    file: str
    line: int
    category: str
    severity: str
    message: str


@dataclass
class DummyResilienceResult:
    measured: bool = True
    defects: list = None
    file_count: int = 5


@dataclass
class DummyTypeSafetyResult:
    measured: bool = True
    score: float = 85.0
    error_count: int = 2
    file_count: int = 10


@dataclass
class DummyTestQualityResult:
    measured: bool = True
    score: float = 90.0
    total_tests: int = 20
    fake_tests: int = 1
    fake_test_ratio: float = 0.05
    avg_assertion_density: float = 2.5


@dataclass
class DummyDockerResult:
    applicable: bool = True
    measured: bool = True
    score: float = 85.0
    has_dockerfile: bool = True
    has_healthcheck: bool = True
    has_non_root_user: bool = False
    has_multistage: bool = True
    has_env_example: bool = True
    has_docker_compose: bool = False


@dataclass
class DummyCommitHygieneResult:
    measured: bool = True
    score: float = 92.0
    total_commits: int = 50
    bad_commits: int = 2
    bad_ratio: float = 0.04
    avg_length: float = 45.0


def test_scorecard_empty_or_unmeasured_inputs():
    svc = ScorecardAggregatorService()

    # Empty duplication
    assert svc._score_duplication({}) == 100.0

    # Complexity with rank_distribution of total 0
    assert svc._score_complexity({"rank_distribution": {"A": 0, "B": 0}}) == 100.0

    # Empty tech debt
    assert svc._score_tech_debt(None) == 100.0
    assert svc._score_tech_debt({}) == 100.0


def test_scorecard_tech_debt_dataclass_and_hotspot():
    svc = ScorecardAggregatorService()

    # Dataclass input with hotspot matching complexity outlier
    entry = DummyChurnEntry(file="core/main.py", commit_count=15, age_days=30)
    marker = DummyTodoMarker(file="core/main.py", line=42, tag="TODO")
    debt = DummyTechDebtResult(
        measured=True,
        total_commits_in_window=20,
        churn_entries=[entry],
        todo_markers=[marker],
    )

    complexity = {
        "outlier_blocks": [{"file": "core/main.py", "complexity": 25}]
    }

    score = svc._score_tech_debt(debt, complexity=complexity)
    assert 0.0 <= score < 100.0


def test_scorecard_resilience_dataclass():
    svc = ScorecardAggregatorService()
    defect1 = DummyResilienceDefect(file="a.py", line=1, category="timeout", severity="HIGH", message="no timeout")
    defect2 = DummyResilienceDefect(file="b.py", line=2, category="broad_except", severity="MEDIUM", message="broad")
    res_data = DummyResilienceResult(measured=True, defects=[defect1, defect2], file_count=5)

    score = svc._score_resilience(res_data)
    assert 0.0 <= score < 100.0


def test_scorecard_member_objects_and_dataclasses():
    svc = ScorecardAggregatorService()

    layer1_data = {
        "docker_readiness": DummyDockerResult(score=85.0),
        "type_safety": DummyTypeSafetyResult(score=88.0),
        "test_quality": DummyTestQualityResult(score=91.0),
        "commit_hygiene": DummyCommitHygieneResult(score=92.0),
        "docs": DummyResilienceResult(measured=True, defects=[]),
        "resilience": DummyResilienceResult(measured=True, defects=[]),
        "duplication": {"measured": True, "duplication_pct": 2.0},
        "tech_debt": {"measured": True, "churn_entries": [], "todo_markers": []},
        "lint": {"measured": True, "score": 95.0},
    }

    scores = svc._extract_member_scores(layer1_data)
    assert scores["docker_readiness"] == 85.0
    assert scores["type_safety"] == 88.0
    assert scores["test_quality"] == 91.0
    assert scores["commit_hygiene"] == 92.0
    assert "documentation" in scores
    assert "resilience_ast" in scores
    assert "duplication_jscpd" in scores
    assert "tech_debt_churn" in scores
    assert "lint_style_ruff" in scores


def test_scorecard_grade_thresholds():
    svc = ScorecardAggregatorService()
    assert svc._get_grade(96) == "A+"
    assert svc._get_grade(92) == "A"
    assert svc._get_grade(85) == "B"
    assert svc._get_grade(75) == "C"
    assert svc._get_grade(65) == "D"
    assert svc._get_grade(45) == "F"

