"""Type safety analyzer utilizing Mypy type checker."""

import logging
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from core.services.shared.scan_exclusions import get_scan_exclusion_pattern
from core.utils.file_discovery import discover_source_files

logger = logging.getLogger(__name__)

MYPY_ERROR_PATTERN = re.compile(
    r"^(?P<file>[^:]+\.py):(?P<line>\d+):(?:\d+:)?\s*error:\s*(?P<message>.+?)(?:\s*\[(?P<code>[\w-]+)\])?$"
)


@dataclass
class MypyError:
    """Represents a single Mypy type-checking finding."""

    file: str
    line: int
    message: str
    code: str


@dataclass
class TypeSafetyResult:
    """Represents Mypy type-checking analysis metrics and error density."""

    score: float | None
    error_count: int
    file_count: int
    error_density: float
    measured: bool = True
    reason: str = "measured_successfully"
    errors: list[MypyError] = field(default_factory=list)


class TypeSafetyService:
    """Service to measure static type consistency and error density using Mypy."""

    def __init__(self, timeout_sec: int = 120) -> None:
        self.timeout_sec = timeout_sec

    def _resolve_mypy_cmd(self) -> list[str]:
        """Resolves available Mypy executable across PATH, virtualenv, or uv."""
        bin_path = shutil.which("mypy")
        if bin_path:
            return [bin_path]
        venv_bin = Path(sys.executable).parent / "mypy"
        if venv_bin.exists():
            return [str(venv_bin)]
        if shutil.which("uv"):
            return ["uv", "run", "mypy"]
        return []

    def _run_mypy(self, repo_path: Path, mypy_base: list[str]) -> subprocess.CompletedProcess[str]:
        """Executes Mypy with strict baseline flags, ignoring local evasive configs."""
        baseline_config = Path(__file__).resolve().parent.parent / "rules" / "mypy_baseline.ini"
        exclusion_pattern = get_scan_exclusion_pattern(
            repo_path,
            extra=["fixtures", "test_data", "tests/fixtures", "tests/test_data", "dummy_"],
        )

        cmd = list(mypy_base) + [
            str(repo_path),
            "--no-error-summary",
            "--ignore-missing-imports",
            "--check-untyped-defs",
            f"--exclude={exclusion_pattern}",
        ]
        if baseline_config.exists():
            cmd.append(f"--config-file={baseline_config}")

        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout_sec,
            check=False,
        )

    def _parse_errors(self, output: str, repo_path: Path) -> list[MypyError]:
        """Extracts structured MypyError objects using strict regex match."""
        errors: list[MypyError] = []
        for line in output.splitlines():
            match = MYPY_ERROR_PATTERN.match(line.strip())
            if match:
                raw_file = match.group("file")
                try:
                    rel_file = str(Path(raw_file).relative_to(repo_path))
                except Exception:
                    rel_file = raw_file

                errors.append(
                    MypyError(
                        file=rel_file,
                        line=int(match.group("line")),
                        message=match.group("message").strip(),
                        code=match.group("code") or "unknown",
                    )
                )
        return errors

    def _score_from_density(self, density: float) -> float:
        """Computes 0-100 score from defect density without an artificial 20-point floor."""
        raw = 100.0 - ((density / 0.5) * 10.0)
        return round(max(0.0, min(100.0, raw)), 1)

    async def analyze(self, repo_path: Path) -> TypeSafetyResult:
        """Runs Mypy against repository source files and computes error density."""
        import asyncio

        def run_analysis() -> TypeSafetyResult:
            files = discover_source_files(repo_path)
            py_files = [f for f in files if f.suffix == ".py"]
            file_count = len(py_files)

            if file_count == 0:
                return TypeSafetyResult(
                    score=None,
                    measured=False,
                    error_count=0,
                    file_count=0,
                    error_density=0.0,
                    reason="no_python_files",
                )

            mypy_base = self._resolve_mypy_cmd()
            if not mypy_base:
                return TypeSafetyResult(
                    score=None,
                    measured=False,
                    error_count=0,
                    file_count=file_count,
                    error_density=0.0,
                    reason="mypy_binary_not_found",
                )

            try:
                res = self._run_mypy(repo_path, mypy_base)
            except subprocess.TimeoutExpired:
                logger.warning(f"Mypy timed out after {self.timeout_sec}s on {repo_path}")
                return TypeSafetyResult(
                    score=None,
                    measured=False,
                    error_count=0,
                    file_count=file_count,
                    error_density=0.0,
                    reason="mypy_execution_timeout",
                )
            except Exception as e:
                logger.warning(f"Failed to run mypy: {e}")
                return TypeSafetyResult(
                    score=None,
                    measured=False,
                    error_count=0,
                    file_count=file_count,
                    error_density=0.0,
                    reason=f"mypy_execution_failed: {e}",
                )

            if res.returncode not in (0, 1):
                logger.warning(f"Mypy returned unexpected exit code {res.returncode}")
                return TypeSafetyResult(
                    score=None,
                    measured=False,
                    error_count=0,
                    file_count=file_count,
                    error_density=0.0,
                    reason=f"mypy_crashed_exit_{res.returncode}",
                )

            output = (res.stdout or "") + "\n" + (res.stderr or "")
            errors = self._parse_errors(output, repo_path)
            error_count = len(errors)
            density = round(error_count / file_count, 3)
            score = self._score_from_density(density)

            return TypeSafetyResult(
                score=score,
                measured=True,
                error_count=error_count,
                file_count=file_count,
                error_density=density,
                reason="measured_successfully",
                errors=errors,
            )

        return await asyncio.to_thread(run_analysis)

