"""Unit tests for pluggable Layer 1 analyzer architecture."""

from pathlib import Path

import pytest

from core.analyzers.adapters import SecurityAnalyzer
from core.analyzers.protocol import AnalysisContext, AnalyzerOutput, AnalyzerPlugin
from core.analyzers.registry import AnalyzerRegistry, create_default_registry


class DummyGoodAnalyzer:
    key = "dummy_good"
    display_name = "Dummy Good"

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        return AnalyzerOutput(
            key=self.key,
            data={"status": "ok"},
            summary={"dummy_metric": 42},
            extra_data={"dummy_meta": {"version": 1}},
        )


class DummyFailingAnalyzer:
    key = "dummy_fail"
    display_name = "Dummy Fail"

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        raise RuntimeError("Unexpected boom in analyzer")


def test_analyzer_protocol_conformance() -> None:
    assert isinstance(DummyGoodAnalyzer(), AnalyzerPlugin)
    assert isinstance(SecurityAnalyzer(), AnalyzerPlugin)


def test_registry_register_and_get() -> None:
    reg = AnalyzerRegistry()
    good = DummyGoodAnalyzer()
    reg.register(good)

    assert reg.get("dummy_good") is good
    assert reg.get("nonexistent") is None
    assert len(reg.list_all()) == 1

    assert reg.unregister("dummy_good") is True
    assert reg.get("dummy_good") is None
    assert reg.unregister("dummy_good") is False


@pytest.mark.asyncio
async def test_registry_run_all_success_and_fault_isolation(tmp_path: Path) -> None:
    reg = AnalyzerRegistry()
    reg.register(DummyGoodAnalyzer())
    reg.register(DummyFailingAnalyzer())

    ctx = AnalysisContext(repo_path=tmp_path)
    layer1_data, l1_summary = await reg.run_all(ctx)

    # The good analyzer output and extra_data must be present
    assert layer1_data["dummy_good"] == {"status": "ok"}
    assert layer1_data["dummy_meta"] == {"version": 1}
    assert l1_summary["dummy_metric"] == 42

    # The failing analyzer must NOT crash run_all; its failure is contained
    assert layer1_data["dummy_fail"] is None


def test_create_default_registry_has_all_16_analyzers() -> None:
    reg = create_default_registry()
    keys = {a.key for a in reg.list_all()}

    expected_keys = {
        "security",
        "dependencies",
        "complexity",
        "lint",
        "leaks",
        "coverage",
        "docs",
        "resilience",
        "license_compliance",
        "type_safety",
        "test_quality",
        "cicd_presence",
        "docker_readiness",
        "commit_hygiene",
        "duplication",
        "tech_debt",
    }
    assert expected_keys.issubset(keys)
    assert len(reg.list_all()) >= 16
