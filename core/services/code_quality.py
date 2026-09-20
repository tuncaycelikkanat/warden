import json
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.services.shared.loc_counter import count_source_lines
from core.services.shared.scan_exclusions import get_scan_exclusions

logger = logging.getLogger(__name__)


@dataclass
class ComplexityResult:
    """Represents cyclomatic complexity metrics and identified high-complexity files."""
    avg_complexity: float
    high_complexity_files: list[dict[str, Any]]


class CodeComplexityService:
    """Service to measure cyclomatic complexity across Python source files using Radon."""

    async def analyze(self, repo_path: Path) -> ComplexityResult:
        """Runs radon cc to measure cyclomatic complexity."""
        import asyncio

        def run_radon():
            cmd = ["radon", "cc", str(repo_path), "--json", "-a", "-i", "fixtures,test_data", "-e", "*dummy_*"]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                return json.loads(result.stdout)
            except Exception as e:
                logger.error(f"Failed to run radon: {e}")
                return {}

        data = await asyncio.to_thread(run_radon)

        total_complexity = 0
        block_count = 0
        high_complexity_files = []

        for file_path, blocks in data.items():
            if file_path == "error" or not isinstance(blocks, list):
                continue

            file_complexity = sum(b.get("complexity", 0) for b in blocks if "complexity" in b)
            file_blocks = [b for b in blocks if "complexity" in b]

            if file_blocks:
                total_complexity += file_complexity
                block_count += len(file_blocks)

                if (file_complexity / len(file_blocks)) > 10:
                    high_complexity_files.append({"file": file_path, "complexity": file_complexity})

        avg = (total_complexity / block_count) if block_count > 0 else 0.0

        return ComplexityResult(
            avg_complexity=round(avg, 2),
            high_complexity_files=high_complexity_files
        )


@dataclass
class LintIssueDetail:
    """Detailed metadata for a single lint issue."""

    file_path: str
    line: int
    column: int
    code: str
    message: str
    fixable: bool = False
    severity: str = "minor"  # "critical", "major", "minor"


@dataclass
class LintResult:
    """Represents lint and formatting error counts, density, and detailed findings."""

    error_count: int
    issues_by_rule: dict[str, int]
    score: float = 100.0
    measured: bool = True
    reason: str = "measured_successfully"
    project_scoped_count: int = 0
    baseline_count: int = 0
    total_loc: int = 0
    density_per_kloc: float = 0.0
    weighted_density: float = 0.0
    issues: list[LintIssueDetail] = field(default_factory=list)


RUFF_SEVERITY_TIERS = {
    "critical": ("E9", "F821", "F822", "F823", "F811"),
    "major": ("F401", "F841", "B", "S"),
}

TIER_WEIGHTS = {
    "critical": 3.0,
    "major": 1.5,
    "minor": 0.5,
}


class LintStyleService:
    """Service to measure code quality and lint defects via Ruff with dual-config and density normalization."""

    def __init__(self, timeout_sec: int = 45) -> None:
        self.timeout_sec = timeout_sec

    def _resolve_ruff_cmd(self) -> list[str]:
        """Resolves available Ruff executable across PATH, virtualenv, or uv."""
        bin_path = shutil.which("ruff")
        if bin_path:
            return [bin_path]
        venv_bin = Path(sys.executable).parent / "ruff"
        if venv_bin.exists():
            return [str(venv_bin)]
        if shutil.which("uv"):
            return ["uv", "run", "ruff"]
        return []

    def _get_issue_severity(self, code: str) -> str:
        """Determines the severity tier for a given Ruff rule code."""
        for tier, prefixes in RUFF_SEVERITY_TIERS.items():
            if any(code.startswith(prefix) for prefix in prefixes):
                return tier
        return "minor"

    def _calc_weighted_issue_count(self, issues: list[dict[str, Any]]) -> float:
        """Calculates total weighted defects considering severity and fixability."""
        total = 0.0
        for issue in issues:
            code = str(issue.get("code", ""))
            severity = self._get_issue_severity(code)
            weight = TIER_WEIGHTS.get(severity, 0.5)
            if issue.get("fix"):
                weight *= 0.7  # Fixable issues discounted by 30%
            total += weight
        return total

    def _merge_dedup(self, issues1: list[dict[str, Any]], issues2: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Merges issues from project-scoped and baseline scans, removing duplicates."""
        seen: set[tuple[str, int, int, str]] = set()
        combined: list[dict[str, Any]] = []
        for issue in issues1 + issues2:
            loc = issue.get("location") or {}
            key = (
                str(issue.get("filename", "")),
                int(loc.get("row", 0)),
                int(loc.get("column", 0)),
                str(issue.get("code", "")),
            )
            if key not in seen:
                seen.add(key)
                combined.append(issue)
        return combined

    async def analyze(self, repo_path: Path) -> LintResult:
        """Runs dual-config ruff check to find linting, style, and security issues."""
        import asyncio

        ruff_base = self._resolve_ruff_cmd()
        if not ruff_base:
            return LintResult(
                error_count=0,
                issues_by_rule={},
                score=0.0,
                measured=False,
                reason="ruff_binary_not_found",
            )

        exclusions = get_scan_exclusions(
            repo_path,
            extra=["fixtures", "test_data", "tests/fixtures", "tests/test_data", "dummy_*.py"],
        )
        exclude_arg = ",".join(exclusions)

        baseline_config = Path(__file__).resolve().parent.parent / "rules" / "ruff_baseline.toml"

        def run_ruff_scans() -> tuple[bool, str, list[dict[str, Any]], list[dict[str, Any]]]:
            # Run 1: Project-scoped scan
            cmd1 = list(ruff_base) + [
                "check",
                str(repo_path),
                "--output-format=json",
                f"--exclude={exclude_arg}",
            ]
            try:
                res1 = subprocess.run(cmd1, capture_output=True, text=True, timeout=self.timeout_sec, check=False)
                issues_proj = json.loads(res1.stdout) if res1.stdout else []
            except subprocess.TimeoutExpired:
                return False, "project_scan_timed_out", [], []
            except Exception as e:
                return False, f"project_scan_error: {e}", [], []

            # Run 2: WARDEN Baseline scan
            cmd2 = list(ruff_base) + [
                "check",
                str(repo_path),
                "--output-format=json",
                f"--exclude={exclude_arg}",
            ]
            if baseline_config.exists():
                cmd2.append(f"--config={baseline_config}")
            else:
                cmd2.extend(["--select=E9,F821,F822,F823,F811,F401,F841,B,S", "--ignore=S101"])

            try:
                res2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=self.timeout_sec, check=False)
                issues_base = json.loads(res2.stdout) if res2.stdout else []
            except subprocess.TimeoutExpired:
                return False, "baseline_scan_timed_out", [], []
            except Exception as e:
                return False, f"baseline_scan_error: {e}", [], []

            return True, "ok", issues_proj, issues_base

        success, reason, issues_proj, issues_base = await asyncio.to_thread(run_ruff_scans)
        if not success:
            return LintResult(
                error_count=0,
                issues_by_rule={},
                score=0.0,
                measured=False,
                reason=reason,
            )

        combined_raw = self._merge_dedup(issues_proj, issues_base)
        total_loc = await asyncio.to_thread(count_source_lines, repo_path, exclusions)

        # Parse detailed issue findings
        detailed_issues: list[LintIssueDetail] = []
        issues_by_rule: dict[str, int] = {}

        for item in combined_raw:
            code = str(item.get("code", "UNKNOWN"))
            issues_by_rule[code] = issues_by_rule.get(code, 0) + 1

            loc = item.get("location") or {}
            raw_filename = item.get("filename", "")
            try:
                rel_path = str(Path(raw_filename).relative_to(repo_path))
            except Exception:
                rel_path = raw_filename

            detailed_issues.append(
                LintIssueDetail(
                    file_path=rel_path,
                    line=int(loc.get("row", 0)),
                    column=int(loc.get("column", 0)),
                    code=code,
                    message=str(item.get("message", "")),
                    fixable=bool(item.get("fix")),
                    severity=self._get_issue_severity(code),
                )
            )

        error_count = len(combined_raw)

        # Scoring with density normalization
        if total_loc == 0:
            score = 100.0 if error_count == 0 else 50.0
            density = 0.0
            weighted_density = 0.0
        else:
            density = round((error_count / total_loc) * 1000.0, 2)
            weighted_count = self._calc_weighted_issue_count(combined_raw)
            weighted_density = round((weighted_count / total_loc) * 1000.0, 2)
            penalty = min(100.0, weighted_density * 4.0)
            score = round(max(0.0, 100.0 - penalty), 1)

        return LintResult(
            error_count=error_count,
            issues_by_rule=issues_by_rule,
            score=score,
            measured=True,
            reason="measured_successfully",
            project_scoped_count=len(issues_proj),
            baseline_count=len(issues_base),
            total_loc=total_loc,
            density_per_kloc=density,
            weighted_density=weighted_density,
            issues=detailed_issues,
        )
