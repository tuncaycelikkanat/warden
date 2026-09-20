import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.services.shared.loc_counter import count_source_lines
from core.services.shared.scan_exclusions import get_scan_exclusions, is_generated_file

logger = logging.getLogger(__name__)


@dataclass
class ComplexityResult:
    """Represents cyclomatic complexity metrics and identified high-complexity files."""

    measured: bool = True
    avg_complexity: float = 0.0
    rank_distribution: dict[str, int] = field(default_factory=lambda: {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0})
    outlier_blocks: list[dict[str, Any]] = field(default_factory=list)
    high_complexity_files: list[dict[str, Any]] = field(default_factory=list)
    file_count: int = 0
    generated_files_excluded: list[str] = field(default_factory=list)
    reason: str | None = None
    note: str | None = None
    score: float | None = None


RANK_THRESHOLDS: dict[str, int] = {"C": 11, "D": 21, "E": 31, "F": 41}
RANK_PENALTY_WEIGHT: dict[str, float] = {"C": 1.0, "D": 2.5, "E": 4.0, "F": 6.0}


class CodeComplexityService:
    """Service to measure cyclomatic complexity across Python source files using Radon."""

    def _resolve_radon_cmd(self, repo_path: Path) -> list[str]:
        """Resolves executable command for running radon."""
        radon_bin = shutil.which("radon")
        if radon_bin:
            return [radon_bin]

        venv_radon = Path(sys.prefix) / "bin" / "radon"
        if venv_radon.is_file() and os.access(venv_radon, os.X_OK):
            return [str(venv_radon)]

        for venv_name in [".venv", "venv"]:
            cand = repo_path / venv_name / "bin" / "radon"
            if cand.is_file() and os.access(cand, os.X_OK):
                return [str(cand)]

        uv_bin = shutil.which("uv")
        if uv_bin:
            return [uv_bin, "run", "radon"]

        import importlib.util

        if importlib.util.find_spec("radon") is not None:
            return [sys.executable, "-m", "radon"]

        raise FileNotFoundError("radon not found in WARDEN's own environment")

    def _run_radon(self, repo_path: Path) -> str:
        """Executes radon subprocess with centralized exclusions and timeout."""
        cmd_prefix = self._resolve_radon_cmd(repo_path)
        ignore_dirs = ",".join(get_scan_exclusions(repo_path))
        exclude_globs = "*dummy_*,*_pb2.py,*.g.py"

        cmd = [
            *cmd_prefix,
            "cc",
            str(repo_path),
            "--json",
            "-a",
            "-i",
            ignore_dirs,
            "-e",
            exclude_globs,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        if result.returncode not in (0,):
            logger.warning(f"radon exited with code {result.returncode}: {result.stderr}")
        return result.stdout

    def _cc_to_rank(self, cc: int) -> str:
        """Maps numeric cyclomatic complexity to letter rank."""
        if cc <= 5:
            return "A"
        if cc <= 10:
            return "B"
        if cc <= 20:
            return "C"
        if cc <= 30:
            return "D"
        if cc <= 40:
            return "E"
        return "F"

    def _build_result(self, parsed: dict[str, Any], repo_path: Path) -> ComplexityResult:
        """Constructs ComplexityResult with rank distributions and outlier blocks."""
        rank_distribution: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0}
        outlier_blocks: list[dict[str, Any]] = []
        high_complexity_files: list[dict[str, Any]] = []
        generated_files_excluded: list[str] = []
        total_complexity = 0
        total_blocks = 0
        analyzed_file_count = 0

        for file_path, blocks in parsed.items():
            if file_path == "error" or not isinstance(blocks, list):
                continue

            # Check if generated file
            is_gen, _ = is_generated_file(file_path, repo_path)
            if is_gen:
                generated_files_excluded.append(file_path)
                continue

            analyzed_file_count += 1
            file_complexity = 0
            file_blocks_count = 0

            for b in blocks:
                if not isinstance(b, dict) or "complexity" not in b:
                    continue
                cc = int(b.get("complexity", 0))
                rank = b.get("rank") or self._cc_to_rank(cc)
                if rank in rank_distribution:
                    rank_distribution[rank] += 1
                else:
                    rank_distribution[self._cc_to_rank(cc)] += 1

                total_complexity += cc
                total_blocks += 1
                file_complexity += cc
                file_blocks_count += 1

                if cc >= RANK_THRESHOLDS["C"]:
                    outlier_blocks.append({
                        "file": file_path,
                        "function": b.get("name", "unknown"),
                        "line": b.get("lineno", 0),
                        "complexity": cc,
                        "rank": rank,
                    })

            if file_blocks_count > 0:
                if any(b.get("complexity", 0) >= RANK_THRESHOLDS["C"] for b in blocks if isinstance(b, dict)) or (file_complexity / file_blocks_count) > 10:
                    high_complexity_files.append({"file": file_path, "complexity": file_complexity})

        avg = round(total_complexity / total_blocks, 2) if total_blocks > 0 else 0.0
        note = "no_analyzable_blocks" if total_blocks == 0 else None

        return ComplexityResult(
            measured=True,
            avg_complexity=avg,
            rank_distribution=rank_distribution,
            outlier_blocks=outlier_blocks,
            high_complexity_files=high_complexity_files,
            file_count=analyzed_file_count,
            generated_files_excluded=generated_files_excluded,
            note=note,
        )

    async def analyze(self, repo_path: Path) -> ComplexityResult:
        """Runs radon cc to measure cyclomatic complexity."""
        try:
            raw_output = await asyncio.to_thread(self._run_radon, repo_path)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning(f"radon could not be executed: {e}")
            return ComplexityResult(measured=False, reason=f"radon_execution_failed: {e}")

        try:
            parsed = json.loads(raw_output)
        except json.JSONDecodeError as e:
            logger.warning(f"radon output could not be parsed: {e}")
            return ComplexityResult(measured=False, reason="radon_json_parse_error")

        return self._build_result(parsed, repo_path)


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
