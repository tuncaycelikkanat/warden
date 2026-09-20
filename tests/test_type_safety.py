from pathlib import Path
from unittest.mock import patch

import pytest

from core.services.scorecard import ScorecardAggregatorService
from core.services.type_safety import TypeSafetyResult, TypeSafetyService


@pytest.mark.asyncio
async def test_type_safety_on_current_repo():
    """Runs type safety analyzer on WARDEN repo itself."""
    service = TypeSafetyService()
    res = await service.analyze(Path("."))

    assert res.measured is True
    assert res.score is not None
    assert 0.0 <= res.score <= 100.0
    assert res.file_count > 0


@pytest.mark.asyncio
async def test_type_safety_no_python_files(tmp_path: Path):
    """Empty folder returns measured=False with no_python_files reason."""
    service = TypeSafetyService()
    res: TypeSafetyResult = await service.analyze(tmp_path)

    assert res.measured is False
    assert res.score is None
    assert res.reason == "no_python_files"


@pytest.mark.asyncio
async def test_type_safety_binary_missing(tmp_path: Path):
    """When mypy binary is unavailable, returns measured=False, NOT silent 100."""
    (tmp_path / "hello.py").write_text("x: int = 1\n")
    service = TypeSafetyService()
    with patch.object(service, "_resolve_mypy_cmd", return_value=[]):
        res: TypeSafetyResult = await service.analyze(tmp_path)
        assert res.measured is False
        assert res.score is None
        assert res.reason == "mypy_binary_not_found"


@pytest.mark.asyncio
async def test_mypy_crash_returns_unmeasured(tmp_path: Path):
    """A syntax error causes Mypy to crash (exit code 2), returning measured=False, NOT 100."""
    (tmp_path / "broken.py").write_text("def broken_syntax(\n")

    service = TypeSafetyService()
    res: TypeSafetyResult = await service.analyze(tmp_path)

    assert res.measured is False
    assert res.score is None
    assert "mypy_crashed_exit_2" in res.reason

    # Verify scorecard redistributes weight instead of giving 100
    sc = ScorecardAggregatorService()
    scores = sc.calculate({"type_safety": None}, [])
    assert "type_safety" not in scores.breakdown.get("member_scores", {})


@pytest.mark.asyncio
async def test_untyped_code_paradox_detected(tmp_path: Path):
    """Untyped function with invalid operations must be caught via --check-untyped-defs."""
    (tmp_path / "untyped.py").write_text(
        "def compute():\n"
        "    x = 'text' + 123\n"
        "    return x\n"
    )

    service = TypeSafetyService()
    res: TypeSafetyResult = await service.analyze(tmp_path)

    assert res.measured is True
    assert res.error_count > 0
    assert res.score is not None
    assert res.score < 100.0


@pytest.mark.asyncio
async def test_config_evasion_ignored(tmp_path: Path):
    """Target project configuring ignore_errors = true cannot bypass WARDEN baseline."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[tool.mypy]\n"
        "ignore_errors = true\n"
    )

    (tmp_path / "typed_err.py").write_text(
        "def greet(name: str) -> int:\n"
        "    return name\n"
    )

    service = TypeSafetyService()
    res: TypeSafetyResult = await service.analyze(tmp_path)

    assert res.measured is True
    assert res.error_count > 0
    assert any(e.code == "return-value" for e in res.errors)


@pytest.mark.asyncio
async def test_error_string_in_docstring_not_false_positive(tmp_path: Path):
    """Lines containing 'error:' in comments or strings must not be falsely parsed as type defects."""
    (tmp_path / "clean.py").write_text(
        '"""This module handles error: network error properly."""\n\n'
        'def add(a: int, b: int) -> int:\n'
        '    # error: ignore this comment\n'
        '    return a + b\n'
    )

    service = TypeSafetyService()
    res: TypeSafetyResult = await service.analyze(tmp_path)

    assert res.measured is True
    assert res.error_count == 0
    assert res.score == 100.0

