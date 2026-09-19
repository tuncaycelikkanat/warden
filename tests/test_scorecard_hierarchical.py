import pytest
from core.services.scorecard import ScorecardAggregatorService
from core.services.core_group_catalog import CORE_GROUPS

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
