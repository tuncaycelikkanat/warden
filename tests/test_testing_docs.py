"""Unit tests for TestCoverageAnalyzerService and DocumentationAnalyzerService."""

from pathlib import Path

import pytest

from core.services.testing_docs import (
    CoverageResult,
    DocumentationAnalyzerService,
    DocumentationResult,
    TestCoverageAnalyzerService,
)


@pytest.mark.asyncio
async def test_coverage_analyzer_nonexistent_tests(tmp_path: Path):
    """Zero test files must be measured as 0.0% coverage, NOT unmeasured."""
    service = TestCoverageAnalyzerService()
    res: CoverageResult = await service.analyze(tmp_path)
    assert res.measured is True
    assert res.coverage_pct == 0.0
    assert res.has_tests is False
    assert res.reason == "no_test_files_found"


@pytest.mark.asyncio
async def test_coverage_singular_test_directory(tmp_path: Path):
    """Test discovery in 'test/' directory with tempfile isolation."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "calc.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

    test_dir = tmp_path / "test"
    test_dir.mkdir()
    (test_dir / "test_calc.py").write_text(
        "from calc import add\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n"
    )

    service = TestCoverageAnalyzerService()
    res: CoverageResult = await service.analyze(tmp_path)

    assert res.measured is True
    assert res.has_tests is True
    assert res.coverage_pct is not None
    assert res.coverage_pct > 0.0
    assert res.reason == "measured_successfully"

    # Verify no coverage files left in target repository
    assert not (tmp_path / ".coverage").exists()
    assert not (tmp_path / "coverage.json").exists()


@pytest.mark.asyncio
async def test_coverage_collection_error(tmp_path: Path):
    """Collection error (broken imports) returns unmeasured state."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_broken.py").write_text("import non_existent_mystery_lib_xyz\n\ndef test_dummy(): pass\n")

    service = TestCoverageAnalyzerService()
    res: CoverageResult = await service.analyze(tmp_path)

    assert res.measured is False
    assert res.coverage_pct is None
    assert res.has_tests is True
    assert res.reason == "collection_error"
    assert "non_existent_mystery_lib_xyz" in res.detail or "collection error" in res.detail.lower()


@pytest.mark.asyncio
async def test_coverage_execution_timeout(tmp_path: Path):
    """Long-running or hanging tests trigger execution_timeout."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sleep.py").write_text("import time\n\ndef test_hang():\n    time.sleep(3)\n")

    service = TestCoverageAnalyzerService(timeout_sec=1)
    res: CoverageResult = await service.analyze(tmp_path)

    assert res.measured is False
    assert res.coverage_pct is None
    assert res.reason == "execution_timeout"


@pytest.mark.asyncio
async def test_documentation_analyzer(tmp_path: Path):
    """Test documentation analyzer on a directory with README and simple python file."""
    readme = tmp_path / "README.md"
    readme.write_text("# Project\n\n## Installation\nrun pip install\n\n## Usage\nrun python main.py")

    py_file = tmp_path / "hello.py"
    py_file.write_text('"""Hello module."""\n\ndef greet():\n    """Greet user."""\n    return "hello"\n')

    service = DocumentationAnalyzerService()
    res: DocumentationResult = await service.analyze(tmp_path)

    assert res.measured is True
    assert res.has_readme_setup_section is True
    assert res.has_readme_usage_section is True
    assert res.docstring_coverage_pct is not None
    assert res.docstring_coverage_pct >= 0.0


@pytest.mark.asyncio
async def test_docs_interrogate_missing_unmeasured(tmp_path: Path):
    """When interrogate binary is not found, measured=False with clear reason is returned."""
    from unittest.mock import patch

    (tmp_path / "main.py").write_text("def run(): pass\n")
    service = DocumentationAnalyzerService()

    with patch.object(service, "_resolve_interrogate_cmd", return_value=None):
        res = await service.analyze(tmp_path)
        assert res.measured is False
        assert res.reason == "interrogate_not_found"
        assert res.docstring_coverage_pct is None


@pytest.mark.asyncio
async def test_docs_non_python_repo_unmeasured(tmp_path: Path):
    """Repos with no Python files are marked unmeasured rather than falsely 0% docstring."""
    (tmp_path / "Dockerfile").write_text("FROM alpine\n")
    (tmp_path / "README.md").write_text("# Infra\nSetup and usage guide\n")

    service = DocumentationAnalyzerService()
    res = await service.analyze(tmp_path)

    assert res.measured is False
    assert res.reason == "no_python_files"
    assert res.docstring_coverage_pct is None
    # README checks should still be captured
    assert res.has_readme_setup_section is True
    assert res.has_readme_usage_section is True


@pytest.mark.asyncio
async def test_docs_negation_readme_not_matched(tmp_path: Path):
    """Negated mentions such as 'kurulum gerekmez' or 'usage is not documented' do not count as positive."""
    (tmp_path / "main.py").write_text('"""Main."""\ndef f(): pass\n')
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Minimal Lib\n"
        "Bu proje herhangi bir kurulum gerektirmez.\n"
        "Usage is not yet documented.\n"
    )

    service = DocumentationAnalyzerService()
    res = await service.analyze(tmp_path)

    assert res.has_readme_setup_section is False
    assert res.has_readme_usage_section is False


@pytest.mark.asyncio
async def test_docs_external_docs_link_full_score(tmp_path: Path):
    """README pointing to external documentation site (ReadTheDocs, etc.) is awarded full setup/usage."""
    (tmp_path / "main.py").write_text('"""Main."""\ndef f(): pass\n')
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Enterprise SDK\n\n"
        "Welcome! Complete API documentation and quickstart guides are hosted at:\n"
        "https://warden-sdk.readthedocs.io/en/latest/\n"
    )

    service = DocumentationAnalyzerService()
    res = await service.analyze(tmp_path)

    assert res.readme_links_external_docs is True
    assert res.has_readme_setup_section is True
    assert res.has_readme_usage_section is True


@pytest.mark.asyncio
async def test_docs_interrogate_timeout_unmeasured(tmp_path: Path):
    """Timeout during interrogate returns measured=False rather than hanging or returning 0."""
    import subprocess
    from unittest.mock import patch

    (tmp_path / "main.py").write_text("def run(): pass\n")
    service = DocumentationAnalyzerService()

    with patch.object(
        subprocess,
        "run",
        side_effect=subprocess.TimeoutExpired(cmd=["interrogate"], timeout=60),
    ):
        res = await service.analyze(tmp_path)
        assert res.measured is False
        assert res.reason == "interrogate_timeout"


def test_docs_scorecard_unmeasured_weight_redistributed():
    """ScorecardAggregatorService omits unmeasured documentation so group weight is redistributed."""
    from core.services.scorecard import ScorecardAggregatorService

    sc = ScorecardAggregatorService()
    scores = sc.calculate({"docs": {"measured": False}}, [])
    assert "documentation" not in scores.breakdown.get("member_scores", {})


def test_resolve_interrogate_cmd_fallbacks():
    import shutil
    import subprocess
    from unittest.mock import MagicMock, patch

    svc = DocumentationAnalyzerService()

    # 1. which finds interrogate
    with patch("shutil.which", side_effect=lambda x: "/bin/interrogate" if x == "interrogate" else None):
        assert svc._resolve_interrogate_cmd() == ["/bin/interrogate"]

    # 2. python -m interrogate
    with patch("shutil.which", return_value=None), \
         patch("pathlib.Path.is_file", return_value=False), \
         patch("subprocess.run", return_value=MagicMock(returncode=0)):
        res = svc._resolve_interrogate_cmd()
        assert res is not None
        assert "-m" in res and "interrogate" in res

    # 3. uv run interrogate
    with patch("shutil.which", side_effect=lambda x: "/bin/uv" if x == "uv" else None), \
         patch("pathlib.Path.is_file", return_value=False), \
         patch("subprocess.run", return_value=MagicMock(returncode=1)):
        assert svc._resolve_interrogate_cmd() == ["uv", "run", "interrogate"]

    # 4. Nothing found
    with patch("shutil.which", return_value=None), \
         patch("pathlib.Path.is_file", return_value=False), \
         patch("subprocess.run", return_value=MagicMock(returncode=1)):
        assert svc._resolve_interrogate_cmd() is None


@pytest.mark.asyncio
async def test_docs_interrogate_unparseable_and_no_files(tmp_path: Path):
    from unittest.mock import MagicMock, patch

    (tmp_path / "app.py").write_text("print(1)")
    svc = DocumentationAnalyzerService()

    # "No files to display" -> 100.0%
    mock_run1 = MagicMock(stdout="No files to display!")
    with patch("subprocess.run", return_value=mock_run1):
        cov, measured, reason = svc._run_interrogate(tmp_path)
        assert cov == 100.0
        assert measured is True

    # Unparseable output
    mock_run2 = MagicMock(stdout="Some garbage text without actual percentage")
    with patch("subprocess.run", return_value=mock_run2):
        cov2, measured2, reason2 = svc._run_interrogate(tmp_path)
        assert cov2 is None
        assert measured2 is False
        assert reason2 == "interrogate_output_unparseable"

    # Generic exception
    with patch("subprocess.run", side_effect=OSError("Interrogate crashed")):
        cov3, measured3, reason3 = svc._run_interrogate(tmp_path)
        assert measured3 is False
        assert reason3 == "interrogate_not_found"


@pytest.mark.asyncio
async def test_coverage_analyzer_timeout_and_error(tmp_path: Path):
    from unittest.mock import AsyncMock, patch
    from core.infra.sandboxed_executor import SandboxedRunResult

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_ok(): assert True")

    svc = TestCoverageAnalyzerService()

    # Timeout in executor
    timeout_result = SandboxedRunResult(exit_code=-1, stdout="", stderr="timed out", timed_out=True)
    with patch.object(svc.executor, "run_command", new_callable=AsyncMock, return_value=timeout_result):
        res = await svc.analyze(tmp_path)
        assert res.measured is False
        assert res.reason == "execution_timeout"

    # Exit without creating coverage db
    exit_result = SandboxedRunResult(exit_code=1, stdout="", stderr="failed")
    with patch.object(svc.executor, "run_command", new_callable=AsyncMock, return_value=exit_result):
        res2 = await svc.analyze(tmp_path)
        assert res2.measured is False
        assert res2.reason == "no_coverage_data"


