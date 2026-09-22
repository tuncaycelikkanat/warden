"""Comprehensive unit tests for TypeSafetyService."""
from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch
import pytest

from core.services.type_safety import TypeSafetyService, TypeSafetyResult


def test_resolve_mypy_cmd_fallbacks(tmp_path: Path):
    analyzer = TypeSafetyService()

    # Case 1: shutil.which('mypy') succeeds
    with patch("shutil.which", side_effect=lambda name: "/usr/bin/mypy" if name == "mypy" else None):
        cmd = analyzer._resolve_mypy_cmd()
        assert cmd == ["/usr/bin/mypy"]

    # Case 2: venv binary exists
    with patch("shutil.which", return_value=None):
        with patch.object(Path, "exists", return_value=True):
            cmd = analyzer._resolve_mypy_cmd()
            assert len(cmd) == 1
            assert cmd[0].endswith("mypy")

    # Case 3: uv is available
    with patch("shutil.which", side_effect=lambda name: "/usr/bin/uv" if name == "uv" else None):
        with patch.object(Path, "exists", return_value=False):
            cmd = analyzer._resolve_mypy_cmd()
            assert cmd == ["uv", "run", "mypy"]

    # Case 4: Nothing is available
    with patch("shutil.which", return_value=None):
        with patch.object(Path, "exists", return_value=False):
            cmd = analyzer._resolve_mypy_cmd()
            assert cmd == []


@pytest.mark.asyncio
async def test_type_safety_analyzer_timeout_and_exceptions(tmp_path: Path):
    analyzer = TypeSafetyService(timeout_sec=5)
    (tmp_path / "app.py").write_text("x: int = 1\n", encoding="utf-8")

    with patch.object(analyzer, "_resolve_mypy_cmd", return_value=["mypy"]):
        # Test TimeoutExpired
        with patch.object(analyzer, "_run_mypy", side_effect=subprocess.TimeoutExpired(cmd=["mypy"], timeout=5)):
            res = await analyzer.analyze(tmp_path)
            assert res.measured is False
            assert res.reason == "mypy_execution_timeout"

        # Test generic Exception
        with patch.object(analyzer, "_run_mypy", side_effect=RuntimeError("Subprocess crash")):
            res = await analyzer.analyze(tmp_path)
            assert res.measured is False
            assert "mypy_execution_failed" in (res.reason or "")

        # Test unexpected exit code (e.g. 2 for usage error)
        proc_mock = MagicMock(returncode=2, stdout="Usage error", stderr="")
        with patch.object(analyzer, "_run_mypy", return_value=proc_mock):
            res = await analyzer.analyze(tmp_path)
            assert res.measured is False
            assert "mypy_crashed_exit_2" in (res.reason or "")


@pytest.mark.asyncio
async def test_type_safety_analyzer_binary_not_found(tmp_path: Path):
    analyzer = TypeSafetyService()
    (tmp_path / "mod.py").write_text("a = 1", encoding="utf-8")
    with patch.object(analyzer, "_resolve_mypy_cmd", return_value=[]):
        res = await analyzer.analyze(tmp_path)
        assert res.measured is False
        assert res.reason == "mypy_binary_not_found"
