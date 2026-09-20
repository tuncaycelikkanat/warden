"""Test coverage analyzer via Coverage.py and documentation analyzer via Interrogate."""

import json
import logging
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from core.infra.sandboxed_executor import SandboxedTestExecutor

logger = logging.getLogger(__name__)

IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    ".tox",
    "__pycache__",
    ".idea",
    ".vscode",
}

COVERAGE_OMIT_PATTERNS = "tests/*,test/*,*/tests/*,*/test/*,fixtures/*,*/fixtures/*,venv/*,.venv/*"


@dataclass
class CoverageResult:
    """Represents test execution coverage percentage."""

    measured: bool
    coverage_pct: float | None
    has_tests: bool = True
    reason: str = "measured_successfully"
    detail: str = ""
    isolation_level: str = "os_limits"


class TestCoverageAnalyzerService:
    """Service to measure line and branch test coverage via Coverage.py and pytest."""

    __test__ = False

    def __init__(
        self,
        executor: SandboxedTestExecutor | None = None,
        timeout_sec: int = 60,
    ) -> None:
        self.executor = executor or SandboxedTestExecutor()
        self.timeout_sec = timeout_sec

    def _discover_test_files(self, repo_path: Path) -> list[Path]:
        """Discovers test files across tests/, test/, or module-adjacent test files."""
        test_files: list[Path] = []
        try:
            for p in repo_path.rglob("*.py"):
                rel = p.relative_to(repo_path)
                if any(part in IGNORE_DIRS or part.startswith(".") for part in rel.parts[:-1]):
                    continue
                rel_parts_lower = [part.lower() for part in rel.parts]
                if (
                    "tests" in rel_parts_lower[:-1]
                    or "test" in rel_parts_lower[:-1]
                    or p.name.startswith("test_")
                    or p.name.endswith("_test.py")
                ):
                    test_files.append(p)
        except Exception as e:
            logger.warning(f"Error discovering test files in {repo_path}: {e}")
        return test_files

    def _get_pytest_targets(self, repo_path: Path, test_files: list[Path]) -> list[str]:
        """Resolves target paths to pass to pytest."""
        if (repo_path / "tests").is_dir():
            return ["tests"]
        if (repo_path / "test").is_dir():
            return ["test"]
        parent_dirs = {str(f.parent.relative_to(repo_path)) for f in test_files}
        return sorted(parent_dirs) if parent_dirs else ["."]

    def _determine_source(self, repo_path: Path) -> str:
        """Determines the primary source directory for coverage measurement."""
        for candidate in ("src", "core", "app"):
            if (repo_path / candidate).is_dir():
                return candidate
        return "."

    def _get_cov_base(self) -> list[str]:
        """Resolves coverage executable based on environment."""
        if self.executor.is_docker_available():
            return ["coverage"]
        return [sys.executable, "-m", "coverage"]

    def _build_cov_run_cmd(
        self,
        repo_path: Path,
        cov_base: list[str],
        targets: list[str],
    ) -> list[str]:
        """Constructs coverage run command with branch coverage and path isolation."""
        cov_rc = repo_path / ".coveragerc"
        cmd = list(cov_base) + ["run", "--branch"]

        if cov_rc.exists():
            cmd.extend(["--rcfile", str(cov_rc)])
        else:
            source = self._determine_source(repo_path)
            cmd.extend([f"--source={source}", f"--omit={COVERAGE_OMIT_PATTERNS}"])

        cmd.extend(["-m", "pytest", "-q"])

        # Ignore fixtures directories
        for fix in ("tests/fixtures", "test/fixtures", "fixtures"):
            if (repo_path / fix).exists():
                cmd.append(f"--ignore={fix}")

        cmd.extend(targets)
        return cmd

    async def analyze(self, repo_path: Path) -> CoverageResult:
        """Runs sandboxed coverage to get the test coverage percentage."""
        test_files = self._discover_test_files(repo_path)
        if not test_files:
            return CoverageResult(
                measured=True,
                coverage_pct=0.0,
                has_tests=False,
                reason="no_test_files_found",
                detail="No test files found in repository",
            )

        targets = self._get_pytest_targets(repo_path, test_files)
        cov_base = self._get_cov_base()
        cov_run_cmd = self._build_cov_run_cmd(repo_path, cov_base, targets)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            cov_db_path = temp_dir_path / ".coverage"
            cov_json_path = temp_dir_path / "coverage.json"

            python_path = str(repo_path)
            if (repo_path / "src").is_dir():
                python_path = f"{repo_path}:{repo_path / 'src'}"

            env = {
                "COVERAGE_FILE": str(cov_db_path),
                "PYTHONPATH": python_path,
            }

            run_res = await self.executor.run_command(
                cov_run_cmd,
                cwd=repo_path,
                env=env,
                timeout_sec=self.timeout_sec,
                temp_dir=temp_dir_path,
            )

            if run_res.timed_out:
                return CoverageResult(
                    measured=False,
                    coverage_pct=None,
                    has_tests=True,
                    reason="execution_timeout",
                    detail=run_res.stderr or f"Execution timed out after {self.timeout_sec}s",
                    isolation_level=run_res.isolation_level,
                )

            if run_res.had_collection_errors:
                return CoverageResult(
                    measured=False,
                    coverage_pct=None,
                    has_tests=True,
                    reason="collection_error",
                    detail=run_res.collection_error_summary or run_res.stderr,
                    isolation_level=run_res.isolation_level,
                )

            if not cov_db_path.exists():
                return CoverageResult(
                    measured=False,
                    coverage_pct=None,
                    has_tests=True,
                    reason="no_coverage_data",
                    detail=run_res.stderr or run_res.stdout,
                    isolation_level=run_res.isolation_level,
                )

            # Generate JSON report
            cov_rc = repo_path / ".coveragerc"
            cov_json_cmd = list(cov_base) + ["json", "-o", str(cov_json_path)]
            if cov_rc.exists():
                cov_json_cmd.extend(["--rcfile", str(cov_rc)])

            json_res = await self.executor.run_command(
                cov_json_cmd,
                cwd=repo_path,
                env=env,
                timeout_sec=15,
                temp_dir=temp_dir_path,
            )

            if not cov_json_path.exists():
                return CoverageResult(
                    measured=False,
                    coverage_pct=None,
                    has_tests=True,
                    reason="coverage_report_failed",
                    detail=json_res.stderr or "Failed to generate coverage JSON",
                    isolation_level=run_res.isolation_level,
                )

            try:
                data = json.loads(cov_json_path.read_text(encoding="utf-8"))
                pct = float(data.get("totals", {}).get("percent_covered", 0.0))
                return CoverageResult(
                    measured=True,
                    coverage_pct=round(pct, 1),
                    has_tests=True,
                    reason="measured_successfully",
                    isolation_level=run_res.isolation_level,
                )
            except Exception as e:
                logger.warning(f"Failed to parse coverage JSON: {e}")
                return CoverageResult(
                    measured=False,
                    coverage_pct=None,
                    has_tests=True,
                    reason="parse_error",
                    detail=str(e),
                    isolation_level=run_res.isolation_level,
                )


@dataclass
class DocumentationResult:
    """Represents docstring coverage percentage and README completeness."""
    docstring_coverage_pct: float
    has_readme_setup_section: bool
    has_readme_usage_section: bool


class DocumentationAnalyzerService:
    """Service to evaluate docstring coverage via Interrogate and README structure."""

    async def analyze(self, repo_path: Path) -> DocumentationResult:
        """Analyzes docstring coverage and README contents."""
        import asyncio

        def run_interrogate():
            try:
                inter_bin = shutil.which("interrogate")
                inter_base = [inter_bin] if inter_bin else ["uv", "run", "interrogate"]

                cmd = list(inter_base) + [
                    "-v",
                    "-e", "node_modules", "-e", "vscode-extension",
                    "-e", "fixtures", "-e", "test_data", "-e", "tests",
                    "-i", "-I", "-s",
                    "--ignore-regex", ".*dummy.*",
                    "."
                ]
                res = subprocess.run(cmd, cwd=str(repo_path), capture_output=True, text=True, check=False)
                for line in res.stdout.splitlines():
                    if "actual:" in line:
                        # e.g., "RESULT: FAILED (minimum: 80.0%, actual: 21.2%)"
                        import re
                        match = re.search(r"actual:\s*([\d\.]+)%", line)
                        if match:
                            return float(match.group(1))
                return 0.0
            except Exception as e:
                logger.warning(f"Failed to run interrogate: {e}")
                return 0.0
                
        def check_readme():
            readme_files = list(repo_path.glob("README*"))
            has_setup = False
            has_usage = False
            if readme_files:
                content = readme_files[0].read_text().lower()
                if "install" in content or "kurulum" in content or "setup" in content:
                    has_setup = True
                if "usage" in content or "kullanım" in content:
                    has_usage = True
            return has_setup, has_usage

        doc_pct = await asyncio.to_thread(run_interrogate)
        has_setup, has_usage = await asyncio.to_thread(check_readme)
        
        return DocumentationResult(
            docstring_coverage_pct=doc_pct,
            has_readme_setup_section=has_setup,
            has_readme_usage_section=has_usage
        )
