import hashlib
from dataclasses import dataclass
from pathlib import Path

from core.utils.file_discovery import discover_source_files


@dataclass
class Signal:
    def matches(self, repo_path: Path) -> bool:
        raise NotImplementedError

class DependencySignal(Signal):
    def __init__(self, any_of: list[str]):
        self.any_of = any_of
        
    def matches(self, repo_path: Path) -> bool:
        req_file = repo_path / "requirements.txt"
        if not req_file.exists():
            return False
        content = req_file.read_text().lower()
        for dep in self.any_of:
            # simple check, can be improved with regex
            if dep.lower() in content:
                return True
        return False

class DirectorySignal(Signal):
    def __init__(self, any_of: list[str] | None = None, all_of: list[str] | None = None):
        self.any_of = any_of or []
        self.all_of = all_of or []
        
    def matches(self, repo_path: Path) -> bool:
        if self.any_of:
            for pattern in self.any_of:
                if list(repo_path.glob(pattern)):
                    return True
            return False
        if self.all_of:
            for pattern in self.all_of:
                if not list(repo_path.glob(pattern)):
                    return False
            return True
        return False

class FilePatternSignal(Signal):
    def __init__(self, any_of: list[str], min_count: int = 1):
        self.any_of = any_of
        self.min_count = min_count
        
    def matches(self, repo_path: Path) -> bool:
        count = 0
        for pattern in self.any_of:
            count += len(list(repo_path.glob(pattern)))
        return count >= self.min_count

class SourcePatternSignal(Signal):
    def __init__(self, any_of: list[str]):
        self.any_of = any_of
        
    def matches(self, repo_path: Path) -> bool:
        files = discover_source_files(repo_path)
        for f in files:
            try:
                content = f.read_text(encoding="utf-8")
                for pattern in self.any_of:
                    if pattern in content:
                        return True
            except Exception:
                continue
        return False

CATALOG_VERSION = "v1.0"

CATEGORY_CATALOG = {
    "frontend_ux": {
        "label": "💻 Frontend & Kullanıcı Deneyimi",
        "signals": [
            DependencySignal(any_of=["react", "vue", "svelte", "next"]),
            FilePatternSignal(any_of=["**/*.tsx", "**/*.vue"], min_count=5),
        ],
    },
    "devops_deployment": {
        "label": "🚀 DevOps & Dağıtım",
        "signals": [FilePatternSignal(any_of=["Dockerfile", "docker-compose*.yml", "fly.toml", "render.yaml"])],
    },
    "quantitative_logic": {
        "label": "📈 Kantitatif & Matematiksel Mantık",
        "signals": [
            DependencySignal(any_of=["numba", "scipy", "optuna", "pandas-ta"]),
            DirectorySignal(any_of=["**/backtesting", "**/optimization", "**/backtesting/", "**/optimization/"]),
        ],
    },
    "llm_integration": {
        "label": "🤖 LLM Entegrasyonu & Prompt Güvenliği",
        "signals": [
            DependencySignal(any_of=["anthropic", "openai", "google-genai", "ollama"]),
            DirectorySignal(any_of=["**/agents", "**/prompts", "**/agents/", "**/prompts/"]),
        ],
    },
    "architectural_discipline": {
        "label": "🏗️ Mimari Disiplin (Katmanlı/DDD)",
        "signals": [DirectorySignal(all_of=["**/domain", "**/entities", "**/domain/", "**/entities/"])],
    },
    "api_design": {
        "label": "🔌 API Tasarımı",
        "signals": [DependencySignal(any_of=["fastapi", "flask", "django", "express"])],
    },
    "concurrency_safety": {
        "label": "🔀 Eşzamanlılık & Yarış Durumu Güvenliği",
        "signals": [SourcePatternSignal(any_of=["asyncio.gather", "threading.Lock", "multiprocessing"])],
    },
}

@dataclass
class MatchedCategory:
    key: str
    label: str
    evidence: list[Signal]

@dataclass
class ProjectProfile:
    dynamic_categories: list[MatchedCategory]
    signature: str
    catalog_version: str

class ProjectProfilerService:
    MAX_DYNAMIC_CATEGORIES = 5

    def profile(self, repo_path: Path) -> ProjectProfile:
        matched = []
        for key, spec in CATEGORY_CATALOG.items():
            hits = [s for s in spec["signals"] if s.matches(repo_path)]
            if hits:
                matched.append(MatchedCategory(key=key, label=spec["label"], evidence=hits))

        # Sort by number of evidence hits
        matched.sort(key=lambda m: len(m.evidence), reverse=True)
        selected = matched[: self.MAX_DYNAMIC_CATEGORIES]

        return ProjectProfile(
            dynamic_categories=selected,
            signature=self._compute_signature(selected),
            catalog_version=CATALOG_VERSION,
        )
        
    def _compute_signature(self, selected: list[MatchedCategory]) -> str:
        # Create a deterministic string from selected category keys
        keys = sorted([c.key for c in selected])
        raw = "::".join(keys)
        return hashlib.sha256(raw.encode()).hexdigest()[:8]
