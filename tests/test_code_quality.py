"""Tests for CodeComplexityService and LintStyleService."""

from pathlib import Path
from unittest.mock import patch

import pytest

from core.services.code_quality import (
    CodeComplexityService,
    LintResult,
    LintStyleService,
)
from core.services.scorecard import ScorecardAggregatorService


@pytest.mark.asyncio
async def test_code_complexity_and_lint():
    """Verifies radon and ruff analyzers on current repo."""
    comp_svc = CodeComplexityService()
    comp_res = await comp_svc.analyze(Path("."))
    assert comp_res.avg_complexity >= 0.0
    assert isinstance(comp_res.high_complexity_files, list)

    lint_svc = LintStyleService()
    lint_res = await lint_svc.analyze(Path("."))
    assert lint_res.error_count >= 0
    assert isinstance(lint_res.issues_by_rule, dict)
    assert lint_res.measured is True
    assert 0.0 <= lint_res.score <= 100.0


@pytest.mark.asyncio
async def test_lint_unmeasured_when_binary_missing(tmp_path: Path):
    """When ruff binary cannot be resolved, service returns measured=False rather than silent 100."""
    service = LintStyleService()
    with patch.object(service, "_resolve_ruff_cmd", return_value=[]):
        res: LintResult = await service.analyze(tmp_path)
        assert res.measured is False
        assert res.reason == "ruff_binary_not_found"

    # Verify scorecard redistributes weight instead of giving 100
    sc = ScorecardAggregatorService()
    scores = sc.calculate({"lint": {"measured": False}}, [])
    assert "lint_style_ruff" not in scores.breakdown.get("member_scores", {})


@pytest.mark.asyncio
async def test_dual_config_catches_silenced_rules(tmp_path: Path):
    """Target project silencing all rules in pyproject.toml cannot evade WARDEN's immutable baseline."""
    # Project config explicitly ignores all rules
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[tool.ruff.lint]\n"
        "select = []\n"
        'ignore = ["ALL"]\n'
    )

    # File with obvious defect (unused import)
    code_file = tmp_path / "bad.py"
    code_file.write_text("import sys\nimport os\n\ndef foo(): pass\n")

    service = LintStyleService()
    res: LintResult = await service.analyze(tmp_path)

    assert res.measured is True
    assert res.project_scoped_count == 0  # Project local config silenced everything
    assert res.baseline_count > 0         # WARDEN baseline caught F401
    assert res.error_count > 0            # Overall error count is non-zero
    assert "F401" in res.issues_by_rule


@pytest.mark.asyncio
async def test_centralized_exclusions(tmp_path: Path):
    """Errors inside excluded directories (node_modules, .venv) must be ignored."""
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    (node_modules / "vendor.py").write_text("import non_existent_mod_12345\nx = 1\n")

    venv_dir = tmp_path / ".venv"
    venv_dir.mkdir()
    (venv_dir / "lib_pkg.py").write_text("import another_broken_pkg\ny = 2\n")

    # Clean file in root
    (tmp_path / "app.py").write_text("def ok():\n    return 42\n")

    service = LintStyleService()
    res: LintResult = await service.analyze(tmp_path)

    assert res.measured is True
    # The defects in node_modules and .venv should be excluded
    file_paths = [i.file_path for i in res.issues]
    assert not any("node_modules" in p or ".venv" in p for p in file_paths)


@pytest.mark.asyncio
async def test_density_normalization(tmp_path: Path):
    """Dense defects in a small file get penalized much more than sparse defects in a large file."""
    service = LintStyleService()

    # Small repo: 5 lines, 2 unused imports (very high density)
    small_repo = tmp_path / "small"
    small_repo.mkdir()
    (small_repo / "main.py").write_text("import os\nimport sys\n\n\ndef run():\n    pass\n")

    res_small = await service.analyze(small_repo)

    # Large repo: 1000 lines of valid code with 2 unused imports (very low density)
    large_repo = tmp_path / "large"
    large_repo.mkdir()
    large_lines = ["import os", "import sys", ""] + [f"x_{i} = {i}" for i in range(1000)]
    (large_repo / "main.py").write_text("\n".join(large_lines))

    res_large = await service.analyze(large_repo)

    # Both have the same 2 errors, but density in large repo is much lower
    assert res_small.error_count == res_large.error_count == 2
    assert res_small.density_per_kloc > res_large.density_per_kloc
    assert res_large.score > res_small.score


@pytest.mark.asyncio
async def test_detailed_issue_locations(tmp_path: Path):
    """Detailed metadata like file path, line number, message, and severity must be recorded."""
    (tmp_path / "sample.py").write_text("import sys\n\nx = 1\n")

    service = LintStyleService()
    res: LintResult = await service.analyze(tmp_path)

    assert len(res.issues) > 0
    issue = res.issues[0]
    assert issue.file_path == "sample.py"
    assert issue.line == 1
    assert issue.code == "F401"
    assert "sys" in issue.message.lower()
    assert issue.severity == "major"

