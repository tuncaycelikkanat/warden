import os
import logging
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class CiCdResult:
    score: float
    has_file: bool
    has_valid_content: bool

class CiCdPresenceService:
    async def analyze(self, repo_path: Path) -> CiCdResult:
        import asyncio
        
        def check_cicd():
            ci_files = []
            
            # .github/workflows/*.yml or *.yaml
            gh_dir = repo_path / ".github" / "workflows"
            if gh_dir.exists() and gh_dir.is_dir():
                for ext in ["*.yml", "*.yaml"]:
                    ci_files.extend(list(gh_dir.glob(ext)))
                    
            # others
            others = [".gitlab-ci.yml", ".circleci/config.yml", "Jenkinsfile", ".travis.yml"]
            for o in others:
                p = repo_path / o
                if p.exists() and p.is_file():
                    ci_files.append(p)
                    
            if not ci_files:
                return False, False
                
            has_valid = False
            keywords = ["job", "step", "script", "stage", "run", "pipeline"]
            
            for cf in ci_files:
                try:
                    content = cf.read_text(encoding="utf-8").lower()
                    if any(k in content for k in keywords):
                        has_valid = True
                        break
                except Exception as e:
                    logger.warning(f"Failed to read CI file {cf}: {e}")
                    
            return True, has_valid

        has_file, has_valid = await asyncio.to_thread(check_cicd)
        
        if has_valid:
            score = 100.0
        elif has_file:
            score = 50.0
        else:
            score = 0.0
            
        return CiCdResult(
            score=score,
            has_file=has_file,
            has_valid_content=has_valid
        )
