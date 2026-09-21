"""Project profiling and dynamic category detection based on architectural signals."""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.services.shared.scan_exclusions import get_scan_exclusions
from core.utils.file_discovery import discover_source_files

logger = logging.getLogger(__name__)

CATALOG_VERSION = "v1.1"
MANIFEST_FILES = ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile", "package.json"]


def _is_path_excluded(path: Path, repo_path: Path) -> bool:
    """Checks if a path resides inside central scan exclusion directories."""
    exclusions = set(get_scan_exclusions(repo_path, extra=["tests", "test", "fixtures", "test_data", "examples"]))
    try:
        rel = path.relative_to(repo_path)
        parts = rel.parts
    except ValueError:
        parts = path.parts

    for p in parts:
        if p in exclusions or (p.startswith(".") and p not in {".github", ".docker"}):
            return True
    return False


@dataclass
class SignalMatch:
    """Represents the outcome of a signal evaluation."""

    matched: bool
    evidence: list[str] = field(default_factory=list)
    signal_type: str = "generic"


class Signal:
    """Base signal class for architectural pattern detection."""

    def evaluate(self, repo_path: Path, manifests: dict[str, str]) -> SignalMatch:
        """Evaluates the signal within the repository path and manifest collection."""
        raise NotImplementedError

    def matches(self, repo_path: Path) -> bool:
        """Legacy helper for backward compatibility."""
        manifests = {}
        for m in MANIFEST_FILES:
            p = repo_path / m
            if p.is_file() and not _is_path_excluded(p, repo_path):
                try:
                    manifests[m] = p.read_text(encoding="utf-8", errors="ignore").lower()
                except OSError:
                    pass
        return self.evaluate(repo_path, manifests).matched


class DependencySignal(Signal):
    """Detects dependencies mentioned in repository manifests with word boundary precision."""

    def __init__(self, any_of: list[str], manifests: list[str] | None = None):
        """Initializes dependency candidates and target manifest files."""
        self.any_of = any_of
        self.manifests = manifests

    def _word_boundary_match(self, keyword: str, content: str) -> bool:
        """
        Matches keyword when bounded by quotes, colons, commas, brackets, or line delimiters.
        Prevents false positive substring matches (e.g., 'pytest-reactor' matching 'react').
        """
        pattern = re.compile(
            rf'(?:^|[\s"\'\,\[\(]){re.escape(keyword)}(?:[\s"\'\,\]\)=><~:]|$)',
            re.IGNORECASE | re.MULTILINE,
        )
        return bool(pattern.search(content))

    def evaluate(self, repo_path: Path, manifests: dict[str, str]) -> SignalMatch:
        evidence: list[str] = []
        target_manifests = self.manifests if self.manifests is not None else list(manifests.keys())

        for mf in target_manifests:
            if mf in manifests:
                content = manifests[mf]
                for dep in self.any_of:
                    if self._word_boundary_match(dep, content):
                        evidence.append(f"dependency:{mf}:{dep}")

        return SignalMatch(
            matched=len(evidence) > 0,
            evidence=evidence,
            signal_type="dependency",
        )


class DirectorySignal(Signal):
    """Detects directory structure presence in the project, respecting exclusions."""

    def __init__(self, any_of: list[str] | None = None, all_of: list[str] | None = None):
        """Initializes any_of or all_of directory patterns."""
        self.any_of = any_of or []
        self.all_of = all_of or []

    def evaluate(self, repo_path: Path, manifests: dict[str, str]) -> SignalMatch:
        evidence: list[str] = []

        if self.any_of:
            for pattern in self.any_of:
                matched_dirs = [
                    d for d in repo_path.glob(pattern)
                    if d.is_dir() and not _is_path_excluded(d, repo_path)
                ]
                if matched_dirs:
                    try:
                        rel = str(matched_dirs[0].relative_to(repo_path))
                    except ValueError:
                        rel = str(matched_dirs[0])
                    evidence.append(f"directory:{rel}")
                    return SignalMatch(matched=True, evidence=evidence, signal_type="directory")
            return SignalMatch(matched=False, evidence=[], signal_type="directory")

        if self.all_of:
            for pattern in self.all_of:
                matched_dirs = [
                    d for d in repo_path.glob(pattern)
                    if d.is_dir() and not _is_path_excluded(d, repo_path)
                ]
                if not matched_dirs:
                    return SignalMatch(matched=False, evidence=[], signal_type="directory")
                try:
                    rel = str(matched_dirs[0].relative_to(repo_path))
                except ValueError:
                    rel = str(matched_dirs[0])
                evidence.append(f"directory:{rel}")

            return SignalMatch(matched=True, evidence=evidence, signal_type="directory")

        return SignalMatch(matched=False, evidence=[], signal_type="directory")


class FilePatternSignal(Signal):
    """Detects file glob patterns with minimum occurrences, respecting exclusions."""

    def __init__(self, any_of: list[str], min_count: int = 1):
        """Initializes glob patterns and threshold count."""
        self.any_of = any_of
        self.min_count = min_count

    def evaluate(self, repo_path: Path, manifests: dict[str, str]) -> SignalMatch:
        matching_files: list[str] = []
        for pattern in self.any_of:
            for f in repo_path.glob(pattern):
                if f.is_file() and not _is_path_excluded(f, repo_path):
                    try:
                        matching_files.append(str(f.relative_to(repo_path)))
                    except ValueError:
                        matching_files.append(str(f))

        if len(matching_files) >= self.min_count:
            return SignalMatch(
                matched=True,
                evidence=[f"files:{len(matching_files)}_matching"],
                signal_type="file_pattern",
            )
        return SignalMatch(matched=False, evidence=[], signal_type="file_pattern")


class SourcePatternSignal(Signal):
    """Scans repository source files for specific code patterns."""

    def __init__(self, any_of: list[str]):
        """Initializes code patterns to locate in source files."""
        self.any_of = any_of

    def evaluate(self, repo_path: Path, manifests: dict[str, str]) -> SignalMatch:
        files = discover_source_files(repo_path)
        evidence: list[str] = []
        for f in files:
            if _is_path_excluded(f, repo_path):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                for pattern in self.any_of:
                    if pattern in content:
                        try:
                            rel = str(f.relative_to(repo_path))
                        except ValueError:
                            rel = str(f)
                        evidence.append(f"source:{rel}:{pattern}")
                        if len(evidence) >= 3:
                            break
            except OSError:
                continue
            if evidence:
                break

        return SignalMatch(
            matched=len(evidence) > 0,
            evidence=evidence,
            signal_type="source_pattern",
        )


CATEGORY_CATALOG: dict[str, dict[str, Any]] = {
    "frontend_ux": {
        "label": "💻 Frontend & Kullanıcı Deneyimi",
        "signals": [
            DependencySignal(any_of=["react", "vue", "svelte", "next"], manifests=["package.json"]),
            FilePatternSignal(any_of=["**/*.tsx", "**/*.vue", "**/*.jsx"], min_count=5),
        ],
    },
    "devops_deployment": {
        "label": "🚀 DevOps & Dağıtım",
        "signals": [
            FilePatternSignal(any_of=["Dockerfile", "docker-compose*.yml", "fly.toml", "render.yaml"]),
            DirectorySignal(any_of=[".github/workflows", "deploy", "docker", "terraform", "k8s", "helm"]),
        ],
    },
    "quantitative_logic": {
        "label": "📈 Kantitatif & Matematiksel Mantık",
        "signals": [
            DependencySignal(any_of=["numba", "scipy", "optuna", "pandas-ta"]),
            DirectorySignal(any_of=["**/backtesting", "**/quant_optimization", "backtesting", "quant_optimization"]),
        ],
    },
    "llm_integration": {
        "label": "🤖 LLM Entegrasyonu & Prompt Güvenliği",
        "signals": [
            DependencySignal(any_of=["anthropic", "openai", "google-genai", "ollama", "langchain"]),
            DirectorySignal(any_of=["**/agents", "**/prompts"]),
        ],
    },
    "architectural_discipline": {
        "label": "🏗️ Mimari Disiplin (Katmanlı/DDD)",
        "signals": [
            DirectorySignal(all_of=["**/domain", "**/entities"]),
            DirectorySignal(any_of=["**/usecases", "**/ports", "**/adapters", "**/repositories"]),
        ],
    },
    "api_design": {
        "label": "🔌 API Tasarımı",
        "signals": [
            DependencySignal(any_of=["fastapi", "flask", "django", "express", "tornado", "sanic"]),
            DirectorySignal(any_of=["**/api", "**/routes", "**/routers", "**/endpoints", "api", "routes", "routers"]),
        ],
    },
    "concurrency_safety": {
        "label": "🔀 Eşzamanlılık & Yarış Durumu Güvenliği",
        "signals": [
            DependencySignal(any_of=["celery", "ray", "dask", "gevent", "anyio"]),
            SourcePatternSignal(any_of=["asyncio.gather", "threading.Lock", "multiprocessing"]),
        ],
    },
}


@dataclass
class MatchedCategory:
    """Represents a dynamically matched category and its matching signals."""

    key: str
    label: str
    evidence: list[Any]
    confidence: str = "weak"


@dataclass
class ProjectProfile:
    """Encapsulates profiled dynamic categories and profile signature."""

    dynamic_categories: list[MatchedCategory]
    signature: str
    catalog_version: str
    manifests_found: list[str] = field(default_factory=list)
    profiling_confidence: str = "normal"

    @property
    def matched_categories(self) -> list[MatchedCategory]:
        """Alias for backward compatibility."""
        return self.dynamic_categories


# Alias for backward compatibility
ProfileResult = ProjectProfile


class ProjectProfilerService:
    """Profiles repositories and selects relevant dynamic Layer 2 categories."""

    MAX_DYNAMIC_CATEGORIES = 5

    def _read_all_manifests(self, repo_path: Path) -> dict[str, str]:
        """Reads content of all existing manifests in repo_path."""
        manifests = {}
        for m in MANIFEST_FILES:
            p = repo_path / m
            if p.is_file() and not _is_path_excluded(p, repo_path):
                try:
                    manifests[m] = p.read_text(encoding="utf-8", errors="ignore").lower()
                except OSError as e:
                    logger.warning(f"Failed to read manifest {p}: {e}")
        return manifests

    def _compute_signature(self, selected: list[MatchedCategory]) -> str:
        """Creates a deterministic sha256 signature from sorted category keys."""
        keys = sorted([c.key for c in selected])
        raw = "::".join(keys)
        return hashlib.sha256(raw.encode()).hexdigest()[:8]

    def profile(self, repo_path: Path) -> ProjectProfile:
        """Profiles project against signal catalog to select relevant dynamic categories."""
        manifests = self._read_all_manifests(repo_path)
        matched: list[MatchedCategory] = []

        for key, spec in CATEGORY_CATALOG.items():
            signals: list[Signal] = spec["signals"]
            evidence_items: list[str] = []
            signal_types: set[str] = set()

            for s in signals:
                match_res = s.evaluate(repo_path, manifests)
                if match_res.matched:
                    evidence_items.extend(match_res.evidence)
                    signal_types.add(match_res.signal_type)

            if evidence_items:
                confidence = "strong" if len(signal_types) >= 2 else "weak"
                matched.append(
                    MatchedCategory(
                        key=key,
                        label=str(spec["label"]),
                        evidence=evidence_items,
                        confidence=confidence,
                    )
                )

        ranked = sorted(
            matched,
            key=lambda m: (m.confidence == "strong", len(m.evidence)),
            reverse=True,
        )

        strong = [m for m in ranked if m.confidence == "strong"]
        weak = [m for m in ranked if m.confidence == "weak"]

        if len(strong) >= self.MAX_DYNAMIC_CATEGORIES:
            selected = strong
        else:
            remaining_slots = max(0, self.MAX_DYNAMIC_CATEGORIES - len(strong))
            selected = strong + weak[:remaining_slots]

        profiling_confidence = "normal"
        if not selected and not manifests:
            profiling_confidence = "low_signal_no_manifest"

        return ProjectProfile(
            dynamic_categories=selected,
            signature=self._compute_signature(selected),
            catalog_version=CATALOG_VERSION,
            manifests_found=list(manifests.keys()),
            profiling_confidence=profiling_confidence,
        )

