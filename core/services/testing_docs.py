"""Test coverage analyzer via Coverage.py and documentation analyzer via Interrogate."""

import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from core.infra.sandboxed_executor import SandboxedTestExecutor
from core.services.shared.scan_exclusions import (
    get_interrogate_exclude_args,
    is_duplication_excluded,
    is_lockfile_or_vendor,
)
from core.utils.file_discovery import discover_source_files

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


WARDEN_BASELINE_INTERROGATE_CONFIG = (
    Path(__file__).resolve().parent.parent.parent / "config" / "interrogate.warden-baseline.toml"
)
EXTERNAL_DOCS_PATTERN = re.compile(
    r"(readthedocs\.io|docs\.[\w-]+\.\w+|\.github\.io/|mkdocs|sphinx|gitbook\.io|notion\.site)",
    re.IGNORECASE,
)
NEGATION_MARKERS = {"not", "no", "değil", "degil", "gerekmez", "yok", "without", "doesn't", "don't", "yet"}


@dataclass
class DocumentationResult:
    """Represents docstring coverage percentage and README completeness."""

    measured: bool = True
    docstring_coverage_pct: float | None = None
    has_readme_setup_section: bool = False
    has_readme_usage_section: bool = False
    readme_links_external_docs: bool = False
    reason: str | None = None


class DocumentationAnalyzerService:
    """Service to evaluate docstring coverage via Interrogate and README structure."""

    def _resolve_interrogate_cmd(self) -> list[str] | None:
        """Resolves interrogate binary or execution wrapper."""
        which_inter = shutil.which("interrogate")
        if which_inter:
            return [which_inter]

        venv_inter = Path(".venv/bin/interrogate")
        if venv_inter.is_file():
            return [str(venv_inter.resolve())]

        # Try python module
        try:
            check_mod = subprocess.run(
                [sys.executable, "-m", "interrogate", "--help"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if check_mod.returncode == 0:
                return [sys.executable, "-m", "interrogate"]
        except Exception:
            pass

        # Try uv run
        if shutil.which("uv"):
            return ["uv", "run", "interrogate"]

        return None

    def _has_positive_mention(self, content: str, keywords: list[str]) -> bool:
        """Checks if keywords appear in positive context, rejecting negated occurrences."""
        words = re.findall(r"[\w]+", content.lower())
        for i, word in enumerate(words):
            if any(kw in word for kw in keywords):
                start = max(0, i - 4)
                end = min(len(words), i + 5)
                window = words[start:end]
                if not any(marker in window for marker in NEGATION_MARKERS):
                    return True
        return False

    def _check_readme(self, repo_path: Path) -> tuple[bool, bool, bool]:
        """Checks for README file, external docs links, and positive setup/usage mentions."""
        readme_candidates = [
            f for f in repo_path.iterdir()
            if f.is_file() and f.name.lower().startswith("readme")
        ] if repo_path.is_dir() else []

        if not readme_candidates:
            return False, False, False

        readme_file = min(readme_candidates)
        try:
            content = readme_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return False, False, False

        # 1. External docs link detection (ReadTheDocs, Sphinx, MkDocs, etc.)
        links_external = bool(EXTERNAL_DOCS_PATTERN.search(content))
        if links_external:
            return True, True, True

        # 2. Setup & Usage with negation awareness
        has_setup = self._has_positive_mention(content, ["install", "kurulum", "setup"])
        has_usage = self._has_positive_mention(content, ["usage", "kullanım", "kullanim"])

        return has_setup, has_usage, False

    def _has_python_files(self, repo_path: Path) -> bool:
        """Checks if the repository contains at least one non-excluded Python file."""
        all_files = discover_source_files(repo_path)
        for f in all_files:
            if f.suffix != ".py":
                continue
            rel_str = str(f.relative_to(repo_path)) if f.is_relative_to(repo_path) else str(f)
            if is_lockfile_or_vendor(rel_str, repo_path) or is_duplication_excluded(rel_str, repo_path):
                continue
            return True
        return False

    def _run_interrogate(self, repo_path: Path) -> tuple[float | None, bool, str | None]:
        """Executes interrogate with baseline config and centralized exclusions."""
        cmd_base = self._resolve_interrogate_cmd()
        if not cmd_base:
            return None, False, "interrogate_not_found"

        cmd = list(cmd_base) + ["-v"]

        # Override project's pyproject.toml [tool.interrogate] with WARDEN baseline config
        if WARDEN_BASELINE_INTERROGATE_CONFIG.is_file():
            cmd.extend(["-c", str(WARDEN_BASELINE_INTERROGATE_CONFIG)])

        # Centralized exclusions
        cmd.extend(get_interrogate_exclude_args(repo_path))

        # Standard baseline flags
        cmd.extend(["-i", "-I", "-s", "--ignore-regex", ".*dummy.*", "."])

        try:
            res = subprocess.run(
                cmd,
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return None, False, "interrogate_timeout"
        except Exception as e:
            logger.warning("Failed to run interrogate: %s", e)
            return None, False, "interrogate_not_found"

        for line in res.stdout.splitlines():
            if "actual:" in line:
                match = re.search(r"actual:\s*([\d.]+)%", line)
                if match:
                    return float(match.group(1)), True, None

        if "no files to display" in res.stdout.lower() or "passed" in res.stdout.lower():
            return 100.0, True, None

        return None, False, "interrogate_output_unparseable"

    async def analyze(self, repo_path: Path) -> DocumentationResult:
        """Analyzes docstring coverage and README contents."""
        import asyncio

        has_setup, has_usage, links_ext = await asyncio.to_thread(self._check_readme, repo_path)

        # Check if Python files exist
        has_py = await asyncio.to_thread(self._has_python_files, repo_path)
        if not has_py:
            return DocumentationResult(
                measured=False,
                docstring_coverage_pct=None,
                has_readme_setup_section=has_setup,
                has_readme_usage_section=has_usage,
                readme_links_external_docs=links_ext,
                reason="no_python_files",
            )

        doc_pct, measured, reason = await asyncio.to_thread(self._run_interrogate, repo_path)
        if not measured:
            return DocumentationResult(
                measured=False,
                docstring_coverage_pct=None,
                has_readme_setup_section=has_setup,
                has_readme_usage_section=has_usage,
                readme_links_external_docs=links_ext,
                reason=reason,
            )

        return DocumentationResult(
            measured=True,
            docstring_coverage_pct=doc_pct,
            has_readme_setup_section=has_setup,
            has_readme_usage_section=has_usage,
            readme_links_external_docs=links_ext,
            reason=None,
        )
