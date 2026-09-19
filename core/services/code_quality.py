import subprocess
import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ComplexityResult:
    avg_complexity: float
    high_complexity_files: List[Dict[str, Any]]

@dataclass
class LintResult:
    error_count: int
    issues_by_rule: Dict[str, int]

class CodeComplexityService:
    async def analyze(self, repo_path: Path) -> ComplexityResult:
        """Runs radon cc to measure cyclomatic complexity."""
        import asyncio
        
        def run_radon():
            # Run radon cc <repo_path> --json -a (average)
            cmd = ["radon", "cc", str(repo_path), "--json", "-a"]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                return json.loads(result.stdout)
            except Exception as e:
                logger.error(f"Failed to run radon: {e}")
                return {}
                
        data = await asyncio.to_thread(run_radon)
        
        # radon JSON output format has filename keys, and an "average" key if -a is used
        # wait, -a output in json might put average somewhere else, or we can just compute it.
        # Let's compute it to be safe, filtering out 'error' keys.
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
                
                # If average complexity of blocks in file > 10, mark as high
                if (file_complexity / len(file_blocks)) > 10:
                    high_complexity_files.append({"file": file_path, "complexity": file_complexity})

        avg = (total_complexity / block_count) if block_count > 0 else 0.0
        
        return ComplexityResult(
            avg_complexity=round(avg, 2),
            high_complexity_files=high_complexity_files
        )

class LintStyleService:
    async def analyze(self, repo_path: Path) -> LintResult:
        """Runs ruff check to find linting and style issues."""
        import asyncio
        
        def run_ruff():
            cmd = ["ruff", "check", str(repo_path), "--output-format=json"]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                # Ruff might return exit code 1 if issues found, so we ignore check=True
                return json.loads(result.stdout) if result.stdout else []
            except Exception as e:
                logger.error(f"Failed to run ruff: {e}")
                return []

        issues = await asyncio.to_thread(run_ruff)
        
        issues_by_rule = {}
        for issue in issues:
            rule = issue.get("code", "UNKNOWN")
            issues_by_rule[rule] = issues_by_rule.get(rule, 0) + 1
            
        return LintResult(
            error_count=len(issues),
            issues_by_rule=issues_by_rule
        )
