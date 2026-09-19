import json
import subprocess
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class CoverageResult:
    measured: bool
    coverage_pct: Optional[float]

class TestCoverageAnalyzerService:
    async def analyze(self, repo_path: Path) -> CoverageResult:
        """Runs coverage to get the test coverage percentage."""
        import asyncio
        
        def run_coverage():
            # Only run if there is a pytest or tests directory, otherwise it might fail.
            if not (repo_path / "tests").exists():
                return None
                
            # Run coverage. We run pytest through coverage.
            try:
                # We do not fail if tests fail, we just want coverage.
                subprocess.run(["coverage", "run", "-m", "pytest"], cwd=str(repo_path), capture_output=True, check=False)
                
                # Generate json output
                subprocess.run(["coverage", "json", "-o", "coverage.json"], cwd=str(repo_path), capture_output=True, check=False)
                
                cov_file = repo_path / "coverage.json"
                if cov_file.exists():
                    data = json.loads(cov_file.read_text())
                    return data.get("totals", {}).get("percent_covered", 0.0)
                return None
            except Exception as e:
                logger.warning(f"Failed to measure coverage: {e}")
                return None

        pct = await asyncio.to_thread(run_coverage)
        if pct is None:
            return CoverageResult(measured=False, coverage_pct=None)
        return CoverageResult(measured=True, coverage_pct=round(pct, 1))

@dataclass
class DocumentationResult:
    docstring_coverage_pct: float
    has_readme_setup_section: bool
    has_readme_usage_section: bool

class DocumentationAnalyzerService:
    async def analyze(self, repo_path: Path) -> DocumentationResult:
        """Analyzes docstring coverage and README contents."""
        import asyncio
        
        def run_interrogate():
            try:
                # interrogate returns 1 if it fails the threshold, so we don't check=True
                # interrogate -f json . doesn't exist, we must use grep/awk or simple run
                # Actually, interrogate generates json if requested, wait, let's use a simpler way:
                # interrogate --generate-badge /dev/null -v . might be hard to parse.
                # Let's just use subprocess and regex or write a small script.
                # Interrogate does not have a simple --json flag. But wait, it prints "RESULT: PASSED (minimum: 80.0%, actual: 21.2%)"
                res = subprocess.run(["interrogate", "-v", "."], cwd=str(repo_path), capture_output=True, text=True, check=False)
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
