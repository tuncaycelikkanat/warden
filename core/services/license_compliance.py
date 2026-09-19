import json
import subprocess
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

@dataclass
class LicenseResult:
    score: float
    copyleft_count: int
    unknown_count: int
    dependencies: List[Dict[str, str]]

class LicenseComplianceService:
    async def analyze(self, repo_path: Path) -> LicenseResult:
        """Analyzes dependency licenses and repo license."""
        import asyncio
        
        def run_pip_licenses():
            # Attempt to install pip-licenses locally or use uv
            # Since the requirement says "uv pip install pip-licenses", let's ensure it's available or run via uv
            try:
                # Assuming the env where Warden is running has it, or we install it to the target's venv.
                # Actually, running `uv run pip-licenses` in repo_path:
                subprocess.run(["uv", "pip", "install", "pip-licenses"], cwd=str(repo_path), capture_output=True, check=False)
                res = subprocess.run(["uv", "run", "pip-licenses", "--format=json"], cwd=str(repo_path), capture_output=True, text=True, check=False)
                if not res.stdout.strip():
                    return []
                return json.loads(res.stdout)
            except Exception as e:
                logger.warning(f"Failed to run pip-licenses: {e}")
                return []
                
        deps = await asyncio.to_thread(run_pip_licenses)
        
        copyleft_count = 0
        unknown_count = 0
        dep_list = []
        
        for dep in deps:
            name = dep.get("Name", "Unknown")
            license_str = dep.get("License", "Unknown")
            
            is_copyleft = False
            is_unknown = False
            
            upper_lic = license_str.upper()
            if "GPL" in upper_lic or "AGPL" in upper_lic or "LGPL" in upper_lic:
                is_copyleft = True
                copyleft_count += 1
            elif "UNKNOWN" in upper_lic or not license_str.strip():
                is_unknown = True
                unknown_count += 1
                
            dep_list.append({
                "name": name,
                "license": license_str,
                "is_copyleft": is_copyleft,
                "is_unknown": is_unknown
            })
            
        score = 100.0
        score -= (copyleft_count * 15)
        score -= (unknown_count * 5)
        
        return LicenseResult(
            score=max(0.0, score),
            copyleft_count=copyleft_count,
            unknown_count=unknown_count,
            dependencies=dep_list
        )
