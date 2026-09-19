import logging
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class DockerResult:
    score: float
    has_dockerfile: bool
    has_healthcheck: bool
    has_env_example: bool
    has_docker_compose: bool

class DockerReadinessService:
    async def analyze(self, repo_path: Path) -> DockerResult:
        import asyncio
        
        def check_docker():
            has_dockerfile = False
            has_healthcheck = False
            
            df_path = repo_path / "Dockerfile"
            if df_path.exists() and df_path.is_file():
                has_dockerfile = True
                try:
                    content = df_path.read_text(encoding="utf-8")
                    if "HEALTHCHECK" in content:
                        has_healthcheck = True
                except Exception as e:
                    logger.warning(f"Failed to read Dockerfile: {e}")
                    
            has_env_example = (repo_path / ".env.example").exists() or (repo_path / ".env.sample").exists()
            has_docker_compose = (repo_path / "docker-compose.yml").exists() or (repo_path / "docker-compose.yaml").exists()
            
            return has_dockerfile, has_healthcheck, has_env_example, has_docker_compose

        has_dockerfile, has_healthcheck, has_env_example, has_docker_compose = await asyncio.to_thread(check_docker)
        
        if not has_dockerfile:
            score = 0.0
        else:
            score = 40.0
            if has_healthcheck:
                score += 30.0
            if has_env_example:
                score += 20.0
            if has_docker_compose:
                score += 10.0
                
        return DockerResult(
            score=min(100.0, score),
            has_dockerfile=has_dockerfile,
            has_healthcheck=has_healthcheck,
            has_env_example=has_env_example,
            has_docker_compose=has_docker_compose
        )
