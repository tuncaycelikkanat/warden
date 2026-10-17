"""Registry for pluggable Layer 1 code analyzers."""

from __future__ import annotations

import asyncio
import importlib.metadata
import logging
from typing import Any

from core.analyzers.adapters import (
    CiCdAnalyzer,
    CommitHygieneAnalyzer,
    ComplexityAnalyzer,
    CoverageAnalyzer,
    DependencyAnalyzer,
    DockerAnalyzer,
    DocumentationAnalyzer,
    DuplicationAnalyzer,
    LicenseAnalyzer,
    LintAnalyzer,
    ResilienceAnalyzer,
    SecretLeakAnalyzer,
    SecurityAnalyzer,
    TechDebtAnalyzer,
    TestQualityAnalyzer,
    TypeSafetyAnalyzer,
)
from core.analyzers.protocol import AnalysisContext, AnalyzerOutput, AnalyzerPlugin

logger = logging.getLogger(__name__)


class AnalyzerRegistry:
    """Central registry holding all active Layer 1 analyzers."""

    def __init__(self) -> None:
        self._analyzers: dict[str, AnalyzerPlugin] = {}

    def register(self, analyzer: AnalyzerPlugin) -> None:
        """Registers an analyzer plugin under its key."""
        self._analyzers[analyzer.key] = analyzer
        logger.debug(f"Registered analyzer: {analyzer.key} ({analyzer.display_name})")

    def unregister(self, key: str) -> bool:
        """Removes an analyzer from the registry if present."""
        return self._analyzers.pop(key, None) is not None

    def get(self, key: str) -> AnalyzerPlugin | None:
        """Retrieves an analyzer by key."""
        return self._analyzers.get(key)

    def list_all(self) -> list[AnalyzerPlugin]:
        """Returns all registered analyzer plugins."""
        return list(self._analyzers.values())

    def load_entrypoints(self, group: str = "warden.analyzers") -> int:
        """Discovers and registers 3rd-party analyzer plugins via entry_points.

        Returns:
            The number of newly loaded external plugins.
        """
        loaded = 0
        try:
            eps = importlib.metadata.entry_points()
            plugins: Any = (
                eps.select(group=group)
                if hasattr(eps, "select")
                else getattr(eps, "get", lambda *_: [])(group, [])
            )
            for ep in plugins:
                try:
                    plugin_cls = ep.load()
                    plugin_instance = plugin_cls() if isinstance(plugin_cls, type) else plugin_cls
                    if isinstance(plugin_instance, AnalyzerPlugin):
                        self.register(plugin_instance)
                        loaded += 1
                        logger.info(f"Loaded external analyzer plugin: {ep.name}")
                except Exception as err:
                    logger.warning(f"Failed to load analyzer entrypoint '{ep.name}': {err}")
        except Exception as err:
            logger.debug(f"Entrypoint discovery skipped: {err}")
        return loaded

    async def run_all(
        self, ctx: AnalysisContext
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Runs all registered analyzers concurrently with fault isolation.

        Returns:
            A tuple of (layer1_data, l1_summary) ready for scorecard calculation.
        """
        keys = list(self._analyzers.keys())
        tasks = [self._safe_run(self._analyzers[k], ctx) for k in keys]
        outputs: list[AnalyzerOutput] = await asyncio.gather(*tasks)

        layer1_data: dict[str, Any] = {}
        l1_summary: dict[str, Any] = {}

        for out in outputs:
            layer1_data[out.key] = out.data
            if out.extra_data:
                layer1_data.update(out.extra_data)
            if out.summary:
                l1_summary.update(out.summary)

        return layer1_data, l1_summary

    async def _safe_run(self, analyzer: AnalyzerPlugin, ctx: AnalysisContext) -> AnalyzerOutput:
        """Executes a single analyzer with exception containment."""
        try:
            return await analyzer.run(ctx)
        except Exception as exc:
            logger.exception(f"Analyzer '{analyzer.key}' raised unexpected error")
            return AnalyzerOutput(
                key=analyzer.key,
                data=None,
                summary={},
                measured=False,
                error=str(exc),
            )


def create_default_registry() -> AnalyzerRegistry:
    """Instantiates and registers all 16 built-in Layer 1 analyzers."""
    registry = AnalyzerRegistry()
    default_analyzers: list[AnalyzerPlugin] = [
        SecurityAnalyzer(),
        DependencyAnalyzer(),
        ComplexityAnalyzer(),
        LintAnalyzer(),
        SecretLeakAnalyzer(),
        CoverageAnalyzer(),
        DocumentationAnalyzer(),
        ResilienceAnalyzer(),
        LicenseAnalyzer(),
        TypeSafetyAnalyzer(),
        TestQualityAnalyzer(),
        CiCdAnalyzer(),
        DockerAnalyzer(),
        CommitHygieneAnalyzer(),
        DuplicationAnalyzer(),
        TechDebtAnalyzer(),
    ]
    for analyzer in default_analyzers:
        registry.register(analyzer)

    # Automatically load any installed entry_points plugins
    registry.load_entrypoints()
    return registry
