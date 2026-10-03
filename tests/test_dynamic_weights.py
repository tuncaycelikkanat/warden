"""Unit and integration tests for Section C1 Dynamic Weighting Service."""

from __future__ import annotations

import json
from pathlib import Path

from core.services.dynamic_weight_service import (
    ARCHETYPE_PROFILES,
    DEFAULT_LAYER1_WEIGHTS,
    DEFAULT_LAYER2_WEIGHTS,
    ArchetypeWeightProfile,
    DynamicWeightService,
    WeightAdjustmentReport,
)
from core.services.scorecard import ScorecardAggregatorService


class TestArchetypeProfiles:
    """Tests the integrity and completeness of Archetype profiles."""

    def test_all_archetypes_defined(self):
        svc = DynamicWeightService()
        expected = [
            "FASTAPI_API",
            "DJANGO_WEB",
            "FLASK_APP",
            "CLI_TOOL",
            "DATA_SCIENCE_ML",
            "LIBRARY_PACKAGE",
            "GENERIC_BACKEND",
        ]
        for arch in expected:
            profile = svc.get_profile(arch)
            assert isinstance(profile, ArchetypeWeightProfile)
            assert profile.archetype == arch
            assert profile.label != ""

    def test_unknown_archetype_fallback(self):
        svc = DynamicWeightService()
        fallback = svc.get_profile("UNKNOWN_CUSTOM_ARCHETYPE")
        assert fallback.archetype == "GENERIC_BACKEND"


class TestLayer1DynamicWeighting:
    """Tests Layer 1 static group dynamic weight adjustments and normalization."""

    def test_weights_sum_to_one(self):
        svc = DynamicWeightService()
        for arch in ARCHETYPE_PROFILES:
            w = svc.get_adjusted_layer1_weights(arch)
            assert len(w) == len(DEFAULT_LAYER1_WEIGHTS)
            total = sum(w.values())
            assert abs(total - 1.0) < 0.005, f"Weights for {arch} must sum to 1.0, got {total}"

    def test_fastapi_boosts_security_and_resilience(self):
        svc = DynamicWeightService()
        w = svc.get_adjusted_layer1_weights("FASTAPI_API")
        base_sec = DEFAULT_LAYER1_WEIGHTS["security_supply_chain"] / sum(DEFAULT_LAYER1_WEIGHTS.values())
        base_res = DEFAULT_LAYER1_WEIGHTS["resilience_performance"] / sum(DEFAULT_LAYER1_WEIGHTS.values())

        assert w["security_supply_chain"] > base_sec
        assert w["resilience_performance"] > base_res

    def test_cli_boosts_dev_hygiene_and_code_health(self):
        svc = DynamicWeightService()
        w = svc.get_adjusted_layer1_weights("CLI_TOOL")
        base_hygiene = DEFAULT_LAYER1_WEIGHTS["dev_hygiene_devops"] / sum(DEFAULT_LAYER1_WEIGHTS.values())

        assert w["dev_hygiene_devops"] > base_hygiene
        # Local CLI has smaller security attack surface than web API
        assert w["security_supply_chain"] < svc.get_adjusted_layer1_weights("FASTAPI_API")["security_supply_chain"]

    def test_library_boosts_code_health_and_structure(self):
        svc = DynamicWeightService()
        w = svc.get_adjusted_layer1_weights("LIBRARY_PACKAGE")
        base_struct = DEFAULT_LAYER1_WEIGHTS["structural_health"] / sum(DEFAULT_LAYER1_WEIGHTS.values())

        assert w["structural_health"] > base_struct
        assert w["code_health_test"] > 0.30


class TestLayer2DynamicWeighting:
    """Tests Layer 2 rubric category dynamic weight adjustments and normalization."""

    def test_layer2_average_weight_is_one(self):
        svc = DynamicWeightService()
        for arch in ARCHETYPE_PROFILES:
            w = svc.get_adjusted_layer2_weights(arch)
            assert len(w) == len(DEFAULT_LAYER2_WEIGHTS)
            avg = sum(w.values()) / len(w)
            assert abs(avg - 1.0) < 0.05, f"Avg weight for {arch} must be ~1.0, got {avg}"

    def test_fastapi_boosts_api_design_and_concurrency(self):
        svc = DynamicWeightService()
        w = svc.get_adjusted_layer2_weights("FASTAPI_API")
        assert w["api_design"] > 1.3
        assert w["concurrency_safety"] > 1.2
        assert w["frontend_ux"] < 0.6  # Backend API has low UI importance

    def test_data_science_boosts_quantitative_logic(self):
        svc = DynamicWeightService()
        w = svc.get_adjusted_layer2_weights("DATA_SCIENCE_ML")
        assert w["quantitative_logic"] > 1.5
        assert w["concurrency_safety"] > 1.1

    def test_django_boosts_frontend_and_architecture(self):
        svc = DynamicWeightService()
        w = svc.get_adjusted_layer2_weights("DJANGO_WEB")
        assert w["frontend_ux"] > 1.1
        assert w["architectural_discipline"] > 1.2


class TestSmartHybridOverrides:
    """Tests user custom weight overrides and automatic re-normalization."""

    def test_layer1_override_priority(self):
        svc = DynamicWeightService()
        overrides = {"security_supply_chain": 0.80}
        w = svc.get_adjusted_layer1_weights("FASTAPI_API", custom_overrides=overrides)

        # The overridden group should dominate the distribution
        assert w["security_supply_chain"] > 0.50
        assert abs(sum(w.values()) - 1.0) < 0.005

    def test_layer2_override_priority(self):
        svc = DynamicWeightService()
        overrides = {"api_design": 3.0}
        w = svc.get_adjusted_layer2_weights("CLI_TOOL", custom_overrides=overrides)

        assert w["api_design"] > 2.0
        assert len(w) == len(DEFAULT_LAYER2_WEIGHTS)

    def test_weight_adjustment_report_model(self, tmp_path: Path):
        # Create minimal manifest
        (tmp_path / "pyproject.toml").write_text("[project]\ndependencies = ['fastapi', 'uvicorn']\n", encoding="utf-8")
        svc = DynamicWeightService()
        report = svc.analyze_project_weights(tmp_path, custom_overrides={"security_supply_chain": 0.45})

        assert isinstance(report, WeightAdjustmentReport)
        assert report.archetype == "FASTAPI_API"
        assert report.confidence > 0.5
        d = report.to_dict()
        assert d["archetype"] == "FASTAPI_API"
        assert "security_supply_chain" in d["layer1_adjusted"]
        assert d["custom_overrides"] == {"security_supply_chain": 0.45}


class TestScorecardIntegration:
    """Tests the impact of dynamic weights when calculating Scorecard results."""

    def test_scorecard_with_archetype(self):
        sc = ScorecardAggregatorService()
        l1 = {
            "security": [{"severity": "ERROR"}, {"severity": "ERROR"}],  # security penalty
            "coverage": 80.0,
            "complexity": {"rank_distribution": {"A": 100.0}},
            "resilience": {"defects": []},
            "docs": {"docstring_coverage_pct": 95.0, "has_readme_setup_section": True, "has_readme_usage_section": True},
        }

        # Calculate standard vs FastAPI vs CLI
        res_default = sc.calculate(l1, layer2_data=[])
        res_fastapi = sc.calculate(l1, layer2_data=[], archetype="FASTAPI_API")
        res_cli = sc.calculate(l1, layer2_data=[], archetype="CLI_TOOL")

        assert res_default.total_score > 0
        assert res_fastapi.archetype == "FASTAPI_API"
        assert res_fastapi.dynamic_weights is not None
        assert "layer1" in res_fastapi.dynamic_weights

        # FastAPI prioritizes security more heavily than CLI, so score must be lower
        assert res_fastapi.total_score < res_cli.total_score

    def test_scorecard_backwards_compatibility(self):
        sc = ScorecardAggregatorService()
        l1 = {"coverage": 80.0, "lint": {"score": 90.0}}
        res = sc.calculate(l1, layer2_data=[])

        assert res.archetype is None
        assert res.dynamic_weights is None
        assert res.total_score > 0

    def test_scorecard_with_layer2_dynamic_rubric(self):
        sc = ScorecardAggregatorService()
        l1 = {"coverage": 80.0}
        # Rubric with high quantitative logic (level 9) and lower api_design (level 4)
        l2 = [
            {"category": "quantitative_logic", "rubric_verdict": {"level": 9, "evaluated": True}},
            {"category": "api_design", "rubric_verdict": {"level": 4, "evaluated": True}},
        ]

        # ML archetype prioritizes quantitative logic heavily, so Layer 2 score should be higher than API archetype
        res_ml = sc.calculate(l1, layer2_data=l2, archetype="DATA_SCIENCE_ML")
        res_api = sc.calculate(l1, layer2_data=l2, archetype="FASTAPI_API")

        assert res_ml.layer2_score is not None
        assert res_api.layer2_score is not None
        assert res_ml.layer2_score > res_api.layer2_score


class TestCLIClassifyCommand:
    """Tests CLI `warden classify` command outputs and options."""

    def test_cli_classify_text_output(self, capsys):
        from core.main import _run_classify_command

        _run_classify_command(".", show_weights=True)
        captured = capsys.readouterr()

        assert "WARDEN PROJE ARKETİPİ VE DİNAMİK AĞIRLIKLANDIRMA" in captured.out
        assert "Arketip" in captured.out
        assert "LAYER 1 (STATİK GRUPLAR) DİNAMİK AĞIRLIK DAĞILIMI" in captured.out
        assert "LAYER 2 (LLM RUBRIC) DİNAMİK KATEGORİ ÇARPANLARI" in captured.out

    def test_cli_classify_json_output(self, capsys):
        from core.main import _run_classify_command

        _run_classify_command(".", as_json=True)
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        assert "archetype" in data
        assert "layer1_adjusted" in data
        assert "layer2_adjusted" in data

    def test_cli_classify_with_override(self, capsys):
        from core.main import _run_classify_command

        _run_classify_command(
            ".",
            show_weights=True,
            overrides=["security_supply_chain=0.55", "invalid_override"],
        )
        captured = capsys.readouterr()

        assert "security_supply_chain" in captured.out
        assert "Uygulanan Kullanıcı Override'ları" in captured.out
        assert "0.55" in captured.out
