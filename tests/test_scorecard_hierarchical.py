from core.services.scorecard import ScorecardAggregatorService


def test_hierarchical_scorecard_calculation():
    service = ScorecardAggregatorService()
    
    # Dummy data
    layer1_data = {
        "security": [{"severity": "ERROR"}, {"severity": "WARNING"}],
        "leaks": [{"dummy": "leak"}],
        "dependencies": [{"status": "failed_check"}],
        "coverage": 60.0,
        "complexity": {},
        "lint": {},
        "docs": {},
        "resilience": {}
    }
    
    layer2_data = [
        {"rubric_verdict": {"level": 8}},
        {"rubric_verdict": {"level": 6}}
    ]
    
    result = service.calculate(layer1_data, layer2_data)
    
    ms = result.breakdown["member_scores"]
    assert ms["security_semgrep"] == 50
    assert ms["secret_leak_gitleaks"] == 50
    assert ms["dependency_osv"] == 80
    assert ms["test_coverage"] == 75.0
    assert ms["complexity_radon"] == 100
    assert ms["lint_style_ruff"] == 100
    assert ms["documentation"] == 100
    assert ms["resilience_ast"] == 100

    gs = result.group_scores
    # Check security_supply_chain
    # weights: sec: 7/16, leak: 4/16, dep: 4/16. missing license (1/16)
    # total weight = 15/16
    expected_sec = (50 * 7/16 + 50 * 4/16 + 80 * 4/16) / (15/16)
    assert round(gs["security_supply_chain"], 2) == round(expected_sec, 2)
    
    assert result.layer2_score == 70
    assert 0 <= result.layer1_score <= 100
    assert 0 <= result.total_score <= 100

def test_all_100_yields_100():
    """
    Verification for Item 1:
    When all 14 active members receive a score of 100,
    the Layer 1 score and total score must be exactly 100 (not 91.7).
    This proves that the active group weights (16+18+10+4+7 = 55) are dynamically
    normalized (W_k / sum(W_active)) across the 100% Layer 1 scale.
    """
    from core.services.core_group_catalog import MEMBER_TO_GROUP
    service = ScorecardAggregatorService()
    
    # All 14 members receive 100
    all_100_members = {k: 100.0 for k in MEMBER_TO_GROUP}
    
    # When Layer 2 is empty (or disabled)
    result = service.calculate(all_100_members, [])
    assert result.layer1_score == 100
    assert result.total_score == 100
    assert result.grade == "A+"
    for g_score in result.group_scores.values():
        assert g_score == 100.0

def test_unmeasured_category_redistributes_weight():
    """
    Roadmap Step 8.32 / Roadmap Item 3:
    When an optional/unmeasured category is missing (e.g. coverage was not measured),
    it is not penalized with 0; its intra-group weight is proportionally redistributed
    among the remaining members of that group.
    """
    service = ScorecardAggregatorService()
    
    # Suppose in code_health_test:
    # test_quality = 100 (weight 4/18), lint_style_ruff = 100 (weight 4/18), type_safety = 100 (weight 3/18)
    # test_coverage is UNMEASURED (not provided)
    data = {
        "test_quality": 100.0,
        "lint_style_ruff": 100.0,
        "type_safety": 100.0
    }
    result = service.calculate(data, [])
    # group score for code_health_test should be 100.0, not penalized for missing coverage
    assert result.group_scores["code_health_test"] == 100.0

