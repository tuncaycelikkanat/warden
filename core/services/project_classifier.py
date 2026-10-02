"""Automated Project Type Classifier for WARDEN.

Analyzes repository structure, entry points, dependencies, and code patterns to determine
the primary architectural archetype of the project:
- FASTAPI_API: High-performance asynchronous RESTful APIs
- DJANGO_WEB: Full-featured Django web application
- FLASK_APP: Lightweight WSGI microservices
- CLI_TOOL: Command-line utilities (Click, Typer, Argparse)
- DATA_SCIENCE_ML: Machine learning and scientific computing pipelines
- LIBRARY_PACKAGE: Reusable Python library or SDK
- GENERIC_BACKEND: General backend services and data processors

Provides archetype-tailored rubric recommendations and category weight adjustments.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.services.evidence.base import safe_read_file

logger = logging.getLogger(__name__)

ARCHETYPE_LABELS = {
    "FASTAPI_API": "⚡ FastAPI REST / Async API",
    "DJANGO_WEB": "🌐 Django Full-Stack Web App",
    "FLASK_APP": "🧪 Flask Microservice",
    "CLI_TOOL": "💻 CLI Terminal Application",
    "DATA_SCIENCE_ML": "🔬 Data Science & Machine Learning",
    "LIBRARY_PACKAGE": "📦 Reusable Library / SDK",
    "GENERIC_BACKEND": "⚙️ Genel Python Arka Plan Servisi",
}

ARCHETYPE_RECOMMENDATIONS = {
    "FASTAPI_API": "API şema doğrulaması, JWT/OAuth2 güvenliği, Pydantic modelleri ve async I/O yönetimi öncelikli.",
    "DJANGO_WEB": "ORM sorgu optimizasyonu, CSRF/XSS koruması, yetkilendirme ve settings sır yönetimi öncelikli.",
    "FLASK_APP": "Blueprint modülerliği, istek doğrulama, hata sayfaları ve WSGI uyumluluğu öncelikli.",
    "CLI_TOOL": "Parametre ve bayrak doğrulama, çıkış kodları (exit codes), bağımlılık hafifliği ve CLI kullanıcı deneyimi öncelikli.",
    "DATA_SCIENCE_ML": "Bellek optimizasyonu, deterministik pipeline'lar, model sürümleme ve veri güvenliği öncelikli.",
    "LIBRARY_PACKAGE": "Geriye dönük API uyumluluğu, docstring kapsamı, tip ipuçları (type hints) ve test kapsamı öncelikli.",
    "GENERIC_BACKEND": "Katmanlı mimari disiplini, hata yönetimi ve kod sağlığı standartları dengeli şekilde uygulanmalıdır.",
}

# Category weight multipliers by archetype
ARCHETYPE_WEIGHT_MODIFIERS: dict[str, dict[str, float]] = {
    "FASTAPI_API": {"group_security": 1.25, "group_resilience": 1.15, "group_dev_hygiene": 0.9},
    "DJANGO_WEB": {"group_security": 1.30, "group_structural": 1.15, "group_resilience": 1.0},
    "FLASK_APP": {"group_security": 1.20, "group_code_health": 1.10},
    "CLI_TOOL": {"group_dev_hygiene": 1.30, "group_code_health": 1.20, "group_security": 0.8},
    "DATA_SCIENCE_ML": {"group_code_health": 1.25, "group_resilience": 1.20, "group_structural": 0.9},
    "LIBRARY_PACKAGE": {"group_code_health": 1.30, "group_structural": 1.25, "group_dev_hygiene": 1.1},
    "GENERIC_BACKEND": {},
}


@dataclass
class ArchetypeClassification:
    """The classified primary project archetype and associated metadata."""

    archetype: str
    label: str
    confidence: float  # 0.0 to 1.0
    matched_traits: list[str] = field(default_factory=list)
    recommended_rubric: str = ""
    suggested_weights: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "archetype": self.archetype,
            "label": self.label,
            "confidence": round(self.confidence, 3),
            "matched_traits": self.matched_traits,
            "recommended_rubric": self.recommended_rubric,
            "suggested_weights": self.suggested_weights,
        }


class ProjectTypeClassifier:
    """Classifies repository archetype from manifest dependencies and structural traits."""

    def _read_manifests(self, repo_path: Path) -> dict[str, str]:
        """Reads dependency manifests if present."""
        manifests = {}
        for m in ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile"):
            p = repo_path / m
            if p.is_file():
                try:
                    manifests[m] = p.read_text(encoding="utf-8", errors="ignore").lower()
                except OSError:
                    pass
        return manifests

    def classify(self, repo_path: Path) -> ArchetypeClassification:
        """Determines the primary architectural archetype of the given repository."""
        repo_path = repo_path.resolve()
        manifests = self._read_manifests(repo_path)
        all_manifest_content = " ".join(manifests.values())

        scores: dict[str, float] = {k: 0.0 for k in ARCHETYPE_LABELS}
        traits: dict[str, list[str]] = {k: [] for k in ARCHETYPE_LABELS}

        # 1. FastAPI Detection
        if "fastapi" in all_manifest_content:
            scores["FASTAPI_API"] += 45.0
            traits["FASTAPI_API"].append("manifest:fastapi")
        if "uvicorn" in all_manifest_content:
            scores["FASTAPI_API"] += 20.0
            traits["FASTAPI_API"].append("manifest:uvicorn")
        if any(repo_path.glob("**/api/**/*.py")) or any(repo_path.glob("**/routers/**/*.py")):
            scores["FASTAPI_API"] += 15.0
            traits["FASTAPI_API"].append("layout:api_or_routers_dir")

        # 2. Django Detection
        if "django" in all_manifest_content:
            scores["DJANGO_WEB"] += 50.0
            traits["DJANGO_WEB"].append("manifest:django")
        if (repo_path / "manage.py").is_file():
            scores["DJANGO_WEB"] += 40.0
            traits["DJANGO_WEB"].append("file:manage.py")
        if any(repo_path.glob("**/wsgi.py")) or any(repo_path.glob("**/asgi.py")):
            scores["DJANGO_WEB"] += 15.0
            traits["DJANGO_WEB"].append("layout:wsgi_or_asgi")

        # 3. Flask Detection
        if "flask" in all_manifest_content and "fastapi" not in all_manifest_content:
            scores["FLASK_APP"] += 45.0
            traits["FLASK_APP"].append("manifest:flask")

        # 4. CLI Tool Detection
        cli_libs = ["click", "typer", "rich", "argparse"]
        for lib in cli_libs:
            if lib in all_manifest_content:
                scores["CLI_TOOL"] += 20.0
                traits["CLI_TOOL"].append(f"manifest:{lib}")
        pyproj = manifests.get("pyproject.toml", "")
        if "project.scripts" in pyproj or "[project.scripts]" in pyproj or "console_scripts" in all_manifest_content:
            scores["CLI_TOOL"] += 35.0
            traits["CLI_TOOL"].append("config:console_scripts")

        # 5. Data Science / Machine Learning
        ml_libs = ["torch", "tensorflow", "scikit-learn", "sklearn", "pandas", "numpy", "scipy"]
        ml_matches = [lib for lib in ml_libs if lib in all_manifest_content]
        if len(ml_matches) >= 2:
            scores["DATA_SCIENCE_ML"] += 40.0 + len(ml_matches) * 8.0
            traits["DATA_SCIENCE_ML"].append(f"manifest:ml_libs({len(ml_matches)})")
        if any(repo_path.glob("**/*.ipynb")):
            scores["DATA_SCIENCE_ML"] += 25.0
            traits["DATA_SCIENCE_ML"].append("files:jupyter_notebooks")

        # 6. Library / Package Detection
        if (repo_path / "setup.py").is_file() or ("build-backend" in pyproj and "fastapi" not in all_manifest_content and "django" not in all_manifest_content):
            scores["LIBRARY_PACKAGE"] += 30.0
            traits["LIBRARY_PACKAGE"].append("packaging:build_backend_library")

        # Select highest-scoring archetype
        top_archetype, top_score = max(scores.items(), key=lambda item: item[1])

        if top_score < 25.0:
            top_archetype = "GENERIC_BACKEND"
            confidence = 0.60
            matched_traits = ["default:generic_python_structure"]
        else:
            confidence = min(0.98, max(0.55, top_score / 90.0))
            matched_traits = traits[top_archetype]

        return ArchetypeClassification(
            archetype=top_archetype,
            label=ARCHETYPE_LABELS.get(top_archetype, top_archetype),
            confidence=round(confidence, 3),
            matched_traits=matched_traits,
            recommended_rubric=ARCHETYPE_RECOMMENDATIONS.get(top_archetype, ""),
            suggested_weights=ARCHETYPE_WEIGHT_MODIFIERS.get(top_archetype, {}),
        )
