"""Central project configuration reader and model for WARDEN.

Reads configuration from `warden.config.yaml`, `.warden.yaml`, or defaults.
Allows repositories to define custom weights, thresholds, ignore rules,
and LLM parameters.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core.config.scoring_constants import LAYER1_WEIGHT, LAYER2_WEIGHT

logger = logging.getLogger(__name__)

# Default weights for dynamic Layer 2 categories (Phase 1: Weighted Rubrics)
DEFAULT_CATEGORY_WEIGHTS: dict[str, float] = {
    "architectural_discipline": 2.0,  # Critical architectural foundation
    "llm_integration": 1.5,           # High relevance in AI era
    "concurrency_safety": 1.5,        # High crash / corruption risk
    "api_design": 1.2,                # Public contract quality
    "devops_deployment": 1.0,         # Infrastructure hygiene
    "frontend_ux": 1.0,               # UI / client quality
    "quantitative_logic": 1.2,        # Data consistency / backtesting
}

CONFIG_FILENAMES = (
    "warden.config.yaml",
    "warden.config.yml",
    ".warden.yaml",
    ".warden.yml",
)


@dataclass
class ScoringConfig:
    """Scoring weights and quality gate thresholds."""

    layer1_weight: float = LAYER1_WEIGHT
    layer2_weight: float = LAYER2_WEIGHT
    min_score_gate: int | None = None
    category_weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_CATEGORY_WEIGHTS))


@dataclass
class ThresholdsConfig:
    """Configurable quality and health threshold targets."""

    min_coverage: float = 80.0
    max_complexity: float = 10.0
    max_duplication_pct: float = 5.0
    min_docstring_pct: float = 80.0


@dataclass
class LLMRuntimeConfig:
    """LLM provider and evaluation parameters."""

    provider: str = "gemini"  # "gemini" | "openai" | "anthropic" | "ollama"
    models: list[str] = field(default_factory=lambda: ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"])
    temperature: float = 0.0
    timeout_sec: int = 60


@dataclass
class IgnoreConfig:
    """Paths and rules to ignore during scan."""

    paths: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)


@dataclass
class WardenConfig:
    """Top-level WARDEN repository configuration."""

    version: int = 1
    profile: str = "auto"
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    thresholds: ThresholdsConfig = field(default_factory=ThresholdsConfig)
    llm: LLMRuntimeConfig = field(default_factory=LLMRuntimeConfig)
    ignore: IgnoreConfig = field(default_factory=IgnoreConfig)

    @classmethod
    def load_from_repo(cls, repo_path: Path | str) -> "WardenConfig":
        """Loads configuration from the repo directory, or returns default if not found."""
        path = Path(repo_path)
        for fname in CONFIG_FILENAMES:
            candidate = path / fname
            if candidate.is_file():
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                    logger.info(f"Loaded WARDEN configuration from {candidate}")
                    return cls.from_dict(data)
                except Exception as e:
                    logger.warning(f"Failed to parse {candidate}: {e}. Using defaults.")

        return cls()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WardenConfig":
        """Parses a dictionary into a typed WardenConfig instance."""
        scoring_data = data.get("scoring", {})
        cat_weights = dict(DEFAULT_CATEGORY_WEIGHTS)
        if "category_weights" in scoring_data and isinstance(scoring_data["category_weights"], dict):
            cat_weights.update(scoring_data["category_weights"])

        scoring = ScoringConfig(
            layer1_weight=float(scoring_data.get("layer1_weight", LAYER1_WEIGHT)),
            layer2_weight=float(scoring_data.get("layer2_weight", LAYER2_WEIGHT)),
            min_score_gate=scoring_data.get("min_score_gate"),
            category_weights=cat_weights,
        )

        thresh_data = data.get("thresholds", {})
        thresholds = ThresholdsConfig(
            min_coverage=float(thresh_data.get("min_coverage", 80.0)),
            max_complexity=float(thresh_data.get("max_complexity", 10.0)),
            max_duplication_pct=float(thresh_data.get("max_duplication_pct", 5.0)),
            min_docstring_pct=float(thresh_data.get("min_docstring_pct", 80.0)),
        )

        llm_data = data.get("llm", {})
        llm = LLMRuntimeConfig(
            provider=str(llm_data.get("provider", "gemini")),
            models=list(llm_data.get("models", ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"])),
            temperature=float(llm_data.get("temperature", 0.0)),
            timeout_sec=int(llm_data.get("timeout_sec", 60)),
        )

        ignore_data = data.get("ignore", {})
        ignore = IgnoreConfig(
            paths=list(ignore_data.get("paths", [])),
            rules=list(ignore_data.get("rules", [])),
        )

        return cls(
            version=int(data.get("version", 1)),
            profile=str(data.get("profile", "auto")),
            scoring=scoring,
            thresholds=thresholds,
            llm=llm,
            ignore=ignore,
        )
