import subprocess
import logging
from pathlib import Path
from dataclasses import dataclass
from core.utils.file_discovery import discover_source_files

logger = logging.getLogger(__name__)

@dataclass
class TypeSafetyResult:
    score: float
    error_count: int
    file_count: int
    error_density: float

class TypeSafetyService:
    async def analyze(self, repo_path: Path) -> TypeSafetyResult:
        import asyncio
        
        def run_mypy():
            files = discover_source_files(repo_path)
            py_files = [f for f in files if f.suffix == ".py"]
            file_count = len(py_files)
            
            if file_count == 0:
                return 0, 0
                
            try:
                subprocess.run(["uv", "pip", "install", "mypy"], cwd=str(repo_path), capture_output=True, check=False)
                res = subprocess.run(
                    ["uv", "run", "mypy", str(repo_path), "--no-error-summary", "--ignore-missing-imports"],
                    cwd=str(repo_path), capture_output=True, text=True, check=False
                )
                
                error_count = 0
                output = res.stdout + "\n" + res.stderr
                for line in output.splitlines():
                    if "error:" in line.lower():
                        error_count += 1
                        
                return error_count, file_count
            except Exception as e:
                logger.warning(f"Failed to run mypy: {e}")
                return 0, file_count
                
        error_count, file_count = await asyncio.to_thread(run_mypy)
        
        if file_count == 0:
            return TypeSafetyResult(score=100.0, error_count=0, file_count=0, error_density=0.0)
            
        density = error_count / file_count
        score = 100.0 - ((density / 0.5) * 10.0)
        
        return TypeSafetyResult(
            score=max(20.0, min(100.0, score)),
            error_count=error_count,
            file_count=file_count,
            error_density=density
        )
