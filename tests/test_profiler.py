"""Tests for ProjectProfilerService and architectural signals."""

from pathlib import Path

from core.services.profiler import (
    DependencySignal,
    MatchedCategory,
    ProjectProfilerService,
)


def test_profiler_current_repo():
    """Verifies profile execution and signature generation on current repo."""
    profiler = ProjectProfilerService()
    profile = profiler.profile(Path("."))

    assert len(profile.signature) == 8
    assert len(profile.dynamic_categories) >= 1
    assert "pyproject.toml" in profile.manifests_found or "requirements.txt" in profile.manifests_found
    assert profile.profiling_confidence == "normal"


def test_profiler_pyproject_toml_manifest(tmp_path: Path):
    """Verifies that pyproject.toml alone triggers api_design and llm_integration."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("""
[project]
name = "my-ai-service"
version = "0.1.0"
dependencies = [
    "fastapi>=0.110.0",
    "anthropic>=0.20.0"
]
""")

    profiler = ProjectProfilerService()
    profile = profiler.profile(tmp_path)

    keys = [c.key for c in profile.dynamic_categories]
    assert "api_design" in keys
    assert "llm_integration" in keys
    assert "pyproject.toml" in profile.manifests_found


def test_profiler_package_json_frontend(tmp_path: Path):
    """Verifies that package.json triggers frontend_ux."""
    pkg = tmp_path / "package.json"
    pkg.write_text("""{
  "name": "my-frontend-app",
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  }
}""")

    profiler = ProjectProfilerService()
    profile = profiler.profile(tmp_path)

    keys = [c.key for c in profile.dynamic_categories]
    assert "frontend_ux" in keys
    assert "package.json" in profile.manifests_found


def test_substring_false_positive_prevention(tmp_path: Path):
    """Verifies that 'pytest-reactor' or 'reaction-diffusion' does not trigger react."""
    req = tmp_path / "requirements.txt"
    req.write_text("pytest-reactor==1.2.0\nreaction-diffusion==0.1.0\n")

    dep_signal = DependencySignal(any_of=["react"])
    assert dep_signal.matches(tmp_path) is False

    profiler = ProjectProfilerService()
    profile = profiler.profile(tmp_path)
    keys = [c.key for c in profile.dynamic_categories]
    assert "frontend_ux" not in keys


def test_scan_exclusion_in_profiler(tmp_path: Path):
    """Verifies that .venv or test fixtures with threading.Lock do not trigger concurrency_safety."""
    venv_dir = tmp_path / ".venv" / "site-packages" / "external_pkg"
    venv_dir.mkdir(parents=True, exist_ok=True)
    (venv_dir / "worker.py").write_text("import threading\nlock = threading.Lock()\n")

    profiler = ProjectProfilerService()
    profile = profiler.profile(tmp_path)
    keys = [c.key for c in profile.dynamic_categories]
    assert "concurrency_safety" not in keys


def test_zero_signal_ambiguity_flag(tmp_path: Path):
    """Verifies that repo with no manifests and no matching signals is flagged as low_signal_no_manifest."""
    (tmp_path / "notes.txt").write_text("just some random text")

    profiler = ProjectProfilerService()
    profile = profiler.profile(tmp_path)

    assert len(profile.dynamic_categories) == 0
    assert len(profile.manifests_found) == 0
    assert profile.profiling_confidence == "low_signal_no_manifest"


def test_strong_vs_weak_confidence(tmp_path: Path):
    """Verifies that category with 2+ distinct signal types is marked 'strong' while 1 is 'weak'."""
    # Add dependency for api_design (only 1 signal type: dependency) -> weak
    # Add dependency AND directory for llm_integration (dependency + directory) -> strong
    req = tmp_path / "requirements.txt"
    req.write_text("fastapi==0.110.0\nopenai==1.12.0\n")
    (tmp_path / "prompts").mkdir(parents=True, exist_ok=True)

    profiler = ProjectProfilerService()
    profile = profiler.profile(tmp_path)

    cat_map = {c.key: c for c in profile.dynamic_categories}
    assert "llm_integration" in cat_map
    assert "api_design" in cat_map

    assert cat_map["llm_integration"].confidence == "strong"
    assert cat_map["api_design"].confidence == "weak"


def test_multidisciplinary_project_no_pruning_of_strong(tmp_path: Path):
    """Verifies that 6 strong categories are all preserved and not arbitrarily pruned to 5."""
    req = tmp_path / "requirements.txt"
    req.write_text("""
fastapi==0.110.0
anthropic==0.20.0
numba==0.59.0
celery==5.3.0
""")
    # 1. frontend_ux: package.json + 5 tsx files (dependency + file_pattern)
    (tmp_path / "package.json").write_text('{"dependencies": {"react": "^18.0.0"}}')
    for i in range(5):
        (tmp_path / f"Component_{i}.tsx").write_text("export const C = () => null;")

    # 2. devops_deployment: Dockerfile + deploy directory (file_pattern + directory)
    (tmp_path / "Dockerfile").write_text("FROM python:3.12")
    (tmp_path / "deploy").mkdir(parents=True, exist_ok=True)

    # 3. quantitative_logic: numba + backtesting directory (dependency + directory)
    (tmp_path / "backtesting").mkdir(parents=True, exist_ok=True)

    # 4. llm_integration: anthropic + prompts directory (dependency + directory)
    (tmp_path / "prompts").mkdir(parents=True, exist_ok=True)

    # 5. api_design: fastapi + api directory (dependency + directory)
    (tmp_path / "api").mkdir(parents=True, exist_ok=True)

    # 6. concurrency_safety: celery + asyncio.gather source code (dependency + source_pattern)
    (tmp_path / "worker.py").write_text("import asyncio\nasync def run(): await asyncio.gather()\n")

    profiler = ProjectProfilerService()
    profile = profiler.profile(tmp_path)

    strong_categories = [c for c in profile.dynamic_categories if c.confidence == "strong"]
    # All 6 strong categories should be preserved (pruning limit of 5 is safely bypassed for strong categories)
    assert len(strong_categories) == 6
    assert len(profile.dynamic_categories) == 6


def test_deterministic_signature_reproducibility():
    """Verifies that identical categories produce identical signatures deterministically."""
    profiler = ProjectProfilerService()
    cats_a = [
        MatchedCategory(key="api_design", label="API", evidence=["e1"]),
        MatchedCategory(key="devops_deployment", label="DevOps", evidence=["e2"]),
    ]
    cats_b = [
        MatchedCategory(key="devops_deployment", label="DevOps", evidence=["e2"]),
        MatchedCategory(key="api_design", label="API", evidence=["e1"]),
    ]
    sig_a = profiler._compute_signature(cats_a)
    sig_b = profiler._compute_signature(cats_b)

    assert sig_a == sig_b
    assert len(sig_a) == 8


def test_directory_collision_prevention(tmp_path: Path):
    """Verifies that 'db/query_optimization' does not falsely trigger quantitative_logic."""
    query_opt_dir = tmp_path / "db" / "query_optimization"
    query_opt_dir.mkdir(parents=True, exist_ok=True)

    profiler = ProjectProfilerService()
    profile = profiler.profile(tmp_path)

    keys = [c.key for c in profile.dynamic_categories]
    assert "quantitative_logic" not in keys


def test_directory_signal_all_of(tmp_path: Path):
    from core.services.profiler import DirectorySignal

    d1 = tmp_path / "routes"
    d1.mkdir()
    d2 = tmp_path / "controllers"
    d2.mkdir()

    sig = DirectorySignal(all_of=["routes", "controllers"])
    match = sig.evaluate(tmp_path, {})
    assert match.matched is True
    assert len(match.evidence) == 2

    # If one is missing
    sig_missing = DirectorySignal(all_of=["routes", "missing_dir"])
    assert sig_missing.evaluate(tmp_path, {}).matched is False


def test_source_pattern_signal_oserror(tmp_path: Path):
    from unittest.mock import patch
    from core.services.profiler import SourcePatternSignal

    f = tmp_path / "test.py"
    f.write_text("pattern_here")

    sig = SourcePatternSignal(any_of=["pattern_here"])
    # Normal match
    assert sig.evaluate(tmp_path, {}).matched is True

    # OSError on read_text
    with patch("pathlib.Path.read_text", side_effect=OSError("Permission denied")):
        match = sig.evaluate(tmp_path, {})
        assert match.matched is False


