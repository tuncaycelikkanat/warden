"""Comprehensive tests for ScorecardAggregatorService edge cases and formula branches."""
from types import SimpleNamespace

from core.services.scorecard import ScorecardAggregatorService


def test_score_tech_debt_churn_hotspots():
    svc = ScorecardAggregatorService()
    # Mock data with dict churn entries having age_days >= 30, high churn ratio, in outlier_blocks
    debt_data = {
        "total_commits_in_window": 100,
        "churn_entries": [
            {"file": "core/heavy.py", "commit_count": 20, "age_days": 60},  # ratio 0.20 > 0.05
            {"file": "core/new.py", "commit_count": 10, "age_days": 15},    # age < 30 -> exempt
        ],
        "todo_markers": ["TODO: fixme"] * 5
    }
    complexity_data = {
        "outlier_blocks": [{"file": "core/heavy.py"}]
    }
    score = svc._score_tech_debt(debt_data, complexity=complexity_data)
    # hotspot penalty = 0.20 * 40.0 = 8.0, todo penalty = 5 * 0.2 = 1.0 -> 100 - 9 = 91.0
    assert score == 91.0


def test_score_resilience_edge_cases():
    svc = ScorecardAggregatorService()

    # Case 1: list of defects directly
    list_score = svc._score_resilience(["defect1", "defect2"])
    assert list_score == 50.0  # 100 - 2 * 25.0

    # Case 2: dict with file_count <= 0
    dict_score = svc._score_resilience({"defects": ["d1"], "file_count": 0})
    assert dict_score < 100.0


def test_extract_resilience_unmeasured_objects():
    svc = ScorecardAggregatorService()
    scores = {}

    # Unmeasured docs object (SimpleNamespace)
    mock_docs = SimpleNamespace(measured=False, score=None)
    mock_resilience = SimpleNamespace(measured=False, score=None)

    svc._extract_resilience_metrics({"docs": mock_docs, "resilience": mock_resilience}, scores)
    assert "documentation" not in scores
    assert "resilience_ast" not in scores

    # Measured resilience object
    mock_res_measured = SimpleNamespace(measured=True, defects=[], file_count=5)
    svc._extract_resilience_metrics({"resilience": mock_res_measured}, scores)
    assert scores["resilience_ast"] == 100.0


def test_calc_layer1_and_layer2_zero_weights():
    svc = ScorecardAggregatorService()

    # calc_layer1 with empty group scores -> total_group_weight == 0
    assert svc._calc_layer1({}) == 0

    # calc_layer2 with category weight <= 0
    cats = [
        {
            "category": "cat1",
            "weight": 0.0,
            "rubric_verdict": {"evaluated": True, "level": 8.0}
        }
    ]
    val, redistributed = svc._calc_layer2(cats, category_weights={"cat1": 0.0})
    assert val is None
    assert redistributed is True


def test_get_grade_full_scale():
    svc = ScorecardAggregatorService()
    assert svc._get_grade(98) == "A+"
    assert svc._get_grade(92) == "A"
    assert svc._get_grade(85) == "B"
    assert svc._get_grade(75) == "C"
    assert svc._get_grade(65) == "D"
    assert svc._get_grade(40) == "F"
