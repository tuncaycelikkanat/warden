"""Lightweight sandboxed execution engine for tests with OS resource limits, timeouts, and Docker fallback."""

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SandboxedRunResult:
    """Represents the execution outcome of a sandboxed command."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    had_collection_errors: bool = False
    collection_error_summary: str = ""
    isolation_level: str = "os_limits"  # "docker", "os_limits", "none"


class SandboxedTestExecutor:
    """Executes test commands inside Docker or with OS resource limits and timeouts."""

    def __init__(self, docker_image: str = "warden-test-runner:latest") -> None:
        self.docker_image = docker_image
        self._docker_checked = False
        self._docker_is_available = False

    def is_docker_available(self) -> bool:
        """Verifies if Docker daemon is running and responsive."""
        if self._docker_checked:
            return self._docker_is_available

        self._docker_checked = True
        docker_bin = shutil.which("docker")
        if not docker_bin:
            self._docker_is_available = False
            return False

        try:
            res = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=2,
                check=False,
            )
            if res.returncode == 0:
                # Check if test runner image exists
                img_check = subprocess.run(
                    ["docker", "image", "inspect", self.docker_image],
                    capture_output=True,
                    timeout=2,
                    check=False,
                )
                self._docker_is_available = (img_check.returncode == 0)
            else:
                self._docker_is_available = False
        except Exception:
            self._docker_is_available = False

        return self._docker_is_available

    def _check_collection_errors(self, exit_code: int, stdout: str, stderr: str) -> tuple[bool, str]:
        """Detects if pytest failed during test collection (import or syntax errors)."""
        combined = f"{stdout}\n{stderr}"

        # Pytest ExitCode 2 typically signifies collection failure or CLI usage error
        has_collection_err = (
            "ERROR collecting" in combined
            or "Errors during collection" in combined
            or "collection failed" in combined
            or (exit_code == 2 and ("ImportError" in combined or "ModuleNotFoundError" in combined))
        )

        if has_collection_err:
            lines = [
                line.strip()
                for line in combined.splitlines()
                if any(k in line for k in ("ERROR collecting", "ImportError", "ModuleNotFoundError", "SyntaxError"))
            ]
            summary = "; ".join(lines[:3]) if lines else "Pytest collection error"
            return True, summary

        return False, ""

    async def run_command(
        self,
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
        timeout_sec: int = 60,
        temp_dir: Path | None = None,
    ) -> SandboxedRunResult:
        """Runs command via Docker container if available, otherwise with OS limits."""
        import asyncio

        if self.is_docker_available():
            return await asyncio.to_thread(self._run_in_docker, cmd, cwd, env, timeout_sec, temp_dir)
        return await asyncio.to_thread(self._run_with_os_limits, cmd, cwd, env, timeout_sec)

    def _run_in_docker(
        self,
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None,
        timeout_sec: int,
        temp_dir: Path | None = None,
    ) -> SandboxedRunResult:
        """Executes test command inside a hardened Docker container."""
        abs_cwd = str(cwd.resolve())
        docker_cmd = [
            "docker", "run", "--rm",
            "--network=none",
            "--memory=512m",
            "--cpus=1.0",
            "--read-only",
            "-v", f"{abs_cwd}:/repo:ro",
            "--tmpfs", "/tmp",
            "-w", "/repo",
        ]

        if temp_dir:
            docker_cmd.extend(["-v", f"{temp_dir.resolve()}:/cov_tmp:rw"])

        if env:
            for k, v in env.items():
                if k == "COVERAGE_FILE" and temp_dir:
                    docker_cmd.extend(["-e", f"COVERAGE_FILE=/cov_tmp/{Path(v).name}"])
                elif k in ("COVERAGE_FILE", "PYTHONPATH"):
                    docker_cmd.extend(["-e", f"{k}={v}"])

        docker_cmd.append(self.docker_image)
        docker_cmd.extend(cmd)

        try:
            res = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
            had_coll, coll_summary = self._check_collection_errors(res.returncode, res.stdout, res.stderr)
            return SandboxedRunResult(
                exit_code=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
                timed_out=False,
                had_collection_errors=had_coll,
                collection_error_summary=coll_summary,
                isolation_level="docker",
            )
        except subprocess.TimeoutExpired:
            return SandboxedRunResult(
                exit_code=-1,
                stdout="",
                stderr=f"Test execution timed out after {timeout_sec}s in Docker",
                timed_out=True,
                isolation_level="docker",
            )
        except Exception as e:
            logger.warning(f"Docker execution failed, falling back to OS limits: {e}")
            return self._run_with_os_limits(cmd, cwd, env, timeout_sec)

    def _run_with_os_limits(
        self,
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None,
        timeout_sec: int,
    ) -> SandboxedRunResult:
        """Executes command with process limits and strict timeout on host."""
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        def _set_resource_limits() -> None:
            try:
                import resource
                # 2GB virtual memory ceiling
                mem_bytes = 2 * 1024 * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            except Exception:
                pass

        try:
            res = subprocess.run(
                cmd,
                cwd=str(cwd),
                env=run_env,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                preexec_fn=_set_resource_limits if os.name != "nt" else None,
                check=False,
            )
            had_coll, coll_summary = self._check_collection_errors(res.returncode, res.stdout, res.stderr)
            return SandboxedRunResult(
                exit_code=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
                timed_out=False,
                had_collection_errors=had_coll,
                collection_error_summary=coll_summary,
                isolation_level="os_limits",
            )
        except subprocess.TimeoutExpired as te:
            stdout_str = te.stdout.decode() if isinstance(te.stdout, bytes) else str(te.stdout or "")
            stderr_str = te.stderr.decode() if isinstance(te.stderr, bytes) else str(te.stderr or "")
            return SandboxedRunResult(
                exit_code=-1,
                stdout=stdout_str,
                stderr=f"Test execution timed out after {timeout_sec}s: {stderr_str}",
                timed_out=True,
                isolation_level="os_limits",
            )
        except Exception as e:
            return SandboxedRunResult(
                exit_code=-1,
                stdout="",
                stderr=f"Process execution error: {e}",
                timed_out=False,
                isolation_level="os_limits",
            )
