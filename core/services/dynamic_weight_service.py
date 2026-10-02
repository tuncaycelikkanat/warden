"""Dynamic Weighting Service for WARDEN (Section C1).

Optimizes Layer 1 static analyzer group weights and Layer 2 LLM rubric category weights
based on architectural project archetypes (FastAPI, Django, CLI, ML, Library, etc.).
Supports smart hybrid overrides via configuration or CLI flags.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.services.core_group_catalog import CORE_GROUPS
from core.services.project_classifier import ProjectTypeClassifier

logger = logging.getLogger(__name__)

# Base Layer 1 group keys and default catalog weights
DEFAULT_LAYER1_WEIGHTS: dict[str, float] = {
    g.key: round(g.weight, 4) for g in CORE_GROUPS
}

# Base Layer 2 rubric categories and default baseline weights
DEFAULT_LAYER2_WEIGHTS: dict[str, float] = {
    "architectural_discipline": 1.0,
    "quantitative_logic": 1.0,
    "llm_integration": 1.0,
    "devops_deployment": 1.0,
    "frontend_ux": 1.0,
    "api_design": 1.0,
    "concurrency_safety": 1.0,
}


@dataclass
class ArchetypeWeightProfile:
    """Weight modifiers and architectural priorities for a given archetype."""

    archetype: str
    label: str
    description: str
    layer1_modifiers: dict[str, float] = field(default_factory=dict)
    layer2_modifiers: dict[str, float] = field(default_factory=dict)


# Archetype Profiles defining structural emphasis across Layer 1 and Layer 2
ARCHETYPE_PROFILES: dict[str, ArchetypeWeightProfile] = {
    "FASTAPI_API": ArchetypeWeightProfile(
        archetype="FASTAPI_API",
        label="⚡ FastAPI REST / Async API",
        description="Öncelik: Ağ saldırı yüzeyi güvenliği, asenkron dayanıklılık ve OpenAPI şema doğruluğu.",
        layer1_modifiers={
            "security_supply_chain": 1.35,
            "resilience_performance": 1.30,
            "code_health_test": 1.00,
            "structural_health": 0.95,
            "dev_hygiene_devops": 0.85,
        },
        layer2_modifiers={
            "api_design": 1.50,
            "concurrency_safety": 1.40,
            "architectural_discipline": 1.15,
            "devops_deployment": 1.05,
            "llm_integration": 1.00,
            "quantitative_logic": 0.70,
            "frontend_ux": 0.40,
        },
    ),
    "DJANGO_WEB": ArchetypeWeightProfile(
        archetype="DJANGO_WEB",
        label="🌐 Django Full-Stack Web App",
        description="Öncelik: Web güvenliği (CSRF/XSS/Auth), modüler katman ayrımı ve UI/form akışı.",
        layer1_modifiers={
            "security_supply_chain": 1.35,
            "structural_health": 1.20,
            "code_health_test": 1.00,
            "dev_hygiene_devops": 0.95,
            "resilience_performance": 0.90,
        },
        layer2_modifiers={
            "architectural_discipline": 1.35,
            "api_design": 1.25,
            "frontend_ux": 1.25,
            "devops_deployment": 1.15,
            "concurrency_safety": 0.80,
            "quantitative_logic": 0.70,
            "llm_integration": 1.00,
        },
    ),
    "FLASK_APP": ArchetypeWeightProfile(
        archetype="FLASK_APP",
        label="🧪 Flask Microservice",
        description="Öncelik: Hafif WSGI API tasarımı, uç nokta güvenliği ve blueprint disiplini.",
        layer1_modifiers={
            "security_supply_chain": 1.25,
            "code_health_test": 1.15,
            "resilience_performance": 1.05,
            "structural_health": 1.00,
            "dev_hygiene_devops": 0.90,
        },
        layer2_modifiers={
            "api_design": 1.35,
            "architectural_discipline": 1.15,
            "concurrency_safety": 1.05,
            "devops_deployment": 1.05,
            "frontend_ux": 0.90,
            "quantitative_logic": 0.70,
            "llm_integration": 1.00,
        },
    ),
    "CLI_TOOL": ArchetypeWeightProfile(
        archetype="CLI_TOOL",
        label="💻 CLI Terminal Application",
        description="Öncelik: Geliştirici dokümantasyonu, CLI argüman/çıkış hijyeni ve katı test disiplini.",
        layer1_modifiers={
            "dev_hygiene_devops": 1.45,
            "code_health_test": 1.25,
            "structural_health": 1.10,
            "resilience_performance": 0.90,
            "security_supply_chain": 0.75,
        },
        layer2_modifiers={
            "architectural_discipline": 1.25,
            "devops_deployment": 1.20,
            "concurrency_safety": 0.75,
            "api_design": 0.40,
            "frontend_ux": 0.40,
            "quantitative_logic": 0.80,
            "llm_integration": 1.00,
        },
    ),
    "DATA_SCIENCE_ML": ArchetypeWeightProfile(
        archetype="DATA_SCIENCE_ML",
        label="🔬 Data Science & Machine Learning",
        description="Öncelik: İstatistiki doğrulama (Quantitative Logic), bellek dayanıklılığı ve veri akışı.",
        layer1_modifiers={
            "resilience_performance": 1.40,
            "code_health_test": 1.25,
            "structural_health": 1.05,
            "security_supply_chain": 0.90,
            "dev_hygiene_devops": 0.85,
        },
        layer2_modifiers={
            "quantitative_logic": 1.70,
            "concurrency_safety": 1.25,
            "architectural_discipline": 1.15,
            "devops_deployment": 1.00,
            "llm_integration": 1.10,
            "api_design": 0.50,
            "frontend_ux": 0.40,
        },
    ),
    "LIBRARY_PACKAGE": ArchetypeWeightProfile(
        archetype="LIBRARY_PACKAGE",
        label="📦 Reusable Library / SDK",
        description="Öncelik: Tip güvenliği, sıfır döngüsel bağımlılık, docstring kapsamı ve API kararlılığı.",
        layer1_modifiers={
            "code_health_test": 1.35,
            "structural_health": 1.30,
            "dev_hygiene_devops": 1.15,
            "resilience_performance": 1.00,
            "security_supply_chain": 0.85,
        },
        layer2_modifiers={
            "architectural_discipline": 1.45,
            "devops_deployment": 1.25,
            "api_design": 1.15,
            "concurrency_safety": 1.00,
            "quantitative_logic": 0.80,
            "llm_integration": 0.90,
            "frontend_ux": 0.30,
        },
    ),
    "GENERIC_BACKEND": ArchetypeWeightProfile(
        archetype="GENERIC_BACKEND",
        label="⚙️ Genel Python Arka Plan Servisi",
        description="Dengeli standart kalite ağırlıkları.",
        layer1_modifiers={},
        layer2_modifiers={},
    ),
}


@dataclass
class WeightAdjustmentReport:
    """Report detailing dynamic weight calculations for both layers."""

    archetype: str
    label: str
    confidence: float
    description: str
    matched_traits: list[str] = field(default_factory=list)
    layer1_baseline: dict[str, float] = field(default_factory=dict)
    layer1_adjusted: dict[str, float] = field(default_factory=dict)
    layer2_baseline: dict[str, float] = field(default_factory=dict)
    layer2_adjusted: dict[str, float] = field(default_factory=dict)
    custom_overrides: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DynamicWeightService:
    """Calculates and normalizes archetype-driven dynamic weights across Layer 1 and Layer 2."""

    def __init__(self) -> None:
        self.classifier = ProjectTypeClassifier()

    def get_profile(self, archetype: str) -> ArchetypeWeightProfile:
        """Retrieves profile by archetype name, falling back to GENERIC_BACKEND."""
        return ARCHETYPE_PROFILES.get(archetype, ARCHETYPE_PROFILES["GENERIC_BACKEND"])

    def get_adjusted_layer1_weights(
        self,
        archetype: str,
        custom_overrides: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Calculates normalized Layer 1 group weights based on archetype and optional overrides.

        The resulting weights maintain the exact proportions while summing to 1.0.
        """
        profile = self.get_profile(archetype)
        overrides = custom_overrides or {}

        raw_weights: dict[str, float] = {}
        for key, base_w in DEFAULT_LAYER1_WEIGHTS.items():
            if key in overrides:
                raw_weights[key] = max(0.01, float(overrides[key]))
            else:
                mod = profile.layer1_modifiers.get(key, 1.0)
                raw_weights[key] = max(0.01, base_w * mod)

        total = sum(raw_weights.values())
        if total <= 0:
            return DEFAULT_LAYER1_WEIGHTS.copy()

        # Normalize to sum to 1.0 (proportionate redistribution)
        return {k: round(w / total, 4) for k, w in raw_weights.items()}

    def get_adjusted_layer2_weights(
        self,
        archetype: str,
        custom_overrides: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Calculates normalized Layer 2 rubric category weights.

        Normalized such that the average weight across categories is 1.0.
        """
        profile = self.get_profile(archetype)
        overrides = custom_overrides or {}

        raw_weights: dict[str, float] = {}
        for key, base_w in DEFAULT_LAYER2_WEIGHTS.items():
            if key in overrides:
                raw_weights[key] = max(0.05, float(overrides[key]))
            else:
                mod = profile.layer2_modifiers.get(key, 1.0)
                raw_weights[key] = max(0.05, base_w * mod)

        total = sum(raw_weights.values())
        count = len(raw_weights)
        if total <= 0 or count == 0:
            return DEFAULT_LAYER2_WEIGHTS.copy()

        # Normalize so average weight equals 1.0 (preserving relative ratios)
        scale = count / total
        return {k: round(w * scale, 3) for k, w in raw_weights.items()}

    def analyze_project_weights(
        self,
        repo_path: Path,
        custom_overrides: dict[str, float] | None = None,
    ) -> WeightAdjustmentReport:
        """Classifies project and produces comprehensive before/after dynamic weighting report."""
        classification = self.classifier.classify(repo_path)
        arch = classification.archetype
        profile = self.get_profile(arch)

        l1_adj = self.get_adjusted_layer1_weights(arch, custom_overrides=custom_overrides)
        l2_adj = self.get_adjusted_layer2_weights(arch, custom_overrides=custom_overrides)

        # Baseline normalized Layer 1
        base_l1_total = sum(DEFAULT_LAYER1_WEIGHTS.values())
        base_l1_norm = {k: round(v / base_l1_total, 4) for k, v in DEFAULT_LAYER1_WEIGHTS.items()}

        return WeightAdjustmentReport(
            archetype=arch,
            label=profile.label,
            confidence=classification.confidence,
            description=profile.description,
            matched_traits=classification.matched_traits,
            layer1_baseline=base_l1_norm,
            layer1_adjusted=l1_adj,
            layer2_baseline=DEFAULT_LAYER2_WEIGHTS.copy(),
            layer2_adjusted=l2_adj,
            custom_overrides=custom_overrides or {},
        )
