"""Unit tests for SandboxedTestExecutor verifying OS limits, Docker fallback, and timeout isolation."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from core.infra.sandboxed_executor import SandboxedTestExecutor


def test_is_docker_available_no_binary():
    executor = SandboxedTestExecutor()
    with patch("shutil.which", return_value=None):
        assert executor.is_docker_available() is False
        # Cached result check
        assert executor.is_docker_available() is False


def test_is_docker_available_daemon_down():
    executor = SandboxedTestExecutor()
    with patch("shutil.which", return_value="/usr/bin/docker"), \
         patch("subprocess.run", return_value=MagicMock(returncode=1)):
        assert executor.is_docker_available() is False


def test_is_docker_available_image_missing():
    executor = SandboxedTestExecutor()
    # First call: docker info succeeds (returncode=0), second call: image inspect fails (returncode=1)
    mock_info = MagicMock(returncode=0)
    mock_inspect = MagicMock(returncode=1)
    with patch("shutil.which", return_value="/usr/bin/docker"), \
         patch("subprocess.run", side_effect=[mock_info, mock_inspect]):
        assert executor.is_docker_available() is False


def test_is_docker_available_success():
    executor = SandboxedTestExecutor()
    mock_info = MagicMock(returncode=0)
    mock_inspect = MagicMock(returncode=0)
    with patch("shutil.which", return_value="/usr/bin/docker"), \
         patch("subprocess.run", side_effect=[mock_info, mock_inspect]):
        assert executor.is_docker_available() is True


def test_is_docker_available_exception():
    executor = SandboxedTestExecutor()
    with patch("shutil.which", return_value="/usr/bin/docker"), \
         patch("subprocess.run", side_effect=Exception("Docker crashed")):
        assert executor.is_docker_available() is False


def test_check_collection_errors():
    executor = SandboxedTestExecutor()

    # 1. ERROR collecting
    has_err, summary = executor._check_collection_errors(
        1, "ERROR collecting tests/test_foo.py\nImportError: No module named 'bar'", ""
    )
    assert has_err is True
    assert "ERROR collecting" in summary or "ImportError" in summary

    # 2. Exit code 2 with ModuleNotFoundError
    has_err2, summary2 = executor._check_collection_errors(
        2, "", "ModuleNotFoundError: No module named 'baz'"
    )
    assert has_err2 is True
    assert "ModuleNotFoundError" in summary2

    # 3. Clean run
    has_err3, summary3 = executor._check_collection_errors(0, "All tests passed", "")
    assert has_err3 is False
    assert summary3 == ""


@pytest.mark.asyncio
async def test_run_command_os_limits_success(tmp_path):
    executor = SandboxedTestExecutor()
    # Execute simple echo command with env
    res = await executor.run_command(["echo", "hello_warden"], cwd=tmp_path, env={"MY_TEST_VAR": "1"}, timeout_sec=5)
    assert res.exit_code == 0
    assert "hello_warden" in res.stdout
    assert res.timed_out is False
    assert res.isolation_level == "os_limits"


@pytest.mark.asyncio
async def test_run_command_os_limits_timeout(tmp_path):
    executor = SandboxedTestExecutor()
    # Command that sleeps longer than timeout
    res = await executor.run_command(["sleep", "2"], cwd=tmp_path, timeout_sec=1)
    assert res.exit_code == -1
    assert res.timed_out is True
    assert "timed out" in res.stderr.lower()


@pytest.mark.asyncio
async def test_run_command_os_limits_exception(tmp_path):
    executor = SandboxedTestExecutor()
    with patch("subprocess.run", side_effect=OSError("Command not found")):
        res = await executor.run_command(["nonexistent_executable_123"], cwd=tmp_path)
        assert res.exit_code == -1
        assert "Process execution error" in res.stderr


@pytest.mark.asyncio
async def test_run_command_in_docker_success(tmp_path):
    executor = SandboxedTestExecutor()
    executor._docker_checked = True
    executor._docker_is_available = True

    mock_run = MagicMock(returncode=0, stdout="Docker test passed", stderr="")
    with patch("subprocess.run", return_value=mock_run):
        res = await executor.run_command(
            ["pytest"],
            cwd=tmp_path,
            env={"COVERAGE_FILE": str(tmp_path / ".coverage"), "PYTHONPATH": "/repo"},
            temp_dir=tmp_path,
            timeout_sec=30,
        )
        assert res.exit_code == 0
        assert res.isolation_level == "docker"
        assert res.stdout == "Docker test passed"


@pytest.mark.asyncio
async def test_run_command_in_docker_timeout(tmp_path):
    executor = SandboxedTestExecutor()
    executor._docker_checked = True
    executor._docker_is_available = True

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=10)):
        res = await executor.run_command(["pytest"], cwd=tmp_path, timeout_sec=10)
        assert res.exit_code == -1
        assert res.timed_out is True
        assert res.isolation_level == "docker"


@pytest.mark.asyncio
async def test_run_command_in_docker_fallback_to_os(tmp_path):
    executor = SandboxedTestExecutor()
    executor._docker_checked = True
    executor._docker_is_available = True

    # Docker execution raises an unexpected Exception, should fall back to os limits
    call_count = 0

    def mock_subprocess(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Docker daemon exploded")
        return MagicMock(returncode=0, stdout="os fallback executed", stderr="")

    with patch("subprocess.run", side_effect=mock_subprocess):
        res = await executor.run_command(["pytest"], cwd=tmp_path)
        assert res.exit_code == 0
        assert res.isolation_level == "os_limits"
        assert res.stdout == "os fallback executed"
