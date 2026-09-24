"""Comprehensive tests for TestCoverageAnalyzerService and DocumentationAnalyzerService edge cases."""
from pathlib import Path
from unittest.mock import patch

import pytest

from core.infra.sandboxed_executor import SandboxedRunResult
from core.services.testing_docs import (
    DocumentationAnalyzerService,
    TestCoverageAnalyzerService,
)


def test_discover_test_files_error_and_targets(tmp_path: Path):
    analyzer = TestCoverageAnalyzerService()

    # Exception during discovery
    with patch.object(Path, "rglob", side_effect=PermissionError("Permission denied")):
        files = analyzer._discover_test_files(tmp_path)
        assert files == []

    # Target resolution when no tests/ or test/ directory exists
    file1 = tmp_path / "custom_test" / "test_a.py"
    file1.parent.mkdir(parents=True, exist_ok=True)
    file1.touch()
    targets = analyzer._get_pytest_targets(tmp_path, [file1])
    assert targets == ["custom_test"]

    # When no test files exist at all
    assert analyzer._get_pytest_targets(tmp_path, []) == ["."]


def test_determine_source_and_cov_base(tmp_path: Path):
    analyzer = TestCoverageAnalyzerService()

    # Source candidate 'core'
    (tmp_path / "core").mkdir()
    assert analyzer._determine_source(tmp_path) == "core"

    # Docker available cov base
    with patch.object(analyzer.executor, "is_docker_available", return_value=True):
        assert analyzer._get_cov_base() == ["coverage"]


def test_build_cov_run_cmd_with_coveragerc_and_fixtures(tmp_path: Path):
    analyzer = TestCoverageAnalyzerService()
    (tmp_path / ".coveragerc").write_text("[run]\nbranch = True\n")
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)

    cmd = analyzer._build_cov_run_cmd(tmp_path, ["coverage"], ["tests"])
    assert "--rcfile" in cmd
    assert any("--ignore=tests/fixtures" in c for c in cmd)


def test_check_readme_edge_cases(tmp_path: Path):
    doc_analyzer = DocumentationAnalyzerService()

    # External docs link detection
    readme = tmp_path / "README.md"
    readme.write_text("Documentation available at https://myproject.readthedocs.io/en/latest/")
    has_setup, has_usage, is_ext = doc_analyzer._check_readme(tmp_path)
    assert has_setup is True
    assert has_usage is True
    assert is_ext is True

    # OSError on read_text
    with patch.object(Path, "read_text", side_effect=OSError("Read failure")):
        assert doc_analyzer._check_readme(tmp_path) == (False, False, False)


def test_has_python_files_edge_cases(tmp_path: Path):
    doc_analyzer = DocumentationAnalyzerService()

    # Create non-python file and vendor lockfile
    (tmp_path / "main.txt").write_text("not python")
    (tmp_path / "poetry.lock").write_text("lockfile")
    assert doc_analyzer._has_python_files(tmp_path) is False

    # Create real python file
    (tmp_path / "app.py").write_text("print('hello')")
    assert doc_analyzer._has_python_files(tmp_path) is True


@pytest.mark.asyncio
async def test_run_coverage_rcfile_and_missing_json(tmp_path: Path):
    analyzer = TestCoverageAnalyzerService()
    test_file = tmp_path / "tests" / "test_dummy.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_ok(): pass\n")
    (tmp_path / ".coveragerc").write_text("[run]\n")

    async def fake_run_command(cmd, cwd, env, timeout_sec, temp_dir):
        if "run" in cmd:
            # Create .coverage db file
            Path(env["COVERAGE_FILE"]).touch()
            return SandboxedRunResult(exit_code=0, stdout="passed", stderr="", isolation_level="host")
        # For json command, do NOT create json file
        return SandboxedRunResult(exit_code=1, stdout="", stderr="Error generating json", isolation_level="host")

    with patch.object(analyzer.executor, "run_command", side_effect=fake_run_command):
        res = await analyzer.analyze(tmp_path)
        assert res.measured is False
        assert res.reason == "coverage_report_failed"


@pytest.mark.asyncio
async def test_run_coverage_corrupt_json(tmp_path: Path):
    analyzer = TestCoverageAnalyzerService()
    test_file = tmp_path / "tests" / "test_dummy.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_ok(): pass\n")

    async def fake_run_command(cmd, cwd, env, timeout_sec, temp_dir):
        if "run" in cmd:
            Path(env["COVERAGE_FILE"]).touch()
            return SandboxedRunResult(exit_code=0, stdout="passed", stderr="", isolation_level="host")
        # For json command, create invalid JSON
        (temp_dir / "coverage.json").write_text("corrupted {json")
        return SandboxedRunResult(exit_code=0, stdout="", stderr="", isolation_level="host")

    with patch.object(analyzer.executor, "run_command", side_effect=fake_run_command):
        res = await analyzer.analyze(tmp_path)
        assert res.measured is False
        assert res.reason == "parse_error"
