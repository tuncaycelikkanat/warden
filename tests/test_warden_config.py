"""Tests for WARDEN configuration loading and weighted scorecard aggregation."""

import tempfile
from pathlib import Path

import pytest

from core.config.warden_config import WardenConfig, DEFAULT_CATEGORY_WEIGHTS
from core.services.scorecard import ScorecardAggregatorService


class TestWardenConfig:
    def test_default_config(self) -> None:
        cfg = WardenConfig()
        assert cfg.version == 1
        assert cfg.profile == "auto"
        assert cfg.scoring.layer1_weight == 0.60
        assert cfg.scoring.layer2_weight == 0.40
        assert cfg.thresholds.min_coverage == 80.0
        assert cfg.llm.provider == "gemini"
        assert "gemini-2.5-flash" in cfg.llm.models

    def test_load_from_repo_custom_yaml(self, tmp_path: Path) -> None:
        yaml_content = """
version: 1
profile: fintech
scoring:
  layer1_weight: 0.70
  layer2_weight: 0.30
  min_score_gate: 75
  category_weights:
    architectural_discipline: 3.0
    quantitative_logic: 2.5
thresholds:
  min_coverage: 90.0
  max_complexity: 8.0
llm:
  provider: openai
  models: [gpt-4o, gpt-4o-mini]
  temperature: 0.2
ignore:
  paths: [vendor/, legacy/]
  rules: [license_compliance]
"""
        config_file = tmp_path / "warden.config.yaml"
        config_file.write_text(yaml_content)

        cfg = WardenConfig.load_from_repo(tmp_path)
        assert cfg.profile == "fintech"
        assert cfg.scoring.layer1_weight == 0.70
        assert cfg.scoring.layer2_weight == 0.30
        assert cfg.scoring.min_score_gate == 75
        assert cfg.scoring.category_weights["architectural_discipline"] == 3.0
        assert cfg.scoring.category_weights["quantitative_logic"] == 2.5
        assert cfg.thresholds.min_coverage == 90.0
        assert cfg.thresholds.max_complexity == 8.0
        assert cfg.llm.provider == "openai"
        assert cfg.llm.models == ["gpt-4o", "gpt-4o-mini"]
        assert cfg.ignore.paths == ["vendor/", "legacy/"]
        assert "license_compliance" in cfg.ignore.rules

    def test_fallback_when_no_config_file(self, tmp_path: Path) -> None:
        cfg = WardenConfig.load_from_repo(tmp_path)
        assert cfg.profile == "auto"
        assert cfg.scoring.layer1_weight == 0.60


class TestWeightedLayer2Scorecard:
    def test_uniform_weights_match_previous_behavior(self) -> None:
        scorecard = ScorecardAggregatorService()
        categories = [
            {"category": "cat1", "rubric_verdict": {"evaluated": True, "level": 6}},
            {"category": "cat2", "rubric_verdict": {"evaluated": True, "level": 8}},
        ]
        # Uniform average: (6 + 8) / 2 = 7.0 -> 70
        calc_l2, unmeasured = scorecard._calc_layer2(categories)
        assert calc_l2 == 70
        assert not unmeasured

    def test_custom_weights_impact_score(self) -> None:
        scorecard = ScorecardAggregatorService()
        categories = [
            # Critical architecture rated 10 with weight 3.0
            {"category": "architectural_discipline", "rubric_verdict": {"evaluated": True, "level": 10}},
            # Minor frontend rated 2 with weight 1.0
            {"category": "frontend_ux", "rubric_verdict": {"evaluated": True, "level": 2}},
        ]
        weights = {"architectural_discipline": 3.0, "frontend_ux": 1.0}
        # Weighted: (10*3.0 + 2*1.0) / (3.0 + 1.0) = 32 / 4 = 8.0 -> 80
        calc_l2, unmeasured = scorecard._calc_layer2(categories, category_weights=weights)
        assert calc_l2 == 80
        assert not unmeasured

    def test_unmeasured_when_empty_or_all_failed(self) -> None:
        scorecard = ScorecardAggregatorService()
        calc_l2, unmeasured = scorecard._calc_layer2([])
        assert calc_l2 is None
        assert not unmeasured

        categories = [
            {"category": "cat1", "rubric_verdict": {"evaluated": False, "level": None}},
        ]
        calc_l2, unmeasured = scorecard._calc_layer2(categories)
        assert calc_l2 is None
        assert unmeasured
