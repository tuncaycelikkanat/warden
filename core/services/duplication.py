"""Service for measuring code duplication using jscpd."""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.services.shared.scan_exclusions import get_duplication_ignore_pattern, is_duplication_excluded

logger = logging.getLogger(__name__)

WARDEN_BASELINE_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "jscpd.warden-baseline.json"


@dataclass
class ClonePair:
    """Represents a pair of duplicated code fragments."""

    first_file: str
    first_start: int
    first_end: int
    second_file: str
    second_start: int
    second_end: int
    lines: int
    fragment: str = ""


@dataclass
class DuplicationResult:
    """Metrics and evidence of duplicate code."""

    measured: bool
    duplication_pct: float | None = None
    duplicated_lines: int = 0
    total_sloc: int = 0
    clone_pairs: list[dict[str, Any]] = field(default_factory=list)
    reason: str | None = None
    note: str | None = None
    engine_used: str = "jscpd"


class DuplicationService:
    """Detects copy-pasted code blocks across Python source files using jscpd."""

    def _resolve_jscpd_cmd(self) -> str | None:
        """Finds executable jscpd binary in system PATH or local node_modules."""
        bin_path = shutil.which("jscpd")
        if bin_path:
            return bin_path

        # Check project-local node_modules
        root_dir = Path(__file__).resolve().parent.parent.parent
        local_bin = root_dir / "node_modules" / ".bin" / "jscpd"
        if local_bin.is_file() and os.access(local_bin, os.X_OK):
            return str(local_bin)

        return None

    def _run_jscpd(self, repo_path: Path, tmp_dir: Path) -> dict[str, Any]:
        """Executes jscpd subprocess with WARDEN's immutable baseline config."""
        jscpd_bin = self._resolve_jscpd_cmd()
        if not jscpd_bin:
            raise FileNotFoundError("jscpd not found in WARDEN's own environment")

        ignore_pattern = get_duplication_ignore_pattern(repo_path)
        cmd = [
            jscpd_bin,
            str(repo_path),
            "--config",
            str(WARDEN_BASELINE_CONFIG_PATH),
            "--reporters",
            "json",
            "--output",
            str(tmp_dir),
            "--ignore",
            ignore_pattern,
            "--silent",
            "--absolute",
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

        report_file = tmp_dir / "jscpd-report.json"
        if not report_file.is_file():
            if result.returncode == 0:
                return {
                    "statistics": {"total": {"lines": 0, "duplicatedLines": 0, "percentage": 0.0}},
                    "duplicates": [],
                }
            raise FileNotFoundError(f"jscpd output report not found (code {result.returncode}): {result.stderr}")

        try:
            return json.loads(report_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(f"Failed to parse jscpd report: {e}", e.doc, e.pos)

    def _build_result(self, report: dict[str, Any], repo_path: Path) -> DuplicationResult:
        """Constructs DuplicationResult from parsed jscpd JSON report."""
        stats = report.get("statistics", {})
        total = stats.get("total", {})
        total_lines = int(total.get("lines", 0))
        duplicated_lines = int(total.get("duplicatedLines", 0))
        duplication_pct = float(total.get("percentage", 0.0))

        if total_lines == 0:
            return DuplicationResult(
                measured=True,
                duplication_pct=0.0,
                duplicated_lines=0,
                total_sloc=0,
                clone_pairs=[],
                note="no_analyzable_files",
                engine_used="jscpd",
            )

        raw_duplicates = report.get("duplicates", [])
        clone_pairs: list[dict[str, Any]] = []

        for dup in raw_duplicates:
            first = dup.get("firstFile", {})
            second = dup.get("secondFile", {})
            first_name = first.get("name", "")
            second_name = second.get("name", "")

            # Exclude boilerplate/generated files if any escaped jscpd ignore
            if is_duplication_excluded(first_name, repo_path) or is_duplication_excluded(second_name, repo_path):
                continue

            lines = int(dup.get("lines", 0))
            fragment = str(dup.get("fragment", "")).strip()
            # truncate fragment for readability in evidence
            if len(fragment) > 200:
                fragment = fragment[:200] + "..."

            clone_pairs.append({
                "first_file": first_name,
                "first_start": first.get("start", 0),
                "first_end": first.get("end", 0),
                "second_file": second_name,
                "second_start": second.get("start", 0),
                "second_end": second.get("end", 0),
                "lines": lines,
                "fragment": fragment,
            })

        return DuplicationResult(
            measured=True,
            duplication_pct=round(duplication_pct, 2),
            duplicated_lines=duplicated_lines,
            total_sloc=total_lines,
            clone_pairs=clone_pairs,
            engine_used="jscpd",
        )

    async def analyze(self, repo_path: Path) -> DuplicationResult:
        """Runs duplication analysis concurrently."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            try:
                report = await asyncio.to_thread(self._run_jscpd, repo_path, tmp_path)
            except subprocess.TimeoutExpired:
                logger.warning("jscpd timed out after 120 seconds")
                return DuplicationResult(measured=False, reason="jscpd_timeout")
            except FileNotFoundError as e:
                logger.warning(f"jscpd could not be found or executed: {e}")
                return DuplicationResult(measured=False, reason="jscpd_not_found")
            except json.JSONDecodeError as e:
                logger.warning(f"jscpd report could not be parsed: {e}")
                return DuplicationResult(measured=False, reason="jscpd_report_parse_error")
            except Exception as e:
                logger.warning(f"jscpd failed with error: {e}")
                return DuplicationResult(measured=False, reason=f"jscpd_execution_failed: {e}")

            return self._build_result(report, repo_path)
