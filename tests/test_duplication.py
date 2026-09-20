"""Tests for DuplicationService and scorecard duplication scoring."""

from pathlib import Path
from unittest.mock import patch

import pytest

from core.services.duplication import DuplicationService
from core.services.scorecard import ScorecardAggregatorService


@pytest.mark.asyncio
async def test_duplication_clean_project():
    """Clean project with no copy-pasted code receives 0% duplication and 100 score."""
    service = DuplicationService()
    sc = ScorecardAggregatorService()

    res = await service.analyze(Path("tests/fixtures/duplication/clean_project"))
    assert res.measured is True
    assert res.duplication_pct == 0.0
    assert len(res.clone_pairs) == 0

    score = sc._score_duplication(res.__dict__)
    assert score == 100.0


@pytest.mark.asyncio
async def test_duplication_real_copy_paste():
    """Real copy-pasted function across two files is detected with full clone pair evidence."""
    service = DuplicationService()
    sc = ScorecardAggregatorService()

    res = await service.analyze(Path("tests/fixtures/duplication/real_copy_paste"))
    assert res.measured is True
    assert res.duplication_pct > 20.0
    assert len(res.clone_pairs) >= 1

    clone = res.clone_pairs[0]
    assert "service_a.py" in clone["first_file"] or "service_b.py" in clone["first_file"]
    assert "service_a.py" in clone["second_file"] or "service_b.py" in clone["second_file"]
    assert clone["lines"] >= 8
    assert "calculate_composite_metrics" in clone["fragment"]

    score = sc._score_duplication(res.__dict__)
    assert score < 50.0


@pytest.mark.asyncio
async def test_duplication_config_evasion_resistance():
    """A target repo's local .jscpd.json with minTokens: 1000 is ignored in favor of WARDEN's baseline."""
    service = DuplicationService()

    res = await service.analyze(Path("tests/fixtures/duplication/loosened_jscpdrc_project"))
    assert res.measured is True
    # If the local config was used, minTokens: 1000 would have caused 0 clones
    # With WARDEN's immutable baseline, the clone is caught
    assert res.duplication_pct > 20.0
    assert len(res.clone_pairs) >= 1


@pytest.mark.asyncio
async def test_duplication_excludes_boilerplate_models():
    """Models in models.py with similar field definitions are excluded from duplication penalties."""
    service = DuplicationService()
    sc = ScorecardAggregatorService()

    res = await service.analyze(Path("tests/fixtures/duplication/boilerplate_models"))
    assert res.measured is True
    assert res.duplication_pct == 0.0
    assert len(res.clone_pairs) == 0

    score = sc._score_duplication(res.__dict__)
    assert score == 100.0


@pytest.mark.asyncio
async def test_duplication_unmeasured_when_jscpd_missing(tmp_path: Path):
    """When jscpd binary cannot be resolved, service returns measured=False rather than silent 100."""
    service = DuplicationService()
    with patch.object(service, "_resolve_jscpd_cmd", return_value=None):
        res = await service.analyze(tmp_path)
        assert res.measured is False
        assert res.reason == "jscpd_not_found"

    # Scorecard should omit duplication_jscpd from member scores
    sc = ScorecardAggregatorService()
    scores = sc.calculate({"duplication": {"measured": False}}, [])
    assert "duplication_jscpd" not in scores.breakdown.get("member_scores", {})


@pytest.mark.asyncio
async def test_duplication_unmeasured_on_timeout(tmp_path: Path):
    """When jscpd execution exceeds 120s timeout, service returns measured=False."""
    import subprocess
    service = DuplicationService()
    with patch.object(service, "_run_jscpd", side_effect=subprocess.TimeoutExpired(cmd="jscpd", timeout=120)):
        res = await service.analyze(tmp_path)
        assert res.measured is False
        assert res.reason == "jscpd_timeout"


@pytest.mark.asyncio
async def test_duplication_unmeasured_on_malformed_report(tmp_path: Path):
    """When jscpd report contains malformed JSON, service returns measured=False with distinct reason."""
    import json
    service = DuplicationService()
    with patch.object(service, "_run_jscpd", side_effect=json.JSONDecodeError("Invalid JSON", "{", 0)):
        res = await service.analyze(tmp_path)
        assert res.measured is False
        assert res.reason == "jscpd_report_parse_error"


def test_duplication_scoring_formula():
    """Tests the score penalty calculation across different duplication percentages."""
    sc = ScorecardAggregatorService()

    # 0% -> 100
    assert sc._score_duplication({"duplication_pct": 0.0}) == 100.0
    # 5% -> 100 - (5 * 8) = 60
    assert sc._score_duplication({"duplication_pct": 5.0}) == 60.0
    # 10% -> 100 - (10 * 8) = 20
    assert sc._score_duplication({"duplication_pct": 10.0}) == 20.0
    # 12.5%+ -> 0
    assert sc._score_duplication({"duplication_pct": 12.5}) == 0.0
    assert sc._score_duplication({"duplication_pct": 25.0}) == 0.0
