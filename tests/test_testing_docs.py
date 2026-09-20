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
    # Create a minimal README
    readme = tmp_path / "README.md"
    readme.write_text("# Project\n\n## Installation\nrun pip install\n\n## Usage\nrun python main.py")

    # Create a python file with docstring
    py_file = tmp_path / "hello.py"
    py_file.write_text('"""Hello module."""\n\ndef greet():\n    """Greet user."""\n    return "hello"\n')

    service = DocumentationAnalyzerService()
    res: DocumentationResult = await service.analyze(tmp_path)

    assert res.has_readme_setup_section is True
    assert res.has_readme_usage_section is True
    assert res.docstring_coverage_pct >= 0.0
